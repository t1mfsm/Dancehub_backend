from datetime import date, datetime

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.choices import AttendanceStatus, EnrollmentStatus, LessonStatus
from apps.common.files import save_uploaded_file
from apps.common.utils import (
    absolutize_media_url,
    build_full_name,
    course_lifecycle_status,
    first_lesson_start_at,
    has_hours_before,
    lesson_lifecycle_status,
    lesson_start_at,
    lesson_start_iso,
)
from apps.courses.models import AttendanceMark, Course, CourseSchedule, DanceStyle, Enrollment, Lesson, Studio
from apps.courses.payment_utils import (
    build_spots_left_map,
    expire_stale_payment_orders_for_enrollment,
    get_live_pending_payment_order,
)
from apps.users.models import TeacherProfile, User
from apps.users.notifications import (
    create_course_updated_notifications,
    create_favorite_teacher_new_course_notifications,
    create_lesson_changed_notifications,
)

from .serializers import (
    AttendanceMarkRequestSerializer,
    CourseWriteSerializer,
    EnrollmentRequestSerializer,
    LessonUpdateSerializer,
    expand_lessons_for_schedule,
    serialize_course_detail,
    serialize_course_list_item,
    serialize_lesson,
)
from .stats_service import build_course_attendance_stats


class IsAuthenticated(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_authenticated", False))


def require_authenticated_user(request) -> User:
    user = request.user
    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication required.")
    return user


def get_owned_teacher(request) -> TeacherProfile:
    user = require_authenticated_user(request)
    teacher = getattr(user, "teacher_profile", None)
    if teacher is None:
        raise ValidationError({"detail": "User does not have a teacher profile."})
    return teacher


def get_course_or_404(course_id: int) -> Course:
    course = (
        Course.objects.filter(id=course_id)
        .select_related("teacher__user", "dance_style", "studio__city")
        .prefetch_related("schedule_rows", "lessons")
        .annotate(active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)))
        .first()
    )
    if course is None:
        raise ValidationError({"detail": "Course not found."})
    return course


def parse_query_date(value: str | None, field_name: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({field_name: "Invalid date format. Use YYYY-MM-DD."}) from exc


def ensure_teacher_owns_course(teacher: TeacherProfile, course: Course) -> None:
    if course.teacher_id != teacher.id:
        raise PermissionDenied("You can manage only your own courses.")


def build_course_viewer_context(course: Course, user: User | None) -> dict:
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
    payment_order = get_live_pending_payment_order(enrollment)

    if enrollment.status == EnrollmentStatus.CANCELLED and payment_order is None:
        return {
            "viewer_enrollment_status": None,
            "viewer_paid": False,
            "viewer_payment_order": None,
        }

    from .serializers import serialize_payment_order

    return {
        "viewer_enrollment_status": enrollment.status,
        "viewer_paid": enrollment.paid,
        "viewer_payment_order": serialize_payment_order(payment_order) if payment_order is not None else None,
    }


class DanceStyleListAPIView(APIView):
    def get(self, _request):
        styles = DanceStyle.objects.all().order_by("name")
        return Response([{"id": row.id, "name": row.name, "slug": row.slug} for row in styles])


class StudioListAPIView(APIView):
    def get(self, request):
        studios = Studio.objects.select_related("city").order_by("name")
        city = request.query_params.get("city")
        if city:
            studios = studios.filter(city__name__iexact=city)
        return Response(
            [
                {
                    "id": studio.id,
                    "name": studio.name,
                    "city": studio.city.name,
                    "address": studio.address,
                    "metro": studio.metro or "",
                }
                for studio in studios
            ]
        )


class StudioRetrieveAPIView(APIView):
    def get(self, _request, id: int):
        studio = Studio.objects.select_related("city").filter(id=id).first()
        if studio is None:
            raise ValidationError({"detail": "Studio not found."})
        return Response(
            {
                "id": studio.id,
                "name": studio.name,
                "city": studio.city.name,
                "address": studio.address,
                "metro": studio.metro or "",
            }
        )


class MapPointListAPIView(APIView):
    def get(self, request):
        studios = Studio.objects.select_related("city").annotate(
            active_courses_count=Count(
                "courses",
                filter=Q(courses__status__in=["published", "active"]) & Q(courses__date_to__gte=datetime.now().date()),
                distinct=True,
            )
        )
        city = request.query_params.get("city")
        metro = request.query_params.get("metro")
        studio_name = request.query_params.get("studio")
        style = request.query_params.get("style")
        if city:
            studios = studios.filter(city__name__iexact=city)
        if metro:
            studios = studios.filter(metro__icontains=metro)
        if studio_name:
            studios = studios.filter(name__icontains=studio_name)
        if style:
            studios = studios.filter(
                Q(courses__dance_style__slug__iexact=style) | Q(courses__dance_style__name__iexact=style)
            )
        studios = studios.distinct().prefetch_related("courses__dance_style")
        payload = []
        for studio in studios:
            style_names = sorted(
                {
                    course.dance_style.name
                    for course in studio.courses.all()
                    if course_lifecycle_status(course.status, course.date_from, course.date_to) == "active"
                }
            )
            payload.append(
                {
                    "id": studio.id,
                    "name": studio.name,
                    "city": studio.city.name,
                    "address": studio.address,
                    "metro": studio.metro or "",
                    "lat": studio.lat,
                    "lng": studio.lng,
                    "image": studio.image or "",
                    "halls_count": studio.halls_count,
                    "active_courses_count": studio.active_courses_count,
                    "dance_styles": style_names,
                }
            )
        return Response(payload)


class CalendarAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = require_authenticated_user(request)
        mode = request.query_params.get("mode", "all")
        lessons = Lesson.objects.select_related("course__teacher__user", "course__dance_style", "course__studio__city")
        if mode == "teaching":
            lessons = lessons.filter(course__teacher__user=user)
        elif mode == "enrolled":
            lessons = lessons.filter(course__enrollments__user=user, course__enrollments__status=EnrollmentStatus.ACTIVE)
        else:
            lessons = lessons.filter(
                Q(course__teacher__user=user)
                | Q(course__enrollments__user=user, course__enrollments__status=EnrollmentStatus.ACTIVE)
            )
        course_id = request.query_params.get("course_id")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if course_id:
            lessons = lessons.filter(course_id=course_id)
        if date_from:
            lessons = lessons.filter(lesson_date__gte=date_from)
        if date_to:
            lessons = lessons.filter(lesson_date__lte=date_to)
        lessons = lessons.distinct().order_by("lesson_date", "time_from")
        payload = []
        for lesson in lessons:
            payload.append(
                {
                    "id": lesson.id,
                    "course_id": lesson.course_id,
                    "course_name": lesson.course.name,
                    "teacher_name": build_full_name(
                        lesson.course.teacher.user.last_name,
                        lesson.course.teacher.user.first_name,
                        lesson.course.teacher.user.middle_name,
                    )
                    or lesson.course.teacher.user.email,
                    "dance_style": lesson.course.dance_style.name,
                    "level": lesson.course.level,
                    "lesson_date": lesson.lesson_date.isoformat(),
                    "time_from": lesson.time_from.isoformat(timespec="minutes"),
                    "time_to": lesson.time_to.isoformat(timespec="minutes"),
                    "start": lesson_start_iso(lesson.lesson_date, lesson.time_from),
                    "end": lesson_start_iso(lesson.lesson_date, lesson.time_to),
                    "location_text": lesson.location_text,
                    "status": lesson_lifecycle_status(lesson.status, lesson.lesson_date),
                    "studio": lesson.course.studio.name,
                    "city": lesson.course.studio.city.name,
                }
            )
        return Response(payload)


class CourseListAPIView(APIView):
    def get(self, request):
        courses = (
            Course.objects.select_related("teacher__user", "dance_style", "studio__city")
            .prefetch_related("schedule_rows")
            .annotate(active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)))
        )
        if city := request.query_params.get("city"):
            courses = courses.filter(studio__city__name__iexact=city)
        if level := request.query_params.get("level"):
            if level != "any":
                courses = courses.filter(level=level)
        status_filter = request.query_params.get("status")
        if studio := request.query_params.get("studio"):
            courses = courses.filter(studio__name__icontains=studio)
        if style := request.query_params.get("style"):
            courses = courses.filter(Q(dance_style__slug__iexact=style) | Q(dance_style__name__iexact=style))
        if teacher := request.query_params.get("teacher"):
            courses = courses.filter(
                Q(teacher__user__first_name__icontains=teacher)
                | Q(teacher__user__last_name__icontains=teacher)
                | Q(teacher__user__email__icontains=teacher)
            )
        courses = list(courses.distinct().order_by("-id"))
        spots_left_map = build_spots_left_map(courses)
        if status_filter:
            courses = [
                course
                for course in courses
                if course_lifecycle_status(course.status, course.date_from, course.date_to) == status_filter
            ]
        return Response(
            [
                serialize_course_list_item(course, request=request, spots_left=spots_left_map.get(course.id, course.capacity))
                for course in courses
            ]
        )

    @extend_schema(request=CourseWriteSerializer)
    def post(self, request):
        teacher = get_owned_teacher(request)
        serializer = CourseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            course = Course.objects.create(
                teacher=teacher,
                dance_style_id=data["dance_style_id"],
                studio_id=data["studio_id"],
                name=data["name"],
                description=data.get("description", ""),
                music_artist=data.get("music_artist", ""),
                music_track=data.get("music_track", ""),
                music_url=data.get("music_url", ""),
                level=data["level"],
                price=data["price"],
                capacity=data["capacity"],
                date_from=data["date_from"],
                date_to=data["date_to"],
                status=data.get("status", "published"),
                images=[],
                image_cover=data.get("image_cover") or None,
            )
            image_urls = serializer.normalized_image_urls("course-images")
            for image_file in request.FILES.getlist("image_files"):
                image_urls.append(save_uploaded_file(image_file, "course-images"))
            course.images = image_urls
            if image_urls and not course.image_cover:
                course.image_cover = image_urls[0]
            course.save(update_fields=["images", "image_cover"])
            created_schedule = []
            for row in data["schedule"]:
                created_schedule.append(
                    CourseSchedule.objects.create(
                        course=course,
                        weekday=row["weekday"],
                        time_from=row["time_from"],
                        time_to=row["time_to"],
                        location_text=row.get("location_text") or "",
                    )
                )
            for schedule_row in created_schedule:
                lessons = expand_lessons_for_schedule(course.date_from, course.date_to, [row for row in data["schedule"] if row["weekday"] == schedule_row.weekday and row["time_from"] == schedule_row.time_from and row["time_to"] == schedule_row.time_to and (row.get("location_text") or "") == (schedule_row.location_text or "")])
                for lesson_data in lessons:
                    Lesson.objects.create(
                        course=course,
                        schedule=schedule_row,
                        lesson_date=lesson_data["lesson_date"],
                        time_from=lesson_data["time_from"],
                        time_to=lesson_data["time_to"],
                        location_text=lesson_data["location_text"],
                        status=LessonStatus.SCHEDULED,
                    )
        course = get_course_or_404(course.id)
        spots_left = build_spots_left_map([course]).get(course.id, course.capacity)
        create_favorite_teacher_new_course_notifications(course=course)
        return Response(serialize_course_detail(course, request=request, spots_left=spots_left), status=status.HTTP_201_CREATED)


class CourseRetrieveAPIView(APIView):
    def get(self, request, id: int):
        course = get_course_or_404(id)
        spots_left = build_spots_left_map([course]).get(course.id, course.capacity)
        viewer_context = build_course_viewer_context(course, getattr(request, "user", None))
        return Response(
            serialize_course_detail(
                course,
                request=request,
                spots_left=spots_left,
                viewer_context=viewer_context,
            )
        )

    @extend_schema(request=CourseWriteSerializer)
    def patch(self, request, id: int):
        teacher = get_owned_teacher(request)
        course = get_course_or_404(id)
        ensure_teacher_owns_course(teacher, course)
        first_lesson_at = first_lesson_start_at(course.lessons.all())
        if not has_hours_before(first_lesson_at, hours=48):
            raise ValidationError({"detail": "Course editing closes 48 hours before the first lesson."})
        serializer = CourseWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        regenerate_schedule = any(field in data for field in ["date_from", "date_to", "schedule"])
        should_notify_students = regenerate_schedule or any(
            field in data
            for field in [
                "dance_style_id",
                "studio_id",
                "name",
                "description",
                "music_artist",
                "music_track",
                "music_url",
                "level",
                "price",
                "capacity",
                "status",
            ]
        )
        with transaction.atomic():
            for field in [
                "dance_style_id",
                "studio_id",
                "name",
                "description",
                "music_artist",
                "music_track",
                "music_url",
                "level",
                "price",
                "capacity",
                "date_from",
                "date_to",
                "status",
            ]:
                if field in data:
                    setattr(course, field, data[field])
            if "ordered_image_urls" in data:
                course.images = serializer.normalized_image_urls("course-images")
            for image_file in request.FILES.getlist("image_files"):
                course.images.append(save_uploaded_file(image_file, "course-images"))
            if "image_cover" in data:
                course.image_cover = data.get("image_cover") or (course.images[0] if course.images else None)
            elif course.images and not course.image_cover:
                course.image_cover = course.images[0]
            course.save()
            if regenerate_schedule:
                if "schedule" in data:
                    schedule_rows = data["schedule"]
                else:
                    schedule_rows = [
                        {
                            "weekday": row.weekday,
                            "time_from": row.time_from,
                            "time_to": row.time_to,
                            "location_text": row.location_text or "",
                        }
                        for row in course.schedule_rows.all()
                    ]
                CourseSchedule.objects.filter(course=course).delete()
                Lesson.objects.filter(course=course).delete()
                created_schedule = [
                    CourseSchedule.objects.create(
                        course=course,
                        weekday=row["weekday"],
                        time_from=row["time_from"],
                        time_to=row["time_to"],
                        location_text=row.get("location_text") or "",
                    )
                    for row in schedule_rows
                ]
                for schedule_row in created_schedule:
                    lessons = expand_lessons_for_schedule(course.date_from, course.date_to, [row for row in schedule_rows if row["weekday"] == schedule_row.weekday and row["time_from"] == schedule_row.time_from and row["time_to"] == schedule_row.time_to and (row.get("location_text") or "") == (schedule_row.location_text or "")])
                    for lesson_data in lessons:
                        Lesson.objects.create(
                            course=course,
                            schedule=schedule_row,
                            lesson_date=lesson_data["lesson_date"],
                            time_from=lesson_data["time_from"],
                            time_to=lesson_data["time_to"],
                            location_text=lesson_data["location_text"],
                            status=LessonStatus.SCHEDULED,
                        )
        course = get_course_or_404(course.id)
        spots_left = build_spots_left_map([course]).get(course.id, course.capacity)
        if should_notify_students:
            create_course_updated_notifications(course=course, actor=teacher.user)
        return Response(serialize_course_detail(course, request=request, spots_left=spots_left))

    def delete(self, request, id: int):
        teacher = get_owned_teacher(request)
        course = get_course_or_404(id)
        ensure_teacher_owns_course(teacher, course)
        course.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CourseStudentListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id: int):
        teacher = get_owned_teacher(request)
        course = get_course_or_404(id)
        ensure_teacher_owns_course(teacher, course)
        enrollments = (
            Enrollment.objects.filter(course=course, status=EnrollmentStatus.ACTIVE)
            .select_related("user")
            .order_by("-enrolled_at")
        )
        return Response(
            [
                {
                    "enrollment_id": enrollment.id,
                    "user_id": enrollment.user_id,
                    "full_name": enrollment.user.get_full_name() or enrollment.user.email,
                    "email": enrollment.user.email,
                    "avatar": absolutize_media_url(request, enrollment.user.avatar) or "",
                    "dance_level": enrollment.user.dance_level or "",
                    "enrolled_at": enrollment.enrolled_at.isoformat(),
                    "status": enrollment.status,
                    "paid": enrollment.paid,
                }
                for enrollment in enrollments
            ]
        )


class CourseLessonListAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, _request, id: int):
        lessons = Lesson.objects.filter(course_id=id).order_by("lesson_date", "time_from")
        return Response([serialize_lesson(lesson) for lesson in lessons])


class CourseAttendanceListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id: int):
        teacher = get_owned_teacher(request)
        course = get_course_or_404(id)
        ensure_teacher_owns_course(teacher, course)
        marks = (
            AttendanceMark.objects.filter(lesson__course=course)
            .select_related("lesson", "student")
            .order_by("lesson__lesson_date", "student__last_name", "student__first_name")
        )
        return Response(
            [
                {
                    "id": mark.id,
                    "lesson_id": mark.lesson_id,
                    "lesson_date": mark.lesson.lesson_date.isoformat(),
                    "course_id": mark.lesson.course_id,
                    "course_name": mark.lesson.course.name,
                    "student_id": mark.student_id,
                    "student_name": mark.student.get_full_name() or mark.student.email,
                    "status": mark.status,
                    "marked_at": mark.marked_at.isoformat(),
                }
                for mark in marks
            ]
        )


class CourseAttendanceStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id: int):
        teacher = get_owned_teacher(request)
        course = get_course_or_404(id)
        ensure_teacher_owns_course(teacher, course)
        date_from = parse_query_date(request.query_params.get("date_from"), "date_from")
        date_to = parse_query_date(request.query_params.get("date_to"), "date_to")
        return Response(build_course_attendance_stats(course=course, date_from=date_from, date_to=date_to))


class LessonCancelAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None)
    def post(self, request, lesson_id: int):
        teacher = get_owned_teacher(request)
        lesson = Lesson.objects.select_related("course__teacher").filter(id=lesson_id).first()
        if lesson is None:
            raise ValidationError({"detail": "Lesson not found."})
        ensure_teacher_owns_course(teacher, lesson.course)
        lesson.status = LessonStatus.CANCELLED
        lesson.save(update_fields=["status"])
        create_lesson_changed_notifications(
            lesson=lesson,
            actor=teacher.user,
            title="Занятие отменено",
            body=f"Занятие курса «{lesson.course.name}» было отменено.",
        )
        return Response(serialize_lesson(lesson))


class AttendanceMarkAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=AttendanceMarkRequestSerializer)
    def post(self, request, lesson_id: int):
        teacher = get_owned_teacher(request)
        lesson = Lesson.objects.select_related("course__teacher").filter(id=lesson_id).first()
        if lesson is None:
            raise ValidationError({"detail": "Lesson not found."})
        ensure_teacher_owns_course(teacher, lesson.course)
        if timezone.now() < lesson_start_at(lesson.lesson_date, lesson.time_from):
            raise ValidationError({"detail": "Attendance can be marked only after the lesson starts."})
        serializer = AttendanceMarkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mark, _ = AttendanceMark.objects.update_or_create(
            lesson=lesson,
            student_id=serializer.validated_data["student_id"],
            defaults={"status": serializer.validated_data["status"], "marked_at": timezone.now()},
        )
        return Response(
            {
                "id": mark.id,
                "lesson_id": mark.lesson_id,
                "lesson_date": mark.lesson.lesson_date.isoformat(),
                "course_id": mark.lesson.course_id,
                "course_name": mark.lesson.course.name,
                "student_id": mark.student_id,
                "student_name": mark.student.get_full_name() or mark.student.email,
                "status": mark.status,
                "marked_at": mark.marked_at.isoformat(),
            }
        )


class LessonAttendanceListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, lesson_id: int):
        teacher = get_owned_teacher(request)
        lesson = Lesson.objects.select_related("course__teacher").filter(id=lesson_id).first()
        if lesson is None:
            raise ValidationError({"detail": "Lesson not found."})
        ensure_teacher_owns_course(teacher, lesson.course)
        marks = AttendanceMark.objects.filter(lesson=lesson).select_related("student").order_by("student__last_name", "student__first_name")
        return Response(
            [
                {
                    "id": mark.id,
                    "lesson_id": mark.lesson_id,
                    "lesson_date": mark.lesson.lesson_date.isoformat(),
                    "course_id": mark.lesson.course_id,
                    "course_name": mark.lesson.course.name,
                    "student_id": mark.student_id,
                    "student_name": mark.student.get_full_name() or mark.student.email,
                    "status": mark.status,
                    "marked_at": mark.marked_at.isoformat(),
                }
                for mark in marks
            ]
        )


class LessonRetrieveUpdateDestroyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=LessonUpdateSerializer)
    def patch(self, request, lesson_id: int):
        teacher = get_owned_teacher(request)
        lesson = Lesson.objects.select_related("course__teacher").filter(id=lesson_id).first()
        if lesson is None:
            raise ValidationError({"detail": "Lesson not found."})
        ensure_teacher_owns_course(teacher, lesson.course)
        serializer = LessonUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        should_notify_students = any(
            field in serializer.validated_data
            for field in ["lesson_date", "time_from", "time_to", "location_text", "hall", "status"]
        )
        for field, value in serializer.validated_data.items():
            setattr(lesson, field, value)
        lesson.save()
        if should_notify_students:
            create_lesson_changed_notifications(
                lesson=lesson,
                actor=teacher.user,
                title="Занятие изменено",
                body=f"Детали занятия курса «{lesson.course.name}» были изменены. Проверьте актуальное расписание.",
            )
        return Response(serialize_lesson(lesson))
