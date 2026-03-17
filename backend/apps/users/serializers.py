from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.courses.models import Course, DanceStyle, Enrollment, FavoriteCourse, Lesson
from apps.locations.models import City

from .models import (
    FavoriteTeacher,
    TeacherAchievement,
    TeacherProfile,
    TeacherReview,
    User,
    UserPreference,
    UserPreferredWeekday,
    UserSkill,
)


class TeacherAchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherAchievement
        fields = ("id", "title", "description", "achieved_at")


class TeacherReviewSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TeacherReview
        fields = ("id", "author_name", "rating", "text", "created_at")

    def get_author_name(self, obj: TeacherReview) -> str:
        return obj.author_user.get_full_name() or obj.author_user.email


class TeacherCourseShortSerializer(serializers.ModelSerializer):
    dance_style = serializers.CharField(source="dance_style.name", read_only=True)
    studio = serializers.CharField(source="studio.name", read_only=True)

    class Meta:
        model = Course
        fields = (
            "id",
            "name",
            "dance_style",
            "level",
            "price",
            "date_from",
            "date_to",
            "status",
            "studio",
        )


class TeacherListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    city = serializers.CharField(source="user.city.name", read_only=True)

    class Meta:
        model = TeacherProfile
        fields = (
            "id",
            "full_name",
            "bio",
            "experience_years",
            "rating_avg",
            "rating_count",
            "city",
        )

    def get_full_name(self, obj: TeacherProfile) -> str:
        return obj.user.get_full_name() or obj.user.email


class TeacherDetailSerializer(TeacherListSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    avatar = serializers.CharField(source="user.avatar", read_only=True)
    specializations = serializers.SerializerMethodField()
    achievements = TeacherAchievementSerializer(many=True, read_only=True)
    reviews = TeacherReviewSerializer(many=True, read_only=True)
    courses = TeacherCourseShortSerializer(many=True, read_only=True)

    class Meta(TeacherListSerializer.Meta):
        fields = TeacherListSerializer.Meta.fields + (
            "email",
            "phone",
            "avatar",
            "specializations",
            "achievements",
            "reviews",
            "courses",
        )

    def get_specializations(self, obj: TeacherProfile) -> list[dict]:
        return [
            {
                "id": item.dance_style.id,
                "name": item.dance_style.name,
                "slug": item.dance_style.slug,
            }
            for item in obj.specializations.all()
        ]


class UserSkillSerializer(serializers.ModelSerializer):
    dance_style_id = serializers.IntegerField(source="dance_style.id", read_only=True)
    dance_style = serializers.CharField(source="dance_style.name", read_only=True)
    dance_style_slug = serializers.CharField(source="dance_style.slug", read_only=True)

    class Meta:
        model = UserSkill
        fields = ("id", "dance_style_id", "dance_style", "dance_style_slug", "level")


class MeSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True)
    city_id = serializers.IntegerField(source="city.id", read_only=True)
    skills = UserSkillSerializer(many=True, read_only=True)
    favorite_course_ids = serializers.SerializerMethodField()
    favorite_teacher_ids = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "city",
            "city_id",
            "dance_level",
            "role",
            "is_teacher_enabled",
            "survey_completed",
            "favorite_course_ids",
            "favorite_teacher_ids",
            "skills",
        )

    def get_favorite_course_ids(self, obj: User) -> list[int]:
        return list(obj.favorite_courses.values_list("course_id", flat=True))

    def get_favorite_teacher_ids(self, obj: User) -> list[int]:
        return list(obj.favorite_teachers.values_list("teacher_id", flat=True))


class MeUpdateSerializer(serializers.ModelSerializer):
    city_id = serializers.PrimaryKeyRelatedField(
        source="city",
        queryset=City.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "city_id",
            "dance_level",
            "survey_completed",
        )


class UserPreferenceSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True)
    city_id = serializers.PrimaryKeyRelatedField(
        source="city",
        queryset=City.objects.all(),
        allow_null=True,
        required=False,
    )
    preferred_dance_style_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        write_only=True,
    )
    preferred_dance_styles = serializers.SerializerMethodField()
    preferred_weekdays = serializers.ListField(
        child=serializers.CharField(max_length=3),
        required=False,
    )

    class Meta:
        model = UserPreference
        fields = (
            "id",
            "city",
            "city_id",
            "level",
            "preferred_time_from",
            "preferred_time_to",
            "price_from",
            "price_to",
            "goal",
            "preferred_dance_style_ids",
            "preferred_dance_styles",
            "preferred_weekdays",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_preferred_weekdays(self, value: list[str]) -> list[str]:
        valid_values = {choice[0] for choice in UserPreferredWeekday._meta.get_field("weekday").choices}
        invalid = [item for item in value if item not in valid_values]
        if invalid:
            raise serializers.ValidationError(f"Недопустимые дни недели: {', '.join(invalid)}")
        return value

    def validate_preferred_dance_style_ids(self, value: list[int]) -> list[int]:
        existing_ids = set(DanceStyle.objects.filter(id__in=value).values_list("id", flat=True))
        missing_ids = [item for item in value if item not in existing_ids]
        if missing_ids:
            raise serializers.ValidationError(f"Стили не найдены: {', '.join(map(str, missing_ids))}")
        return value

    def get_preferred_dance_styles(self, obj: UserPreference) -> list[dict]:
        return [
            {
                "id": item.dance_style_id,
                "name": item.dance_style.name,
                "slug": item.dance_style.slug,
            }
            for item in obj.preferred_dance_styles.select_related("dance_style").all()
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["preferred_weekdays"] = list(
            instance.preferred_weekdays.values_list("weekday", flat=True).order_by("weekday")
        )
        return data

    def create(self, validated_data):
        preferred_style_ids = validated_data.pop("preferred_dance_style_ids", [])
        preferred_weekdays = validated_data.pop("preferred_weekdays", [])
        preference = UserPreference.objects.create(**validated_data)
        self._save_relations(preference, preferred_style_ids, preferred_weekdays)
        return preference

    def update(self, instance, validated_data):
        preferred_style_ids = validated_data.pop("preferred_dance_style_ids", None)
        preferred_weekdays = validated_data.pop("preferred_weekdays", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        self._save_relations(instance, preferred_style_ids, preferred_weekdays)
        return instance

    def _save_relations(
        self,
        preference: UserPreference,
        preferred_style_ids: list[int] | None,
        preferred_weekdays: list[str] | None,
    ) -> None:
        if preferred_style_ids is not None:
            preference.preferred_dance_styles.exclude(dance_style_id__in=preferred_style_ids).delete()
            existing_ids = set(
                preference.preferred_dance_styles.values_list("dance_style_id", flat=True)
            )
            for style_id in preferred_style_ids:
                if style_id not in existing_ids:
                    preference.preferred_dance_styles.create(dance_style_id=style_id)

        if preferred_weekdays is not None:
            preference.preferred_weekdays.exclude(weekday__in=preferred_weekdays).delete()
            existing_weekdays = set(preference.preferred_weekdays.values_list("weekday", flat=True))
            for weekday in preferred_weekdays:
                if weekday not in existing_weekdays:
                    preference.preferred_weekdays.create(weekday=weekday)


class FavoriteCourseSerializer(serializers.ModelSerializer):
    course = serializers.SerializerMethodField()

    class Meta:
        model = FavoriteCourse
        fields = ("id", "course", "created_at")

    def get_course(self, obj: FavoriteCourse) -> dict:
        teacher = obj.course.teacher

        return {
            "id": obj.course.id,
            "name": obj.course.name,
            "level": obj.course.level,
            "price": str(obj.course.price),
            "status": obj.course.status,
            "teacher": {
                "id": teacher.id,
                "full_name": teacher.user.get_full_name() or teacher.user.email,
                "rating_avg": str(teacher.rating_avg),
                "rating_count": teacher.rating_count,
            },
        }


class FavoriteTeacherSerializer(serializers.ModelSerializer):
    teacher = serializers.SerializerMethodField()

    class Meta:
        model = FavoriteTeacher
        fields = ("id", "teacher", "created_at")

    def get_teacher(self, obj: FavoriteTeacher) -> dict:
        return {
            "id": obj.teacher.id,
            "full_name": obj.teacher.user.get_full_name() or obj.teacher.user.email,
            "rating_avg": str(obj.teacher.rating_avg),
            "rating_count": obj.teacher.rating_count,
        }


class EnrollmentSerializer(serializers.ModelSerializer):
    course = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = (
            "id",
            "course",
            "enrolled_at",
            "status",
            "paid",
            "cancelled_at",
        )

    def get_course(self, obj: Enrollment) -> dict:
        return {
            "id": obj.course.id,
            "name": obj.course.name,
            "level": obj.course.level,
            "status": obj.course.status,
        }


class MyCourseSerializer(serializers.ModelSerializer):
    course = serializers.SerializerMethodField()
    teacher = serializers.SerializerMethodField()
    dance_style = serializers.CharField(source="course.dance_style.name", read_only=True)
    studio = serializers.CharField(source="course.studio.name", read_only=True)
    city = serializers.CharField(source="course.studio.city.name", read_only=True)

    class Meta:
        model = Enrollment
        fields = (
            "id",
            "enrolled_at",
            "status",
            "paid",
            "cancelled_at",
            "teacher",
            "dance_style",
            "studio",
            "city",
            "course",
        )

    def get_teacher(self, obj: Enrollment) -> dict:
        teacher = obj.course.teacher
        return {
            "id": teacher.id,
            "full_name": teacher.user.get_full_name() or teacher.user.email,
        }

    def get_course(self, obj: Enrollment) -> dict:
        return {
            "id": obj.course.id,
            "name": obj.course.name,
            "level": obj.course.level,
            "price": str(obj.course.price),
            "date_from": obj.course.date_from,
            "date_to": obj.course.date_to,
            "status": obj.course.status,
        }


class TeachingCourseSerializer(serializers.ModelSerializer):
    dance_style = serializers.CharField(source="dance_style.name", read_only=True)
    studio = serializers.CharField(source="studio.name", read_only=True)
    students_count = serializers.IntegerField(read_only=True)
    lessons_count = serializers.IntegerField(read_only=True)

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
            "dance_style",
            "studio",
            "students_count",
            "lessons_count",
        )


class TeacherCourseListSerializer(serializers.ModelSerializer):
    dance_style = serializers.CharField(source="dance_style.name", read_only=True)
    studio = serializers.CharField(source="studio.name", read_only=True)

    class Meta:
        model = Course
        fields = (
            "id",
            "name",
            "description",
            "level",
            "price",
            "date_from",
            "date_to",
            "status",
            "dance_style",
            "studio",
        )


class TeacherReviewCreateSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(required=False, allow_blank=True)


class CourseRecommendationSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    dance_style = serializers.CharField(source="dance_style.name", read_only=True)
    dance_style_slug = serializers.CharField(source="dance_style.slug", read_only=True)
    studio = serializers.CharField(source="studio.name", read_only=True)
    city = serializers.CharField(source="studio.city.name", read_only=True)
    recommendation_reason = serializers.CharField(read_only=True)
    recommendation_score = serializers.IntegerField(read_only=True)
    recommendation_reasons = serializers.SerializerMethodField()

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
            "teacher_name",
            "dance_style",
            "dance_style_slug",
            "studio",
            "city",
            "recommendation_reason",
            "recommendation_score",
            "recommendation_reasons",
        )

    def get_teacher_name(self, obj: Course) -> str:
        return obj.teacher.user.get_full_name() or obj.teacher.user.email

    def get_recommendation_reasons(self, obj: Course) -> list[str]:
        return getattr(obj, "recommendation_reasons", [])


class UserSkillWriteItemSerializer(serializers.Serializer):
    dance_style_id = serializers.PrimaryKeyRelatedField(queryset=DanceStyle.objects.all(), source="dance_style")
    level = serializers.ChoiceField(choices=UserSkill._meta.get_field("level").choices)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Пароли не совпадают."})
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class CourseDashboardItemSerializer(serializers.ModelSerializer):
    students_count = serializers.IntegerField(read_only=True)
    lessons_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = ("id", "name", "status", "students_count", "lessons_count")


class LessonDashboardItemSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source="course.name", read_only=True)

    class Meta:
        model = Lesson
        fields = ("id", "course_name", "lesson_date", "time_from", "time_to", "status")


class StudentDashboardSerializer(serializers.Serializer):
    active_courses_count = serializers.IntegerField()
    favorites_count = serializers.IntegerField()
    upcoming_lessons_count = serializers.IntegerField()
    nearest_lessons = LessonDashboardItemSerializer(many=True)


class TeacherDashboardSerializer(serializers.Serializer):
    courses_count = serializers.IntegerField()
    students_count = serializers.IntegerField()
    upcoming_lessons_count = serializers.IntegerField()
    attendance_rate = serializers.FloatField()
    courses = CourseDashboardItemSerializer(many=True)
    nearest_lessons = LessonDashboardItemSerializer(many=True)


class FavoritesResponseSerializer(serializers.Serializer):
    courses = FavoriteCourseSerializer(many=True)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = (
            "email",
            "username",
            "first_name",
            "last_name",
            "phone",
            "password",
            "password_confirm",
        )

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Пароли не совпадают."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            email=attrs["email"],
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError("Неверный email или пароль.")
        attrs["user"] = user
        return attrs
