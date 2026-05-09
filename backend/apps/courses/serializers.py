import json
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.common.choices import (
    AttendanceStatus,
    CourseStatus,
    DanceLevel,
    EnrollmentStatus,
    LessonStatus,
    WeekdayCode,
)
from apps.common.files import persist_image_reference
from apps.common.utils import (
    absolutize_media_url,
    build_full_name,
    course_lifecycle_status,
    first_lesson_start_at,
    has_hours_before,
    lesson_lifecycle_status,
    lesson_start_at,
    lesson_start_iso,
)
from apps.courses.models import Course, Lesson, PaymentOrder


def serialize_schedule_row(row) -> dict:
    return {
        "weekday": row.weekday,
        "time_from": row.time_from.isoformat(timespec="minutes"),
        "time_to": row.time_to.isoformat(timespec="minutes"),
        "location": row.location_text or "",
    }


def serialize_course_list_item(course: Course, request=None, spots_left: int = 0) -> dict:
    teacher_name = build_full_name(
        course.teacher.user.last_name,
        course.teacher.user.first_name,
        course.teacher.user.middle_name,
    ) or course.teacher.user.email
    first_lesson_at = first_lesson_start_at(course.lessons.all())
    return {
        "id": course.id,
        "name": course.name,
        "level": course.level,
        "price": course.price,
        "date_from": course.date_from.isoformat(),
        "date_to": course.date_to.isoformat(),
        "status": course_lifecycle_status(course.status, course.date_from, course.date_to),
        "image": absolutize_media_url(request, course.image_cover or (course.images[0] if course.images else "")),
        "teacher_id": course.teacher_id,
        "teacher_name": teacher_name,
        "dance_style": course.dance_style.name,
        "city": course.studio.city.name,
        "studio": course.studio.name,
        "schedule": [serialize_schedule_row(row) for row in course.schedule_rows.all().order_by("weekday", "time_from")],
        "spots_left": max(spots_left, 0),
        "can_enroll": has_hours_before(first_lesson_at, hours=24),
        "can_cancel_enrollment": has_hours_before(first_lesson_at, hours=24),
        "can_edit": has_hours_before(first_lesson_at, hours=48),
        "first_lesson_at": first_lesson_at.isoformat() if first_lesson_at else None,
    }


def serialize_course_detail(course: Course, request=None, spots_left: int = 0, viewer_context: dict | None = None) -> dict:
    teacher_name = build_full_name(
        course.teacher.user.last_name,
        course.teacher.user.first_name,
        course.teacher.user.middle_name,
    ) or course.teacher.user.email
    first_lesson_at = first_lesson_start_at(course.lessons.all())
    payload = {
        "id": course.id,
        "name": course.name,
        "description": course.description or "",
        "level": course.level,
        "price": course.price,
        "capacity": course.capacity,
        "spots_left": max(spots_left, 0),
        "date_from": course.date_from.isoformat(),
        "date_to": course.date_to.isoformat(),
        "status": course_lifecycle_status(course.status, course.date_from, course.date_to),
        "images": [absolutize_media_url(request, image) for image in (course.images or [])],
        "teacher_id": course.teacher_id,
        "teacher_name": teacher_name,
        "dance_style": course.dance_style.name,
        "city": course.studio.city.name,
        "studio": course.studio.name,
        "schedule": [serialize_schedule_row(row) for row in course.schedule_rows.all().order_by("weekday", "time_from")],
        "music": {
            "artist": course.music_artist or "",
            "track": course.music_track or "",
            "url": course.music_url or "",
        },
        "can_enroll": has_hours_before(first_lesson_at, hours=24),
        "can_cancel_enrollment": has_hours_before(first_lesson_at, hours=24),
        "can_edit": has_hours_before(first_lesson_at, hours=48),
        "first_lesson_at": first_lesson_at.isoformat() if first_lesson_at else None,
    }
    if viewer_context:
        payload.update(viewer_context)
    return payload


def serialize_lesson(lesson: Lesson) -> dict:
    starts_at = lesson_start_at(lesson.lesson_date, lesson.time_from)
    return {
        "id": lesson.id,
        "course_id": lesson.course_id,
        "lesson_date": lesson.lesson_date.isoformat(),
        "time_from": lesson.time_from.isoformat(timespec="minutes"),
        "time_to": lesson.time_to.isoformat(timespec="minutes"),
        "location_text": lesson.location_text,
        "status": lesson_lifecycle_status(lesson.status, lesson.lesson_date),
        "hall": lesson.hall,
        "start_at": starts_at.isoformat(),
        "can_mark_attendance": timezone.now() >= starts_at,
    }


class ScheduleEntrySerializer(serializers.Serializer):
    weekday = serializers.ChoiceField(choices=WeekdayCode.choices)
    time_from = serializers.TimeField()
    time_to = serializers.TimeField()
    location_text = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        if attrs["time_from"] >= attrs["time_to"]:
            raise serializers.ValidationError({"time_to": ["Must be later than time_from."]})
        return attrs


class CourseWriteSerializer(serializers.Serializer):
    dance_style_id = serializers.IntegerField()
    studio_id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, default="")
    music_artist = serializers.CharField(required=False, allow_blank=True, default="")
    music_track = serializers.CharField(required=False, allow_blank=True, default="")
    music_url = serializers.CharField(required=False, allow_blank=True, default="")
    level = serializers.ChoiceField(choices=DanceLevel.choices)
    price = serializers.IntegerField(min_value=0)
    capacity = serializers.IntegerField(min_value=1)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    status = serializers.ChoiceField(required=False, choices=CourseStatus.choices, default=CourseStatus.PUBLISHED)
    schedule = serializers.ListField(required=True)
    ordered_image_urls = serializers.ListField(child=serializers.CharField(), required=False)
    image_cover = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    image_files = serializers.ListField(child=serializers.ImageField(), required=False)

    def to_internal_value(self, data):
        raw = data.copy()
        schedule = raw.get("schedule")
        if isinstance(schedule, str):
            raw["schedule"] = json.loads(schedule)
        return super().to_internal_value(raw)

    def validate_schedule(self, value):
        serializer = ScheduleEntrySerializer(data=value, many=True)
        serializer.is_valid(raise_exception=True)
        validated_rows = serializer.validated_data
        unique_rows: list[dict] = []
        seen_slots: set[tuple[str, str, str]] = set()

        for row in validated_rows:
            slot_key = (
                row["weekday"],
                row["time_from"].isoformat(timespec="minutes"),
                row["time_to"].isoformat(timespec="minutes"),
            )
            if slot_key in seen_slots:
                continue
            seen_slots.add(slot_key)
            unique_rows.append(row)

        return unique_rows

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if date_from is not None and date_to is not None and date_from > date_to:
            raise serializers.ValidationError({"date_to": ["Must not be earlier than date_from."]})
        return attrs

    def normalized_image_urls(self, folder: str) -> list[str]:
        return [persist_image_reference(url, folder) for url in self.validated_data.get("ordered_image_urls", []) if url]


class EnrollmentRequestSerializer(serializers.Serializer):
    pass


def serialize_payment_order(order: PaymentOrder) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "token": order.public_token,
        "amount": order.amount,
        "status": order.status,
        "expires_at": order.expires_at.isoformat(),
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "receipt_email": order.receipt_email or "",
        "payment_method": order.payment_method or "",
        "course_id": order.enrollment.course_id,
        "course_name": order.enrollment.course.name,
    }


class PaymentCardPaySerializer(serializers.Serializer):
    receipt_email = serializers.EmailField()
    card_number = serializers.CharField()
    cardholder_name = serializers.CharField()
    expiry = serializers.CharField()
    cvv = serializers.CharField()

    def validate_card_number(self, value: str) -> str:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) < 16 or len(digits) > 19:
            raise serializers.ValidationError("Card number must contain 16 to 19 digits.")
        return digits

    def validate_cardholder_name(self, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise serializers.ValidationError("Cardholder name is required.")
        return normalized

    def validate_expiry(self, value: str) -> str:
        normalized = value.strip()
        if len(normalized) != 5 or normalized[2] != "/":
            raise serializers.ValidationError("Use MM/YY format.")
        month = normalized[:2]
        year = normalized[3:]
        if not (month.isdigit() and year.isdigit()):
            raise serializers.ValidationError("Use MM/YY format.")
        month_value = int(month)
        if month_value < 1 or month_value > 12:
            raise serializers.ValidationError("Month must be between 01 and 12.")
        return normalized

    def validate_cvv(self, value: str) -> str:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) not in {3, 4}:
            raise serializers.ValidationError("CVV must contain 3 or 4 digits.")
        return digits


class PaymentSbpPaySerializer(serializers.Serializer):
    receipt_email = serializers.EmailField()


class LessonUpdateSerializer(serializers.Serializer):
    lesson_date = serializers.DateField(required=False)
    time_from = serializers.TimeField(required=False)
    time_to = serializers.TimeField(required=False)
    location_text = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    hall = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    status = serializers.ChoiceField(required=False, choices=LessonStatus.choices)

    def validate(self, attrs):
        time_from = attrs.get("time_from")
        time_to = attrs.get("time_to")
        if time_from and time_to and time_from >= time_to:
            raise serializers.ValidationError({"time_to": ["Must be later than time_from."]})
        return attrs


class AttendanceMarkRequestSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=AttendanceStatus.choices)


def expand_lessons_for_schedule(date_from, date_to, schedule_rows: list[dict]) -> list[dict]:
    weekday_to_python = {
        WeekdayCode.MON: 0,
        WeekdayCode.TUE: 1,
        WeekdayCode.WED: 2,
        WeekdayCode.THU: 3,
        WeekdayCode.FRI: 4,
        WeekdayCode.SAT: 5,
        WeekdayCode.SUN: 6,
    }
    current = date_from
    items: list[dict] = []
    while current <= date_to:
        for row in schedule_rows:
            if current.weekday() == weekday_to_python[row["weekday"]]:
                items.append(
                    {
                        "lesson_date": current,
                        "time_from": row["time_from"],
                        "time_to": row["time_to"],
                        "location_text": row.get("location_text") or "",
                    }
                )
        current += timedelta(days=1)
    return items
