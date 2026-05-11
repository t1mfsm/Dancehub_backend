from __future__ import annotations

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from apps.common.choices import CourseStatus, EnrollmentStatus, WeekdayCode
from apps.common.utils import course_lifecycle_status, first_lesson_start_at, has_hours_before
from apps.courses.models import AttendanceMark, Course, DanceStyle, Enrollment
from apps.courses.payment_utils import build_spots_left_map
from apps.courses.serializers import serialize_course_list_item
from apps.recommendations.models import CourseView, UserCourseRecommendation, UserRecommendationProfile
from apps.users.models import TeacherProfile, TeacherReview, User

VIEW_DEDUP_WINDOW = timedelta(minutes=30)
MAX_BEHAVIOR_WEIGHT = Decimal("0.6500")


def _normalize_style_token(value: str | None) -> str:
    return (value or "").strip().lower()


def _resolve_preferred_style_slugs(raw_styles: list[str] | None) -> list[str]:
    normalized_values = {_normalize_style_token(style) for style in (raw_styles or []) if style}
    if not normalized_values:
        return []

    style_lookup: dict[str, str] = {}
    all_slugs: set[str] = set()
    for style in DanceStyle.objects.all().only("name", "slug"):
        normalized_slug = _normalize_style_token(style.slug)
        normalized_name = _normalize_style_token(style.name)
        all_slugs.add(normalized_slug)
        style_lookup[normalized_slug] = normalized_slug
        style_lookup[normalized_name] = normalized_slug

    resolved_slugs = sorted(
        {
            style_lookup[value]
            for value in normalized_values
            if value in style_lookup
        }
    )

    if resolved_slugs and len(resolved_slugs) >= len(all_slugs):
        return []

    return resolved_slugs


def _normalize_preferred_weekdays(raw_days: list[str] | None) -> list[str]:
    normalized_days = sorted({str(day) for day in (raw_days or []) if day})
    all_days = sorted({code for code, _ in WeekdayCode.choices})
    if normalized_days == all_days:
        return []
    return normalized_days


def _counter_to_ranked_json(counter: Counter, *, use_int_keys: bool = False) -> list[dict]:
    ranked = counter.most_common()
    items: list[dict] = []
    for key, weight in ranked:
        items.append(
            {
                "key": int(key) if use_int_keys else key,
                "weight": int(weight),
            }
        )
    return items


def _extract_weight_map(items: list[dict] | None) -> dict:
    result: dict = {}
    for item in items or []:
        key = item.get("key")
        weight = item.get("weight", 0)
        if key in (None, ""):
            continue
        result[key] = float(weight)
    return result


def _profile_behavior_weight(events_count: int) -> Decimal:
    if events_count <= 0:
        return Decimal("0.0000")
    adaptive = Decimal(min(events_count, 20)) / Decimal("20")
    return (adaptive * MAX_BEHAVIOR_WEIGHT).quantize(Decimal("0.0001"))


def _profile_content_weight(profile: UserRecommendationProfile) -> float:
    preferred_styles_count = len(profile.preferred_styles_json or [])
    preferred_weekdays_count = len(profile.preferred_weekdays_json or [])
    has_city = profile.city_id is not None
    has_level = bool(profile.dance_level)
    has_time_window = bool(profile.preferred_time_from and profile.preferred_time_to)
    has_price_range = profile.price_from is not None or profile.price_to is not None

    preference_signals = (
        preferred_styles_count
        + preferred_weekdays_count
        + int(has_city)
        + int(has_level)
        + int(has_time_window)
        + int(has_price_range)
    )

    if preference_signals <= 0:
        return 0.35

    normalized = min(preference_signals, 8) / 8
    return round(0.35 + normalized * 0.5, 4)


def track_course_view(user: User, course: Course, *, source: str = "course_page") -> bool:
    cutoff = timezone.now() - VIEW_DEDUP_WINDOW
    exists_recent = CourseView.objects.filter(user=user, course=course, source=source, viewed_at__gte=cutoff).exists()
    if exists_recent:
        return False
    CourseView.objects.create(user=user, course=course, source=source, viewed_at=timezone.now())
    return True


def refresh_recommendations_for_user(user: User, *, limit: int = 12) -> list[dict]:
    return build_recommendations_for_user(user, limit=limit)


def rebuild_user_recommendation_profile(user: User) -> UserRecommendationProfile:
    preferred_styles = _resolve_preferred_style_slugs(user.preferred_dance_styles)
    preferred_weekdays = _normalize_preferred_weekdays(user.preferred_weekdays)

    favorite_teacher_ids = list(user.favorite_teachers.values_list("teacher_id", flat=True))

    active_enrollments = (
        Enrollment.objects.filter(user=user, status=EnrollmentStatus.ACTIVE)
        .select_related("course__dance_style", "course__studio__city", "course__teacher__user")
        .prefetch_related("course__schedule_rows")
    )
    attendance_marks = AttendanceMark.objects.filter(student=user, status="present").select_related(
        "lesson__course__dance_style",
        "lesson__course__studio__city",
        "lesson__course__teacher__user",
    )
    reviews = TeacherReview.objects.filter(user=user).select_related("teacher__user")
    views = CourseView.objects.filter(user=user).select_related(
        "course__dance_style",
        "course__studio__city",
        "course__teacher__user",
    )

    behavior_style_counter: Counter = Counter()
    teacher_counter: Counter = Counter()
    studio_counter: Counter = Counter()
    city_counter: Counter = Counter()
    event_count = 0

    for enrollment in active_enrollments:
        course = enrollment.course
        behavior_style_counter[_normalize_style_token(course.dance_style.slug)] += 5
        teacher_counter[course.teacher_id] += 5
        studio_counter[course.studio_id] += 4
        city_counter[course.studio.city_id] += 3
        event_count += 5

    for mark in attendance_marks:
        course = mark.lesson.course
        behavior_style_counter[_normalize_style_token(course.dance_style.slug)] += 3
        teacher_counter[course.teacher_id] += 3
        studio_counter[course.studio_id] += 2
        city_counter[course.studio.city_id] += 2
        event_count += 3

    for review in reviews:
        teacher_counter[review.teacher_id] += 4
        event_count += 4

    for teacher_id in favorite_teacher_ids:
        teacher_counter[teacher_id] += 6
        event_count += 6

    for view in views:
        course = view.course
        behavior_style_counter[_normalize_style_token(course.dance_style.slug)] += 1
        teacher_counter[course.teacher_id] += 1
        studio_counter[course.studio_id] += 1
        city_counter[course.studio.city_id] += 1
        event_count += 1

    last_event = views.order_by("-viewed_at").values_list("viewed_at", flat=True).first()
    if last_event is None:
        last_event = active_enrollments.order_by("-enrolled_at").values_list("enrolled_at", flat=True).first()

    defaults = {
        "city_id": user.city_id,
        "dance_level": user.dance_level,
        "preferred_styles_json": [{"key": style, "weight": 1} for style in preferred_styles],
        "preferred_weekdays_json": [{"key": day, "weight": 1} for day in preferred_weekdays],
        "preferred_time_from": user.preferred_time_from,
        "preferred_time_to": user.preferred_time_to,
        "price_from": user.price_from,
        "price_to": user.price_to,
        "behavior_styles_json": _counter_to_ranked_json(behavior_style_counter),
        "teachers_json": _counter_to_ranked_json(teacher_counter, use_int_keys=True),
        "studios_json": _counter_to_ranked_json(studio_counter, use_int_keys=True),
        "cities_json": _counter_to_ranked_json(city_counter, use_int_keys=True),
        "behavior_weight": _profile_behavior_weight(event_count),
        "last_event_at": last_event,
        "updated_at": timezone.now(),
    }
    profile, _ = UserRecommendationProfile.objects.update_or_create(user=user, defaults=defaults)
    return profile


def _course_matches_time(course: Course, profile: UserRecommendationProfile) -> bool:
    if profile.preferred_time_from is None or profile.preferred_time_to is None:
        return False
    for row in course.schedule_rows.all():
        if profile.preferred_time_from <= row.time_from <= profile.preferred_time_to:
            return True
    return False


def _course_matches_weekdays(course: Course, profile: UserRecommendationProfile) -> bool:
    preferred_days = {item.get("key") for item in (profile.preferred_weekdays_json or [])}
    if not preferred_days:
        return False
    return any(row.weekday in preferred_days for row in course.schedule_rows.all())


def _score_course_for_user(user: User, profile: UserRecommendationProfile, course: Course) -> tuple[float, dict, list[str]]:
    behavior_weight = float(profile.behavior_weight or 0)
    base_content_weight = _profile_content_weight(profile)
    content_weight = max(0.25, base_content_weight * (1 - behavior_weight * 0.85))
    behavior_multiplier = 0.75 + behavior_weight

    preferred_style_keys = {item.get("key") for item in (profile.preferred_styles_json or [])}
    behavior_style_map = _extract_weight_map(profile.behavior_styles_json)
    teacher_map = _extract_weight_map(profile.teachers_json)
    studio_map = _extract_weight_map(profile.studios_json)
    city_map = _extract_weight_map(profile.cities_json)

    factors: dict[str, float] = {}
    reasons: list[str] = []

    style_slug = _normalize_style_token(course.dance_style.slug)

    if style_slug in preferred_style_keys:
        factors["preferred_style"] = 35 * content_weight
        reasons.append("Совпадает с вашими любимыми стилями")

    if profile.dance_level and course.level == profile.dance_level:
        factors["level"] = 15 * content_weight
        reasons.append("Подходит по вашему уровню")

    if profile.city_id and course.studio.city_id == profile.city_id:
        factors["city"] = 10 * content_weight
        reasons.append("Курс в вашем городе")
    elif course.studio.city_id in city_map:
        factors["behavior_city"] = min(city_map[course.studio.city_id], 8) * behavior_multiplier

    if profile.price_from is not None and profile.price_to is not None and profile.price_from <= course.price <= profile.price_to:
        factors["price"] = 10 * content_weight
        reasons.append("Попадает в ваш ценовой диапазон")

    elif profile.price_from is not None and profile.price_to is None and course.price >= profile.price_from:
        factors["price"] = 8 * content_weight
        reasons.append("РЎРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ РІР°С€РµРјСѓ Р±СЋРґР¶РµС‚Сѓ")
    elif profile.price_from is None and profile.price_to is not None and course.price <= profile.price_to:
        factors["price"] = 8 * content_weight
        reasons.append("РЎРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ РІР°С€РµРјСѓ Р±СЋРґР¶РµС‚Сѓ")

    if _course_matches_weekdays(course, profile):
        factors["weekday"] = 5 * content_weight
        reasons.append("Подходит по дням недели")

    if _course_matches_time(course, profile):
        factors["time"] = 5 * content_weight
        reasons.append("Подходит по времени")

    if style_slug in behavior_style_map:
        factors["behavior_style"] = min(behavior_style_map[style_slug], 20) * behavior_multiplier
        if "Совпадает с вашими любимыми стилями" not in reasons:
            reasons.append("Похож на курсы, которые вас уже интересовали")

    if course.teacher_id in teacher_map:
        factors["teacher_interest"] = min(teacher_map[course.teacher_id], 14) * behavior_multiplier
        if not any("преподавател" in reason.lower() for reason in reasons):
            reasons.append("У вас уже есть интерес к этому преподавателю")

    if course.studio_id in studio_map:
        factors["studio_interest"] = min(studio_map[course.studio_id], 8) * behavior_multiplier

    popularity = getattr(course, "active_enrollments", 0) or 0
    if popularity > 0:
        factors["popularity"] = min(popularity, 10) * 0.35
        if not reasons:
            reasons.append("РџРѕРїСѓР»СЏСЂРЅС‹Р№ РєСѓСЂСЃ СЃСЂРµРґРё СѓС‡РµРЅРёРєРѕРІ")

    score = round(sum(factors.values()), 4)
    return score, factors, reasons[:3]


def build_recommendations_for_user(user: User, *, limit: int = 12) -> list[dict]:
    profile = rebuild_user_recommendation_profile(user)
    candidates = list(
        Course.objects.select_related("teacher__user", "dance_style", "studio__city")
        .prefetch_related("schedule_rows", "lessons")
        .annotate(active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)))
        .order_by("-id")
    )
    spots_left_map = build_spots_left_map(candidates)

    excluded_course_ids = set(
        Enrollment.objects.filter(user=user, status=EnrollmentStatus.ACTIVE).values_list(
            "course_id", flat=True
        )
    )
    if getattr(user, "teacher_profile", None) is not None:
        candidates = [course for course in candidates if course.teacher_id != user.teacher_profile.id]

    ranked: list[dict] = []
    for course in candidates:
        lifecycle_status = course_lifecycle_status(course.status, course.date_from, course.date_to)
        first_lesson_at = first_lesson_start_at(course.lessons.all())
        if lifecycle_status != CourseStatus.PUBLISHED:
            continue
        if course.id in excluded_course_ids:
            continue
        if not has_hours_before(first_lesson_at, hours=24):
            continue
        if spots_left_map.get(course.id, course.capacity) <= 0:
            continue

        score, factors, reasons = _score_course_for_user(user, profile, course)
        if score <= 0:
            continue
        ranked.append(
            {
                "course": course,
                "score": score,
                "factors": factors,
                "reasons": reasons,
            }
        )

    ranked.sort(key=lambda item: (-item["score"], -item["course"].id))
    top_ranked = ranked[:limit]

    with transaction.atomic():
        UserCourseRecommendation.objects.filter(user=user).exclude(
            course_id__in=[item["course"].id for item in top_ranked]
        ).delete()
        for item in top_ranked:
            UserCourseRecommendation.objects.update_or_create(
                user=user,
                course=item["course"],
                defaults={
                    "score": item["score"],
                    "reasons_json": item["reasons"],
                    "factors_json": item["factors"],
                    "computed_at": timezone.now(),
                },
            )

    return top_ranked


def sort_courses_for_user(user: User, courses: list[Course]) -> list[Course]:
    if not courses:
        return []

    profile = rebuild_user_recommendation_profile(user)

    ranked: list[tuple[float, int, Course]] = []
    for course in courses:
        score, _, _ = _score_course_for_user(user, profile, course)
        ranked.append((score, course.id, course))

    ranked.sort(key=lambda item: (-item[0], -item[1]))
    return [course for _, _, course in ranked]


def serialize_recommendation_payload(user: User, request, *, limit: int = 12) -> list[dict]:
    ranked = build_recommendations_for_user(user, limit=limit)
    spots_left_map = build_spots_left_map([item["course"] for item in ranked])
    return [
        {
            "score": item["score"],
            "reasons": item["reasons"],
            "factors": item["factors"],
            "course": serialize_course_list_item(
                item["course"],
                request=request,
                spots_left=spots_left_map.get(item["course"].id, item["course"].capacity),
            ),
        }
        for item in ranked
    ]
