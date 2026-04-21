import uuid
from pathlib import Path

from django.core.files.storage import default_storage
from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.courses.models import Course, DanceStyle, Enrollment, FavoriteCourse, Lesson
from apps.locations.models import City

from .models import (
    FavoriteTeacher,
    TeacherAchievement,
    TeacherProfile,
    TeacherReview,
    UserRole,
    User,
    UserPreference,
    UserPreferredWeekday,
    UserSkill,
)


def _build_absolute_url(value: str | None, request) -> str:
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    if request is None:
        return value
    return request.build_absolute_uri(value)


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
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)
    avatar = serializers.SerializerMethodField()
    specializations = serializers.SerializerMethodField()
    achievements = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    experience = serializers.IntegerField(source="experience_years", read_only=True)
    rating = serializers.SerializerMethodField()
    reviews = TeacherReviewSerializer(many=True, read_only=True)
    courses = TeacherCourseShortSerializer(many=True, read_only=True)

    class Meta(TeacherListSerializer.Meta):
        fields = TeacherListSerializer.Meta.fields + (
            "user_id",
            "name",
            "email",
            "avatar",
            "images",
            "experience",
            "rating",
            "specializations",
            "achievements",
            "reviews",
            "courses",
        )

    def get_name(self, obj: TeacherProfile) -> str:
        return obj.user.get_full_name() or obj.user.email

    def get_avatar(self, obj: TeacherProfile) -> str:
        request = self.context.get("request")
        return _build_absolute_url(obj.user.avatar, request)

    def get_images(self, obj: TeacherProfile) -> list[str]:
        request = self.context.get("request")
        return [_build_absolute_url(image, request) for image in obj.images]

    def get_rating(self, obj: TeacherProfile) -> float:
        return float(obj.rating_avg)

    def get_specializations(self, obj: TeacherProfile) -> list[str]:
        return [item.dance_style.name for item in obj.specializations.select_related("dance_style").all()]

    def get_achievements(self, obj: TeacherProfile) -> list[str]:
        return [item.title for item in obj.achievements.all().order_by("-achieved_at", "id")]


class MeTeacherSerializer(serializers.ModelSerializer):
    specializations = serializers.SerializerMethodField()
    achievements = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    experience = serializers.IntegerField(source="experience_years", read_only=True)
    rating = serializers.SerializerMethodField()

    class Meta:
        model = TeacherProfile
        fields = (
            "bio",
            "images",
            "experience",
            "specializations",
            "achievements",
            "rating",
        )

    def get_rating(self, obj: TeacherProfile) -> float:
        return float(obj.rating_avg)

    def get_images(self, obj: TeacherProfile) -> list[str]:
        request = self.context.get("request")
        return [_build_absolute_url(image, request) for image in obj.images]

    def get_specializations(self, obj: TeacherProfile) -> list[str]:
        return [item.dance_style.name for item in obj.specializations.select_related("dance_style").all()]

    def get_achievements(self, obj: TeacherProfile) -> list[str]:
        return [item.title for item in obj.achievements.all().order_by("-achieved_at", "id")]


class TeacherProfileUpdateSerializer(serializers.Serializer):
    bio = serializers.CharField(required=False, allow_blank=True)
    images = serializers.ListField(child=serializers.CharField(), required=False)
    achievements = serializers.ListField(child=serializers.CharField(), required=False)
    experience = serializers.IntegerField(required=False, min_value=0)
    specializations = serializers.ListField(child=serializers.CharField(), required=False)

    def validate_specializations(self, value: list[str]) -> list[DanceStyle]:
        if not value:
            return []

        style_names = [item.strip() for item in value if item and item.strip()]
        styles = {style.name.lower(): style for style in DanceStyle.objects.filter(name__in=style_names)}

        missing = [name for name in style_names if name.lower() not in styles]
        if missing:
            fallback_styles = {
                style.name.lower(): style
                for style in DanceStyle.objects.all()
                if style.name.lower() in {name.lower() for name in style_names}
            }
            styles.update(fallback_styles)
            missing = [name for name in style_names if name.lower() not in styles]

        if missing:
            raise serializers.ValidationError(f"Стили не найдены: {', '.join(missing)}")

        return [styles[name.lower()] for name in style_names]

    def update(self, instance: TeacherProfile, validated_data: dict) -> TeacherProfile:
        specializations = validated_data.pop("specializations", None)
        achievements = validated_data.pop("achievements", None)

        if "bio" in validated_data:
            instance.bio = validated_data["bio"]
        if "images" in validated_data:
            instance.images = validated_data["images"]
        if "experience" in validated_data:
            instance.experience_years = validated_data["experience"]

        instance.save()

        if specializations is not None:
            instance.specializations.all().delete()
            for style in specializations:
                instance.specializations.create(dance_style=style)

        if achievements is not None:
            instance.achievements.all().delete()
            for title in achievements:
                title = title.strip()
                if title:
                    instance.achievements.create(title=title)

        return instance


class UserSkillSerializer(serializers.ModelSerializer):
    dance_style_id = serializers.IntegerField(source="dance_style.id", read_only=True)
    dance_style = serializers.CharField(source="dance_style.name", read_only=True)
    dance_style_slug = serializers.CharField(source="dance_style.slug", read_only=True)

    class Meta:
        model = UserSkill
        fields = ("id", "dance_style_id", "dance_style", "dance_style_slug", "level")


class SurveyDataSerializer(serializers.Serializer):
    city = serializers.CharField(allow_blank=True, allow_null=True)
    level = serializers.CharField(allow_blank=True, allow_null=True)
    preferred_time_from = serializers.TimeField(allow_null=True)
    preferred_time_to = serializers.TimeField(allow_null=True)
    price_from = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    price_to = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    preferred_weekdays = serializers.ListField(child=serializers.CharField(), required=False)
    preferred_dance_styles = serializers.ListField(child=serializers.CharField(), required=False)


class MeSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True)
    teacher = serializers.SerializerMethodField()
    favorite_course_ids = serializers.SerializerMethodField()
    favorite_teacher_ids = serializers.SerializerMethodField()
    preferred_time_from = serializers.SerializerMethodField()
    preferred_time_to = serializers.SerializerMethodField()
    price_from = serializers.SerializerMethodField()
    price_to = serializers.SerializerMethodField()
    preferred_weekdays = serializers.SerializerMethodField()
    preferred_dance_styles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "first_name",
            "middle_name",
            "last_name",
            "avatar",
            "city",
            "dance_level",
            "role",
            "survey_completed",
            "teacher",
            "favorite_course_ids",
            "favorite_teacher_ids",
            "preferred_time_from",
            "preferred_time_to",
            "price_from",
            "price_to",
            "preferred_weekdays",
            "preferred_dance_styles",
        )

    def get_favorite_course_ids(self, obj: User) -> list[int]:
        return list(obj.favorite_courses.values_list("course_id", flat=True))

    def get_favorite_teacher_ids(self, obj: User) -> list[int]:
        return list(obj.favorite_teachers.values_list("teacher_id", flat=True))

    def get_teacher(self, obj: User) -> dict | None:
        teacher = TeacherProfile.objects.filter(user=obj).first()

        if teacher is None:
            return None

        return MeTeacherSerializer(teacher, context=self.context).data

    def _get_preference(self, obj: User) -> UserPreference | None:
        try:
            return obj.preferences
        except UserPreference.DoesNotExist:
            return None

    def get_preferred_time_from(self, obj: User):
        preference = self._get_preference(obj)
        return preference.preferred_time_from if preference else None

    def get_preferred_time_to(self, obj: User):
        preference = self._get_preference(obj)
        return preference.preferred_time_to if preference else None

    def get_price_from(self, obj: User):
        preference = self._get_preference(obj)
        return preference.price_from if preference else None

    def get_price_to(self, obj: User):
        preference = self._get_preference(obj)
        return preference.price_to if preference else None

    def get_preferred_weekdays(self, obj: User) -> list[str]:
        preference = self._get_preference(obj)
        if not preference:
            return []

        return list(preference.preferred_weekdays.values_list("weekday", flat=True).order_by("weekday"))

    def get_preferred_dance_styles(self, obj: User) -> list[str]:
        preference = self._get_preference(obj)
        if not preference:
            return []

        return [
            item.dance_style.name
            for item in preference.preferred_dance_styles.select_related("dance_style").all()
        ]


class MeUpdateSerializer(serializers.ModelSerializer):
    avatar_file = serializers.FileField(write_only=True, required=False)
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
            "middle_name",
            "last_name",
            "phone",
            "avatar",
            "avatar_file",
            "city_id",
            "dance_level",
            "survey_completed",
        )

    def update(self, instance, validated_data):
        avatar_file = validated_data.pop("avatar_file", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if avatar_file:
            extension = Path(avatar_file.name).suffix or ".jpg"
            filename = f"avatars/{uuid.uuid4().hex}{extension}"
            stored_path = default_storage.save(filename, avatar_file)
            url = default_storage.url(stored_path)
            request = self.context.get("request")

            if not url.startswith(("http://", "https://")) and request is not None:
                url = request.build_absolute_uri(url)

            instance.avatar = url

        instance.save()
        return instance


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
        write_only=True,
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


class SurveySubmitSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=UserRole.choices, required=False)
    city = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    level = serializers.ChoiceField(choices=UserPreference._meta.get_field("level").choices, required=False)
    preferred_time_from = serializers.TimeField(required=False, allow_null=True)
    preferred_time_to = serializers.TimeField(required=False, allow_null=True)
    price_from = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    price_to = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    preferred_weekdays = serializers.ListField(
        child=serializers.ChoiceField(choices=UserPreferredWeekday._meta.get_field("weekday").choices),
        required=False,
    )
    preferred_dance_styles = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )

    def validate_city(self, value):
        if value in (None, ""):
            return None

        city = City.objects.filter(name__iexact=value.strip()).first()
        if city is None:
            raise serializers.ValidationError("Город не найден.")

        return city

    def validate_preferred_dance_styles(self, value):
        if not value:
            return []

        style_names = [item.strip() for item in value if item and item.strip()]
        styles = {style.name.lower(): style for style in DanceStyle.objects.filter(name__in=style_names)}

        missing = [name for name in style_names if name.lower() not in styles]
        if missing:
            fallback_styles = {
                style.name.lower(): style
                for style in DanceStyle.objects.all()
                if style.name.lower() in {name.lower() for name in style_names}
            }
            styles.update(fallback_styles)
            missing = [name for name in style_names if name.lower() not in styles]

        if missing:
            raise serializers.ValidationError(
                f"Стили не найдены: {', '.join(missing)}"
            )

        return [styles[name.lower()] for name in style_names]

    def save(self, **kwargs):
        user = self.context["request"].user
        validated_data = {**self.validated_data}
        role = validated_data.pop("role", None)
        city = validated_data.get("city")
        preferred_style_items = validated_data.pop("preferred_dance_styles", [])
        preferred_style_ids = [item.id for item in preferred_style_items]
        preferred_weekdays = validated_data.pop("preferred_weekdays", [])

        preference, _ = UserPreference.objects.get_or_create(user=user)
        for attr, value in validated_data.items():
            setattr(preference, attr, value)
        preference.save()

        UserPreferenceSerializer()._save_relations(preference, preferred_style_ids, preferred_weekdays)

        level = self.validated_data.get("level", "") or ""
        user.city = city
        user.dance_level = level
        user.survey_completed = True
        update_fields = ["city", "dance_level", "survey_completed"]

        if role is not None:
            user.role = role
            user.is_teacher_enabled = role == UserRole.TEACHER
            update_fields.extend(["role", "is_teacher_enabled"])

        user.save(update_fields=update_fields)

        if user.role == UserRole.TEACHER:
            TeacherProfile.objects.get_or_create(user=user)
            user.refresh_from_db()

        user.skills.all().delete()
        skills = [
            UserSkill(user=user, dance_style_id=style_id, level=level or "any")
            for style_id in preferred_style_ids
        ]
        if skills:
            UserSkill.objects.bulk_create(skills)

        return user


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
            "middle_name",
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
