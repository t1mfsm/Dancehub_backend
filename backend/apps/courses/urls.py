from django.urls import path

from .views import (
    AttendanceMarkAPIView,
    CalendarAPIView,
    CourseAttendanceListAPIView,
    CourseListAPIView,
    CourseStudentListAPIView,
    CourseRetrieveAPIView,
    DanceStyleListAPIView,
    LessonRetrieveUpdateDestroyAPIView,
    LessonAttendanceListAPIView,
    MapPointListAPIView,
    StudioRetrieveAPIView,
    StudioListAPIView,
)


app_name = "courses"

urlpatterns = [
    path("dance-styles/", DanceStyleListAPIView.as_view(), name="dance-style-list"),
    path("studios/", StudioListAPIView.as_view(), name="studio-list"),
    path("studios/<int:id>/", StudioRetrieveAPIView.as_view(), name="studio-detail"),
    path("map/points/", MapPointListAPIView.as_view(), name="map-points"),
    path("calendar/", CalendarAPIView.as_view(), name="calendar"),
    path("courses/", CourseListAPIView.as_view(), name="course-list"),
    path("courses/<int:id>/", CourseRetrieveAPIView.as_view(), name="course-detail"),
    path("courses/<int:id>/students/", CourseStudentListAPIView.as_view(), name="course-students"),
    path("courses/<int:id>/attendance/", CourseAttendanceListAPIView.as_view(), name="course-attendance"),
    path("lessons/<int:lesson_id>/", LessonRetrieveUpdateDestroyAPIView.as_view(), name="lesson-detail"),
    path("lessons/<int:lesson_id>/attendance/", LessonAttendanceListAPIView.as_view(), name="lesson-attendance"),
    path("lessons/<int:lesson_id>/attendance/mark/", AttendanceMarkAPIView.as_view(), name="attendance-mark"),
]
