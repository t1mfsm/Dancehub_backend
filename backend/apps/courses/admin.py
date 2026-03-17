from django.contrib import admin

from .models import (
    Attendance,
    Course,
    CourseImage,
    CourseMusic,
    CourseScheduleRule,
    DanceStyle,
    Enrollment,
    FavoriteCourse,
    Hall,
    Lesson,
    Review,
    Studio,
    TeacherSpecialization,
    UserPreferredDanceStyle,
)


@admin.register(DanceStyle)
class DanceStyleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug")
    search_fields = ("name", "slug")


@admin.register(Studio)
class StudioAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "city", "metro")
    search_fields = ("name", "address", "metro")
    list_filter = ("city",)


@admin.register(Hall)
class HallAdmin(admin.ModelAdmin):
    list_display = ("id", "studio", "name", "capacity")
    search_fields = ("studio__name", "name")


@admin.register(TeacherSpecialization)
class TeacherSpecializationAdmin(admin.ModelAdmin):
    list_display = ("id", "teacher", "dance_style")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "teacher", "dance_style", "studio", "level", "status")
    list_filter = ("status", "level", "dance_style", "studio")
    search_fields = ("name", "teacher__user__email", "teacher__user__first_name", "teacher__user__last_name")


@admin.register(CourseImage)
class CourseImageAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "sort_order")


@admin.register(CourseMusic)
class CourseMusicAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "artist", "track")


@admin.register(CourseScheduleRule)
class CourseScheduleRuleAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "weekday", "time_from", "time_to", "hall")


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "lesson_date", "time_from", "time_to", "status")
    list_filter = ("status",)


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "course", "status", "paid", "enrolled_at")
    list_filter = ("status", "paid")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("id", "lesson", "student", "status", "marked_at")
    list_filter = ("status",)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "course", "author_user", "rating", "created_at")


@admin.register(FavoriteCourse)
class FavoriteCourseAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "course", "created_at")


@admin.register(UserPreferredDanceStyle)
class UserPreferredDanceStyleAdmin(admin.ModelAdmin):
    list_display = ("id", "preference", "dance_style")

# Register your models here.
