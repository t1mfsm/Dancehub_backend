from rest_framework import serializers

from .models import Attendance, Course, CourseScheduleRule, DanceStyle, Hall, Lesson, Review, Studio


class DanceStyleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DanceStyle
        fields = ("id", "name", "slug")


class StudioSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True)

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


class CourseListSerializer(serializers.ModelSerializer):
    teacher_id = serializers.IntegerField(source="teacher.id", read_only=True)
    teacher_name = serializers.SerializerMethodField()
    dance_style = serializers.CharField(source="dance_style.name", read_only=True)
    dance_style_slug = serializers.CharField(source="dance_style.slug", read_only=True)
    city = serializers.CharField(source="studio.city.name", read_only=True)
    studio = serializers.CharField(source="studio.name", read_only=True)
    hall = serializers.CharField(source="hall.name", read_only=True)

    class Meta:
        model = Course
        fields = (
            "id",
            "name",
            "description",
            "level",
            "price",
            "capacity",
            "date_from",
            "date_to",
            "status",
            "image_cover",
            "teacher_id",
            "teacher_name",
            "dance_style",
            "dance_style_slug",
            "city",
            "studio",
            "hall",
        )

    def get_teacher_name(self, obj: Course) -> str:
        return obj.teacher.user.get_full_name() or obj.teacher.user.email


class CourseDetailSerializer(CourseListSerializer):
    music = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    schedule_rules = CourseScheduleRuleSerializer(many=True, read_only=True)
    studio_data = StudioSerializer(source="studio", read_only=True)
    reviews_count = serializers.IntegerField(source="reviews.count", read_only=True)

    class Meta(CourseListSerializer.Meta):
        fields = CourseListSerializer.Meta.fields + (
            "music",
            "images",
            "schedule_rules",
            "studio_data",
            "reviews_count",
        )

    def get_music(self, obj: Course) -> dict | None:
        if not hasattr(obj, "music"):
            return None

        return {
            "artist": obj.music.artist,
            "track": obj.music.track,
            "url": obj.music.url,
        }

    def get_images(self, obj: Course) -> list[dict]:
        return [
            {
                "id": image.id,
                "image": image.image,
                "sort_order": image.sort_order,
            }
            for image in obj.images.all()
        ]


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


class CourseWriteSerializer(serializers.ModelSerializer):
    teacher_id = serializers.IntegerField(write_only=True, required=False)
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
        )


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
