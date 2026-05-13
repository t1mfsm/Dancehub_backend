import json
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.common.choices import (
    AttendanceStatus,
    CourseStatus,
    DanceLevel,
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
)
from apps.courses.models import COURSE_LEVEL_CHOICES, Course, Lesson


def serialize_schedule_row(row, course: Course | None = None) -> dict:
    studio = getattr(row, "studio", None)
    studio_name = studio.name if studio is not None else (course.studio.name if course is not None else None)
    studio_id = getattr(row, "studio_id", None) or (course.studio_id if course is not None else None)
    return {
        "weekday": row.weekday,
        "time_from": row.time_from.isoformat(timespec="minutes"),
        "time_to": row.time_to.isoformat(timespec="minutes"),
        "location": row.location_text or "",
        "studio": studio_name,
        "studio_id": studio_id,
    }


def serialize_course_list_item(course: Course, request=None, spots_left: int = 0) -> dict:
    teacher_name = build_full_name(
        course.teacher.user.last_name,
        course.teacher.user.first_name,
        course.teacher.user.middle_name,
    ) or course.teacher.user.email
    first_lesson_at = first_lesson_start_at(course.lessons.all())
    payload = {
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
        "schedule": [
            serialize_schedule_row(row, course=course)
            for row in course.schedule_rows.all().order_by("weekday", "time_from")
        ],
        "spots_left": max(spots_left, 0),
        "can_enroll": has_hours_before(first_lesson_at, hours=24),
        "can_cancel_enrollment": has_hours_before(first_lesson_at, hours=24),
        "can_edit": has_hours_before(first_lesson_at, hours=48),
        "first_lesson_at": first_lesson_at.isoformat() if first_lesson_at else None,
        "can_leave_review": False,
    }
    viewer_context = getattr(course, "_viewer_context", None)
    if viewer_context:
        payload.update(viewer_context)
    return payload


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
        "schedule": [
            serialize_schedule_row(row, course=course)
            for row in course.schedule_rows.all().order_by("weekday", "time_from")
        ],
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
        "studio": lesson.studio.name if lesson.studio_id else lesson.course.studio.name,
        "studio_id": lesson.studio_id or lesson.course.studio_id,
        "status": lesson_lifecycle_status(lesson.status, lesson.lesson_date, lesson.time_to),
        "hall": lesson.hall,
        "start_at": starts_at.isoformat(),
        "can_mark_attendance": timezone.now() >= starts_at,
    }


class ScheduleEntrySerializer(serializers.Serializer):
    weekday = serializers.ChoiceField(choices=WeekdayCode.choices)
    time_from = serializers.TimeField()
    time_to = serializers.TimeField()
    studio_id = serializers.IntegerField(required=False, allow_null=True)
    location_text = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        if attrs["time_from"] >= attrs["time_to"]:
            raise serializers.ValidationError({"time_to": ["Must be later than time_from."]})
        return attrs


class CourseWriteSerializer(serializers.Serializer):
    dance_style_id = serializers.IntegerField()
    studio_id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, default="")
    music_artist = serializers.CharField(required=False, allow_blank=True, default="")
    music_track = serializers.CharField(required=False, allow_blank=True, default="")
    music_url = serializers.CharField(required=False, allow_blank=True, default="")
    level = serializers.ChoiceField(choices=COURSE_LEVEL_CHOICES)
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
        if hasattr(data, "lists"):
            raw = {}
            for key, values in data.lists():
                raw[key] = values if len(values) > 1 else values[0]
        else:
            raw = dict(data)
        schedule = raw.get("schedule")
        if isinstance(schedule, str):
            raw["schedule"] = json.loads(schedule)
        elif (
            isinstance(schedule, list)
            and len(schedule) == 1
            and isinstance(schedule[0], str)
        ):
            raw["schedule"] = json.loads(schedule[0])
        return super().to_internal_value(raw)

    def validate_schedule(self, value):
        normalized_rows: list[dict] = []
        for row in value:
            if isinstance(row, list):
                normalized_rows.extend(row)
            else:
                normalized_rows.append(row)

        serializer = ScheduleEntrySerializer(data=normalized_rows, many=True)
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

        if attrs.get("studio_id") is None:
            schedule_rows = attrs.get("schedule") or []
            inferred_studio_id = next(
                (row.get("studio_id") for row in schedule_rows if row.get("studio_id") is not None),
                None,
            )
            if inferred_studio_id is not None:
                attrs["studio_id"] = inferred_studio_id

        if not self.partial and attrs.get("studio_id") is None:
            raise serializers.ValidationError(
                {"studio_id": ["Choose a studio or specify it in at least one schedule row."]}
            )
        return attrs

    def normalized_image_urls(self, folder: str) -> list[str]:
        return [persist_image_reference(url, folder) for url in self.validated_data.get("ordered_image_urls", []) if url]


class EnrollmentRequestSerializer(serializers.Serializer):
    pass


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
                        "studio_id": row.get("studio_id"),
                        "location_text": row.get("location_text") or "",
                    }
                )
        current += timedelta(days=1)
    return items
