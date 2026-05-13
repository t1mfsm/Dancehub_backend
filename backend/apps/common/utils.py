from datetime import date, datetime, time, timedelta

from django.http import HttpRequest
from django.utils import timezone

from .choices import CourseStatus, LessonStatus


def normalize_media_reference(value: str | None) -> str:
    if not value:
        return ""
    if value.startswith("data:"):
        return value
    for marker in ("/dancehub-media/", "/media/"):
        marker_index = value.find(marker)
        if marker_index >= 0:
            return value[marker_index:]
    return value


def build_full_name(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def course_lifecycle_status(course_status: str, date_from: date, date_to: date) -> str:
    today = date.today()
    if course_status == CourseStatus.CANCELLED:
        return CourseStatus.CANCELLED
    if course_status == CourseStatus.COMPLETED or date_to < today:
        return CourseStatus.COMPLETED
    if date_from > today:
        return CourseStatus.PUBLISHED
    return CourseStatus.ACTIVE


def lesson_lifecycle_status(lesson_status: str, lesson_date: date, lesson_time_to: time | None = None) -> str:
    if lesson_status == LessonStatus.CANCELLED:
        return LessonStatus.CANCELLED

    if lesson_time_to is None:
        if lesson_date < timezone.localdate():
            return "completed"
        return LessonStatus.SCHEDULED

    lesson_end = lesson_start_at(lesson_date, lesson_time_to)
    if timezone.now() >= lesson_end:
        return "completed"
    return LessonStatus.SCHEDULED


def lesson_start_iso(lesson_date: date, lesson_time: time) -> str:
    return datetime.combine(lesson_date, lesson_time).isoformat()


def lesson_start_at(lesson_date: date, lesson_time: time) -> datetime:
    naive = datetime.combine(lesson_date, lesson_time)
    current_tz = timezone.get_current_timezone()
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, current_tz)
    return naive.astimezone(current_tz)


def first_lesson_start_at(lessons) -> datetime | None:
    first_lesson = lessons.exclude(status=LessonStatus.CANCELLED).order_by("lesson_date", "time_from").first()
    if first_lesson is None:
        return None
    return lesson_start_at(first_lesson.lesson_date, first_lesson.time_from)


def has_hours_before(moment: datetime | None, hours: int) -> bool:
    if moment is None:
        return True
    return timezone.now() <= moment - timedelta(hours=hours)


def absolutize_media_url(request: HttpRequest | None, value: str | None) -> str:
    normalized = normalize_media_reference(value)
    if not normalized:
        return ""
    if normalized.startswith("data:"):
        return normalized
    if normalized.startswith("/dancehub-media/") or normalized.startswith("/media/"):
        return normalized
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    if request is None:
        return normalized
    return request.build_absolute_uri(normalized)
