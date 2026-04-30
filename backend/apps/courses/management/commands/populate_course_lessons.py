from django.core.management.base import BaseCommand

from apps.courses.models import Course
from apps.courses.services import generate_course_lessons


class Command(BaseCommand):
    help = "Create missing lesson rows from course schedule rules."

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
            total_created += generate_course_lessons(course)

        self.stdout.write(self.style.SUCCESS(f"Created {total_created} lessons."))
