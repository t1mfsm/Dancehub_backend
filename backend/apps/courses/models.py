from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from apps.common.choices import (
    AttendanceStatus,
    CourseStatus,
    DanceLevel,
    EnrollmentStatus,
    LessonStatus,
    PaymentMethod,
    PaymentOrderStatus,
    WeekdayCode,
)


class DanceStyle(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.TextField(unique=True)
    slug = models.TextField(unique=True)

    class Meta:
        db_table = "dance_styles"
        managed = False
        ordering = ["name"]
        verbose_name = "Танцевальный стиль"
        verbose_name_plural = "Танцевальные стили"


class Studio(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.TextField()
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.RESTRICT,
        related_name="studios",
        db_column="city_id",
    )
    address = models.TextField()
    metro = models.TextField(null=True, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    image = models.TextField(null=True, blank=True)
    halls_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "studios"
        managed = False
        ordering = ["name"]
        verbose_name = "Студия"
        verbose_name_plural = "Студии"


class Course(models.Model):
    id = models.BigAutoField(primary_key=True)
    teacher = models.ForeignKey(
        "users.TeacherProfile",
        on_delete=models.RESTRICT,
        related_name="courses",
        db_column="teacher_id",
    )
    dance_style = models.ForeignKey(
        DanceStyle,
        on_delete=models.RESTRICT,
        related_name="courses",
        db_column="dance_style_id",
    )
    studio = models.ForeignKey(
        Studio,
        on_delete=models.RESTRICT,
        related_name="courses",
        db_column="studio_id",
    )
    name = models.TextField()
    description = models.TextField(default="", blank=True)
    music_artist = models.TextField(default="", blank=True)
    music_track = models.TextField(default="", blank=True)
    music_url = models.TextField(default="", blank=True)
    level = models.CharField(max_length=16, choices=DanceLevel.choices)
    price = models.IntegerField()
    capacity = models.PositiveIntegerField()
    date_from = models.DateField()
    date_to = models.DateField()
    status = models.CharField(max_length=16, choices=CourseStatus.choices, default=CourseStatus.PUBLISHED)
    images = ArrayField(base_field=models.TextField(), default=list, blank=True)
    image_cover = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "courses"
        managed = False
        ordering = ["id"]
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"


class CourseSchedule(models.Model):
    id = models.BigAutoField(primary_key=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="schedule_rows", db_column="course_id")
    weekday = models.CharField(max_length=3, choices=WeekdayCode.choices)
    time_from = models.TimeField()
    time_to = models.TimeField()
    location_text = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "course_schedule"
        managed = False
        verbose_name = "Расписание курса"
        verbose_name_plural = "Расписания курсов"


class Lesson(models.Model):
    id = models.BigAutoField(primary_key=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons", db_column="course_id")
    schedule = models.ForeignKey(
        CourseSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
        db_column="schedule_id",
    )
    lesson_date = models.DateField()
    time_from = models.TimeField()
    time_to = models.TimeField()
    location_text = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=LessonStatus.choices, default=LessonStatus.SCHEDULED)
    hall = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "lessons"
        managed = False
        ordering = ["lesson_date", "time_from"]
        verbose_name = "Занятие"
        verbose_name_plural = "Занятия"


class Enrollment(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="enrollments", db_column="user_id")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments", db_column="course_id")
    status = models.CharField(max_length=16, choices=EnrollmentStatus.choices, default=EnrollmentStatus.PENDING)
    enrolled_at = models.DateTimeField(default=timezone.now)
    paid = models.BooleanField(default=False)

    class Meta:
        db_table = "enrollments"
        managed = False
        unique_together = [("user", "course")]
        verbose_name = "Запись на курс"
        verbose_name_plural = "Записи на курсы"


class PaymentOrder(models.Model):
    id = models.BigAutoField(primary_key=True)
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name="payment_orders",
        db_column="enrollment_id",
    )
    order_number = models.TextField(unique=True)
    public_token = models.TextField(unique=True)
    amount = models.IntegerField()
    receipt_email = models.TextField(null=True, blank=True)
    payment_method = models.CharField(max_length=16, choices=PaymentMethod.choices, null=True, blank=True)
    status = models.CharField(max_length=16, choices=PaymentOrderStatus.choices, default=PaymentOrderStatus.PENDING)
    expires_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "payment_orders"
        managed = False
        ordering = ["-created_at", "-id"]
        verbose_name = "Р—Р°РєР°Р· РЅР° РѕРїР»Р°С‚Сѓ"
        verbose_name_plural = "Р—Р°РєР°Р·С‹ РЅР° РѕРїР»Р°С‚Сѓ"


class AttendanceMark(models.Model):
    id = models.BigAutoField(primary_key=True)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="attendance_marks", db_column="lesson_id")
    student = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="attendance_marks",
        db_column="student_id",
    )
    status = models.CharField(max_length=16, choices=AttendanceStatus.choices)
    marked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "attendance_marks"
        managed = False
        unique_together = [("lesson", "student")]
        verbose_name = "Отметка посещаемости"
        verbose_name_plural = "Отметки посещаемости"


class FavoriteCourse(models.Model):
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="favorite_courses", db_column="user_id")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="favorited_by", db_column="course_id")

    class Meta:
        db_table = "favorite_courses"
        managed = False
        unique_together = [("user", "course")]
        verbose_name = "Избранный курс"
        verbose_name_plural = "Избранные курсы"
