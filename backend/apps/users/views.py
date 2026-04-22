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

from apps.courses.models import Course, Enrollment, FavoriteCourse
from apps.courses.serializers import CourseDetailSerializer

from .models import FavoriteTeacher, TeacherProfile
from .serializers import (
    ChangePasswordSerializer,
    CourseRecommendationSerializer,
    FavoriteCourseSerializer,
    FavoriteTeacherSerializer,
    FavoritesResponseSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    MeUpdateSerializer,
    RegisterSerializer,
    TeacherDetailSerializer,
    TeacherProfileUpdateSerializer,
    TeacherCourseListSerializer,
    TeacherListSerializer,
)


def _enrollment_queryset_with_course_detail():
    return Enrollment.objects.select_related(
        "course__teacher__user",
        "course__dance_style",
        "course__studio__city",
    ).prefetch_related(
        "course__images",
        "course__schedule_rules",
    )


@extend_schema_view(
    get=extend_schema(
        tags=["Teachers"],
        summary="Список преподавателей",
        description="Возвращает список преподавателей с базовой фильтрацией.",
        parameters=[
            OpenApiParameter(name="city", description="Название города", type=str),
            OpenApiParameter(name="search", description="Имя, фамилия или email", type=str),
        ],
    )
)
class TeacherListAPIView(generics.ListAPIView):
    serializer_class = TeacherListSerializer

    def get_queryset(self):
        queryset = (
            TeacherProfile.objects.select_related("user__city")
            .all()
            .order_by("user__last_name", "user__first_name")
        )

        city = self.request.query_params.get("city")
        search = self.request.query_params.get("search")

        if city:
            queryset = queryset.filter(user__city__name__icontains=city)

        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
            )

        return queryset.distinct()

    @extend_schema(
        tags=["Teachers"],
        summary="Создать профиль преподавателя текущего пользователя",
        description="Создает профиль преподавателя для текущего пользователя, если его еще нет.",
        request=None,
        responses=TeacherDetailSerializer,
    )
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Требуется авторизация.")

        if request.user.role != "teacher":
            raise ValidationError({"detail": "Профиль преподавателя доступен только для роли teacher."})

        teacher, _ = TeacherProfile.objects.get_or_create(user=request.user)

        return Response(TeacherDetailSerializer(teacher).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        tags=["Teachers"],
        summary="Детальная информация о преподавателе",
        description="Возвращает карточку преподавателя с курсами и отзывами.",
    )
)
class TeacherRetrieveAPIView(generics.RetrieveAPIView):
    serializer_class = TeacherDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return TeacherProfile.objects.select_related("user__city").prefetch_related(
            "reviews__author_user",
            "courses__dance_style",
            "courses__studio",
        )

    @extend_schema(
        tags=["Teachers"],
        summary="Обновить профиль преподавателя",
        description="Обновляет профиль преподавателя для текущего пользователя.",
        request=TeacherProfileUpdateSerializer,
        responses=TeacherDetailSerializer,
    )
    def patch(self, request, *args, **kwargs):
        teacher = self._get_or_create_current_teacher_profile(request)
        serializer = TeacherProfileUpdateSerializer(teacher, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        teacher.refresh_from_db()
        return Response(TeacherDetailSerializer(teacher).data)

    @extend_schema(
        tags=["Teachers"],
        summary="Полностью обновить профиль преподавателя",
        description="Полностью обновляет профиль преподавателя для текущего пользователя.",
        request=TeacherProfileUpdateSerializer,
        responses=TeacherDetailSerializer,
    )
    def put(self, request, *args, **kwargs):
        teacher = self._get_or_create_current_teacher_profile(request)
        serializer = TeacherProfileUpdateSerializer(teacher, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        teacher.refresh_from_db()
        return Response(TeacherDetailSerializer(teacher).data)

    def _get_or_create_current_teacher_profile(self, request) -> TeacherProfile:
        if request.user.role != "teacher":
            raise ValidationError({"detail": "Профиль преподавателя доступен только для роли teacher."})

        teacher = TeacherProfile.objects.filter(user=request.user).first()
        if teacher is None:
            teacher = TeacherProfile.objects.create(user=request.user)
        return teacher


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
        summary="Курсы по записям пользователя",
        description=(
            "Возвращает полные карточки курсов (как GET /api/courses/{id}/) по всем записям "
            "текущего пользователя, кроме отменённых."
        ),
        responses=CourseDetailSerializer(many=True),
    )
)
class EnrollmentListAPIView(generics.ListAPIView):
    serializer_class = CourseDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        return (
            _enrollment_queryset_with_course_detail()
            .filter(user=self.request.user)
            .exclude(status="cancelled")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset
        courses = [e.course for e in rows]
        serializer = CourseDetailSerializer(courses, many=True, context={"request": request})
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        tags=["Teachers"],
        summary="Мои курсы как преподавателя",
        description=(
            "Возвращает полные карточки курсов в том же формате, что и GET /api/courses/{id}/ "
            "(CourseDetailSerializer), для всех курсов текущего преподавателя."
        ),
        parameters=[
            OpenApiParameter(name="status", description="Статус курса", type=str),
        ],
        responses=CourseDetailSerializer(many=True),
    )
)
class MyTeachingCourseListAPIView(generics.ListAPIView):
    serializer_class = CourseDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        queryset = (
            Course.objects.select_related(
                "teacher__user",
                "dance_style",
                "studio__city",
            )
            .prefetch_related(
                "images",
                "schedule_rules",
            )
            .filter(teacher__user=self.request.user)
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
    post=extend_schema(
        tags=["Users"],
        summary="Записаться на курс",
        description="Создает запись текущего пользователя на курс.",
        responses=CourseDetailSerializer,
    ),
    delete=extend_schema(
        tags=["Users"],
        summary="Отменить запись на курс",
        description="Помечает запись текущего пользователя как отмененную.",
    ),
)
class CourseEnrollAPIView(APIView):
    serializer_class = CourseDetailSerializer
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

        enrollment = _enrollment_queryset_with_course_detail().get(pk=enrollment.pk)
        data = CourseDetailSerializer(enrollment.course, context={"request": request}).data
        return Response(
            data,
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
        access = str(refresh.access_token)
        return Response(
            {
                "user": MeSerializer(user, context={"request": request}).data,
                "token": access,
                "access": access,
                "refresh": str(refresh),
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
        tags=["Recommendations"],
        summary="Рекомендованные курсы",
        description="Возвращает топ-10 опубликованных курсов по рейтингу преподавателя, с приоритетом под уровень пользователя.",
        responses=CourseRecommendationSerializer(many=True),
    )
)
class RecommendedCourseListAPIView(generics.ListAPIView):
    serializer_class = CourseRecommendationSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        user = self.request.user
        enrolled_course_ids = set(
            user.enrollments.filter(status__in=["active", "pending", "completed"]).values_list(
                "course_id", flat=True
            )
        )

        queryset = (
            Course.objects.select_related("teacher__user", "dance_style", "studio__city")
            .filter(status="published")
            .exclude(id__in=enrolled_course_ids)
        )

        if user.dance_level:
            queryset = queryset.filter(
                Q(level=user.dance_level) | Q(level="Любой уровень")
            )

        return queryset.order_by("-teacher__rating_avg", "date_from", "id")[:10]
