from django.db.models import Case, CharField, Count, Q, Value, When
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import exceptions, generics, permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.users.models import TeacherProfile

from .constants import CourseLifecycleStatus
from .lesson_utils import can_cancel_lesson
from .models import AttendanceMark, Course, CourseStatus, DanceStyle, Enrollment, Lesson, Studio
from .serializers import (
    AttendanceMarkSerializer,
    AttendanceSerializer,
    CalendarEventSerializer,
    CourseAttendanceStatsSerializer,
    CourseDetailSerializer,
    CourseListSerializer,
    CourseStudentSerializer,
    CourseWriteSerializer,
    DanceStyleSerializer,
    LessonSerializer,
    LessonWriteSerializer,
    MapPointSerializer,
    StudioDetailSerializer,
    StudioSerializer,
)
from .stats_service import build_course_attendance_stats


# ---------------------------------------------------------------------------
# Reference
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(tags=["Reference"], summary="Список танцевальных стилей")
)
class DanceStyleListAPIView(generics.ListAPIView):
    queryset = DanceStyle.objects.all().order_by("name")
    serializer_class = DanceStyleSerializer


@extend_schema_view(
    get=extend_schema(tags=["Reference"], summary="Список студий")
)
class StudioListAPIView(generics.ListAPIView):
    queryset = Studio.objects.select_related("city").all().order_by("name")
    serializer_class = StudioSerializer


@extend_schema_view(
    get=extend_schema(tags=["Reference"], summary="Детальная информация о студии")
)
class StudioRetrieveAPIView(generics.RetrieveAPIView):
    serializer_class = StudioDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Studio.objects.select_related("city").annotate(
            courses_count=Count("courses", distinct=True)
        )


# ---------------------------------------------------------------------------
# Map
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(
        tags=["Map"],
        summary="Точки для карты студий",
        parameters=[
            OpenApiParameter(name="city", type=str),
            OpenApiParameter(name="metro", type=str),
            OpenApiParameter(name="studio", type=str),
            OpenApiParameter(name="style", type=str),
        ],
    )
)
class MapPointListAPIView(generics.ListAPIView):
    serializer_class = MapPointSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        queryset = Studio.objects.select_related("city").annotate(
            active_courses_count=Count(
                "courses", filter=Q(courses__status="published"), distinct=True
            )
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


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(
        tags=["Courses"],
        summary="Список курсов",
        parameters=[
            OpenApiParameter(name="city", type=str),
            OpenApiParameter(name="style", type=str),
            OpenApiParameter(name="teacher", type=str),
            OpenApiParameter(name="level", type=str),
            OpenApiParameter(name="studio", type=str),
            OpenApiParameter(name="status", type=str),
        ],
    )
)
class CourseListAPIView(generics.ListCreateAPIView):
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    @staticmethod
    def _with_activity_status(queryset):
        today = timezone.localdate()
        return queryset.annotate(
            activity_status=Case(
                When(date_to__lt=today, then=Value(CourseLifecycleStatus.COMPLETED)),
                default=Value(CourseLifecycleStatus.ACTIVE),
                output_field=CharField(),
            )
        )

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CourseWriteSerializer
        return CourseListSerializer

    def get_queryset(self):
        queryset = self._with_activity_status(
            Course.objects.select_related("teacher__user", "dance_style", "studio__city")
            .prefetch_related("schedule_rules", "enrollments")
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
                Q(dance_style__slug__icontains=style) | Q(dance_style__name__icontains=style)
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

        if status_param in {"active", "completed"}:
            queryset = queryset.filter(activity_status=status_param)
        elif status_param:
            queryset = queryset.filter(status=status_param)
        elif teacher:
            queryset = queryset.filter(activity_status__in=["active", "completed"])
        else:
            queryset = queryset.filter(
                status=CourseStatus.PUBLISHED,
                activity_status=CourseLifecycleStatus.ACTIVE,
            )

        return queryset.distinct()

    @extend_schema(tags=["Courses"], summary="Создать курс", request=CourseWriteSerializer, responses=CourseDetailSerializer)
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        teacher_profile = getattr(request.user, "teacher_profile", None)
        teacher_id = serializer.validated_data.get("teacher_id")
        if request.user.is_superuser and teacher_id:
            teacher = generics.get_object_or_404(TeacherProfile, id=teacher_id)
        else:
            if not teacher_profile:
                raise exceptions.PermissionDenied("Создавать курс может только преподаватель.")
            teacher = teacher_profile

        course = serializer.save(teacher=teacher)
        return Response(CourseDetailSerializer(course, context={"request": request}).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(tags=["Courses"], summary="Детальная информация о курсе")
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
        return Course.objects.select_related("teacher__user", "dance_style", "studio__city").prefetch_related(
            "schedule_rules", "enrollments"
        )

    @extend_schema(tags=["Courses"], summary="Обновить курс", request=CourseWriteSerializer, responses=CourseDetailSerializer)
    def patch(self, request, *args, **kwargs):
        return self._update(request, partial=True, *args, **kwargs)

    @extend_schema(tags=["Courses"], summary="Полностью обновить курс", request=CourseWriteSerializer, responses=CourseDetailSerializer)
    def put(self, request, *args, **kwargs):
        return self._update(request, partial=False, *args, **kwargs)

    def _update(self, request, partial, *args, **kwargs):
        course = self.get_object()
        if not (request.user.is_superuser or course.teacher.user_id == request.user.id):
            raise exceptions.PermissionDenied("Редактировать курс может только преподаватель курса.")
        serializer = self.get_serializer(course, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        saved = serializer.save()
        return Response(CourseDetailSerializer(saved, context={"request": request}).data)

    @extend_schema(tags=["Courses"], summary="Удалить курс")
    def delete(self, request, *args, **kwargs):
        course = self.get_object()
        if not (request.user.is_superuser or course.teacher.user_id == request.user.id):
            raise exceptions.PermissionDenied("Удалять курс может только преподаватель курса.")
        return super().delete(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(
        tags=["Calendar"],
        summary="Календарь занятий пользователя",
        parameters=[
            OpenApiParameter(name="mode", type=str, description="all | enrolled | teaching"),
            OpenApiParameter(name="course_id", type=int),
            OpenApiParameter(name="date_from", type=str),
            OpenApiParameter(name="date_to", type=str),
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
            "course__teacher__user", "course__dance_style", "course__studio__city"
        )

        enrolled_ids = Enrollment.objects.filter(
            user=user, status__in=["active", "pending", "completed"]
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


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------

@extend_schema_view(
    patch=extend_schema(tags=["Lessons"], summary="Обновить занятие"),
    put=extend_schema(tags=["Lessons"], summary="Полностью обновить занятие"),
    delete=extend_schema(tags=["Lessons"], summary="Удалить занятие"),
)
class LessonRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Lesson.objects.select_related("course__teacher__user")
    lookup_field = "lesson_id"
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_serializer_class(self):
        if self.request.method in {"PATCH", "PUT"}:
            return LessonWriteSerializer
        return LessonSerializer

    def _check_access(self, lesson, user):
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


@extend_schema(tags=["Lessons"], summary="Отменить занятие")
class LessonCancelAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, lesson_id: int):
        lesson = generics.get_object_or_404(Lesson, id=lesson_id)
        if not (request.user.is_superuser or lesson.course.teacher.user_id == request.user.id):
            raise exceptions.PermissionDenied("Отменять занятие может только преподаватель курса.")
        ok, reason = can_cancel_lesson(lesson)
        if not ok:
            return Response({"detail": reason}, status=status.HTTP_400_BAD_REQUEST)
        lesson.status = "cancelled"
        lesson.save(update_fields=["status", "updated_at"])
        return Response(LessonSerializer(lesson).data)


# ---------------------------------------------------------------------------
# Course students & lessons
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(
        tags=["Courses"],
        summary="Студенты курса",
        parameters=[OpenApiParameter(name="status", type=str)],
    )
)
class CourseStudentListAPIView(generics.ListAPIView):
    serializer_class = CourseStudentSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        course = generics.get_object_or_404(Course, id=self.kwargs["id"])
        if not (self.request.user.is_superuser or course.teacher.user_id == self.request.user.id):
            raise exceptions.PermissionDenied("Список студентов доступен только преподавателю курса.")
        queryset = Enrollment.objects.select_related("user").filter(course=course).order_by(
            "user__last_name", "user__first_name"
        )
        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)
        else:
            queryset = queryset.filter(status__in=["active", "pending", "completed"])
        return queryset


@extend_schema_view(
    get=extend_schema(tags=["Lessons"], summary="Занятия курса")
)
class CourseLessonListAPIView(generics.ListAPIView):
    serializer_class = LessonSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        course = generics.get_object_or_404(Course, id=self.kwargs["id"])
        user = self.request.user
        is_allowed = (
            user.is_superuser
            or course.teacher.user_id == user.id
            or Enrollment.objects.filter(user=user, course=course, status__in=["active", "pending", "completed"]).exists()
        )
        if not is_allowed:
            raise exceptions.PermissionDenied("Список занятий недоступен для этого пользователя.")
        return Lesson.objects.filter(course=course).order_by("lesson_date", "time_from")


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

@extend_schema_view(
    get=extend_schema(tags=["Attendance"], summary="Посещаемость по курсу")
)
class CourseAttendanceListAPIView(generics.ListAPIView):
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        return AttendanceMark.objects.select_related("lesson__course", "student").filter(
            lesson__course_id=self.kwargs["id"]
        ).order_by("-lesson__lesson_date", "student_id")


@extend_schema_view(
    get=extend_schema(tags=["Attendance"], summary="Посещаемость по занятию")
)
class LessonAttendanceListAPIView(generics.ListAPIView):
    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get_queryset(self):
        return AttendanceMark.objects.select_related("lesson__course", "student").filter(
            lesson_id=self.kwargs["lesson_id"]
        ).order_by("student_id")


@extend_schema_view(
    get=extend_schema(
        tags=["Attendance"],
        summary="Статистика посещаемости по курсу",
        parameters=[
            OpenApiParameter(name="date_from", type=str),
            OpenApiParameter(name="date_to", type=str),
        ],
    )
)
class CourseAttendanceStatsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, id: int):
        course = generics.get_object_or_404(Course, id=id)
        if not (request.user.is_superuser or course.teacher.user_id == request.user.id):
            raise exceptions.PermissionDenied("Статистика доступна только преподавателю курса.")
        from datetime import date as date_type
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        stats = build_course_attendance_stats(
            course,
            date_from=date_type.fromisoformat(date_from) if date_from else None,
            date_to=date_type.fromisoformat(date_to) if date_to else None,
        )
        return Response(stats)


@extend_schema(tags=["Attendance"], summary="Отметить посещаемость")
class AttendanceMarkAPIView(APIView):
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

        mark, _ = AttendanceMark.objects.update_or_create(
            lesson=lesson,
            student_id=serializer.validated_data["student_id"],
            defaults={"status": serializer.validated_data["status"]},
        )
        return Response(AttendanceSerializer(mark).data, status=status.HTTP_200_OK)
