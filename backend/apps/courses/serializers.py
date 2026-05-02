from django.utils import timezone
from rest_framework import serializers

from .constants import CourseLifecycleStatus
from .lesson_utils import can_cancel_lesson, effective_lesson_status
from .models import (
    AttendanceMark,
    Course,
    CourseSchedule,
    CourseStatus,
    DanceStyle,
    Enrollment,
    Lesson,
    LessonStatus,
    Studio,
)
from .services import refresh_course_lessons_from_schedule


# ---------------------------------------------------------------------------
# Reference
# ---------------------------------------------------------------------------

class DanceStyleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DanceStyle
        fields = ("id", "name", "slug")


class StudioSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True)

    class Meta:
        model = Studio
        fields = ("id", "name", "city", "address", "metro", "lat", "lng", "image", "halls_count")


class StudioDetailSerializer(StudioSerializer):
    courses_count = serializers.IntegerField(read_only=True)

    class Meta(StudioSerializer.Meta):
        fields = StudioSerializer.Meta.fields + ("courses_count",)


class MapPointSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True)
    active_courses_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Studio
        fields = ("id", "name", "city", "address", "metro", "lat", "lng", "image", "halls_count", "active_courses_count")


# ---------------------------------------------------------------------------
# Schedule / Lesson
# ---------------------------------------------------------------------------

class CourseScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseSchedule
        fields = ("id", "weekday", "time_from", "time_to", "location_text")


class CourseScheduleWriteSerializer(serializers.Serializer):
    weekday = serializers.ChoiceField(choices=["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
    time_from = serializers.TimeField()
    time_to = serializers.TimeField()
    location_text = serializers.CharField(max_length=255, required=False, default="")


class LessonSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = (
            "id",
            "course",
            "lesson_date",
            "time_from",
            "time_to",
            "location_text",
            "hall",
            "status",
            "can_cancel",
        )

    def get_status(self, obj: Lesson) -> str:
        return effective_lesson_status(obj)

    def get_can_cancel(self, obj: Lesson) -> bool:
        ok, _ = can_cancel_lesson(obj)
        return ok


class LessonWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ("lesson_date", "time_from", "time_to", "location_text", "hall", "status")


# ---------------------------------------------------------------------------
# Course list / detail / write
# ---------------------------------------------------------------------------

class TeacherShortSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    middle_name = serializers.CharField()
    avatar = serializers.URLField()


class CourseListSerializer(serializers.ModelSerializer):
    teacher = serializers.SerializerMethodField()
    dance_style = DanceStyleSerializer(read_only=True)
    studio = StudioSerializer(read_only=True)
    schedule = CourseScheduleSerializer(source="schedule_rules", many=True, read_only=True)
    status = serializers.SerializerMethodField()
    spots_left = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            "id",
            "name",
            "description",
            "teacher",
            "dance_style",
            "studio",
            "level",
            "price",
            "capacity",
            "spots_left",
            "date_from",
            "date_to",
            "status",
            "images",
            "image_cover",
            "music_artist",
            "music_track",
            "music_url",
            "schedule",
        )

    def get_teacher(self, obj):
        u = obj.teacher.user
        return {
            "id": obj.teacher.id,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "middle_name": u.middle_name,
            "avatar": u.avatar,
        }

    def get_status(self, obj) -> str:
        today = timezone.localdate()
        if obj.date_to < today:
            return CourseLifecycleStatus.COMPLETED
        return CourseLifecycleStatus.ACTIVE

    def get_spots_left(self, obj) -> int:
        active_count = obj.enrollments.filter(
            status__in=["active", "pending", "completed"]
        ).count()
        return max(0, obj.capacity - active_count)


class CourseDetailSerializer(CourseListSerializer):
    pass


class CourseWriteSerializer(serializers.Serializer):
    dance_style_id = serializers.IntegerField()
    studio_id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="")
    level = serializers.ChoiceField(choices=["beginner", "intermediate", "advanced"])
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    capacity = serializers.IntegerField(min_value=1)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    status = serializers.ChoiceField(
        choices=CourseStatus.values,
        required=False,
        default=CourseStatus.PUBLISHED,
    )
    images = serializers.ListField(child=serializers.URLField(), required=False, default=list)
    image_cover = serializers.URLField(required=False, default="")
    music_artist = serializers.CharField(max_length=255, required=False, default="")
    music_track = serializers.CharField(max_length=255, required=False, default="")
    music_url = serializers.URLField(required=False, default="")
    schedule = CourseScheduleWriteSerializer(many=True, required=False, default=list)
    teacher_id = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        if data.get("date_from") and data.get("date_to"):
            if data["date_from"] > data["date_to"]:
                raise serializers.ValidationError("date_from must be before date_to.")
        return data

    def _get_dance_style(self, dance_style_id):
        from .models import DanceStyle as DS
        try:
            return DS.objects.get(id=dance_style_id)
        except DS.DoesNotExist:
            raise serializers.ValidationError({"dance_style_id": "Dance style not found."})

    def _get_studio(self, studio_id):
        if studio_id is None:
            return None
        try:
            return Studio.objects.get(id=studio_id)
        except Studio.DoesNotExist:
            raise serializers.ValidationError({"studio_id": "Studio not found."})

    def create(self, validated_data):
        schedule_data = validated_data.pop("schedule", [])
        validated_data.pop("teacher_id", None)
        dance_style = self._get_dance_style(validated_data.pop("dance_style_id"))
        studio = self._get_studio(validated_data.pop("studio_id", None))

        course = Course.objects.create(
            dance_style=dance_style,
            studio=studio,
            **validated_data,
        )

        for item in schedule_data:
            CourseSchedule.objects.create(course=course, **item)

        refresh_course_lessons_from_schedule(course)
        return course

    def update(self, instance, validated_data):
        schedule_data = validated_data.pop("schedule", None)
        validated_data.pop("teacher_id", None)

        if "dance_style_id" in validated_data:
            instance.dance_style = self._get_dance_style(validated_data.pop("dance_style_id"))
        if "studio_id" in validated_data:
            instance.studio = self._get_studio(validated_data.pop("studio_id"))

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if schedule_data is not None:
            instance.schedule_rules.all().delete()
            for item in schedule_data:
                CourseSchedule.objects.create(course=instance, **item)
            refresh_course_lessons_from_schedule(instance)

        return instance


# ---------------------------------------------------------------------------
# Enrollment / Students
# ---------------------------------------------------------------------------

class CourseStudentSerializer(serializers.ModelSerializer):
    student_id = serializers.IntegerField(source="user.id")
    email = serializers.EmailField(source="user.email")
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    middle_name = serializers.CharField(source="user.middle_name")
    avatar = serializers.URLField(source="user.avatar")

    class Meta:
        model = Enrollment
        fields = (
            "student_id",
            "email",
            "first_name",
            "last_name",
            "middle_name",
            "avatar",
            "status",
            "paid",
            "enrolled_at",
        )


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

class AttendanceSerializer(serializers.ModelSerializer):
    student_id = serializers.IntegerField(source="student.id")
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceMark
        fields = ("id", "lesson", "student_id", "student_name", "status", "marked_at")

    def get_student_name(self, obj) -> str:
        return obj.student.get_full_name() or obj.student.email


class AttendanceMarkSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["present", "absent"])


# ---------------------------------------------------------------------------
# Attendance stats (delegated to stats_service)
# ---------------------------------------------------------------------------

class CourseAttendanceStatsSerializer(serializers.Serializer):
    total_lessons = serializers.IntegerField()
    conducted_lessons = serializers.IntegerField()
    cancelled_lessons = serializers.IntegerField()
    avg_attendance_percent = serializers.IntegerField()
    total_students = serializers.IntegerField()
    per_lesson = serializers.ListField()
    per_student = serializers.ListField()


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

class CalendarEventSerializer(serializers.ModelSerializer):
    course_id = serializers.IntegerField(source="course.id")
    course_name = serializers.CharField(source="course.name")
    dance_style = serializers.CharField(source="course.dance_style.name")
    teacher_name = serializers.SerializerMethodField()
    studio_name = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = (
            "id",
            "course_id",
            "course_name",
            "dance_style",
            "teacher_name",
            "studio_name",
            "lesson_date",
            "time_from",
            "time_to",
            "location_text",
            "hall",
            "status",
        )

    def get_teacher_name(self, obj) -> str:
        u = obj.course.teacher.user
        return u.get_full_name() or u.email

    def get_studio_name(self, obj) -> str:
        return obj.course.studio.name if obj.course.studio else ""

    def get_status(self, obj) -> str:
        return effective_lesson_status(obj)
