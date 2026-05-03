from django.contrib import admin
from django.db.models import Avg

from .admin_views import FavoriteTeacherAdminView, UserFlagAdminView, UserSkillAdminView
from .models import Notification, TeacherProfile, TeacherReview, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "username", "first_name", "last_name", "role", "city", "survey_completed")
    list_filter = ("role", "survey_completed", "dance_level", "city")
    search_fields = ("email", "username", "first_name", "middle_name", "last_name")
    ordering = ("id",)
    readonly_fields = ("password_hash",)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "experience_years", "rating_preview")
    search_fields = ("user__email", "user__username", "user__first_name", "user__last_name")
    ordering = ("id",)

    @admin.display(description="Rating")
    def rating_preview(self, obj):
        return round(float(obj.reviews.aggregate(value=Avg("rating"))["value"] or 0), 2)


@admin.register(TeacherReview)
class TeacherReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "teacher", "user", "lesson", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("teacher__user__email", "user__email", "text")
    ordering = ("-created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "kind", "title", "course", "lesson", "read_at", "created_at")
    list_filter = ("kind", "read_at", "created_at")
    search_fields = ("user__email", "user__username", "title", "body")
    ordering = ("-created_at", "-id")


class ReadOnlyAdmin(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserFlagAdminView)
class UserFlagAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "value")
    list_filter = ("value",)
    search_fields = ("user__email", "user__username", "name")
    ordering = ("user", "name")
    readonly_fields = ("user", "name", "value")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserSkillAdminView)
class UserSkillAdmin(ReadOnlyAdmin):
    list_display = ("user", "dance_style", "level")
    list_filter = ("level", "dance_style")
    search_fields = ("user__email", "user__username", "dance_style__name")
    ordering = ("user", "dance_style")
    readonly_fields = ("user", "dance_style", "level")


@admin.register(FavoriteTeacherAdminView)
class FavoriteTeacherAdmin(ReadOnlyAdmin):
    list_display = ("user", "teacher")
    search_fields = ("user__email", "teacher__user__email", "teacher__user__first_name", "teacher__user__last_name")
    ordering = ("user", "teacher")
    readonly_fields = ("user", "teacher")
