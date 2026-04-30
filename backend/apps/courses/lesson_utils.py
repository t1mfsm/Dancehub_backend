"""Helpers for lesson scheduling and status."""

from datetime import datetime

from django.conf import settings
from django.utils import timezone

from apps.courses.models import Lesson, LessonStatus


def lesson_end_datetime(lesson: Lesson) -> datetime:
    """End of lesson as timezone-aware datetime."""
    combined = datetime.combine(lesson.lesson_date, lesson.time_to)
    if settings.USE_TZ:
        tz = timezone.get_current_timezone()
        return timezone.make_aware(combined, tz)
    return combined


def lesson_has_ended(lesson: Lesson) -> bool:
    return lesson_end_datetime(lesson) < timezone.now()


def effective_lesson_status(lesson: Lesson) -> str:
    """
    Effective status for API: cancelled first, then completed if the lesson is in the past,
    otherwise the stored status.
    """
    if lesson.status == LessonStatus.CANCELLED:
        return LessonStatus.CANCELLED
    if lesson_has_ended(lesson):
        return LessonStatus.COMPLETED
    return lesson.status


def can_cancel_lesson(lesson: Lesson) -> tuple[bool, str | None]:
    if lesson.status == LessonStatus.CANCELLED:
        return False, "Занятие уже отменено."
    if lesson_has_ended(lesson):
        return False, "Нельзя отменить прошедшее занятие."
    return True, None
