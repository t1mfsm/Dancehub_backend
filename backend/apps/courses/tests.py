from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.locations.models import City
from apps.users.models import DanceLevel, TeacherProfile, User, UserRole

from .models import Course, CourseStatus, DanceStyle, Studio


class CourseListAPIViewTests(APITestCase):
    def setUp(self):
        self.city = City.objects.create(name="Москва")
        self.studio = Studio.objects.create(
            name="Dance Hub",
            city=self.city,
            address="Тверская, 1",
        )
        self.style = DanceStyle.objects.create(name="High Heels", slug="high-heels")
        self.teacher_user = User.objects.create_user(
            username="teacher",
            email="teacher@example.com",
            password="password123",
            first_name="Ксения",
            last_name="Карпова",
            role=UserRole.TEACHER,
            is_teacher_enabled=True,
        )
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user)

    def _create_course(self, *, name: str, date_from_offset: int, date_to_offset: int) -> Course:
        today = timezone.localdate()
        return Course.objects.create(
            teacher=self.teacher,
            dance_style=self.style,
            studio=self.studio,
            name=name,
            description="Описание",
            level=DanceLevel.BEGINNER,
            price="5000.00",
            capacity=10,
            date_from=today + timedelta(days=date_from_offset),
            date_to=today + timedelta(days=date_to_offset),
            status=CourseStatus.PUBLISHED,
        )

    def test_course_list_returns_only_published_and_calendar_active_by_default(self):
        active_course = self._create_course(
            name="Active course",
            date_from_offset=-5,
            date_to_offset=5,
        )
        self._create_course(
            name="Completed course",
            date_from_offset=-20,
            date_to_offset=-1,
        )

        response = self.client.get(reverse("courses:course-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], active_course.id)
        self.assertEqual(response.data[0]["status"], "active")

    def test_course_list_can_filter_completed_courses_explicitly(self):
        self._create_course(
            name="Active course",
            date_from_offset=-5,
            date_to_offset=5,
        )
        completed_course = self._create_course(
            name="Completed course",
            date_from_offset=-20,
            date_to_offset=-1,
        )

        response = self.client.get(reverse("courses:course-list"), {"status": "completed"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], completed_course.id)
        self.assertEqual(response.data[0]["status"], "completed")
