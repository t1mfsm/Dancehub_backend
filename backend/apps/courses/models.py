from django.db import models

from apps.users.models import AttendanceStatus, DanceLevel, Weekday


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CourseStatus(models.TextChoices):
    PUBLISHED = "published", "Опубликован"
    ACTIVE = "active", "Активен"
    COMPLETED = "completed", "Завершён"
    CANCELLED = "cancelled", "Отменён"


class LessonStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Запланировано"
    CANCELLED = "cancelled", "Отменено"


class EnrollmentStatus(models.TextChoices):
    ACTIVE = "active", "Активна"
    PENDING = "pending", "Ожидает оплаты"
    CANCELLED = "cancelled", "Отменена"
    COMPLETED = "completed", "Завершена"


class DanceStyle(models.Model):
    name = models.CharField(max_length=128, unique=True)
    slug = models.SlugField(max_length=140, unique=True)

    class Meta:
        db_table = "dance_styles"
        verbose_name = "Танцевальный стиль"
        verbose_name_plural = "Танцевальные стили"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Studio(TimeStampedModel):
    name = models.CharField(max_length=255)
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.CASCADE,
        related_name="studios",
    )
    address = models.CharField(max_length=255)
    metro = models.CharField(max_length=128, blank=True)
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    image = models.URLField(blank=True)
    halls_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "studios"
        verbose_name = "Студия"
        verbose_name_plural = "Студии"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Course(TimeStampedModel):
    teacher = models.ForeignKey(
        "users.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="courses",
    )
    dance_style = models.ForeignKey(
        DanceStyle,
        on_delete=models.PROTECT,
        related_name="courses",
    )
    studio = models.ForeignKey(
        Studio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    level = models.CharField(max_length=16, choices=DanceLevel.choices)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.PositiveIntegerField()
    date_from = models.DateField()
    date_to = models.DateField()
    status = models.CharField(
        max_length=16,
        choices=CourseStatus.choices,
        default=CourseStatus.PUBLISHED,
    )
    images = models.JSONField(default=list, blank=True)
    image_cover = models.URLField(blank=True)
    music_artist = models.CharField(max_length=255, blank=True)
    music_track = models.CharField(max_length=255, blank=True)
    music_url = models.URLField(blank=True)

    class Meta:
        db_table = "courses"
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class CourseSchedule(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="schedule_rules",
    )
    weekday = models.CharField(max_length=3, choices=Weekday.choices)
    time_from = models.TimeField()
    time_to = models.TimeField()
    location_text = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "course_schedule"
        verbose_name = "Расписание курса"
        verbose_name_plural = "Расписания курсов"


class Lesson(TimeStampedModel):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="lessons",
    )
    schedule = models.ForeignKey(
        CourseSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
    )
    lesson_date = models.DateField()
    time_from = models.TimeField()
    time_to = models.TimeField()
    location_text = models.CharField(max_length=255, blank=True)
    hall = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=16,
        choices=LessonStatus.choices,
        default=LessonStatus.SCHEDULED,
    )

    class Meta:
        db_table = "lessons"
        verbose_name = "Занятие"
        verbose_name_plural = "Занятия"
        ordering = ["lesson_date", "time_from"]


class Enrollment(TimeStampedModel):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    enrolled_at = models.DateField()
    status = models.CharField(
        max_length=16,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.PENDING,
    )
    paid = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "enrollments"
        verbose_name = "Запись на курс"
        verbose_name_plural = "Записи на курсы"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "course"],
                name="unique_enrollment_per_user_and_course",
            )
        ]


class AttendanceMark(models.Model):
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="attendance_marks",
    )
    student = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="attendance_marks",
    )
    status = models.CharField(
        max_length=16,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
    )
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance_marks"
        verbose_name = "Отметка посещаемости"
        verbose_name_plural = "Отметки посещаемости"
        constraints = [
            models.UniqueConstraint(
                fields=["lesson", "student"],
                name="unique_attendance_per_lesson_and_student",
            )
        ]


class FavoriteCourse(models.Model):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="favorite_courses",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "favorite_courses"
        verbose_name = "Избранный курс"
        verbose_name_plural = "Избранные курсы"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "course"],
                name="unique_favorite_course",
            )
        ]
