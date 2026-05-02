from datetime import date, datetime, time

from django.http import HttpRequest

from .choices import CourseStatus, LessonStatus


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


def lesson_lifecycle_status(lesson_status: str, lesson_date: date) -> str:
    today = date.today()
    if lesson_status == LessonStatus.CANCELLED:
        return LessonStatus.CANCELLED
    if lesson_date < today:
        return "completed"
    return LessonStatus.SCHEDULED


def lesson_start_iso(lesson_date: date, lesson_time: time) -> str:
    return datetime.combine(lesson_date, lesson_time).isoformat()


def absolutize_media_url(request: HttpRequest | None, value: str | None) -> str:
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://") or value.startswith("data:"):
        return value
    if request is None:
        return value
    return request.build_absolute_uri(value)
