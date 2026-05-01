from django.core.management.base import BaseCommand

from apps.courses.models import Course
from apps.courses.services import refresh_course_lessons_from_schedule


class Command(BaseCommand):
    help = (
        "Пересобрать занятия курсов из правил расписания: удалить вне дат курса и создать недостающие."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--course-id",
            type=int,
            default=None,
            help="Generate lessons only for one course.",
        )

    def handle(self, *args, **options):
        queryset = Course.objects.prefetch_related("schedule_rules").all()

        if options["course_id"] is not None:
            queryset = queryset.filter(id=options["course_id"])

        total_created = 0

        for course in queryset:
            total_created += refresh_course_lessons_from_schedule(course)

        self.stdout.write(self.style.SUCCESS(f"Created {total_created} lessons."))
