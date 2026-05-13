from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from apps.common.choices import DanceLevel, UserRole, WeekdayCode
from apps.common.utils import build_full_name


class User(models.Model):
    id = models.BigAutoField(primary_key=True)
    email = models.TextField(unique=True)
    username = models.TextField(unique=True)
    first_name = models.TextField()
    middle_name = models.TextField(default="", blank=True)
    last_name = models.TextField()
    password_hash = models.TextField()
    avatar = models.TextField(null=True, blank=True)
    city = models.ForeignKey(
        "locations.City",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        db_column="city_id",
    )
    dance_level = models.CharField(max_length=16, choices=DanceLevel.choices, null=True, blank=True)
    role = models.CharField(max_length=16, choices=UserRole.choices, default=UserRole.STUDENT)
    survey_completed = models.BooleanField(default=False)
    preferred_time_from = models.TimeField(null=True, blank=True)
    preferred_time_to = models.TimeField(null=True, blank=True)
    preferred_weekdays = ArrayField(
        base_field=models.CharField(max_length=3, choices=WeekdayCode.choices),
        default=list,
        blank=True,
    )
    preferred_dance_styles = ArrayField(base_field=models.TextField(), default=list, blank=True)
    price_from = models.IntegerField(null=True, blank=True)
    price_to = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "users"
        managed = False
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_full_name(self) -> str:
        return build_full_name(self.last_name, self.first_name, self.middle_name)

    def __str__(self) -> str:
        return self.get_full_name() or self.email


class UserFlag(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="flags", db_column="user_id")
    name = models.TextField()
    value = models.BooleanField()

    class Meta:
        db_table = "user_flags"
        managed = False
        unique_together = [("user", "name")]
        verbose_name = "Флаг пользователя"
        verbose_name_plural = "Флаги пользователей"


class UserSkill(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="skills", db_column="user_id")
    dance_style = models.ForeignKey(
        "courses.DanceStyle",
        on_delete=models.CASCADE,
        related_name="user_skills",
        db_column="dance_style_id",
    )
    level = models.CharField(max_length=16, choices=DanceLevel.choices)

    class Meta:
        db_table = "user_skills"
        managed = False
        unique_together = [("user", "dance_style")]
        verbose_name = "Навык пользователя"
        verbose_name_plural = "Навыки пользователей"


class TeacherProfile(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
        db_column="user_id",
    )
    bio = models.TextField(default="", blank=True)
    experience_years = models.PositiveIntegerField(default=0)
    images = ArrayField(base_field=models.TextField(), default=list, blank=True)
    achievements = ArrayField(base_field=models.TextField(), default=list, blank=True)
    specializations = ArrayField(base_field=models.TextField(), default=list, blank=True)

    class Meta:
        db_table = "teachers"
        managed = False
        verbose_name = "Профиль преподавателя"
        verbose_name_plural = "Профили преподавателей"


class FavoriteTeacher(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorite_teachers", db_column="user_id")
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="favorited_by",
        db_column="teacher_id",
    )

    class Meta:
        db_table = "favorite_teachers"
        managed = False
        unique_together = [("user", "teacher")]
        verbose_name = "Избранный преподаватель"
        verbose_name_plural = "Избранные преподаватели"


class TeacherReview(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="teacher_reviews_left", db_column="user_id")
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name="reviews",
        db_column="teacher_id",
    )
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="teacher_reviews", db_column="course_id")
    lesson = models.ForeignKey(
        "courses.Lesson",
        on_delete=models.CASCADE,
        related_name="teacher_reviews",
        db_column="lesson_id",
        null=True,
        blank=True,
    )
    rating = models.PositiveSmallIntegerField()
    text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "teacher_reviews"
        managed = False
        unique_together = [("user", "course")]
        verbose_name = "Отзыв о преподавателе"
        verbose_name_plural = "Отзывы о преподавателях"


class Notification(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications", db_column="user_id")
    kind = models.TextField()
    title = models.TextField()
    body = models.TextField()
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        db_column="course_id",
    )
    lesson = models.ForeignKey(
        "courses.Lesson",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        db_column="lesson_id",
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "notifications"
        managed = False
        ordering = ["-created_at", "-id"]
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
