from django.urls import path

from .views import CourseViewTrackAPIView, RecommendationListAPIView, RecommendationRebuildAPIView

app_name = "recommendations"

urlpatterns = [
    path("recommendations/", RecommendationListAPIView.as_view(), name="recommendation-list"),
    path("recommendations/rebuild/", RecommendationRebuildAPIView.as_view(), name="recommendation-rebuild"),
    path("course-views/<int:course_id>/", CourseViewTrackAPIView.as_view(), name="course-view-track"),
]
