from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.courses.models import Course
from apps.users.models import User

from .services import rebuild_user_recommendation_profile, serialize_recommendation_payload, track_course_view


class IsAuthenticated(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_authenticated", False))


def require_authenticated_user(request) -> User:
    user = request.user
    if not user or not getattr(user, "is_authenticated", False):
        raise ValidationError({"detail": "Authentication required."})
    return user


class RecommendationListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = require_authenticated_user(request)
        limit = int(request.query_params.get("limit", 12))
        limit = max(1, min(limit, 50))
        return Response(serialize_recommendation_payload(user, request, limit=limit))


class RecommendationRebuildAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None)
    def post(self, request):
        user = require_authenticated_user(request)
        profile = rebuild_user_recommendation_profile(user)
        return Response(
            {
                "detail": "ok",
                "updated_at": profile.updated_at.isoformat(),
                "behavior_weight": str(profile.behavior_weight),
            }
        )


class CourseViewTrackAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None)
    def post(self, request, course_id: int):
        user = require_authenticated_user(request)
        course = Course.objects.filter(id=course_id).first()
        if course is None:
            raise ValidationError({"detail": "Course not found."})
        created = track_course_view(user, course)
        return Response({"tracked": created})

