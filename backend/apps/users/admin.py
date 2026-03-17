from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    FavoriteTeacher,
    TeacherAchievement,
    TeacherProfile,
    TeacherReview,
    User,
    UserPreference,
    UserPreferredWeekday,
    UserSkill,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("id", "email", "first_name", "last_name", "role", "city", "survey_completed")
    list_filter = ("role", "survey_completed", "is_staff", "is_superuser")
    search_fields = ("email", "first_name", "last_name", "phone")
    ordering = ("id",)
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Дополнительно",
            {
                "fields": (
                    "phone",
                    "avatar",
                    "city",
                    "dance_level",
                    "role",
                    "is_teacher_enabled",
                    "survey_completed",
                )
            },
        ),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (
            "Дополнительно",
            {
                "fields": (
                    "email",
                    "phone",
                    "role",
                    "is_teacher_enabled",
                    "survey_completed",
                )
            },
        ),
    )


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "experience_years", "rating_avg", "rating_count")
    search_fields = ("user__email", "user__first_name", "user__last_name")


@admin.register(TeacherAchievement)
class TeacherAchievementAdmin(admin.ModelAdmin):
    list_display = ("id", "teacher", "title", "achieved_at")
    search_fields = ("title", "teacher__user__email")


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "city", "level", "price_from", "price_to")
    search_fields = ("user__email",)


@admin.register(UserPreferredWeekday)
class UserPreferredWeekdayAdmin(admin.ModelAdmin):
    list_display = ("id", "preference", "weekday")


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "dance_style", "level")
    search_fields = ("user__email", "dance_style__name")


@admin.register(FavoriteTeacher)
class FavoriteTeacherAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "teacher", "created_at")


@admin.register(TeacherReview)
class TeacherReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "teacher", "author_user", "rating", "created_at")
    search_fields = ("teacher__user__email", "author_user__email")

# Register your models here.
