from django.contrib import admin

from .models import (
    AttendanceMark,
    Course,
    CourseSchedule,
    DanceStyle,
    Enrollment,
    FavoriteCourse,
    Lesson,
    Studio,
)


@admin.register(DanceStyle)
class DanceStyleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug")
    search_fields = ("name", "slug")


@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "city", "metro", "halls_count")
    search_fields = ("name", "address", "metro")
    list_filter = ("city",)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "teacher", "dance_style", "studio", "level", "status")
    list_filter = ("status", "level", "dance_style", "studio")
    search_fields = ("name", "teacher__user__email", "teacher__user__first_name", "teacher__user__last_name")


@admin.register(CourseSchedule)
class CourseScheduleAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "weekday", "time_from", "time_to")


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "lesson_date", "time_from", "time_to", "hall", "status")
    list_filter = ("status",)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "course", "status", "paid", "enrolled_at")
    list_filter = ("status", "paid")


@admin.register(AttendanceMark)
class AttendanceMarkAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "student", "status", "marked_at")
    list_filter = ("status",)


@admin.register(FavoriteCourse)
class FavoriteCourseAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "course", "created_at")
