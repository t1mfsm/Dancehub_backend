from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    FavoriteTeacher,
    TeacherProfile,
    TeacherReview,
    User,
    UserDanceStyleSkill,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("id", "email", "first_name", "middle_name", "last_name", "role", "city", "survey_completed")
    list_filter = ("role", "survey_completed", "is_staff", "is_superuser")
    search_fields = ("email", "username", "first_name", "middle_name", "last_name", "phone")
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
                    "survey_completed",
                    "preferred_time_from",
                    "preferred_time_to",
                    "preferred_weekdays",
                    "preferred_dance_styles",
                    "survey_preferences",
                    "flags",
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
                    "survey_completed",
                )
            },
        ),
    )


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "experience_years", "rating_avg", "rating_count")
    search_fields = ("user__email", "user__first_name", "user__last_name")


@admin.register(FavoriteTeacher)
class FavoriteTeacherAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "teacher", "created_at")


@admin.register(TeacherReview)
class TeacherReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "teacher", "author_user", "rating", "created_at")
    search_fields = ("teacher__user__email", "author_user__email")


@admin.register(UserDanceStyleSkill)
class UserDanceStyleSkillAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "dance_style", "level")
    list_filter = ("level", "dance_style")
    search_fields = ("user__email", "dance_style__name")
