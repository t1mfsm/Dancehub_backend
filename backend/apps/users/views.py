from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.courses.models import Course, Enrollment, FavoriteCourse, Lesson
from apps.courses.serializers import CourseDetailSerializer

from .models import FavoriteTeacher, TeacherProfile, TeacherReview, User, UserFlag, UserSkill
from .serializers import (
    ChangePasswordSerializer,
    CourseDashboardItemSerializer,
    CourseRecommendationSerializer,
    FavoritesResponseSerializer,
    LessonDashboardItemSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    MeUpdateSerializer,
    MyCourseSerializer,
    RegisterSerializer,
    StudentDashboardSerializer,
    SurveySubmitSerializer,
    TeacherCourseListSerializer,
    TeacherDashboardSerializer,
    TeacherDetailSerializer,
    TeacherListSerializer,
    TeacherProfileUpdateSerializer,
    TeacherReviewCreateSerializer,
    TeacherReviewSerializer,
    UserFlagSerializer,
    UserSkillSerializer,
    UserSkillWriteItemSerializer,
)


def _enrollment_queryset_with_course_detail():
    return Enrollment.objects.select_related(
        "course__teacher__user",
        "course__dance_style",
        "course__studio__city",
    ).prefetch_related(
        "course__schedule_rules",
        "course__enrollments",
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@extend_schema(tags=["Auth"], summary="Регистрация", request=RegisterSerializer)
class RegisterAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        return Response(
            {
                "user": MeSerializer(user, context={"request": request}).data,
                "token": access,
                "access": access,
                "refresh": str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Auth"], summary="Логин", request=LoginSerializer)
class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)
        return Response(
            {
                "user": MeSerializer(user, context={"request": request}).data,
                "token": access,
                "access": access,
                "refresh": str(refresh),
            }
        )


@extend_schema(tags=["Auth"], summary="Обновить access token", request=TokenRefreshSerializer)
class RefreshTokenAPIView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]


@extend_schema(tags=["Auth"], summary="Выход из системы", request=LogoutSerializer)
class LogoutAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except Exception as exc:
            raise ValidationError({"refresh": f"Не удалось завершить сессию: {exc}"}) from exc
        return Response({"detail": "Выход выполнен."}, status=status.HTTP_200_OK)


@extend_schema(tags=["Auth"], summary="Сменить пароль", request=ChangePasswordSerializer)
class ChangePasswordAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            raise ValidationError({"current_password": "Текущий пароль введён неверно."})
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Пароль обновлён."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(tags=["Users"], summary="Текущий пользователь"),
    patch=extend_schema(tags=["Users"], summary="Обновить профиль"),
    put=extend_schema(tags=["Users"], summary="Полностью обновить профиль"),
)
class MeAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_serializer_class(self):
        if self.request.method in {"PATCH", "PUT"}:
            return MeUpdateSerializer
        return MeSerializer

    def get_object(self):
        return self.request.user

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = MeUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(user, context=self.get_serializer_context()).data)

    def put(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = MeUpdateSerializer(user, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(user, context=self.get_serializer_context()).data)


@extend_schema(tags=["Users"], summary="Сохранить результаты опроса", request=SurveySubmitSerializer)
class UserSurveyAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def patch(self, request):
        serializer = SurveySubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update(request.user, serializer.validated_data)
        return Response({"detail": "OK"})


@extend_schema(tags=["Users"], summary="Обновить предпочтения пользователя", request=SurveySubmitSerializer)
class UserPreferenceAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def patch(self, request):
        serializer = SurveySubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.update(request.user, serializer.validated_data)
        return Response({"detail": "updated"})


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

@extend_schema(
    tags=["Users"],
    summary="Сохранить навыки пользователя",
    request=UserSkillWriteItemSerializer(many=True),
)
class UserSkillAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        skills = UserSkill.objects.select_related("dance_style").filter(user=request.user)
        return Response(UserSkillSerializer(skills, many=True).data)

    def put(self, request):
        serializer = UserSkillWriteItemSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        UserSkill.objects.filter(user=request.user).delete()
        from apps.courses.models import DanceStyle
        UserSkill.objects.bulk_create([
            UserSkill(
                user=request.user,
                dance_style=DanceStyle.objects.get(id=item["dance_style_id"]),
                level=item["level"],
            )
            for item in serializer.validated_data
        ])
        return Response({"detail": "skills saved"})


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

@extend_schema(tags=["Users"], summary="Установить пользовательский флаг", request=UserFlagSerializer)
class UserFlagAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        serializer = UserFlagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        UserFlag.objects.update_or_create(
            user=request.user,
            name=serializer.validated_data["name"],
            defaults={"value": serializer.validated_data["value"]},
        )
        return Response({"detail": "ok"})


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(
        tags=["Teachers"],
        summary="Список преподавателей",
        parameters=[
            OpenApiParameter(name="city", type=str),
            OpenApiParameter(name="style", type=str),
            OpenApiParameter(name="search", type=str),
        ],
    )
)
class TeacherListAPIView(generics.ListAPIView):
    serializer_class = TeacherListSerializer

    def get_queryset(self):
        queryset = TeacherProfile.objects.select_related("user__city").order_by(
            "user__last_name", "user__first_name"
        )
        city = self.request.query_params.get("city")
        style = self.request.query_params.get("style")
        search = self.request.query_params.get("search")

        if city:
            queryset = queryset.filter(user__city__name__icontains=city)
        if style:
            queryset = queryset.filter(
                Q(specializations__icontains=style)
            )
        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
            )
        return queryset.distinct()

    @extend_schema(tags=["Teachers"], summary="Создать профиль преподавателя")
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация.")
        if request.user.role != "teacher":
            raise ValidationError({"detail": "Профиль преподавателя доступен только для роли teacher."})
        teacher, _ = TeacherProfile.objects.get_or_create(user=request.user)
        return Response(TeacherDetailSerializer(teacher).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(tags=["Teachers"], summary="Детальная информация о преподавателе"),
    patch=extend_schema(tags=["Teachers"], summary="Обновить профиль преподавателя", request=TeacherProfileUpdateSerializer),
    put=extend_schema(tags=["Teachers"], summary="Полностью обновить профиль преподавателя", request=TeacherProfileUpdateSerializer),
)
class TeacherRetrieveAPIView(generics.RetrieveAPIView):
    serializer_class = TeacherDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return TeacherProfile.objects.select_related("user__city").prefetch_related("reviews__author_user", "courses__dance_style")

    def patch(self, request, *args, **kwargs):
        teacher = self._get_or_create_profile(request)
        serializer = TeacherProfileUpdateSerializer(teacher, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        teacher.refresh_from_db()
        return Response(TeacherDetailSerializer(teacher).data)

    def put(self, request, *args, **kwargs):
        teacher = self._get_or_create_profile(request)
        serializer = TeacherProfileUpdateSerializer(teacher, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        teacher.refresh_from_db()
        return Response(TeacherDetailSerializer(teacher).data)

    def _get_or_create_profile(self, request) -> TeacherProfile:
        if request.user.role != "teacher":
            raise ValidationError({"detail": "Профиль преподавателя доступен только для роли teacher."})
        teacher, _ = TeacherProfile.objects.get_or_create(user=request.user)
        return teacher


@extend_schema_view(
    get=extend_schema(
        tags=["Teachers"],
        summary="Курсы преподавателя",
        parameters=[OpenApiParameter(name="status", type=str)],
    )
)
class TeacherCourseListAPIView(generics.ListAPIView):
    serializer_class = TeacherCourseListSerializer

    def get_queryset(self):
        queryset = Course.objects.select_related("dance_style", "studio").filter(
            teacher_id=self.kwargs["id"]
        ).order_by("date_from", "id")
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = TeacherCourseListSerializer(queryset, many=True)
        return Response(serializer.data)


@extend_schema(
    tags=["Teachers"],
    summary="Оставить отзыв о преподавателе",
    request=TeacherReviewCreateSerializer,
)
class TeacherReviewCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, teacher_id: int):
        generics.get_object_or_404(TeacherProfile, id=teacher_id)
        serializer = TeacherReviewCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        review = TeacherReview.objects.create(
            author_user=request.user,
            teacher=serializer.validated_data["teacher"],
            lesson=serializer.validated_data["lesson"],
            rating=serializer.validated_data["rating"],
            text=serializer.validated_data.get("text", ""),
        )
        return Response(TeacherReviewSerializer(review).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(tags=["Users"], summary="Избранные курсы и преподаватели")
)
class FavoritesAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        fav_courses = FavoriteCourse.objects.select_related("course").filter(user=request.user)
        fav_teachers = FavoriteTeacher.objects.select_related("teacher__user").filter(user=request.user)
        return Response(
            {
                "courses": [
                    {"course_id": f.course.id, "course_name": f.course.name}
                    for f in fav_courses.order_by("-created_at")
                ],
                "teachers": [
                    {
                        "teacher_id": f.teacher.id,
                        "teacher_name": f.teacher.user.get_full_name() or f.teacher.user.email,
                    }
                    for f in fav_teachers.order_by("-created_at")
                ],
            }
        )


@extend_schema_view(
    post=extend_schema(tags=["Users"], summary="Добавить курс в избранное"),
    delete=extend_schema(tags=["Users"], summary="Удалить курс из избранного"),
)
class FavoriteCourseAddAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, course_id: int):
        course = generics.get_object_or_404(Course, id=course_id)
        _, created = FavoriteCourse.objects.get_or_create(user=request.user, course=course)
        return Response(
            {"course_id": course.id, "course_name": course.name},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, course_id: int):
        deleted, _ = FavoriteCourse.objects.filter(user=request.user, course_id=course_id).delete()
        if not deleted:
            return Response({"detail": "Курс не найден в избранном."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    post=extend_schema(tags=["Users"], summary="Добавить преподавателя в избранное"),
    delete=extend_schema(tags=["Users"], summary="Удалить преподавателя из избранного"),
)
class FavoriteTeacherAddAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, teacher_id: int):
        teacher = generics.get_object_or_404(TeacherProfile, id=teacher_id)
        _, created = FavoriteTeacher.objects.get_or_create(user=request.user, teacher=teacher)
        return Response(
            {"teacher_id": teacher.id, "teacher_name": teacher.user.get_full_name() or teacher.user.email},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, teacher_id: int):
        deleted, _ = FavoriteTeacher.objects.filter(user=request.user, teacher_id=teacher_id).delete()
        if not deleted:
            return Response({"detail": "Преподаватель не найден в избранном."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Enrollments / My courses
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(tags=["Users"], summary="Курсы по записям пользователя", responses=CourseDetailSerializer(many=True))
)
class EnrollmentListAPIView(generics.ListAPIView):
    serializer_class = CourseDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    pagination_class = None

    def get_queryset(self):
        return (
            _enrollment_queryset_with_course_detail()
            .filter(user=self.request.user)
            .exclude(status="cancelled")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        courses = [e.course for e in queryset]
        return Response(CourseDetailSerializer(courses, many=True, context={"request": request}).data)


@extend_schema_view(
    get=extend_schema(tags=["Users"], summary="Короткий список моих записей")
)
class MyCourseListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        return Enrollment.objects.filter(user=self.request.user).select_related("course").order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        return Response(MyCourseSerializer(queryset, many=True).data)


@extend_schema_view(
    get=extend_schema(
        tags=["Teachers"],
        summary="Мои курсы как преподавателя",
        parameters=[OpenApiParameter(name="status", type=str)],
        responses=CourseDetailSerializer(many=True),
    )
)
class MyTeachingCourseListAPIView(generics.ListAPIView):
    serializer_class = CourseDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    pagination_class = None

    def get_queryset(self):
        queryset = Course.objects.select_related("teacher__user", "dance_style", "studio__city").prefetch_related(
            "schedule_rules", "enrollments"
        ).filter(teacher__user=self.request.user).order_by("date_from", "id")
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset


@extend_schema_view(
    post=extend_schema(tags=["Users"], summary="Записаться на курс"),
    delete=extend_schema(tags=["Users"], summary="Отменить запись на курс"),
)
class CourseEnrollAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, course_id: int):
        course = generics.get_object_or_404(Course, id=course_id)
        enrollment, created = Enrollment.objects.get_or_create(
            user=request.user,
            course=course,
            defaults={"enrolled_at": timezone.now().date(), "status": "active", "paid": False},
        )
        if not created and enrollment.status == "cancelled":
            enrollment.status = "active"
            enrollment.cancelled_at = None
            enrollment.save(update_fields=["status", "cancelled_at", "updated_at"])
        enrollment = _enrollment_queryset_with_course_detail().get(pk=enrollment.pk)
        data = CourseDetailSerializer(enrollment.course, context={"request": request}).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request, course_id: int):
        enrollment = Enrollment.objects.filter(user=request.user, course_id=course_id).first()
        if not enrollment:
            return Response({"detail": "Запись не найдена."}, status=status.HTTP_404_NOT_FOUND)
        enrollment.status = "cancelled"
        enrollment.cancelled_at = timezone.now()
        enrollment.save(update_fields=["status", "cancelled_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(tags=["Recommendations"], summary="Рекомендованные курсы")
)
class RecommendedCourseListAPIView(generics.ListAPIView):
    serializer_class = CourseRecommendationSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        user = self.request.user
        enrolled_ids = set(
            user.enrollments.filter(status__in=["active", "pending", "completed"]).values_list("course_id", flat=True)
        )
        queryset = Course.objects.select_related("teacher__user", "dance_style", "studio__city").filter(
            status="published"
        ).exclude(id__in=enrolled_ids)
        if user.dance_level:
            queryset = queryset.filter(level=user.dance_level)
        return queryset.order_by("-teacher__rating_avg", "date_from", "id")[:10]


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(tags=["Users"], summary="Дашборд студента")
)
class StudentDashboardAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        today = timezone.localdate()

        enrolled_course_ids = Enrollment.objects.filter(
            user=user, status__in=["active", "pending"]
        ).values_list("course_id", flat=True)

        upcoming_lessons = (
            Lesson.objects.select_related("course__dance_style", "course__teacher__user")
            .filter(course_id__in=enrolled_course_ids, lesson_date__gte=today, status="scheduled")
            .order_by("lesson_date", "time_from")[:5]
        )

        return Response(
            {
                "enrolled_courses_count": len(enrolled_course_ids),
                "upcoming_lessons": LessonDashboardItemSerializer(upcoming_lessons, many=True).data,
                "favorite_courses_count": FavoriteCourse.objects.filter(user=user).count(),
            }
        )


@extend_schema_view(
    get=extend_schema(tags=["Teachers"], summary="Дашборд преподавателя")
)
class TeacherDashboardAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        today = timezone.localdate()

        teacher_profile = getattr(user, "teacher_profile", None)
        if not teacher_profile:
            return Response({"detail": "Профиль преподавателя не найден."}, status=status.HTTP_404_NOT_FOUND)

        active_courses = Course.objects.filter(
            teacher=teacher_profile,
            status__in=["published", "active"],
            date_to__gte=today,
        )
        active_course_ids = list(active_courses.values_list("id", flat=True))

        total_students = Enrollment.objects.filter(
            course_id__in=active_course_ids, status__in=["active", "pending"]
        ).values("user_id").distinct().count()

        upcoming_lessons = (
            Lesson.objects.select_related("course__dance_style")
            .filter(course_id__in=active_course_ids, lesson_date__gte=today, status="scheduled")
            .order_by("lesson_date", "time_from")[:5]
        )

        return Response(
            {
                "active_courses_count": active_courses.count(),
                "total_students": total_students,
                "upcoming_lessons": LessonDashboardItemSerializer(upcoming_lessons, many=True).data,
            }
        )
