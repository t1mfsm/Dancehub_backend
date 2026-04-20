import json
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils import timezone
from rest_framework import serializers

from .constants import CourseLifecycleStatus
from .models import Attendance, Course, CourseImage, CourseScheduleRule, DanceStyle, Hall, Lesson, Review, Studio


def _build_absolute_url(value: str | None, request) -> str:
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    if request is None:
        return value
    return request.build_absolute_uri(value)


class DanceStyleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DanceStyle
        fields = ("id", "name", "slug")


class StudioSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Studio
        fields = (
            "id",
            "name",
            "city",
            "address",
            "metro",
            "lat",
            "lng",
            "image",
        )

    def get_image(self, obj: Studio) -> str:
        request = self.context.get("request")
        return _build_absolute_url(obj.image, request)


class HallShortSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    capacity = serializers.IntegerField(allow_null=True)


class StudioDetailSerializer(StudioSerializer):
    halls = serializers.SerializerMethodField()
    courses_count = serializers.IntegerField(read_only=True)

    class Meta(StudioSerializer.Meta):
        fields = StudioSerializer.Meta.fields + (
            "courses_count",
            "halls",
        )

    def get_halls(self, obj: Studio) -> list[dict]:
        return [
            {
                "id": hall.id,
                "name": hall.name,
                "capacity": hall.capacity,
            }
            for hall in obj.halls.all().order_by("name")
        ]


class MapPointSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True)
    halls_count = serializers.IntegerField(read_only=True)
    active_courses_count = serializers.IntegerField(read_only=True)
    dance_styles = serializers.SerializerMethodField()

    class Meta:
        model = Studio
        fields = (
            "id",
            "name",
            "city",
            "address",
            "metro",
            "lat",
            "lng",
            "image",
            "halls_count",
            "active_courses_count",
            "dance_styles",
        )

    def get_dance_styles(self, obj: Studio) -> list[str]:
        styles = obj.courses.select_related("dance_style").values_list("dance_style__name", flat=True).distinct()
        return list(styles)


WEEKDAY_TO_RU = {
    "mon": "Пн",
    "tue": "Вт",
    "wed": "Ср",
    "thu": "Чт",
    "fri": "Пт",
    "sat": "Сб",
    "sun": "Вс",
}
WEEKDAY_ORDER = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class CourseScheduleRuleSerializer(serializers.ModelSerializer):
    hall = serializers.CharField(source="hall.name", read_only=True)

    class Meta:
        model = CourseScheduleRule
        fields = (
            "id",
            "weekday",
            "time_from",
            "time_to",
            "hall",
            "location_text",
        )


def _format_schedule(course: Course, include_location: bool = False) -> list[dict]:
    """Формат расписания для списка и детальной карточки курса."""
    rules = list(course.schedule_rules.order_by("time_from", "weekday"))
    if not rules:
        return []

    grouped: dict[tuple, list[str]] = {}
    for r in rules:
        key = (r.time_from.strftime("%H:%M"), r.time_to.strftime("%H:%M"), r.location_text or "")
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(r.weekday)

    result = []
    for (time_from, time_to, location), weekdays in grouped.items():
        sorted_ru = [
            WEEKDAY_TO_RU[w]
            for w in sorted(weekdays, key=lambda x: WEEKDAY_ORDER.index(x) if x in WEEKDAY_ORDER else 99)
        ]
        item = {
            "weekday": ", ".join(sorted_ru),
            "time_from": time_from,
            "time_to": time_to,
        }
        if include_location:
            item["location"] = location or None

        result.append(item)
    return result


def _get_images_list(course: Course, request=None) -> list[str]:
    """Массив URL изображений (формат cards.ts: images: string[])."""
    imgs = list(course.images.all().order_by("sort_order", "id"))
    if imgs:
        return [_build_absolute_url(img.image, request) for img in imgs]
    if course.image_cover:
        return [_build_absolute_url(course.image_cover, request)]
    return []


class CourseListSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    teacher_id = serializers.IntegerField(source="teacher.id", read_only=True)
    teacher_name = serializers.SerializerMethodField()
    dance_style = serializers.CharField(source="dance_style.name", read_only=True)
    city = serializers.SerializerMethodField()
    studio = serializers.SerializerMethodField()
    schedule = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    spots_left = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = (
            "id",
            "name",
            "level",
            "price",
            "date_from",
            "date_to",
            "status",
            "image",
            "teacher_id",
            "teacher_name",
            "dance_style",
            "city",
            "studio",
            "schedule",
            "spots_left",
        )

    def get_city(self, obj: Course) -> str:
        return obj.studio.city.name if obj.studio and obj.studio.city else ""

    def get_studio(self, obj: Course) -> str:
        return obj.studio.name if obj.studio else ""

    def get_schedule(self, obj: Course) -> list[dict]:
        return _format_schedule(obj)

    def get_image(self, obj: Course) -> str:
        request = self.context.get("request")
        images = _get_images_list(obj, request)
        return images[0] if images else ""

    def get_teacher_name(self, obj: Course) -> str:
        return obj.teacher.user.get_full_name() or obj.teacher.user.email

    def get_spots_left(self, obj: Course) -> int:
        active = obj.enrollments.filter(status="active").count()
        return max(0, obj.capacity - active)

    def get_status(self, obj: Course) -> str:
        """Витрина: только active | completed по date_to (см. CourseLifecycleStatus)."""
        if hasattr(obj, "activity_status"):
            return obj.activity_status
        today = timezone.localdate()
        return (
            CourseLifecycleStatus.COMPLETED
            if obj.date_to < today
            else CourseLifecycleStatus.ACTIVE
        )


class CourseDetailSerializer(CourseListSerializer):
    music = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    schedule = serializers.SerializerMethodField()

    class Meta(CourseListSerializer.Meta):
        fields = (
            "id",
            "name",
            "description",
            "level",
            "price",
            "capacity",
            "spots_left",
            "date_from",
            "date_to",
            "status",
            "images",
            "teacher_id",
            "teacher_name",
            "dance_style",
            "city",
            "studio",
            "schedule",
            "music",
        )

    def get_schedule(self, obj: Course) -> list[dict]:
        return _format_schedule(obj, include_location=True)

    def get_music(self, obj: Course) -> dict:
        return {
            "artist": obj.music_artist or "",
            "track": obj.music_track or "",
            "url": obj.music_url or "",
        }

    def get_images(self, obj: Course) -> list[str]:
        request = self.context.get("request")
        return _get_images_list(obj, request)



class LessonSerializer(serializers.ModelSerializer):
    course_id = serializers.IntegerField(source="course.id", read_only=True)
    course_name = serializers.CharField(source="course.name", read_only=True)
    teacher_name = serializers.SerializerMethodField()
    hall = serializers.CharField(source="hall.name", read_only=True)
    studio = serializers.CharField(source="course.studio.name", read_only=True)
    city = serializers.CharField(source="course.studio.city.name", read_only=True)

    class Meta:
        model = Lesson
        fields = (
            "id",
            "course_id",
            "course_name",
            "teacher_name",
            "lesson_date",
            "time_from",
            "time_to",
            "location_text",
            "status",
            "hall",
            "studio",
            "city",
        )

    def get_teacher_name(self, obj: Lesson) -> str:
        return obj.course.teacher.user.get_full_name() or obj.course.teacher.user.email


class CalendarEventSerializer(serializers.ModelSerializer):
    course_id = serializers.IntegerField(source="course.id", read_only=True)
    course_name = serializers.CharField(source="course.name", read_only=True)
    teacher_name = serializers.SerializerMethodField()
    dance_style = serializers.CharField(source="course.dance_style.name", read_only=True)
    studio = serializers.CharField(source="course.studio.name", read_only=True)
    city = serializers.CharField(source="course.studio.city.name", read_only=True)
    start = serializers.SerializerMethodField()
    end = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = (
            "id",
            "course_id",
            "course_name",
            "teacher_name",
            "dance_style",
            "lesson_date",
            "time_from",
            "time_to",
            "start",
            "end",
            "location_text",
            "status",
            "studio",
            "city",
        )

    def get_teacher_name(self, obj: Lesson) -> str:
        return obj.course.teacher.user.get_full_name() or obj.course.teacher.user.email

    def get_start(self, obj: Lesson) -> str:
        return f"{obj.lesson_date}T{obj.time_from}"

    def get_end(self, obj: Lesson) -> str:
        return f"{obj.lesson_date}T{obj.time_to}"


class AttendanceSerializer(serializers.ModelSerializer):
    lesson_id = serializers.IntegerField(source="lesson.id", read_only=True)
    lesson_date = serializers.DateField(source="lesson.lesson_date", read_only=True)
    course_id = serializers.IntegerField(source="lesson.course.id", read_only=True)
    course_name = serializers.CharField(source="lesson.course.name", read_only=True)
    student_id = serializers.IntegerField(source="student.id", read_only=True)
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = (
            "id",
            "lesson_id",
            "lesson_date",
            "course_id",
            "course_name",
            "student_id",
            "student_name",
            "status",
            "marked_at",
        )

    def get_student_name(self, obj: Attendance) -> str:
        return obj.student.get_full_name() or obj.student.email


class AttendanceMarkSerializer(serializers.Serializer):
    student_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=Attendance._meta.get_field("status").choices)


class CourseStudentSerializer(serializers.Serializer):
    enrollment_id = serializers.IntegerField(source="id")
    user_id = serializers.IntegerField(source="user.id")
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email")
    phone = serializers.CharField(source="user.phone")
    dance_level = serializers.CharField(source="user.dance_level")
    enrolled_at = serializers.DateField()
    status = serializers.CharField()
    paid = serializers.BooleanField()

    def get_full_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.email


class CourseReviewCreateSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(required=False, allow_blank=True)


class CourseReviewSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ("id", "author_name", "rating", "text", "created_at")

    def get_author_name(self, obj) -> str:
        return obj.author_user.get_full_name() or obj.author_user.email


class CourseScheduleRuleWriteSerializer(serializers.Serializer):
    weekday = serializers.ChoiceField(choices=CourseScheduleRule._meta.get_field("weekday").choices)
    time_from = serializers.TimeField()
    time_to = serializers.TimeField()
    hall_id = serializers.PrimaryKeyRelatedField(
        source="hall",
        queryset=Hall.objects.all(),
        allow_null=True,
        required=False,
    )
    location_text = serializers.CharField(required=False, allow_blank=True)


class CourseWriteSerializer(serializers.ModelSerializer):
    teacher_id = serializers.IntegerField(write_only=True, required=False)
    image_file = serializers.FileField(write_only=True, required=False)
    image_files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=False,
    )
    music_artist = serializers.CharField(write_only=True, required=False, allow_blank=True)
    music_track = serializers.CharField(write_only=True, required=False, allow_blank=True)
    music_url = serializers.URLField(write_only=True, required=False, allow_blank=True)
    dance_style_id = serializers.PrimaryKeyRelatedField(
        source="dance_style",
        queryset=DanceStyle.objects.all(),
    )
    studio_id = serializers.PrimaryKeyRelatedField(
        source="studio",
        queryset=Studio.objects.all(),
        allow_null=True,
        required=False,
    )
    hall_id = serializers.PrimaryKeyRelatedField(
        source="hall",
        queryset=Hall.objects.all(),
        allow_null=True,
        required=False,
    )
    schedule = CourseScheduleRuleWriteSerializer(many=True, required=False)
    ordered_image_urls = serializers.ListField(
        child=serializers.URLField(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Course
        fields = (
            "teacher_id",
            "dance_style_id",
            "studio_id",
            "hall_id",
            "name",
            "description",
            "level",
            "price",
            "capacity",
            "date_from",
            "date_to",
            "status",
            "image_cover",
            "image_file",
            "image_files",
            "ordered_image_urls",
            "music_artist",
            "music_track",
            "music_url",
            "schedule",
        )
        extra_kwargs = {
            "image_cover": {
                "required": False,
                "allow_null": True,
                "allow_blank": True,
            }
        }

    def to_internal_value(self, data):
        mutable_data = data.copy()
        schedule = mutable_data.get("schedule")

        if isinstance(schedule, str):
            mutable_data["schedule"] = json.loads(schedule)

        request = self.context.get("request")
        if request is not None:
            uploaded_images = request.FILES.getlist("image_files")
            if uploaded_images:
                mutable_data.setlist("image_files", uploaded_images)

        return super().to_internal_value(mutable_data)

    def create(self, validated_data):
        image_file = validated_data.pop("image_file", None)
        image_files = validated_data.pop("image_files", [])
        validated_data.pop("ordered_image_urls", None)
        schedule_data = validated_data.pop("schedule", [])
        self._apply_uploaded_image(validated_data, image_file)
        if validated_data.get("image_cover") is None:
            validated_data["image_cover"] = ""
        course = super().create(validated_data)
        self._save_uploaded_images(course, image_files)
        self._save_schedule(course, schedule_data)
        return course

    def update(self, instance, validated_data):
        image_file = validated_data.pop("image_file", None)
        image_files = validated_data.pop("image_files", [])
        ordered_image_urls = validated_data.pop("ordered_image_urls", None)
        schedule_data = validated_data.pop("schedule", None)
        self._apply_uploaded_image(validated_data, image_file)
        if validated_data.get("image_cover") is None:
            validated_data["image_cover"] = ""
        course = super().update(instance, validated_data)
        if image_files:
            self._save_uploaded_images(course, image_files, replace_existing=True)
        elif ordered_image_urls:
            self._apply_ordered_gallery_urls(course, ordered_image_urls)
        if schedule_data is not None:
            self._save_schedule(course, schedule_data)
        return course

    def _save_schedule(self, course: Course, schedule_data: list[dict]) -> None:
        course.schedule_rules.all().delete()
        if not schedule_data:
            return

        CourseScheduleRule.objects.bulk_create(
            [
                CourseScheduleRule(
                    course=course,
                    weekday=item["weekday"],
                    time_from=item["time_from"],
                    time_to=item["time_to"],
                    hall=item.get("hall"),
                    location_text=item.get("location_text", ""),
                )
                for item in schedule_data
            ]
        )

    @staticmethod
    def _urls_equal_for_gallery(stored: str, client: str) -> bool:
        a = (stored or "").strip().rstrip("/")
        b = (client or "").strip().rstrip("/")
        if a == b:
            return True
        return Path(a).name == Path(b).name

    def _apply_ordered_gallery_urls(self, course: Course, urls: list[str]) -> None:
        if not urls:
            return

        remaining = list(course.images.all())
        for index, url in enumerate(urls):
            match = None
            for ci in remaining:
                if self._urls_equal_for_gallery(ci.image, url):
                    match = ci
                    break
            if match is None:
                continue
            if match.sort_order != index:
                match.sort_order = index
                match.save(update_fields=["sort_order"])
            remaining.remove(match)

        course.image_cover = urls[0]
        course.save(update_fields=["image_cover"])

    def _save_uploaded_images(
        self,
        course: Course,
        image_files: list,
        replace_existing: bool = False,
    ) -> None:
        if not image_files:
            return

        if replace_existing:
            course.images.all().delete()

        image_urls = [self._store_uploaded_file(image_file) for image_file in image_files]

        CourseImage.objects.bulk_create(
            [
                CourseImage(
                    course=course,
                    image=image_url,
                    sort_order=index,
                )
                for index, image_url in enumerate(image_urls)
            ]
        )

        course.image_cover = image_urls[0]
        course.save(update_fields=["image_cover"])

    def _apply_uploaded_image(self, validated_data: dict, image_file) -> None:
        if not image_file:
            return

        validated_data["image_cover"] = self._store_uploaded_file(image_file)

    def _store_uploaded_file(self, image_file) -> str:
        extension = Path(image_file.name).suffix or ".jpg"
        filename = f"courses/{uuid.uuid4().hex}{extension}"
        stored_path = default_storage.save(filename, image_file)
        media_url = f"{settings.MEDIA_URL}{stored_path}".replace("//", "/")
        request = self.context.get("request")

        if request is not None:
            return request.build_absolute_uri(media_url)

        return media_url


class LessonWriteSerializer(serializers.ModelSerializer):
    schedule_rule_id = serializers.PrimaryKeyRelatedField(
        source="schedule_rule",
        queryset=CourseScheduleRule.objects.all(),
        allow_null=True,
        required=False,
    )
    hall_id = serializers.PrimaryKeyRelatedField(
        source="hall",
        queryset=Hall.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Lesson
        fields = (
            "schedule_rule_id",
            "hall_id",
            "lesson_date",
            "time_from",
            "time_to",
            "location_text",
            "status",
        )
