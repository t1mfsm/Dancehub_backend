from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import exceptions, generics, permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.users.models import TeacherProfile

from .models import Attendance, Course, DanceStyle, Enrollment, Lesson, Review, Studio
from .serializers import (
    AttendanceMarkSerializer,
    AttendanceSerializer,
    CalendarEventSerializer,
    CourseReviewCreateSerializer,
    CourseReviewSerializer,
    CourseStudentSerializer,
    CourseDetailSerializer,
    CourseListSerializer,
    CourseWriteSerializer,
    DanceStyleSerializer,
    LessonSerializer,
    LessonWriteSerializer,
    MapPointSerializer,
    StudioDetailSerializer,
    StudioSerializer,
)


@extend_schema_view(
    get=extend_schema(
        tags=["Reference"],
        summary="Список танцевальных стилей",
        description="Возвращает справочник танцевальных стилей.",
    )
)
class DanceStyleListAPIView(generics.ListAPIView):
    queryset = DanceStyle.objects.all().order_by("name")
    serializer_class = DanceStyleSerializer


@extend_schema_view(
    get=extend_schema(
        tags=["Reference"],
        summary="Список студий",
        description="Возвращает список студий для карты и фильтров.",
    )
)
class StudioListAPIView(generics.ListAPIView):
    queryset = Studio.objects.select_related("city").all().order_by("name")
    serializer_class = StudioSerializer


@extend_schema_view(
    get=extend_schema(
        tags=["Reference"],
        summary="Детальная информация о студии",
        description="Возвращает студию с залами и количеством курсов.",
    )
)
class StudioRetrieveAPIView(generics.RetrieveAPIView):
    serializer_class = StudioDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Studio.objects.select_related("city").prefetch_related("halls").annotate(
            courses_count=Count("courses", distinct=True)
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Map"],
        summary="Точки для карты студий",
        description="Возвращает студии для карты с базовой фильтрацией.",
        parameters=[
            OpenApiParameter(name="city", description="Название города", type=str),
            OpenApiParameter(name="metro", description="Станция метро", type=str),
            OpenApiParameter(name="studio", description="Название студии", type=str),
            OpenApiParameter(name="style", description="Стиль курса в студии", type=str),
        ],
    )
)
class MapPointListAPIView(generics.ListAPIView):
    serializer_class = MapPointSerializer

    def get_queryset(self):
        queryset = Studio.objects.select_related("city").annotate(
            halls_count=Count("halls", distinct=True),
            active_courses_count=Count("courses", filter=Q(courses__status="published"), distinct=True),
        )

        city = self.request.query_params.get("city")
        metro = self.request.query_params.get("metro")
        studio = self.request.query_params.get("studio")
        style = self.request.query_params.get("style")

        if city:
            queryset = queryset.filter(city__name__icontains=city)
        if metro:
            queryset = queryset.filter(metro__icontains=metro)
        if studio:
            queryset = queryset.filter(name__icontains=studio)
        if style:
            queryset = queryset.filter(
                Q(courses__dance_style__slug__icontains=style)
                | Q(courses__dance_style__name__icontains=style)
            )

        return queryset.distinct().order_by("name")


@extend_schema_view(
    get=extend_schema(
        tags=["Courses"],
        summary="Список курсов",
        description="Возвращает список курсов с простой фильтрацией по query params.",
        parameters=[
            OpenApiParameter(name="city", description="Название города", type=str),
            OpenApiParameter(name="style", description="Slug или название стиля", type=str),
            OpenApiParameter(name="teacher", description="Имя, фамилия или email преподавателя", type=str),
            OpenApiParameter(name="level", description="Уровень: beginner/intermediate/advanced/any", type=str),
            OpenApiParameter(name="studio", description="Название студии", type=str),
            OpenApiParameter(name="status", description="Статус курса", type=str),
        ],
    )
)
class CourseListAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.AllowAny]

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CourseWriteSerializer
        return CourseListSerializer

    def get_queryset(self):
        queryset = (
            Course.objects.select_related(
                "teacher__user",
                "dance_style",
                "studio__city",
                "hall",
            )
            .prefetch_related("schedule_rules", "images")
            .all()
            .order_by("date_from", "id")
        )

        city = self.request.query_params.get("city")
        style = self.request.query_params.get("style")
        teacher = self.request.query_params.get("teacher")
        level = self.request.query_params.get("level")
        studio = self.request.query_params.get("studio")
        status_param = self.request.query_params.get("status")

        if city:
            queryset = queryset.filter(studio__city__name__icontains=city)

        if style:
            queryset = queryset.filter(
                Q(dance_style__slug__icontains=style)
                | Q(dance_style__name__icontains=style)
            )

        if teacher:
            queryset = queryset.filter(
                Q(teacher__user__first_name__icontains=teacher)
                | Q(teacher__user__last_name__icontains=teacher)
                | Q(teacher__user__email__icontains=teacher)
            )

        if level:
            queryset = queryset.filter(level=level)

        if studio:
            queryset = queryset.filter(studio__name__icontains=studio)

        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset.distinct()

    @extend_schema(
        tags=["Courses"],
        summary="Создать курс",
        description="Создает новый курс. Доступно преподавателю или администратору.",
        request=CourseWriteSerializer,
        responses=CourseDetailSerializer,
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        teacher_profile = getattr(request.user, "teacher_profile", None)
        teacher_id = serializer.validated_data.pop("teacher_id", None)
        if request.user.is_superuser and teacher_id:
            teacher = generics.get_object_or_404(TeacherProfile, id=teacher_id)
        else:
            if not teacher_profile:
                raise exceptions.PermissionDenied("Создавать курс может только преподаватель.")
            teacher = teacher_profile

        course = serializer.save(teacher=teacher)
        response_serializer = CourseDetailSerializer(course, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        tags=["Courses"],
        summary="Детальная информация о курсе",
        description="Возвращает полную карточку курса для детальной страницы.",
    )
)
class CourseRetrieveAPIView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "id"

    def get_permissions(self):
        if self.request.method in {"PATCH", "PUT", "DELETE"}:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.request.method in {"PATCH", "PUT"}:
            return CourseWriteSerializer
        return CourseDetailSerializer

    def get_queryset(self):
        return Course.objects.select_related(
            "teacher__user",
            "dance_style",
            "studio__city",
            "hall",
            "music",
        ).prefetch_related(
            "images",
            "schedule_rules__hall",
            "reviews",
        )

    @extend_schema(
        tags=["Courses"],
        summary="Обновить курс",
        description="Обновляет курс. Доступно преподавателю курса или администратору.",
        request=CourseWriteSerializer,
        responses=CourseDetailSerializer,
    )
    def patch(self, request, *args, **kwargs):
        return self._update(request, partial=True, *args, **kwargs)

    @extend_schema(
        tags=["Courses"],
        summary="Полностью обновить курс",
        description="Полностью обновляет курс. Доступно преподавателю курса или администратору.",
        request=CourseWriteSerializer,
        responses=CourseDetailSerializer,
    )
    def put(self, request, *args, **kwargs):
        return self._update(request, partial=False, *args, **kwargs)

    def _update(self, request, partial: bool, *args, **kwargs):
        course = self.get_object()
        if not (request.user.is_superuser or course.teacher.user_id == request.user.id):
            raise exceptions.PermissionDenied("Редактировать курс может только преподаватель курса.")
        serializer = self.get_serializer(course, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        teacher_id = serializer.validated_data.pop("teacher_id", None)
        if teacher_id and request.user.is_superuser:
            teacher = generics.get_object_or_404(TeacherProfile, id=teacher_id)
            saved = serializer.save(teacher=teacher)
        else:
            saved = serializer.save()
        return Response(CourseDetailSerializer(saved, context={"request": request}).data)

    @extend_schema(
        tags=["Courses"],
        summary="Удалить курс",
        description="Удаляет курс. Доступно преподавателю курса или администратору.",
    )
    def delete(self, request, *args, **kwargs):
        course = self.get_object()
        if not (request.user.is_superuser or course.teacher.user_id == request.user.id):
            raise exceptions.PermissionDenied("Удалять курс может только преподаватель курса.")
        return super().delete(request, *args, **kwargs)


@extend_schema_view(
    get=extend_schema(
        tags=["Calendar"],
        summary="Календарь занятий пользователя",
        description="Возвращает занятия для календаря текущего пользователя.",
        parameters=[
            OpenApiParameter(name="mode", description="all | enrolled | teaching", type=str),
            OpenApiParameter(name="course_id", description="Фильтр по курсу", type=int),
            OpenApiParameter(name="date_from", description="Дата от YYYY-MM-DD", type=str),
            OpenApiParameter(name="date_to", description="Дата до YYYY-MM-DD", type=str),
        ],
    )
)
class CalendarAPIView(generics.ListAPIView):
    serializer_class = CalendarEventSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        user = self.request.user
        mode = self.request.query_params.get("mode", "all")
        course_id = self.request.query_params.get("course_id")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        queryset = Lesson.objects.select_related(
            "course__teacher__user",
            "course__dance_style",
            "course__studio__city",
        ).all()

        enrolled_ids = Enrollment.objects.filter(
            user=user,
            status__in=["active", "pending", "completed"],
        ).values_list("course_id", flat=True)
        teaching_ids = Course.objects.filter(teacher__user=user).values_list("id", flat=True)

        if mode == "enrolled":
            queryset = queryset.filter(course_id__in=enrolled_ids)
        elif mode == "teaching":
            queryset = queryset.filter(course_id__in=teaching_ids)
        else:
            queryset = queryset.filter(Q(course_id__in=enrolled_ids) | Q(course_id__in=teaching_ids))

        if course_id:
            queryset = queryset.filter(course_id=course_id)
        if date_from:
            queryset = queryset.filter(lesson_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(lesson_date__lte=date_to)

        return queryset.order_by("lesson_date", "time_from")


@extend_schema_view(
    get=extend_schema(
        tags=["Lessons"],
        summary="Занятия курса",
        description="Возвращает список занятий выбранного курса.",
        parameters=[
            OpenApiParameter(name="status", description="Фильтр по статусу занятия", type=str),
        ],
    )
)
class CourseLessonListAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return LessonWriteSerializer
        return LessonSerializer

    def get_queryset(self):
        queryset = Lesson.objects.select_related(
            "course__teacher__user",
            "course__studio__city",
            "hall",
        ).filter(course_id=self.kwargs["id"])

        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset.order_by("lesson_date", "time_from")

    @extend_schema(
        tags=["Lessons"],
        summary="Создать занятие курса",
        description="Создает новое занятие для курса. Доступно преподавателю курса или администратору.",
        request=LessonWriteSerializer,
        responses=LessonSerializer,
    )
    def post(self, request, *args, **kwargs):
        course = generics.get_object_or_404(Course, id=self.kwargs["id"])
        if not (request.user.is_superuser or course.teacher.user_id == request.user.id):
            raise exceptions.PermissionDenied("Создавать занятия может только преподаватель курса.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lesson = serializer.save(course=course)
        return Response(LessonSerializer(lesson).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    patch=extend_schema(
        tags=["Lessons"],
        summary="Обновить занятие",
        description="Обновляет занятие. Доступно преподавателю курса или администратору.",
        request=LessonWriteSerializer,
        responses=LessonSerializer,
    ),
    put=extend_schema(
        tags=["Lessons"],
        summary="Полностью обновить занятие",
        description="Полностью обновляет занятие. Доступно преподавателю курса или администратору.",
        request=LessonWriteSerializer,
        responses=LessonSerializer,
    ),
    delete=extend_schema(
        tags=["Lessons"],
        summary="Удалить занятие",
        description="Удаляет занятие. Доступно преподавателю курса или администратору.",
    ),
)
class LessonRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Lesson.objects.select_related("course__teacher__user", "hall")
    lookup_field = "lesson_id"
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_serializer_class(self):
        if self.request.method in {"PATCH", "PUT"}:
            return LessonWriteSerializer
        return LessonSerializer

    def _check_access(self, lesson: Lesson, user):
        if not (user.is_superuser or lesson.course.teacher.user_id == user.id):
            raise exceptions.PermissionDenied("Управлять занятием может только преподаватель курса.")

    def patch(self, request, *args, **kwargs):
        lesson = self.get_object()
        self._check_access(lesson, request.user)
        serializer = self.get_serializer(lesson, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(LessonSerializer(lesson).data)

    def put(self, request, *args, **kwargs):
        lesson = self.get_object()
        self._check_access(lesson, request.user)
        serializer = self.get_serializer(lesson, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(LessonSerializer(lesson).data)

    def delete(self, request, *args, **kwargs):
        lesson = self.get_object()
        self._check_access(lesson, request.user)
        return super().delete(request, *args, **kwargs)


@extend_schema_view(
    get=extend_schema(
        tags=["Courses"],
        summary="Студенты курса",
        description="Возвращает список учеников, записанных на выбранный курс.",
        parameters=[
            OpenApiParameter(name="status", description="Статус записи", type=str),
        ],
    )
)
class CourseStudentListAPIView(generics.ListAPIView):
    serializer_class = CourseStudentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        course = generics.get_object_or_404(Course, id=self.kwargs["id"])
        user = self.request.user
        is_allowed = user.is_superuser or course.teacher.user_id == user.id
        if not is_allowed:
            raise exceptions.PermissionDenied("Список студентов доступен только преподавателю курса.")

        queryset = Enrollment.objects.select_related("user").filter(course=course).order_by("user__last_name", "user__first_name")
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        else:
            queryset = queryset.filter(status__in=["active", "pending", "completed"])
        return queryset


@extend_schema_view(
    get=extend_schema(
        tags=["Attendance"],
        summary="Посещаемость по курсу",
        description="Возвращает все отметки посещаемости по выбранному курсу.",
    )
)
class CourseAttendanceListAPIView(generics.ListAPIView):
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        return Attendance.objects.select_related(
            "lesson__course",
            "student",
        ).filter(lesson__course_id=self.kwargs["id"]).order_by("-lesson__lesson_date", "student_id")


@extend_schema_view(
    get=extend_schema(
        tags=["Attendance"],
        summary="Посещаемость по занятию",
        description="Возвращает отметки посещаемости по конкретному занятию.",
    )
)
class LessonAttendanceListAPIView(generics.ListAPIView):
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        return Attendance.objects.select_related(
            "lesson__course",
            "student",
        ).filter(lesson_id=self.kwargs["lesson_id"]).order_by("student_id")


@extend_schema(
    tags=["Attendance"],
    summary="Отметить посещаемость",
    description="Создает или обновляет отметку посещаемости ученика по занятию.",
    request=AttendanceMarkSerializer,
)
class AttendanceMarkAPIView(APIView):
    serializer_class = AttendanceMarkSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, lesson_id: int):
        serializer = AttendanceMarkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        lesson = generics.get_object_or_404(Lesson, id=lesson_id)
        if lesson.course.teacher.user_id != request.user.id:
            return Response(
                {"detail": "Только преподаватель курса может отмечать посещаемость."},
                status=status.HTTP_403_FORBIDDEN,
            )

        attendance, _ = Attendance.objects.update_or_create(
            lesson=lesson,
            student_id=serializer.validated_data["student_id"],
            defaults={"status": serializer.validated_data["status"]},
        )
        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_200_OK)


@extend_schema_view(
    get=extend_schema(
        tags=["Reviews"],
        summary="Список отзывов о курсе",
        description="Возвращает все отзывы выбранного курса.",
        responses=CourseReviewSerializer(many=True),
    ),
    post=extend_schema(
        tags=["Reviews"],
        summary="Оставить отзыв о курсе",
        description="Создает или обновляет отзыв текущего пользователя о курсе.",
        request=CourseReviewCreateSerializer,
    ),
)
class CourseReviewCreateAPIView(APIView):
    serializer_class = CourseReviewCreateSerializer
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_permissions(self):
        if self.request.method == "GET":
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get(self, request, course_id: int):
        reviews = Review.objects.select_related("author_user").filter(course_id=course_id).order_by("-created_at")
        return Response(CourseReviewSerializer(reviews, many=True).data)

    def post(self, request, course_id: int):
        course = generics.get_object_or_404(Course, id=course_id)
        serializer = CourseReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review, _ = Review.objects.update_or_create(
            author_user=request.user,
            course=course,
            defaults=serializer.validated_data,
        )
        return Response(
            {
                "id": review.id,
                "course_id": course.id,
                "rating": review.rating,
                "text": review.text,
                "created_at": review.created_at,
            },
            status=status.HTTP_200_OK,
        )
