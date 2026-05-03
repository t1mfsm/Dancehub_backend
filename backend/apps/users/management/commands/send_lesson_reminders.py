from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.common.choices import LessonStatus
from apps.common.utils import lesson_start_at
from apps.courses.models import Lesson
from apps.users.notifications import create_student_lesson_reminders, create_teacher_lesson_reminder


class Command(BaseCommand):
    help = "Send lesson reminder notifications ahead of lesson start."

    def add_arguments(self, parser):
        parser.add_argument("--hours-ahead", type=int, default=24)
        parser.add_argument("--window-minutes", type=int, default=60)

    def handle(self, *args, **options):
        hours_ahead = options["hours_ahead"]
        window_minutes = options["window_minutes"]
        now = timezone.now()
        target_time = now + timedelta(hours=hours_ahead)
        aligned_minutes = (target_time.minute // window_minutes) * window_minutes
        window_start = target_time.replace(minute=aligned_minutes, second=0, microsecond=0)
        window_end = window_start + timedelta(minutes=window_minutes)

        lessons = (
            Lesson.objects.exclude(status=LessonStatus.CANCELLED)
            .select_related("course__teacher__user")
            .filter(lesson_date__gte=window_start.date(), lesson_date__lte=window_end.date())
            .order_by("lesson_date", "time_from")
        )

        teacher_count = 0
        student_count = 0

        for lesson in lessons:
            start_at = lesson_start_at(lesson.lesson_date, lesson.time_from)
            if not (window_start <= start_at < window_end):
                continue

            if create_teacher_lesson_reminder(lesson=lesson) is not None:
                teacher_count += 1
            student_count += create_student_lesson_reminders(lesson=lesson)

        self.stdout.write(
            self.style.SUCCESS(
                f"Sent lesson reminders: teachers={teacher_count}, students={student_count}."
            )
        )
