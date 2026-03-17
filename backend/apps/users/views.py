from django.db.models import Avg, Count, Q
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

from apps.courses.models import Attendance, Course, Enrollment, FavoriteCourse, Lesson

from .models import FavoriteTeacher, TeacherProfile, TeacherReview, UserPreference, UserSkill
from .serializers import (
    ChangePasswordSerializer,
    CourseDashboardItemSerializer,
    CourseRecommendationSerializer,
    LessonDashboardItemSerializer,
    EnrollmentSerializer,
    FavoriteCourseSerializer,
    FavoriteTeacherSerializer,
    FavoritesResponseSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    MeUpdateSerializer,
    MyCourseSerializer,
    RegisterSerializer,
    StudentDashboardSerializer,
    TeacherDetailSerializer,
    TeacherDashboardSerializer,
    TeacherReviewCreateSerializer,
    TeacherReviewSerializer,
    TeacherCourseListSerializer,
    TeacherListSerializer,
    TeachingCourseSerializer,
    UserPreferenceSerializer,
    UserSkillSerializer,
    UserSkillWriteItemSerializer,
)


@extend_schema_view(
    get=extend_schema(
        tags=["Teachers"],
        summary="Список преподавателей",
        description="Возвращает список преподавателей с базовой фильтрацией.",
        parameters=[
            OpenApiParameter(name="city", description="Название города", type=str),
            OpenApiParameter(name="style", description="Slug или название стиля", type=str),
            OpenApiParameter(name="search", description="Имя, фамилия или email", type=str),
        ],
    )
)
class TeacherListAPIView(generics.ListAPIView):
    serializer_class = TeacherListSerializer

    def get_queryset(self):
        queryset = (
            TeacherProfile.objects.select_related("user__city")
            .prefetch_related("specializations__dance_style")
            .all()
            .order_by("user__last_name", "user__first_name")
        )

        city = self.request.query_params.get("city")
        style = self.request.query_params.get("style")
        search = self.request.query_params.get("search")

        if city:
            queryset = queryset.filter(user__city__name__icontains=city)

        if style:
            queryset = queryset.filter(
                Q(specializations__dance_style__slug__icontains=style)
                | Q(specializations__dance_style__name__icontains=style)
            )

        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
            )

        return queryset.distinct()


@extend_schema_view(
    get=extend_schema(
        tags=["Teachers"],
        summary="Детальная информация о преподавателе",
        description="Возвращает карточку преподавателя с курсами, достижениями и отзывами.",
    )
)
class TeacherRetrieveAPIView(generics.RetrieveAPIView):
    serializer_class = TeacherDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return TeacherProfile.objects.select_related("user__city").prefetch_related(
            "specializations__dance_style",
            "achievements",
            "reviews__author_user",
            "courses__dance_style",
            "courses__studio",
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Users"],
        summary="Текущий пользователь",
        description="Возвращает профиль текущего авторизованного пользователя.",
    )
)
class MeAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_serializer_class(self):
        if self.request.method in {"PATCH", "PUT"}:
            return MeUpdateSerializer
        return MeSerializer

    @extend_schema(
        tags=["Users"],
        summary="Обновить текущего пользователя",
        description="Частично обновляет профиль текущего авторизованного пользователя.",
        request=MeUpdateSerializer,
        responses=MeSerializer,
    )
    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(user, context=self.get_serializer_context()).data)

    @extend_schema(
        tags=["Users"],
        summary="Полностью обновить текущего пользователя",
        description="Полностью обновляет профиль текущего авторизованного пользователя.",
        request=MeUpdateSerializer,
        responses=MeSerializer,
    )
    def put(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(user, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(user, context=self.get_serializer_context()).data)

    def get_object(self):
        return self.request.user


@extend_schema_view(
    get=extend_schema(
        tags=["Users"],
        summary="Избранные курсы пользователя",
        description="Возвращает избранные курсы текущего пользователя.",
        responses=FavoritesResponseSerializer,
    )
)
class FavoritesAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        favorite_courses = (
            FavoriteCourse.objects.select_related("course__teacher__user")
            .filter(user=request.user)
            .order_by("-created_at")
        )
        data = {
            "courses": FavoriteCourseSerializer(favorite_courses, many=True).data,
        }
        return Response(data)


@extend_schema_view(
    post=extend_schema(
        tags=["Users"],
        summary="Добавить курс в избранное",
        description="Добавляет курс в избранное текущего пользователя.",
    ),
    delete=extend_schema(
        tags=["Users"],
        summary="Удалить курс из избранного",
        description="Удаляет курс из избранного текущего пользователя.",
    ),
)
class FavoriteCourseAddAPIView(APIView):
    serializer_class = FavoriteCourseSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, course_id: int):
        course = generics.get_object_or_404(Course, id=course_id)
        favorite, created = FavoriteCourse.objects.get_or_create(user=request.user, course=course)
        serializer = FavoriteCourseSerializer(favorite)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, course_id: int):
        deleted, _ = FavoriteCourse.objects.filter(user=request.user, course_id=course_id).delete()
        if not deleted:
            return Response({"detail": "Курс не найден в избранном."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    post=extend_schema(
        tags=["Users"],
        summary="Добавить преподавателя в избранное",
        description="Добавляет преподавателя в избранное текущего пользователя.",
    ),
    delete=extend_schema(
        tags=["Users"],
        summary="Удалить преподавателя из избранного",
        description="Удаляет преподавателя из избранного текущего пользователя.",
    ),
)
class FavoriteTeacherAddAPIView(APIView):
    serializer_class = FavoriteTeacherSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, teacher_id: int):
        teacher = generics.get_object_or_404(TeacherProfile, id=teacher_id)
        favorite, created = FavoriteTeacher.objects.get_or_create(user=request.user, teacher=teacher)
        serializer = FavoriteTeacherSerializer(favorite)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, teacher_id: int):
        deleted, _ = FavoriteTeacher.objects.filter(user=request.user, teacher_id=teacher_id).delete()
        if not deleted:
            return Response(
                {"detail": "Преподаватель не найден в избранном."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    get=extend_schema(
        tags=["Users"],
        summary="Записи пользователя на курсы",
        description="Возвращает записи текущего пользователя на курсы.",
    )
)
class EnrollmentListAPIView(generics.ListAPIView):
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        return (
            Enrollment.objects.select_related("course")
            .filter(user=self.request.user)
            .order_by("-created_at")
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Users"],
        summary="Мои курсы",
        description="Возвращает курсы текущего пользователя вместе со статусом записи.",
        parameters=[
            OpenApiParameter(name="status", description="Статус записи: active/pending/cancelled/completed", type=str),
        ],
    )
)
class MyCourseListAPIView(generics.ListAPIView):
    serializer_class = MyCourseSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        queryset = (
            Enrollment.objects.select_related(
                "course__teacher__user",
                "course__dance_style",
                "course__studio__city",
            )
            .filter(user=self.request.user)
            .order_by("-created_at")
        )
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset


@extend_schema_view(
    get=extend_schema(
        tags=["Teachers"],
        summary="Мои курсы как преподавателя",
        description="Возвращает курсы, которые ведет текущий преподаватель.",
        parameters=[
            OpenApiParameter(name="status", description="Статус курса", type=str),
        ],
    )
)
class MyTeachingCourseListAPIView(generics.ListAPIView):
    serializer_class = TeachingCourseSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        queryset = (
            Course.objects.select_related("dance_style", "studio")
            .filter(teacher__user=self.request.user)
            .annotate(
                students_count=Count(
                    "enrollments",
                    filter=Q(enrollments__status__in=["active", "pending", "completed"]),
                    distinct=True,
                ),
                lessons_count=Count("lessons", distinct=True),
            )
            .order_by("date_from", "id")
        )
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset


@extend_schema_view(
    get=extend_schema(
        tags=["Teachers"],
        summary="Курсы преподавателя",
        description="Возвращает список курсов выбранного преподавателя.",
        parameters=[
            OpenApiParameter(name="status", description="Статус курса", type=str),
        ],
    )
)
class TeacherCourseListAPIView(generics.ListAPIView):
    serializer_class = TeacherCourseListSerializer

    def get_queryset(self):
        queryset = (
            Course.objects.select_related("dance_style", "studio")
            .filter(teacher_id=self.kwargs["id"])
            .order_by("date_from", "id")
        )
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset


@extend_schema_view(
    get=extend_schema(
        tags=["Users"],
        summary="Предпочтения пользователя",
        description="Возвращает предпочтения текущего пользователя для опроса и рекомендаций.",
        responses=UserPreferenceSerializer,
    ),
    patch=extend_schema(
        tags=["Users"],
        summary="Обновить предпочтения пользователя",
        description="Создает или обновляет предпочтения текущего пользователя.",
        request=UserPreferenceSerializer,
        responses=UserPreferenceSerializer,
    ),
)
class UserPreferenceAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_object(self):
        preference, _ = UserPreference.objects.get_or_create(user=self.request.user)
        return preference

    def get(self, request):
        serializer = UserPreferenceSerializer(self.get_object())
        return Response(serializer.data)

    def patch(self, request):
        preference = self.get_object()
        serializer = UserPreferenceSerializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserPreferenceSerializer(preference).data)


@extend_schema_view(
    get=extend_schema(
        tags=["Users"],
        summary="Навыки пользователя",
        description="Возвращает навыки текущего пользователя.",
        responses=UserSkillSerializer(many=True),
    ),
    put=extend_schema(
        tags=["Users"],
        summary="Полностью заменить навыки пользователя",
        description="Полностью заменяет список навыков текущего пользователя.",
        request=UserSkillWriteItemSerializer(many=True),
        responses=UserSkillSerializer(many=True),
    ),
    patch=extend_schema(
        tags=["Users"],
        summary="Частично обновить навыки пользователя",
        description="Добавляет или обновляет навыки текущего пользователя.",
        request=UserSkillWriteItemSerializer(many=True),
        responses=UserSkillSerializer(many=True),
    ),
)
class UserSkillAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        skills = request.user.skills.select_related("dance_style").all().order_by("dance_style__name")
        return Response(UserSkillSerializer(skills, many=True).data)

    def put(self, request):
        serializer = UserSkillWriteItemSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        request.user.skills.all().delete()
        skills = [
            UserSkill(user=request.user, **item)
            for item in serializer.validated_data
        ]
        UserSkill.objects.bulk_create(skills)
        fresh = request.user.skills.select_related("dance_style").all().order_by("dance_style__name")
        return Response(UserSkillSerializer(fresh, many=True).data)

    def patch(self, request):
        serializer = UserSkillWriteItemSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        for item in serializer.validated_data:
            UserSkill.objects.update_or_create(
                user=request.user,
                dance_style=item["dance_style"],
                defaults={"level": item["level"]},
            )
        fresh = request.user.skills.select_related("dance_style").all().order_by("dance_style__name")
        return Response(UserSkillSerializer(fresh, many=True).data)


@extend_schema_view(
    post=extend_schema(
        tags=["Users"],
        summary="Записаться на курс",
        description="Создает запись текущего пользователя на курс.",
    ),
    delete=extend_schema(
        tags=["Users"],
        summary="Отменить запись на курс",
        description="Помечает запись текущего пользователя как отмененную.",
    ),
)
class CourseEnrollAPIView(APIView):
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, course_id: int):
        course = generics.get_object_or_404(Course, id=course_id)
        enrollment, created = Enrollment.objects.get_or_create(
            user=request.user,
            course=course,
            defaults={
                "enrolled_at": timezone.now().date(),
                "status": "active",
                "paid": False,
            },
        )
        if not created and enrollment.status == "cancelled":
            enrollment.status = "active"
            enrollment.cancelled_at = None
            enrollment.save(update_fields=["status", "cancelled_at", "updated_at"])

        serializer = EnrollmentSerializer(enrollment)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, course_id: int):
        enrollment = Enrollment.objects.filter(user=request.user, course_id=course_id).first()
        if not enrollment:
            return Response({"detail": "Запись не найдена."}, status=status.HTTP_404_NOT_FOUND)

        enrollment.status = "cancelled"
        enrollment.cancelled_at = timezone.now()
        enrollment.save(update_fields=["status", "cancelled_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["Auth"],
    summary="Регистрация",
    description="Создает нового пользователя и сразу возвращает JWT токены.",
    request=RegisterSerializer,
)
class RegisterAPIView(APIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": MeSerializer(user).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Auth"],
    summary="Логин",
    description="Авторизует пользователя и возвращает JWT токены.",
    request=LoginSerializer,
)
class LoginAPIView(APIView):
    serializer_class = LoginSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": MeSerializer(user).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }
        )


@extend_schema(
    tags=["Auth"],
    summary="Обновить access token",
    description="Принимает refresh token и возвращает новый access token.",
    request=TokenRefreshSerializer,
)
class RefreshTokenAPIView(TokenRefreshView):
    serializer_class = TokenRefreshSerializer
    permission_classes = [permissions.AllowAny]


@extend_schema(
    tags=["Auth"],
    summary="Выход из системы",
    description="Добавляет refresh token в blacklist и завершает сессию пользователя.",
    request=LogoutSerializer,
)
class LogoutAPIView(APIView):
    serializer_class = LogoutSerializer
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


@extend_schema(
    tags=["Auth"],
    summary="Сменить пароль",
    description="Меняет пароль текущего пользователя.",
    request=ChangePasswordSerializer,
)
class ChangePasswordAPIView(APIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["current_password"]):
            raise ValidationError({"current_password": "Текущий пароль введен неверно."})
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Пароль обновлен."}, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        tags=["Dashboard"],
        summary="Дашборд ученика",
        description="Возвращает краткую сводку по активным курсам, избранному и ближайшим занятиям ученика.",
        responses=StudentDashboardSerializer,
    )
)
class StudentDashboardAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        active_enrollments = Enrollment.objects.filter(
            user=request.user,
            status__in=["active", "pending", "completed"],
        )
        active_course_ids = active_enrollments.values_list("course_id", flat=True)
        nearest_lessons = Lesson.objects.filter(
            course_id__in=active_course_ids,
            lesson_date__gte=timezone.localdate(),
        ).select_related("course").order_by("lesson_date", "time_from")[:5]
        data = {
            "active_courses_count": active_enrollments.filter(status="active").count(),
            "favorites_count": request.user.favorite_courses.count(),
            "upcoming_lessons_count": Lesson.objects.filter(course_id__in=active_course_ids, lesson_date__gte=timezone.localdate()).count(),
            "nearest_lessons": LessonDashboardItemSerializer(nearest_lessons, many=True).data,
        }
        return Response(data)


@extend_schema_view(
    get=extend_schema(
        tags=["Dashboard"],
        summary="Дашборд преподавателя",
        description="Возвращает сводку по курсам, ученикам, ближайшим занятиям и посещаемости преподавателя.",
        responses=TeacherDashboardSerializer,
    )
)
class TeacherDashboardAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        if not hasattr(request.user, "teacher_profile"):
            raise PermissionDenied("Дашборд преподавателя доступен только преподавателю.")

        courses = Course.objects.filter(teacher__user=request.user).annotate(
            students_count=Count(
                "enrollments",
                filter=Q(enrollments__status__in=["active", "pending", "completed"]),
                distinct=True,
            ),
            lessons_count=Count("lessons", distinct=True),
        ).order_by("date_from", "id")

        course_ids = courses.values_list("id", flat=True)
        nearest_lessons = Lesson.objects.filter(
            course_id__in=course_ids,
            lesson_date__gte=timezone.localdate(),
        ).select_related("course").order_by("lesson_date", "time_from")[:5]

        attendance_total = Attendance.objects.filter(lesson__course_id__in=course_ids).count()
        attendance_present = Attendance.objects.filter(
            lesson__course_id__in=course_ids,
            status="present",
        ).count()
        attendance_rate = round((attendance_present / attendance_total) * 100, 2) if attendance_total else 0.0

        data = {
            "courses_count": courses.count(),
            "students_count": Enrollment.objects.filter(
                course_id__in=course_ids,
                status__in=["active", "pending", "completed"],
            ).values("user_id").distinct().count(),
            "upcoming_lessons_count": Lesson.objects.filter(course_id__in=course_ids, lesson_date__gte=timezone.localdate()).count(),
            "attendance_rate": attendance_rate,
            "courses": CourseDashboardItemSerializer(courses[:5], many=True).data,
            "nearest_lessons": LessonDashboardItemSerializer(nearest_lessons, many=True).data,
        }
        return Response(data)


@extend_schema_view(
    get=extend_schema(
        tags=["Recommendations"],
        summary="Рекомендованные курсы",
        description="Возвращает рекомендованные курсы на основе предпочтений и навыков пользователя.",
        responses=CourseRecommendationSerializer(many=True),
    )
)
class RecommendedCourseListAPIView(generics.ListAPIView):
    serializer_class = CourseRecommendationSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    LEVEL_ORDER = {
        "beginner": 1,
        "intermediate": 2,
        "advanced": 3,
        "any": 0,
    }

    def _score_level(self, preference_level: str | None, course_level: str) -> tuple[int, str | None]:
        if not preference_level:
            return 0, None
        if course_level == "any":
            return 2, "подходит для любого уровня"
        if preference_level == course_level:
            return 5, "точно совпадает по уровню"

        user_rank = self.LEVEL_ORDER.get(preference_level, 0)
        course_rank = self.LEVEL_ORDER.get(course_level, 0)
        if user_rank and course_rank and abs(user_rank - course_rank) == 1:
            return 2, "близкий уровень подготовки"
        return 0, None

    def _score_price(self, preference, course: Course) -> tuple[int, str | None]:
        if not preference:
            return 0, None
        if preference.price_from and preference.price_to:
            if preference.price_from <= course.price <= preference.price_to:
                return 4, "входит в желаемый бюджет"
            return 0, None
        if preference.price_to and course.price <= preference.price_to:
            return 2, "ниже максимального бюджета"
        if preference.price_from and course.price >= preference.price_from:
            return 1, "соответствует минимальному бюджету"
        return 0, None

    def _score_schedule(self, preference, course: Course) -> tuple[int, list[str]]:
        if not preference:
            return 0, []

        score = 0
        reasons: list[str] = []
        rules = list(course.schedule_rules.all())

        preferred_weekdays = set(preference.preferred_weekdays.values_list("weekday", flat=True))
        if preferred_weekdays and any(rule.weekday in preferred_weekdays for rule in rules):
            score += 3
            reasons.append("есть удобные дни недели")

        if preference.preferred_time_from or preference.preferred_time_to:
            for rule in rules:
                start_ok = (
                    preference.preferred_time_from is None
                    or rule.time_from >= preference.preferred_time_from
                )
                end_ok = (
                    preference.preferred_time_to is None
                    or rule.time_to <= preference.preferred_time_to
                )
                if start_ok and end_ok:
                    score += 3
                    reasons.append("подходит по времени занятий")
                    break

        return score, reasons

    def get_queryset(self):
        user = self.request.user
        try:
            preference = user.preferences
        except UserPreference.DoesNotExist:
            preference = None
        skill_style_ids = set(user.skills.values_list("dance_style_id", flat=True))
        preferred_style_ids = (
            set(preference.preferred_dance_styles.values_list("dance_style_id", flat=True))
            if preference else set()
        )
        enrolled_course_ids = set(
            user.enrollments.filter(status__in=["active", "pending", "completed"]).values_list("course_id", flat=True)
        )
        favorite_course_ids = set(user.favorite_courses.values_list("course_id", flat=True))

        queryset = Course.objects.select_related(
            "teacher__user",
            "dance_style",
            "studio__city",
        ).prefetch_related(
            "schedule_rules",
        ).filter(status="published").exclude(id__in=enrolled_course_ids)

        city_name = self.request.query_params.get("city")
        if city_name:
            queryset = queryset.filter(studio__city__name__icontains=city_name)
        elif preference and preference.city_id:
            queryset = queryset.filter(Q(studio__city_id=preference.city_id) | Q(studio__isnull=True))

        scored = []
        for course in queryset:
            score = 0
            reasons: list[str] = []

            if course.dance_style_id in preferred_style_ids:
                score += 6
                reasons.append("совпадает с предпочтительным стилем")
            if course.dance_style_id in skill_style_ids:
                score += 3
                reasons.append("основан на текущих навыках")
            if course.id in favorite_course_ids:
                score += 2
                reasons.append("похож на курс из избранного")

            level_score, level_reason = self._score_level(preference.level if preference else None, course.level)
            score += level_score
            if level_reason:
                reasons.append(level_reason)

            if preference and preference.city_id and course.studio and course.studio.city_id == preference.city_id:
                score += 4
                reasons.append("проходит в выбранном городе")

            price_score, price_reason = self._score_price(preference, course)
            score += price_score
            if price_reason:
                reasons.append(price_reason)

            schedule_score, schedule_reasons = self._score_schedule(preference, course)
            score += schedule_score
            reasons.extend(schedule_reasons)

            if course.teacher.rating_avg >= 4.7:
                score += 2
                reasons.append("высокий рейтинг преподавателя")
            elif course.teacher.rating_avg >= 4.3:
                score += 1
                reasons.append("хороший рейтинг преподавателя")

            if course.teacher.rating_count >= 50:
                score += 1
                reasons.append("преподаватель с подтвержденным опытом по отзывам")

            if preference and not preferred_style_ids and not skill_style_ids and preference.city_id and course.studio and course.studio.city_id == preference.city_id:
                score += 1

            if score > 0:
                course.recommendation_score = score
                course.recommendation_reason = ", ".join(reasons)
                course.recommendation_reasons = reasons
                scored.append(course)

        if not scored:
            fallback = list(
                queryset.order_by("-teacher__rating_avg", "date_from", "id")[:10]
            )
            for course in fallback:
                course.recommendation_score = 1
                course.recommendation_reasons = ["популярный опубликованный курс"]
                course.recommendation_reason = "популярный опубликованный курс"
            return fallback

        scored.sort(
            key=lambda item: (
                -item.recommendation_score,
                -float(item.teacher.rating_avg),
                item.date_from,
                item.id,
            )
        )
        return scored[:10]


@extend_schema_view(
    get=extend_schema(
        tags=["Reviews"],
        summary="Список отзывов о преподавателе",
        description="Возвращает все отзывы выбранного преподавателя.",
        responses=TeacherReviewSerializer(many=True),
    ),
    post=extend_schema(
        tags=["Reviews"],
        summary="Оставить отзыв о преподавателе",
        description="Создает или обновляет отзыв текущего пользователя о преподавателе.",
        request=TeacherReviewCreateSerializer,
    ),
)
class TeacherReviewCreateAPIView(APIView):
    serializer_class = TeacherReviewCreateSerializer
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get(self, request, teacher_id: int):
        reviews = TeacherReview.objects.select_related("author_user").filter(teacher_id=teacher_id).order_by("-created_at")
        return Response(TeacherReviewSerializer(reviews, many=True).data)

    def post(self, request, teacher_id: int):
        teacher = generics.get_object_or_404(TeacherProfile, id=teacher_id)
        serializer = TeacherReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review, _ = TeacherReview.objects.update_or_create(
            author_user=request.user,
            teacher=teacher,
            defaults=serializer.validated_data,
        )
        teacher.rating_count = teacher.reviews.count()
        teacher.rating_avg = teacher.reviews.aggregate(avg=Avg("rating"))["avg"] or 0
        teacher.save(update_fields=["rating_count", "rating_avg", "updated_at"])
        return Response(
            {
                "id": review.id,
                "teacher_id": teacher.id,
                "rating": review.rating,
                "text": review.text,
                "created_at": review.created_at,
            },
            status=status.HTTP_200_OK,
        )
