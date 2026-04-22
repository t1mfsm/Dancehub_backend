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
    BEGINNER = "Начинающие", "Начинающие"
    INTERMEDIATE = "Средний уровень", "Средний уровень"
    ADVANCED = "Продвинутые", "Продвинутые"
    ANY = "Любой уровень", "Любой уровень"


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
        max_length=32,
        choices=DanceLevel.choices,
        blank=True,
    )
    role = models.CharField(
        max_length=16,
        choices=UserRole.choices,
        default=UserRole.STUDENT,
    )
    survey_completed = models.BooleanField(default=False)
    flags = models.JSONField(default=dict, blank=True)

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
    achievements = models.JSONField(default=list, blank=True)
    specializations = models.JSONField(default=list, blank=True)
    experience_years = models.PositiveIntegerField(default=0)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "teacher_profiles"
        verbose_name = "Профиль преподавателя"
        verbose_name_plural = "Профили преподавателей"

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.email}"


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
