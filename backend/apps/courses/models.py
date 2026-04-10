from django.db import models

from apps.users.models import AttendanceStatus, DanceLevel, Weekday


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CourseStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    PUBLISHED = "published", "Опубликован"
    CANCELLED = "cancelled", "Отменен"
    COMPLETED = "completed", "Завершен"


class LessonStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Запланировано"
    CANCELLED = "cancelled", "Отменено"
    COMPLETED = "completed", "Проведено"


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

    class Meta:
        db_table = "studios"
        verbose_name = "Студия"
        verbose_name_plural = "Студии"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Hall(models.Model):
    studio = models.ForeignKey(
        Studio,
        on_delete=models.CASCADE,
        related_name="halls",
    )
    name = models.CharField(max_length=128)
    capacity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "halls"
        verbose_name = "Зал"
        verbose_name_plural = "Залы"
        constraints = [
            models.UniqueConstraint(
                fields=["studio", "name"],
                name="unique_hall_name_per_studio",
            )
        ]

    def __str__(self) -> str:
        return f"{self.studio.name} / {self.name}"


class TeacherSpecialization(models.Model):
    teacher = models.ForeignKey(
        "users.TeacherProfile",
        on_delete=models.CASCADE,
        related_name="specializations",
    )
    dance_style = models.ForeignKey(
        DanceStyle,
        on_delete=models.CASCADE,
        related_name="teacher_specializations",
    )

    class Meta:
        db_table = "teacher_specializations"
        verbose_name = "Специализация преподавателя"
        verbose_name_plural = "Специализации преподавателей"
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "dance_style"],
                name="unique_teacher_specialization",
            )
        ]


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
    hall = models.ForeignKey(
        Hall,
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
    spots_left = models.PositiveIntegerField(null=True, blank=True)
    date_from = models.DateField()
    date_to = models.DateField()
    status = models.CharField(
        max_length=16,
        choices=CourseStatus.choices,
        default=CourseStatus.DRAFT,
    )
    music_artist = models.CharField(max_length=255, blank=True)
    music_track = models.CharField(max_length=255, blank=True)
    music_url = models.URLField(blank=True)
    image_cover = models.URLField(blank=True)

    class Meta:
        db_table = "courses"
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class CourseImage(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.URLField()
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "course_images"
        verbose_name = "Изображение курса"
        verbose_name_plural = "Изображения курсов"
        ordering = ["sort_order", "id"]


class CourseScheduleRule(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="schedule_rules",
    )
    weekday = models.CharField(max_length=3, choices=Weekday.choices)
    time_from = models.TimeField()
    time_to = models.TimeField()
    hall = models.ForeignKey(
        Hall,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedule_rules",
    )
    location_text = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "course_schedule_rules"
        verbose_name = "Правило расписания курса"
        verbose_name_plural = "Правила расписания курсов"


class Lesson(TimeStampedModel):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="lessons",
    )
    schedule_rule = models.ForeignKey(
        CourseScheduleRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
    )
    hall = models.ForeignKey(
        Hall,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
    )
    lesson_date = models.DateField()
    time_from = models.TimeField()
    time_to = models.TimeField()
    location_text = models.CharField(max_length=255, blank=True)
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


class Attendance(models.Model):
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    student = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    status = models.CharField(max_length=16, choices=AttendanceStatus.choices)
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendance"
        verbose_name = "Посещаемость"
        verbose_name_plural = "Посещаемость"
        constraints = [
            models.UniqueConstraint(
                fields=["lesson", "student"],
                name="unique_attendance_per_lesson_and_student",
            )
        ]


class Review(TimeStampedModel):
    author_user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="course_reviews_left",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField()
    text = models.TextField(blank=True)

    class Meta:
        db_table = "reviews"
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        constraints = [
            models.UniqueConstraint(
                fields=["author_user", "course"],
                name="unique_course_review_per_author",
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


class UserPreferredDanceStyle(models.Model):
    preference = models.ForeignKey(
        "users.UserPreference",
        on_delete=models.CASCADE,
        related_name="preferred_dance_styles",
    )
    dance_style = models.ForeignKey(
        DanceStyle,
        on_delete=models.CASCADE,
        related_name="preferred_by_users",
    )

    class Meta:
        db_table = "user_preferred_dance_styles"
        verbose_name = "Предпочитаемый стиль"
        verbose_name_plural = "Предпочитаемые стили"
        constraints = [
            models.UniqueConstraint(
                fields=["preference", "dance_style"],
                name="unique_preferred_style_per_preference",
            )
        ]
