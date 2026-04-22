import uuid
from pathlib import Path

from django.core.files.storage import default_storage
from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.courses.models import Course, Enrollment, FavoriteCourse, Lesson
from apps.locations.models import City

from .models import (
    FavoriteTeacher,
    TeacherProfile,
    TeacherReview,
    UserRole,
    User,
)


def _build_absolute_url(value: str | None, request) -> str:
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    if request is None:
        return value
    return request.build_absolute_uri(value)


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
    specializations = serializers.ListField(child=serializers.CharField(), read_only=True)
    achievements = serializers.ListField(child=serializers.CharField(), read_only=True)
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


class MeTeacherSerializer(serializers.ModelSerializer):
    specializations = serializers.ListField(child=serializers.CharField(), read_only=True)
    achievements = serializers.ListField(child=serializers.CharField(), read_only=True)
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


class TeacherProfileUpdateSerializer(serializers.Serializer):
    bio = serializers.CharField(required=False, allow_blank=True)
    images = serializers.ListField(child=serializers.CharField(), required=False)
    achievements = serializers.ListField(child=serializers.CharField(), required=False)
    experience = serializers.IntegerField(required=False, min_value=0)
    specializations = serializers.ListField(child=serializers.CharField(), required=False)

    def update(self, instance: TeacherProfile, validated_data: dict) -> TeacherProfile:
        if "bio" in validated_data:
            instance.bio = validated_data["bio"]
        if "images" in validated_data:
            instance.images = validated_data["images"]
        if "experience" in validated_data:
            instance.experience_years = validated_data["experience"]
        if "achievements" in validated_data:
            instance.achievements = [
                title.strip() for title in validated_data["achievements"] if title and title.strip()
            ]
        if "specializations" in validated_data:
            instance.specializations = [
                name.strip() for name in validated_data["specializations"] if name and name.strip()
            ]
        instance.save()
        return instance


class MeSerializer(serializers.ModelSerializer):
    city = serializers.CharField(source="city.name", read_only=True, default="")
    level = serializers.CharField(source="dance_level", read_only=True)
    registered_at = serializers.DateTimeField(source="date_joined", read_only=True)
    teacher = serializers.SerializerMethodField()
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
            "level",
            "role",
            "registered_at",
            "survey_completed",
            "flags",
            "teacher",
            "favorite_course_ids",
            "favorite_teacher_ids",
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
            "last_name",
            "phone",
            "avatar",
            "avatar_file",
            "city_id",
            "dance_level",
            "survey_completed",
            "flags",
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


class CourseRecommendationSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    dance_style = serializers.CharField(source="dance_style.name", read_only=True)
    dance_style_slug = serializers.CharField(source="dance_style.slug", read_only=True)
    studio = serializers.CharField(source="studio.name", read_only=True)
    city = serializers.CharField(source="studio.city.name", read_only=True)

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
        )

    def get_teacher_name(self, obj: Course) -> str:
        return obj.teacher.user.get_full_name() or obj.teacher.user.email


class FavoritesResponseSerializer(serializers.Serializer):
    courses = FavoriteCourseSerializer(many=True)


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


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=UserRole.choices, required=False, default=UserRole.STUDENT)

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует.")
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data["password"]
        user = User(
            email=email,
            username=email,
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            phone=validated_data.get("phone", ""),
            role=validated_data.get("role", UserRole.STUDENT),
        )
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
