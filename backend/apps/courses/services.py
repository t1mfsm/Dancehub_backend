from datetime import timedelta

from apps.users.models import Weekday

from .models import Course, Lesson


WEEKDAY_INDEX = {
    Weekday.MONDAY: 0,
    Weekday.TUESDAY: 1,
    Weekday.WEDNESDAY: 2,
    Weekday.THURSDAY: 3,
    Weekday.FRIDAY: 4,
    Weekday.SATURDAY: 5,
    Weekday.SUNDAY: 6,
}


def generate_course_lessons(course: Course) -> int:
    """Create missing lesson rows from course schedule rules."""
    created_count = 0

    for rule in course.schedule_rules.all():
        target_weekday = WEEKDAY_INDEX.get(rule.weekday)

        if target_weekday is None:
            continue

        current = course.date_from

        while current.weekday() != target_weekday:
            current += timedelta(days=1)

        while current <= course.date_to:
            _, created = Lesson.objects.get_or_create(
                course=course,
                lesson_date=current,
                time_from=rule.time_from,
                time_to=rule.time_to,
                defaults={
                    "schedule_rule": rule,
                    "hall": rule.hall or course.hall,
                    "location_text": rule.location_text,
                },
            )

            if created:
                created_count += 1

            current += timedelta(days=7)

    return created_count


def prune_lessons_outside_course_dates(course: Course) -> None:
    """Remove lesson rows whose date is outside course [date_from, date_to]."""
    Lesson.objects.filter(course=course).exclude(
        lesson_date__range=(course.date_from, course.date_to)
    ).delete()


def refresh_course_lessons_from_schedule(course: Course) -> int:
    """Remove out-of-window lessons, then append missing lesson rows from schedule rules."""
    prune_lessons_outside_course_dates(course)

    return generate_course_lessons(course)
