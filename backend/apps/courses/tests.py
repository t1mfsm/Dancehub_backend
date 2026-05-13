from datetime import time, timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.common.choices import AttendanceStatus, EnrollmentStatus, LessonStatus
from apps.locations.models import City
from apps.users.models import DanceLevel, TeacherProfile, User, UserRole

from .models import AttendanceMark, Course, CourseStatus, DanceStyle, Enrollment, Lesson, Studio


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

    def test_course_list_returns_only_catalog_visible_courses_by_default(self):
        visible_course = self._create_course(
            name="Visible course",
            date_from_offset=3,
            date_to_offset=20,
        )
        self._create_course(
            name="Starts soon",
            date_from_offset=0,
            date_to_offset=20,
        )
        self._create_course(
            name="Completed course",
            date_from_offset=-20,
            date_to_offset=-1,
        )

        response = self.client.get(reverse("courses:course-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], visible_course.id)
        self.assertEqual(response.data[0]["status"], "published")

    def test_course_list_can_filter_completed_courses_explicitly(self):
        self._create_course(
            name="Visible course",
            date_from_offset=3,
            date_to_offset=20,
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

    def test_course_list_hides_already_enrolled_course_for_authenticated_user(self):
        visible_course = self._create_course(
            name="Visible course",
            date_from_offset=3,
            date_to_offset=20,
        )
        hidden_course = self._create_course(
            name="Already enrolled",
            date_from_offset=4,
            date_to_offset=20,
        )
        student = User.objects.create_user(
            username="student_catalog",
            email="student-catalog@example.com",
            password="password123",
            first_name="Иван",
            last_name="Петров",
            role=UserRole.STUDENT,
        )
        Enrollment.objects.create(course=hidden_course, user=student, status=EnrollmentStatus.ACTIVE)

        self.client.force_authenticate(student)
        response = self.client.get(reverse("courses:course-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], visible_course.id)

    def test_course_list_hides_courses_owned_by_current_teacher(self):
        self._create_course(
            name="Own course",
            date_from_offset=4,
            date_to_offset=20,
        )
        second_teacher_user = User.objects.create_user(
            username="teacher_two",
            email="teacher-two@example.com",
            password="password123",
            first_name="Мария",
            last_name="Соколова",
            role=UserRole.TEACHER,
        )
        second_teacher = TeacherProfile.objects.create(user=second_teacher_user)
        today = timezone.localdate()
        visible_course = Course.objects.create(
            teacher=second_teacher,
            dance_style=self.style,
            studio=self.studio,
            name="Visible from another teacher",
            description="Описание",
            level=DanceLevel.BEGINNER,
            price="5000.00",
            capacity=10,
            date_from=today + timedelta(days=5),
            date_to=today + timedelta(days=20),
            status=CourseStatus.PUBLISHED,
        )

        self.client.force_authenticate(self.teacher_user)
        response = self.client.get(reverse("courses:course-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], visible_course.id)


class CourseAttendanceStatsAPIViewTests(APITestCase):
    def setUp(self):
        self.city = City.objects.create(name="Москва")
        self.studio = Studio.objects.create(
            name="Dance Hub",
            city=self.city,
            address="Тверская, 1",
        )
        self.style = DanceStyle.objects.create(name="High Heels", slug="high-heels")
        self.teacher_user = User.objects.create_user(
            username="teacher_stats",
            email="teacher-stats@example.com",
            password="password123",
            first_name="Анна",
            last_name="Иванова",
            role=UserRole.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user)
        self.client.force_authenticate(self.teacher_user)

    def _create_student(self, index: int) -> User:
        return User.objects.create_user(
            username=f"student_{index}",
            email=f"student_{index}@example.com",
            password="password123",
            first_name=f"Student{index}",
            last_name="User",
            role=UserRole.STUDENT,
        )

    def _create_active_course(self, name: str = "Stats course") -> Course:
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
            date_from=today - timedelta(days=2),
            date_to=today + timedelta(days=2),
            status=CourseStatus.PUBLISHED,
        )

    def test_stats_count_unmarked_students_as_absent(self):
        course = self._create_active_course()
        lesson_one = Lesson.objects.create(
            course=course,
            lesson_date=timezone.localdate() - timedelta(days=2),
            time_from=time(18, 0),
            time_to=time(19, 30),
            location_text="Hall A",
            status=LessonStatus.SCHEDULED,
        )
        lesson_two = Lesson.objects.create(
            course=course,
            lesson_date=timezone.localdate() - timedelta(days=1),
            time_from=time(18, 0),
            time_to=time(19, 30),
            location_text="Hall A",
            status=LessonStatus.SCHEDULED,
        )

        students = [self._create_student(i) for i in range(6)]
        for student in students:
            Enrollment.objects.create(course=course, user=student, status=EnrollmentStatus.ACTIVE)
            AttendanceMark.objects.create(lesson=lesson_one, student=student, status=AttendanceStatus.PRESENT)

        for student in students[:4]:
            AttendanceMark.objects.create(lesson=lesson_two, student=student, status=AttendanceStatus.PRESENT)

        response = self.client.get(reverse("courses:course-attendance-stats", kwargs={"id": course.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_students"], 6)
        self.assertEqual(response.data["conducted_lessons"], 2)
        self.assertEqual(len(response.data["per_lesson"]), 2)
        self.assertEqual(response.data["per_lesson"][0]["present"], 6)
        self.assertEqual(response.data["per_lesson"][0]["absent"], 0)
        self.assertEqual(response.data["per_lesson"][0]["total"], 6)
        self.assertEqual(response.data["per_lesson"][0]["percent"], 100.0)
        self.assertEqual(response.data["per_lesson"][1]["present"], 4)
        self.assertEqual(response.data["per_lesson"][1]["absent"], 2)
        self.assertEqual(response.data["per_lesson"][1]["total"], 6)
        self.assertEqual(response.data["per_lesson"][1]["percent"], 66.67)
        self.assertEqual(response.data["avg_attendance_percent"], 83.34)

    def test_published_course_does_not_show_students_in_stats(self):
        today = timezone.localdate()
        course = Course.objects.create(
            teacher=self.teacher,
            dance_style=self.style,
            studio=self.studio,
            name="Future course",
            description="Описание",
            level=DanceLevel.BEGINNER,
            price="5000.00",
            capacity=10,
            date_from=today + timedelta(days=3),
            date_to=today + timedelta(days=10),
            status=CourseStatus.PUBLISHED,
        )
        student = self._create_student(99)
        Enrollment.objects.create(course=course, user=student, status=EnrollmentStatus.ACTIVE)

        response = self.client.get(reverse("courses:course-attendance-stats", kwargs={"id": course.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_students"], 0)
        self.assertEqual(response.data["per_student"], [])
