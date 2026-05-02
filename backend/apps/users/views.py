from django.contrib.auth.hashers import check_password
from django.db import connection
from django.db import transaction
from django.db.models import Avg, Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.choices import CourseStatus, DanceLevel, EnrollmentStatus, UserRole
from apps.common.files import save_uploaded_file
from apps.common.utils import build_full_name, course_lifecycle_status
from apps.courses.models import Course, DanceStyle, Enrollment, FavoriteCourse
from apps.courses.serializers import serialize_course_detail
from apps.courses.serializers import EnrollmentRequestSerializer
from apps.users.models import TeacherProfile, User
from config.authentication import build_tokens_for_user, decode_token

from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    RefreshSerializer,
    RegisterSerializer,
    TeacherProfileUpdateSerializer,
    UserFlagSerializer,
    UserPreferencesSerializer,
    UserSkillItemSerializer,
    UserUpdateSerializer,
    serialize_user,
    update_user_preferences_record,
)


class IsAuthenticated(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_authenticated", False))


def require_authenticated_user(request) -> User:
    user = request.user
    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")
    return user


def get_current_teacher(request) -> TeacherProfile:
    user = require_authenticated_user(request)
    teacher = TeacherProfile.objects.filter(user=user).first()
    if teacher is None:
        raise ValidationError({"detail": "User does not have a teacher profile."})
    return teacher


def user_with_rating(user: User):
    teacher = TeacherProfile.objects.filter(user=user).first()
    rating = 0
    if teacher:
        rating = teacher.reviews.aggregate(value=Avg("rating"))["value"] or 0
    return teacher, rating


def apply_user_preferences(user: User, data: dict, *, mark_survey_completed: bool = False) -> User:
    from apps.locations.models import City

    updates = {}
    if "city" in data:
        city_name = (data.get("city") or "").strip()
        city = City.objects.filter(name=city_name).first() if city_name else None
        updates["city_id"] = city.id if city else None
    if "level" in data:
        updates["dance_level"] = None if data["level"] == "any" else data["level"]
    if "preferred_weekdays" in data:
        updates["preferred_weekdays"] = data["preferred_weekdays"]
    if "preferred_time_from" in data:
        updates["preferred_time_from"] = data["preferred_time_from"]
    if "preferred_time_to" in data:
        updates["preferred_time_to"] = data["preferred_time_to"]
    if "price_from" in data:
        updates["price_from"] = data["price_from"]
    if "price_to" in data:
        updates["price_to"] = data["price_to"]
    if "preferred_dance_styles" in data:
        updates["preferred_dance_styles"] = data["preferred_dance_styles"]
    if "role" in data:
        updates["role"] = data["role"]
    if mark_survey_completed:
        updates["survey_completed"] = True
    return update_user_preferences_record(user.id, **updates)


class RegisterAPIView(APIView):
    authentication_classes = []

    @extend_schema(request=RegisterSerializer)
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        tokens = build_tokens_for_user(user)
        return Response({"user": serialize_user(user, request=request), **tokens})


class LoginAPIView(APIView):
    authentication_classes = []

    @extend_schema(request=LoginSerializer)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email=serializer.validated_data["email"]).select_related("city").first()
        if user is None or not check_password(serializer.validated_data["password"], user.password_hash):
            raise ValidationError({"detail": "Invalid email or password."})
        teacher, rating = user_with_rating(user)
        tokens = build_tokens_for_user(user)
        return Response({"user": serialize_user(user, request=request, teacher=teacher, teacher_rating=rating), **tokens})


class RefreshTokenAPIView(APIView):
    authentication_classes = []

    @extend_schema(request=RefreshSerializer)
    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = decode_token(serializer.validated_data["refresh"], expected_type="refresh")
        user = User.objects.filter(id=payload["sub"]).first()
        if user is None:
            raise ValidationError({"detail": "User not found."})
        return Response(build_tokens_for_user(user))


class LogoutAPIView(APIView):
    authentication_classes = []

    @extend_schema(request=LogoutSerializer)
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"detail": "ok"})


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = require_authenticated_user(request)
        teacher, rating = user_with_rating(user)
        return Response(serialize_user(user, request=request, teacher=teacher, teacher_rating=rating))

    @extend_schema(request=UserUpdateSerializer)
    def patch(self, request):
        user = require_authenticated_user(request)
        serializer = UserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "username" in data and data["username"] != user.username and User.objects.exclude(id=user.id).filter(username=data["username"]).exists():
            raise ValidationError({"username": ["A user with this username already exists."]})
        if "city" in data:
            from apps.locations.models import City

            city_name = (data.get("city") or "").strip()
            user.city = City.objects.filter(name=city_name).first() if city_name else None
        for field in ["username", "first_name", "middle_name", "last_name", "phone", "survey_completed", "dance_level", "role"]:
            if field in data:
                setattr(user, field, data[field])
        if "avatar_file" in data:
            user.avatar = save_uploaded_file(data["avatar_file"], "avatars")
        user.save(
            update_fields=[
                "username",
                "first_name",
                "middle_name",
                "last_name",
                "phone",
                "survey_completed",
                "avatar",
                "city",
                "dance_level",
                "role",
            ]
        )
        teacher, rating = user_with_rating(user)
        return Response(serialize_user(user, request=request, teacher=teacher, teacher_rating=rating))


class UserSurveyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=UserPreferencesSerializer)
    def patch(self, request):
        user = require_authenticated_user(request)
        serializer = UserPreferencesSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = apply_user_preferences(user, serializer.validated_data, mark_survey_completed=True)
        teacher, rating = user_with_rating(user)
        return Response(serialize_user(user, request=request, teacher=teacher, teacher_rating=rating))


class UserPreferenceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=UserPreferencesSerializer)
    def patch(self, request):
        user = require_authenticated_user(request)
        serializer = UserPreferencesSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = apply_user_preferences(user, serializer.validated_data)
        teacher, rating = user_with_rating(user)
        return Response(serialize_user(user, request=request, teacher=teacher, teacher_rating=rating))


class UserSkillAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=UserSkillItemSerializer(many=True))
    def put(self, request):
        user = require_authenticated_user(request)
        serializer = UserSkillItemSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM user_skills WHERE user_id = %s", [user.id])
            for row in serializer.validated_data:
                level = DanceLevel.BEGINNER if row["level"] == "any" else row["level"]
                cursor.execute(
                    "INSERT INTO user_skills (user_id, dance_style_id, level) VALUES (%s, %s, %s)",
                    [user.id, row["dance_style_id"], level],
                )
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserFlagAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=UserFlagSerializer)
    def post(self, request):
        user = require_authenticated_user(request)
        serializer = UserFlagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_flags (user_id, name, value)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, name)
                DO UPDATE SET value = EXCLUDED.value
                """,
                [user.id, serializer.validated_data["name"], serializer.validated_data["value"]],
            )
        return Response(serializer.validated_data)


class TeacherListAPIView(APIView):
    def get(self, request):
        teachers = TeacherProfile.objects.select_related("user__city").annotate(
            rating_avg=Avg("reviews__rating"),
            rating_count=Count("reviews"),
        )
        city = request.query_params.get("city")
        search = request.query_params.get("search")
        style = request.query_params.get("style")
        if city:
            teachers = teachers.filter(user__city__name__iexact=city)
        if search:
            teachers = teachers.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(user__username__icontains=search)
            )
        if style:
            teachers = teachers.filter(
                Q(courses__dance_style__slug__iexact=style) | Q(courses__dance_style__name__iexact=style)
            )
        teachers = teachers.distinct().order_by("user__last_name", "user__first_name")
        payload = []
        for teacher in teachers:
            payload.append(
                {
                    "id": teacher.id,
                    "full_name": build_full_name(teacher.user.last_name, teacher.user.first_name, teacher.user.middle_name)
                    or teacher.user.email,
                    "bio": teacher.bio or "",
                    "experience_years": teacher.experience_years,
                    "rating_avg": round(float(teacher.rating_avg or 0), 2),
                    "rating_count": teacher.rating_count,
                    "city": teacher.user.city.name if teacher.user.city else "",
                }
            )
        return Response(payload)

    @extend_schema(request=None)
    def post(self, request):
        user = require_authenticated_user(request)
        teacher, _ = TeacherProfile.objects.get_or_create(user=user, defaults={"bio": "", "experience_years": 0})
        if user.role != UserRole.TEACHER:
            user.role = UserRole.TEACHER
            user.save(update_fields=["role"])
        return Response({"id": teacher.id}, status=status.HTTP_201_CREATED)


class TeacherRetrieveAPIView(APIView):
    def get(self, request, id: int):
        teacher = TeacherProfile.objects.select_related("user__city").filter(id=id).first()
        if teacher is None:
            raise ValidationError({"detail": "Teacher not found."})
        reviews = teacher.reviews.select_related("user").order_by("-created_at")
        courses = teacher.courses.select_related("dance_style", "studio__city").prefetch_related("schedule_rows").annotate(
            active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE))
        )
        rating = reviews.aggregate(value=Avg("rating"))["value"] or 0
        payload = {
            "id": teacher.id,
            "user_id": teacher.user_id,
            "full_name": build_full_name(teacher.user.last_name, teacher.user.first_name, teacher.user.middle_name)
            or teacher.user.email,
            "name": build_full_name(teacher.user.first_name, teacher.user.last_name) or teacher.user.email,
            "email": teacher.user.email,
            "avatar": teacher.user.avatar or "",
            "city": teacher.user.city.name if teacher.user.city else "",
            "bio": teacher.bio or "",
            "images": teacher.images or [],
            "experience": teacher.experience_years,
            "rating": round(float(rating), 2),
            "specializations": teacher.specializations or [],
            "achievements": teacher.achievements or [],
            "reviews": [
                {
                    "id": review.id,
                    "author_name": build_full_name(review.user.first_name, review.user.last_name) or review.user.email,
                    "rating": review.rating,
                    "text": review.text,
                    "created_at": review.created_at.isoformat(),
                }
                for review in reviews
            ],
            "courses": [
                {
                    "id": course.id,
                    "name": course.name,
                    "dance_style": course.dance_style.name,
                    "level": course.level,
                    "price": course.price,
                    "date_from": course.date_from.isoformat(),
                    "date_to": course.date_to.isoformat(),
                    "status": course_lifecycle_status(course.status, course.date_from, course.date_to),
                    "studio": course.studio.name,
                }
                for course in courses
            ],
        }
        return Response(payload)

    @extend_schema(request=TeacherProfileUpdateSerializer)
    def put(self, request, id: int):
        user = require_authenticated_user(request)
        teacher = TeacherProfile.objects.filter(user=user).first()
        if teacher is None:
            teacher = TeacherProfile.objects.create(user=user, bio="", experience_years=0)
        if id not in (0, teacher.id):
            raise PermissionDenied("You can update only your teacher profile.")
        serializer = TeacherProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "bio" in data:
            teacher.bio = data["bio"]
        if "experience" in data:
            teacher.experience_years = data["experience"]
        if "achievements" in data:
            teacher.achievements = data["achievements"]
        if "specializations" in data:
            teacher.specializations = data["specializations"]
        if "images" in data:
            teacher.images = serializer.normalize_images("teacher-images")
        teacher.save()
        if user.role != UserRole.TEACHER:
            user.role = UserRole.TEACHER
            user.save(update_fields=["role"])
        rating = teacher.reviews.aggregate(value=Avg("rating"))["value"] or 0
        return Response(
            {
                "bio": teacher.bio or "",
                "images": teacher.images or [],
                "achievements": teacher.achievements or [],
                "experience": teacher.experience_years,
                "specializations": teacher.specializations or [],
                "rating": round(float(rating), 2),
            }
        )


class MyTeachingCourseListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        teacher = get_current_teacher(request)
        courses = (
            Course.objects.filter(teacher=teacher)
            .select_related("teacher__user", "dance_style", "studio__city")
            .prefetch_related("schedule_rows")
            .annotate(active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)))
            .order_by("-id")
        )
        return Response(
            [
                serialize_course_detail(course, request=request, spots_left=course.capacity - course.active_enrollments)
                for course in courses
            ]
        )


class TeacherCourseListAPIView(APIView):
    def get(self, request, id: int):
        teacher = TeacherProfile.objects.filter(id=id).first()
        if teacher is None:
            raise ValidationError({"detail": "Teacher not found."})
        courses = (
            Course.objects.filter(teacher=teacher)
            .select_related("teacher__user", "dance_style", "studio__city")
            .prefetch_related("schedule_rows")
            .annotate(active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)))
            .order_by("-id")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            courses = [
                course
                for course in courses
                if course_lifecycle_status(course.status, course.date_from, course.date_to) == status_filter
            ]
        return Response(
            [
                {
                    "id": course.id,
                    "name": course.name,
                    "dance_style": course.dance_style.name,
                    "level": course.level,
                    "price": course.price,
                    "date_from": course.date_from.isoformat(),
                    "date_to": course.date_to.isoformat(),
                    "status": course_lifecycle_status(course.status, course.date_from, course.date_to),
                    "studio": course.studio.name,
                }
                for course in courses
            ]
        )


class FavoriteCourseAddAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, course_id: int):
        user = require_authenticated_user(request)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO favorite_courses (user_id, course_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, course_id) DO NOTHING
                """,
                [user.id, course_id],
            )
        return Response({"detail": "ok"})

    def delete(self, request, course_id: int):
        user = require_authenticated_user(request)
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM favorite_courses WHERE user_id = %s AND course_id = %s", [user.id, course_id])
        return Response(status=status.HTTP_204_NO_CONTENT)


class FavoriteTeacherAddAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, teacher_id: int):
        user = require_authenticated_user(request)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO favorite_teachers (user_id, teacher_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, teacher_id) DO NOTHING
                """,
                [user.id, teacher_id],
            )
        return Response({"detail": "ok"})

    def delete(self, request, teacher_id: int):
        user = require_authenticated_user(request)
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM favorite_teachers WHERE user_id = %s AND teacher_id = %s", [user.id, teacher_id])
        return Response(status=status.HTTP_204_NO_CONTENT)


class EnrollmentListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = require_authenticated_user(request)
        courses = (
            Course.objects.filter(enrollments__user=user, enrollments__status=EnrollmentStatus.ACTIVE)
            .select_related("teacher__user", "dance_style", "studio__city")
            .prefetch_related("schedule_rows")
            .annotate(active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)))
            .distinct()
            .order_by("-id")
        )
        return Response(
            [
                serialize_course_detail(course, request=request, spots_left=course.capacity - course.active_enrollments)
                for course in courses
            ]
        )


class MyCourseListAPIView(EnrollmentListAPIView):
    pass


class CourseEnrollAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=EnrollmentRequestSerializer)
    def post(self, request, course_id: int):
        user = require_authenticated_user(request)
        serializer = EnrollmentRequestSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        course = Course.objects.filter(id=course_id).annotate(
            active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE))
        ).first()
        if course is None:
            raise ValidationError({"detail": "Course not found."})
        lifecycle_status = course_lifecycle_status(course.status, course.date_from, course.date_to)
        if lifecycle_status != CourseStatus.PUBLISHED:
            raise ValidationError({"detail": "Enrollment is allowed only for published courses."})
        if course.teacher.user_id == user.id:
            raise ValidationError({"detail": "Teacher cannot enroll in own course."})
        enrollment = Enrollment.objects.filter(user=user, course=course).first()
        if enrollment is None:
            if course.active_enrollments >= course.capacity:
                raise ValidationError({"detail": "No spots left."})
            enrollment = Enrollment.objects.create(
                user=user,
                course=course,
                status=EnrollmentStatus.ACTIVE,
                paid=serializer.validated_data["paid"],
            )
        else:
            enrollment.status = EnrollmentStatus.ACTIVE
            enrollment.paid = serializer.validated_data["paid"]
            enrollment.save(update_fields=["status", "paid"])
        return Response(
            {
                "id": enrollment.id,
                "user_id": enrollment.user_id,
                "course_id": enrollment.course_id,
                "status": enrollment.status,
                "enrolled_at": enrollment.enrolled_at.isoformat(),
                "paid": enrollment.paid,
            }
        )

    def delete(self, request, course_id: int):
        user = require_authenticated_user(request)
        enrollment = Enrollment.objects.filter(user=user, course_id=course_id).first()
        if enrollment:
            enrollment.status = EnrollmentStatus.CANCELLED
            enrollment.save(update_fields=["status"])
        return Response(status=status.HTTP_204_NO_CONTENT)
