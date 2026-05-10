from django.contrib.auth.hashers import check_password
from django.db import connection
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.choices import CourseStatus, DanceLevel, EnrollmentStatus, PaymentMethod, PaymentOrderStatus, UserRole
from apps.common.files import save_uploaded_file
from apps.common.utils import build_full_name, course_lifecycle_status, first_lesson_start_at, has_hours_before
from apps.courses.models import Course, DanceStyle, Enrollment, FavoriteCourse, PaymentOrder
from apps.courses.payment_receipts import send_payment_receipt_email
from apps.courses.payment_utils import (
    PAYMENT_ORDER_TTL,
    build_spots_left_map,
    cancel_pending_payment_orders,
    expire_payment_order_if_needed,
    expire_stale_payment_orders_for_enrollment,
    generate_payment_order_number,
    generate_payment_public_token,
    get_live_pending_payment_order,
)
from apps.courses.serializers import (
    EnrollmentRequestSerializer,
    PaymentCardPaySerializer,
    PaymentSbpPaySerializer,
    serialize_course_detail,
    serialize_payment_order,
)
from apps.recommendations.services import refresh_recommendations_for_user
from apps.users.models import Notification, TeacherProfile, User
from config.authentication import build_tokens_for_user, decode_token

from .notifications import (
    create_student_enrollment_notification,
    create_student_unenrollment_notification,
    create_teacher_enrollment_notification,
    create_teacher_unenrollment_notification,
)
from .serializers import (
    LoginSerializer,
    NotificationReadSerializer,
    LogoutSerializer,
    RefreshSerializer,
    RegisterSerializer,
    TeacherProfileUpdateSerializer,
    UserFlagSerializer,
    UserPreferencesSerializer,
    UserSkillItemSerializer,
    UserUpdateSerializer,
    serialize_notification,
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


def _build_course_viewer_context(course: Course, user: User | None) -> dict:
    if user is None or not getattr(user, "is_authenticated", False):
        return {
            "viewer_enrollment_status": None,
            "viewer_paid": False,
            "viewer_payment_order": None,
        }

    enrollment = Enrollment.objects.filter(user=user, course=course).first()
    if enrollment is None:
        return {
            "viewer_enrollment_status": None,
            "viewer_paid": False,
            "viewer_payment_order": None,
        }

    expire_stale_payment_orders_for_enrollment(enrollment)
    enrollment.refresh_from_db()

    live_order = get_live_pending_payment_order(enrollment)
    if enrollment.status == EnrollmentStatus.CANCELLED and live_order is None:
        return {
            "viewer_enrollment_status": None,
            "viewer_paid": False,
            "viewer_payment_order": None,
        }

    return {
        "viewer_enrollment_status": enrollment.status,
        "viewer_paid": enrollment.paid,
        "viewer_payment_order": serialize_payment_order(live_order) if live_order is not None else None,
    }


def _serialize_payment_order_response(order: PaymentOrder) -> dict:
    order = expire_payment_order_if_needed(order)
    return {
        "payment_order": serialize_payment_order(order),
        "enrollment_status": order.enrollment.status,
        "paid": order.enrollment.paid,
    }


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
        for field in ["username", "first_name", "middle_name", "last_name", "survey_completed", "dance_level", "role"]:
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
        refresh_recommendations_for_user(user)
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
        refresh_recommendations_for_user(user)
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
        courses = list(
            Course.objects.filter(teacher=teacher)
            .select_related("teacher__user", "dance_style", "studio__city")
            .prefetch_related("schedule_rows")
            .annotate(active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)))
            .order_by("-id")
        )
        spots_left_map = build_spots_left_map(courses)
        return Response(
            [
                serialize_course_detail(course, request=request, spots_left=spots_left_map.get(course.id, course.capacity))
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
        refresh_recommendations_for_user(user)
        return Response({"detail": "ok"})

    def delete(self, request, course_id: int):
        user = require_authenticated_user(request)
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM favorite_courses WHERE user_id = %s AND course_id = %s", [user.id, course_id])
        refresh_recommendations_for_user(user)
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
        refresh_recommendations_for_user(user)
        return Response({"detail": "ok"})

    def delete(self, request, teacher_id: int):
        user = require_authenticated_user(request)
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM favorite_teachers WHERE user_id = %s AND teacher_id = %s", [user.id, teacher_id])
        refresh_recommendations_for_user(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EnrollmentListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = require_authenticated_user(request)
        courses = list(
            Course.objects.filter(enrollments__user=user, enrollments__status=EnrollmentStatus.ACTIVE)
            .select_related("teacher__user", "dance_style", "studio__city")
            .prefetch_related("schedule_rows")
            .annotate(active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)))
            .distinct()
            .order_by("-id")
        )
        spots_left_map = build_spots_left_map(courses)
        return Response(
            [
                serialize_course_detail(course, request=request, spots_left=spots_left_map.get(course.id, course.capacity))
                for course in courses
            ]
        )


class MyCourseListAPIView(EnrollmentListAPIView):
    pass


class NotificationListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = require_authenticated_user(request)
        notifications = Notification.objects.filter(user=user).order_by("-created_at", "-id")
        return Response([serialize_notification(notification) for notification in notifications])


class NotificationReadAllAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None)
    def post(self, request):
        user = require_authenticated_user(request)
        marked = Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=timezone.now())
        return Response({"marked": marked})


class NotificationDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=NotificationReadSerializer)
    def patch(self, request, id: int):
        user = require_authenticated_user(request)
        notification = Notification.objects.filter(id=id, user=user).first()
        if notification is None:
            raise ValidationError({"detail": "Notification not found."})

        serializer = NotificationReadSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data["read"] and notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])

        return Response(serialize_notification(notification))

    def delete(self, request, id: int):
        user = require_authenticated_user(request)
        notification = Notification.objects.filter(id=id, user=user).first()
        if notification is None:
            raise ValidationError({"detail": "Notification not found."})

        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CourseEnrollAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=EnrollmentRequestSerializer)
    def post(self, request, course_id: int):
        user = require_authenticated_user(request)
        serializer = EnrollmentRequestSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            course = (
                Course.objects.select_related("teacher__user")
                .prefetch_related("lessons")
                .annotate(active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)))
                .filter(id=course_id)
                .first()
            )
            if course is None:
                raise ValidationError({"detail": "Course not found."})

            lifecycle_status = course_lifecycle_status(course.status, course.date_from, course.date_to)
            if lifecycle_status != CourseStatus.PUBLISHED:
                raise ValidationError({"detail": "Enrollment is allowed only for published courses."})

            first_lesson_at = first_lesson_start_at(course.lessons.all())
            if not has_hours_before(first_lesson_at, hours=24):
                raise ValidationError({"detail": "Enrollment closes 24 hours before the first lesson."})

            if course.teacher.user_id == user.id:
                raise ValidationError({"detail": "Teacher cannot enroll in own course."})

            enrollment = Enrollment.objects.filter(user=user, course=course).first()
            if enrollment is not None:
                expire_stale_payment_orders_for_enrollment(enrollment)
                enrollment.refresh_from_db()

                if enrollment.status == EnrollmentStatus.ACTIVE and enrollment.paid:
                    raise ValidationError({"detail": "User already paid for this course."})

                live_order = get_live_pending_payment_order(enrollment)
                if live_order is not None:
                    return Response(_serialize_payment_order_response(live_order))

            spots_left = build_spots_left_map([course]).get(course.id, course.capacity)
            if spots_left <= 0:
                raise ValidationError({"detail": "No spots left."})

            if enrollment is None:
                enrollment = Enrollment.objects.create(
                    user=user,
                    course=course,
                    status=EnrollmentStatus.PENDING,
                    paid=False,
                )
            else:
                enrollment.status = EnrollmentStatus.PENDING
                enrollment.paid = False
                enrollment.enrolled_at = timezone.now()
                enrollment.save(update_fields=["status", "paid", "enrolled_at"])

            order = PaymentOrder.objects.create(
                enrollment=enrollment,
                order_number=generate_payment_order_number(),
                public_token=generate_payment_public_token(),
                amount=course.price,
                status=PaymentOrderStatus.PENDING,
                expires_at=timezone.now() + PAYMENT_ORDER_TTL,
                created_at=timezone.now(),
                updated_at=timezone.now(),
            )

        refresh_recommendations_for_user(user)
        return Response(_serialize_payment_order_response(order), status=status.HTTP_201_CREATED)

    def delete(self, request, course_id: int):
        user = require_authenticated_user(request)
        enrollment = Enrollment.objects.filter(user=user, course_id=course_id).first()
        course = Course.objects.filter(id=course_id).first()
        if course is not None:
            first_lesson_at = first_lesson_start_at(course.lessons.all())
            if not has_hours_before(first_lesson_at, hours=24):
                raise ValidationError({"detail": "Enrollment cancellation closes 24 hours before the first lesson."})
        if enrollment and enrollment.status != EnrollmentStatus.CANCELLED:
            was_active_paid = enrollment.status == EnrollmentStatus.ACTIVE and enrollment.paid
            cancel_pending_payment_orders(enrollment)
            enrollment.status = EnrollmentStatus.CANCELLED
            enrollment.save(update_fields=["status"])
            course = Course.objects.select_related("teacher__user").filter(id=enrollment.course_id).first()
            if was_active_paid and course is not None:
                create_teacher_unenrollment_notification(course=course, student=user)
                create_student_unenrollment_notification(course=course, student=user)
            refresh_recommendations_for_user(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PaymentOrderDetailAPIView(APIView):
    authentication_classes = []

    def get(self, _request, token: str):
        order = (
            PaymentOrder.objects.select_related("enrollment__course", "enrollment__user")
            .filter(public_token=token)
            .first()
        )
        if order is None:
            raise ValidationError({"detail": "Payment order not found."})

        order = expire_payment_order_if_needed(order)
        return Response(_serialize_payment_order_response(order))


class PaymentOrderPayCardAPIView(APIView):
    authentication_classes = []

    @extend_schema(request=PaymentCardPaySerializer)
    def post(self, request, token: str):
        serializer = PaymentCardPaySerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            order = (
                PaymentOrder.objects.select_related("enrollment__course__teacher__user", "enrollment__user")
                .filter(public_token=token)
                .first()
            )
            if order is None:
                raise ValidationError({"detail": "Payment order not found."})

            order = expire_payment_order_if_needed(order)
            if order.status == PaymentOrderStatus.EXPIRED:
                raise ValidationError({"detail": "Payment order expired."})
            if order.status == PaymentOrderStatus.CANCELLED:
                raise ValidationError({"detail": "Payment order was cancelled."})
            if order.status == PaymentOrderStatus.PAID:
                return Response(_serialize_payment_order_response(order))

            enrollment = order.enrollment
            enrollment.status = EnrollmentStatus.ACTIVE
            enrollment.paid = True
            enrollment.save(update_fields=["status", "paid"])

            order.receipt_email = serializer.validated_data["receipt_email"]
            order.payment_method = PaymentMethod.CARD
            order.status = PaymentOrderStatus.PAID
            order.paid_at = timezone.now()
            order.updated_at = timezone.now()
            order.save(update_fields=["receipt_email", "payment_method", "status", "paid_at", "updated_at"])

            course = order.enrollment.course
            student = order.enrollment.user
            create_teacher_enrollment_notification(course=course, student=student)
            create_student_enrollment_notification(course=course, student=student)

        refresh_recommendations_for_user(student)
        send_payment_receipt_email(order)
        return Response(_serialize_payment_order_response(order))


class PaymentOrderPaySbpAPIView(APIView):
    authentication_classes = []

    @extend_schema(request=PaymentSbpPaySerializer)
    def post(self, request, token: str):
        serializer = PaymentSbpPaySerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            order = (
                PaymentOrder.objects.select_related("enrollment__course__teacher__user", "enrollment__user")
                .filter(public_token=token)
                .first()
            )
            if order is None:
                raise ValidationError({"detail": "Payment order not found."})

            order = expire_payment_order_if_needed(order)
            if order.status == PaymentOrderStatus.EXPIRED:
                raise ValidationError({"detail": "Payment order expired."})
            if order.status == PaymentOrderStatus.CANCELLED:
                raise ValidationError({"detail": "Payment order was cancelled."})
            if order.status == PaymentOrderStatus.PAID:
                return Response(_serialize_payment_order_response(order))

            enrollment = order.enrollment
            enrollment.status = EnrollmentStatus.ACTIVE
            enrollment.paid = True
            enrollment.save(update_fields=["status", "paid"])

            order.receipt_email = serializer.validated_data["receipt_email"]
            order.payment_method = PaymentMethod.SBP
            order.status = PaymentOrderStatus.PAID
            order.paid_at = timezone.now()
            order.updated_at = timezone.now()
            order.save(update_fields=["receipt_email", "payment_method", "status", "paid_at", "updated_at"])

            course = order.enrollment.course
            student = order.enrollment.user
            create_teacher_enrollment_notification(course=course, student=student)
            create_student_enrollment_notification(course=course, student=student)

        refresh_recommendations_for_user(student)
        send_payment_receipt_email(order)
        return Response(_serialize_payment_order_response(order))
