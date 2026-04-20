from django.contrib.auth.models import AbstractUser
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UserRole(models.TextChoices):
    STUDENT = "student", "Ученик"
    TEACHER = "teacher", "Преподаватель"
    ADMIN = "admin", "Администратор"


class DanceLevel(models.TextChoices):
    BEGINNER = "beginner", "Начинающий"
    INTERMEDIATE = "intermediate", "Средний"
    ADVANCED = "advanced", "Продвинутый"
    ANY = "any", "Любой"


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Присутствовал"
    ABSENT = "absent", "Отсутствовал"
    LATE = "late", "Опоздал"
    EXCUSED = "excused", "Уважительная причина"


class Weekday(models.TextChoices):
    MONDAY = "mon", "Понедельник"
    TUESDAY = "tue", "Вторник"
    WEDNESDAY = "wed", "Среда"
    THURSDAY = "thu", "Четверг"
    FRIDAY = "fri", "Пятница"
    SATURDAY = "sat", "Суббота"
    SUNDAY = "sun", "Воскресенье"


class User(AbstractUser):
    email = models.EmailField(unique=True)
    middle_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    avatar = models.URLField(blank=True)
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )
    dance_level = models.CharField(
        max_length=16,
        choices=DanceLevel.choices,
        blank=True,
    )
    role = models.CharField(
        max_length=16,
        choices=UserRole.choices,
        default=UserRole.STUDENT,
    )
    is_teacher_enabled = models.BooleanField(default=False)
    survey_completed = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"


class TeacherProfile(TimeStampedModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
    )
    bio = models.TextField(blank=True)
    images = models.JSONField(default=list, blank=True)
    experience_years = models.PositiveIntegerField(default=0)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "teacher_profiles"
        verbose_name = "Профиль преподавателя"
        verbose_name_plural = "Профили преподавателей"

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.email}"


class TeacherAchievement(models.Model):
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="achievements",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    achieved_at = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "teacher_achievements"
        verbose_name = "Достижение преподавателя"
        verbose_name_plural = "Достижения преподавателей"

    def __str__(self) -> str:
        return self.title


class UserPreference(TimeStampedModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="preferences",
    )
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_preferences",
    )
    level = models.CharField(max_length=16, choices=DanceLevel.choices, blank=True)
    preferred_time_from = models.TimeField(null=True, blank=True)
    preferred_time_to = models.TimeField(null=True, blank=True)
    price_from = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price_to = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    goal = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "user_preferences"
        verbose_name = "Предпочтение пользователя"
        verbose_name_plural = "Предпочтения пользователей"


class UserPreferredWeekday(models.Model):
    preference = models.ForeignKey(
        UserPreference,
        on_delete=models.CASCADE,
        related_name="preferred_weekdays",
    )
    weekday = models.CharField(max_length=3, choices=Weekday.choices)

    class Meta:
        db_table = "user_preferred_weekdays"
        verbose_name = "Предпочитаемый день"
        verbose_name_plural = "Предпочитаемые дни"
        constraints = [
            models.UniqueConstraint(
                fields=["preference", "weekday"],
                name="unique_preferred_weekday_per_preference",
            )
        ]


class UserSkill(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="skills",
    )
    dance_style = models.ForeignKey(
        "courses.DanceStyle",
        on_delete=models.CASCADE,
        related_name="user_skills",
    )
    level = models.CharField(max_length=16, choices=DanceLevel.choices)

    class Meta:
        db_table = "user_skills"
        verbose_name = "Навык пользователя"
        verbose_name_plural = "Навыки пользователей"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "dance_style"],
                name="unique_skill_per_user_and_style",
            )
        ]


class FavoriteTeacher(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="favorite_teachers",
    )
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "favorite_teachers"
        verbose_name = "Избранный преподаватель"
        verbose_name_plural = "Избранные преподаватели"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "teacher"],
                name="unique_favorite_teacher",
            )
        ]


class TeacherReview(TimeStampedModel):
    author_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_reviews_left",
    )
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField()
    text = models.TextField(blank=True)

    class Meta:
        db_table = "teacher_reviews"
        verbose_name = "Отзыв о преподавателе"
        verbose_name_plural = "Отзывы о преподавателях"
        constraints = [
            models.UniqueConstraint(
                fields=["author_user", "teacher"],
                name="unique_teacher_review_per_author",
            )
        ]
