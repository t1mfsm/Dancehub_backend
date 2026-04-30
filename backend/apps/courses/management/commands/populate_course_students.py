from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.courses.models import Course, Enrollment, EnrollmentStatus
from apps.users.models import DanceLevel, User, UserRole


class Command(BaseCommand):
    help = "Create demo students and enroll them in a course."

    def add_arguments(self, parser):
        parser.add_argument("--course-id", type=int, default=11)
        parser.add_argument("--count", type=int, default=20)
        parser.add_argument("--password", default="student12345")

    def handle(self, *args, **options):
        course_id = options["course_id"]
        count = options["count"]
        password = options["password"]

        course = Course.objects.filter(id=course_id).first()
        if course is None:
            self.stdout.write(
                self.style.WARNING(
                    f"Course {course_id} does not exist; demo students were not enrolled."
                )
            )
            return

        created_users = 0
        created_enrollments = 0

        for i in range(1, count + 1):
            email = f"course{course_id}_student_{i:02d}@dancehub.local"
            user, user_created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": f"Студент {i:02d}",
                    "last_name": f"Курс {course_id}",
                    "role": UserRole.STUDENT,
                    "dance_level": DanceLevel.BEGINNER,
                    "survey_completed": True,
                },
            )

            if user_created:
                user.set_password(password)
                user.save(update_fields=["password"])
                created_users += 1
            else:
                update_fields = []
                if user.username != email:
                    user.username = email
                    update_fields.append("username")
                if user.role != UserRole.STUDENT:
                    user.role = UserRole.STUDENT
                    update_fields.append("role")
                if not user.first_name:
                    user.first_name = f"Студент {i:02d}"
                    update_fields.append("first_name")
                if not user.last_name:
                    user.last_name = f"Курс {course_id}"
                    update_fields.append("last_name")
                if update_fields:
                    user.save(update_fields=update_fields)

            enrollment, enrollment_created = Enrollment.objects.get_or_create(
                user=user,
                course=course,
                defaults={
                    "enrolled_at": timezone.localdate(),
                    "status": EnrollmentStatus.ACTIVE,
                    "paid": True,
                },
            )

            if enrollment_created:
                created_enrollments += 1
            else:
                update_fields = []
                if enrollment.status != EnrollmentStatus.ACTIVE:
                    enrollment.status = EnrollmentStatus.ACTIVE
                    update_fields.append("status")
                if not enrollment.paid:
                    enrollment.paid = True
                    update_fields.append("paid")
                if update_fields:
                    enrollment.save(update_fields=update_fields)

        self.stdout.write(
            self.style.SUCCESS(
                f"Course {course_id}: created {created_users} users, "
                f"created {created_enrollments} enrollments, "
                f"total enrollments {Enrollment.objects.filter(course=course).count()}."
            )
        )
