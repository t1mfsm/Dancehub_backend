from django.contrib import admin

from .admin_views import FavoriteCourseAdminView
from .models import AttendanceMark, Course, CourseSchedule, DanceStyle, Enrollment, Lesson, Studio


@admin.register(DanceStyle)
class DanceStyleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug")
    search_fields = ("name", "slug")
    ordering = ("id",)


@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "city", "metro", "halls_count")
    list_filter = ("city",)
    search_fields = ("name", "address", "metro")
    ordering = ("id",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "teacher", "dance_style", "studio", "level", "status", "date_from", "date_to")
    list_filter = ("status", "level", "dance_style", "studio")
    search_fields = ("name", "teacher__user__email", "teacher__user__first_name", "teacher__user__last_name")
    ordering = ("-id",)


@admin.register(CourseSchedule)
class CourseScheduleAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "weekday", "time_from", "time_to", "location_text")
    list_filter = ("weekday",)
    search_fields = ("course__name", "location_text")
    ordering = ("id",)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "schedule", "lesson_date", "time_from", "time_to", "hall", "status")
    list_filter = ("status", "lesson_date")
    search_fields = ("course__name", "location_text", "hall")
    ordering = ("lesson_date", "time_from")


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "course", "status", "enrolled_at")
    list_filter = ("status",)
    search_fields = ("user__email", "course__name")
    ordering = ("-enrolled_at",)


@admin.register(AttendanceMark)
class AttendanceMarkAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "student", "status", "marked_at")
    list_filter = ("status", "marked_at")
    search_fields = ("student__email", "lesson__course__name")
    ordering = ("-marked_at",)


class ReadOnlyAdmin(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FavoriteCourseAdminView)
class FavoriteCourseAdmin(ReadOnlyAdmin):
    list_display = ("user", "course")
    search_fields = ("user__email", "course__name")
    ordering = ("user", "course")
    readonly_fields = ("user", "course")
