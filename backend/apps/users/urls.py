from django.urls import path

from .views import (
    ChangePasswordAPIView,
    CourseEnrollAPIView,
    EnrollmentListAPIView,
    FavoriteCourseAddAPIView,
    FavoriteTeacherAddAPIView,
    FavoritesAPIView,
    LoginAPIView,
    LogoutAPIView,
    MeAPIView,
    MyTeachingCourseListAPIView,
    RecommendedCourseListAPIView,
    RefreshTokenAPIView,
    RegisterAPIView,
    TeacherCourseListAPIView,
    TeacherListAPIView,
    TeacherRetrieveAPIView,
)


app_name = "users"

urlpatterns = [
    path("auth/register/", RegisterAPIView.as_view(), name="auth-register"),
    path("auth/login/", LoginAPIView.as_view(), name="auth-login"),
    path("auth/refresh/", RefreshTokenAPIView.as_view(), name="auth-refresh"),
    path("auth/logout/", LogoutAPIView.as_view(), name="auth-logout"),
    path("auth/change-password/", ChangePasswordAPIView.as_view(), name="auth-change-password"),
    path("teachers/", TeacherListAPIView.as_view(), name="teacher-list"),
    path("teachers/<int:id>/", TeacherRetrieveAPIView.as_view(), name="teacher-detail"),
    path("teachers/<int:id>/courses/", TeacherCourseListAPIView.as_view(), name="teacher-course-list"),
    path("user/", MeAPIView.as_view(), name="user"),
    path("recommendations/courses/", RecommendedCourseListAPIView.as_view(), name="course-recommendations"),
    path("my-teaching-courses/", MyTeachingCourseListAPIView.as_view(), name="my-teaching-courses"),
    path("favorites/", FavoritesAPIView.as_view(), name="favorites"),
    path("favorite-courses/<int:course_id>/", FavoriteCourseAddAPIView.as_view(), name="favorite-course-add"),
    path("favorite-teachers/<int:teacher_id>/", FavoriteTeacherAddAPIView.as_view(), name="favorite-teacher-add"),
    path("enrollments/", EnrollmentListAPIView.as_view(), name="enrollment-list"),
    path("courses/<int:course_id>/enroll/", CourseEnrollAPIView.as_view(), name="course-enroll"),
]
