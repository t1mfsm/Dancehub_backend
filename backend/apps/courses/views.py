from datetime import datetime

from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.choices import AttendanceStatus, EnrollmentStatus, LessonStatus
from apps.common.files import save_uploaded_file
from apps.common.utils import build_full_name, course_lifecycle_status, lesson_lifecycle_status, lesson_start_iso
from apps.courses.models import AttendanceMark, Course, CourseSchedule, DanceStyle, Enrollment, Lesson, Studio
from apps.users.models import TeacherProfile, User

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
        .prefetch_related("schedule_rows")
        .annotate(active_enrollments=Count("enrollments", filter=Q(enrollments__status=EnrollmentStatus.ACTIVE)))
        .first()
    )
    if course is None:
        raise ValidationError({"detail": "Course not found."})
    return course


def ensure_teacher_owns_course(teacher: TeacherProfile, course: Course) -> None:
    if course.teacher_id != teacher.id:
        raise PermissionDenied("You can manage only your own courses.")


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
        if status_filter:
            courses = [
                course
                for course in courses
                if course_lifecycle_status(course.status, course.date_from, course.date_to) == status_filter
            ]
        return Response(
            [
                serialize_course_list_item(course, request=request, spots_left=course.capacity - course.active_enrollments)
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
        return Response(serialize_course_detail(course, request=request, spots_left=course.capacity - course.active_enrollments), status=status.HTTP_201_CREATED)


class CourseRetrieveAPIView(APIView):
    def get(self, request, id: int):
        course = get_course_or_404(id)
        return Response(serialize_course_detail(course, request=request, spots_left=course.capacity - course.active_enrollments))

    @extend_schema(request=CourseWriteSerializer)
    def patch(self, request, id: int):
        teacher = get_owned_teacher(request)
        course = get_course_or_404(id)
        ensure_teacher_owns_course(teacher, course)
        serializer = CourseWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        regenerate_schedule = any(field in data for field in ["date_from", "date_to", "schedule"])
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
        return Response(serialize_course_detail(course, request=request, spots_left=course.capacity - course.active_enrollments))

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
            Enrollment.objects.filter(course=course)
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
                    "phone": enrollment.user.phone or "",
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
        lessons = Lesson.objects.filter(course=course).order_by("lesson_date", "time_from")
        if date_from := request.query_params.get("date_from"):
            lessons = lessons.filter(lesson_date__gte=date_from)
        if date_to := request.query_params.get("date_to"):
            lessons = lessons.filter(lesson_date__lte=date_to)
        lesson_ids = list(lessons.values_list("id", flat=True))
        marks = AttendanceMark.objects.filter(lesson_id__in=lesson_ids).select_related("student", "lesson")
        students = (
            User.objects.filter(enrollments__course=course)
            .distinct()
            .order_by("last_name", "first_name")
        )
        per_lesson = []
        attendance_percentages = []
        for lesson in lessons:
            present = marks.filter(lesson=lesson, status=AttendanceStatus.PRESENT).count()
            absent = marks.filter(lesson=lesson, status=AttendanceStatus.ABSENT).count()
            total = present + absent
            percent = round((present / total) * 100, 2) if total else 0
            attendance_percentages.append(percent)
            per_lesson.append(
                {
                    "lesson_id": lesson.id,
                    "date": lesson.lesson_date.isoformat(),
                    "present": present,
                    "absent": absent,
                    "total": total,
                    "percent": percent,
                }
            )
        per_student = []
        for student in students:
            student_marks = marks.filter(student=student)
            attended = student_marks.filter(status=AttendanceStatus.PRESENT).count()
            missed = student_marks.filter(status=AttendanceStatus.ABSENT).count()
            total = attended + missed
            percent = round((attended / total) * 100, 2) if total else 0
            per_student.append(
                {
                    "student_id": student.id,
                    "student_name": student.get_full_name() or student.email,
                    "attended": attended,
                    "missed": missed,
                    "total": total,
                    "percent": percent,
                }
            )
        return Response(
            {
                "total_lessons": lessons.count(),
                "conducted_lessons": lessons.exclude(status=LessonStatus.CANCELLED).filter(lesson_date__lt=datetime.now().date()).count(),
                "cancelled_lessons": lessons.filter(status=LessonStatus.CANCELLED).count(),
                "avg_attendance_percent": round(sum(attendance_percentages) / len(attendance_percentages), 2) if attendance_percentages else 0,
                "total_students": students.count(),
                "per_lesson": per_lesson,
                "per_student": per_student,
            }
        )


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
        for field, value in serializer.validated_data.items():
            setattr(lesson, field, value)
        lesson.save()
        return Response(serialize_lesson(lesson))
