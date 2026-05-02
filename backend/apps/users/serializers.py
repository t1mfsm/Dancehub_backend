from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import FavoriteTeacher, TeacherProfile, TeacherReview, User, UserFlag, UserSkill


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует.")
        return value

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Пользователь с таким username уже существует.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(
            request=self.context.get("request"),
            username=data["email"],
            password=data["password"],
        )
        if not user:
            raise serializers.ValidationError("Неверный email или пароль.")
        if not user.is_active:
            raise serializers.ValidationError("Аккаунт заблокирован.")
        data["user"] = user
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

class MeSerializer(serializers.ModelSerializer):
    city = serializers.SerializerMethodField()
    flags = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "middle_name",
            "phone",
            "avatar",
            "city",
            "dance_level",
            "role",
            "survey_completed",
            "preferred_time_from",
            "preferred_time_to",
            "preferred_weekdays",
            "preferred_dance_styles",
            "price_from",
            "price_to",
            "flags",
        )

    def get_city(self, obj):
        if obj.city:
            return {"id": obj.city.id, "name": obj.city.name}
        return None

    def get_flags(self, obj):
        return {f.name: f.value for f in obj.flags.all()}


class MeUpdateSerializer(serializers.ModelSerializer):
    city_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "middle_name",
            "phone",
            "avatar",
            "city_id",
            "dance_level",
        )

    def update(self, instance, validated_data):
        city_id = validated_data.pop("city_id", ...)
        if city_id is not ...:
            from apps.locations.models import City
            instance.city = City.objects.filter(id=city_id).first() if city_id else None
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


# ---------------------------------------------------------------------------
# Survey / preferences
# ---------------------------------------------------------------------------

class SurveySubmitSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["student", "teacher"], required=False)
    city_id = serializers.IntegerField(required=False, allow_null=True)
    dance_level = serializers.ChoiceField(
        choices=["beginner", "intermediate", "advanced"],
        required=False,
        allow_blank=True,
    )
    preferred_weekdays = serializers.ListField(
        child=serializers.ChoiceField(choices=["mon", "tue", "wed", "thu", "fri", "sat", "sun"]),
        required=False,
    )
    preferred_dance_styles = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
    )
    preferred_time_from = serializers.TimeField(required=False, allow_null=True)
    preferred_time_to = serializers.TimeField(required=False, allow_null=True)
    price_from = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    price_to = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)

    def update(self, instance: User, validated_data: dict) -> User:
        if "city_id" in validated_data:
            from apps.locations.models import City
            city_id = validated_data.pop("city_id")
            instance.city = City.objects.filter(id=city_id).first() if city_id else None
        else:
            validated_data.pop("city_id", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.survey_completed = True
        instance.save()
        return instance


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

class UserSkillSerializer(serializers.ModelSerializer):
    dance_style = serializers.SerializerMethodField()

    class Meta:
        model = UserSkill
        fields = ("id", "dance_style", "level")

    def get_dance_style(self, obj):
        return {"id": obj.dance_style.id, "name": obj.dance_style.name, "slug": obj.dance_style.slug}


class UserSkillWriteItemSerializer(serializers.Serializer):
    dance_style_id = serializers.IntegerField()
    level = serializers.ChoiceField(choices=["beginner", "intermediate", "advanced"])

    def validate_dance_style_id(self, value):
        from apps.courses.models import DanceStyle
        if not DanceStyle.objects.filter(id=value).exists():
            raise serializers.ValidationError("Танцевальный стиль не найден.")
        return value


# ---------------------------------------------------------------------------
# User flags
# ---------------------------------------------------------------------------

class UserFlagSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    value = serializers.BooleanField()


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------

class TeacherReviewSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TeacherReview
        fields = ("id", "author_name", "rating", "text", "created_at")

    def get_author_name(self, obj) -> str:
        return obj.author_user.get_full_name() or obj.author_user.email


class TeacherReviewCreateSerializer(serializers.Serializer):
    lesson_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(required=False, default="")

    def validate(self, data):
        from apps.courses.models import AttendanceMark, Lesson
        request = self.context["request"]
        user = request.user

        try:
            lesson = Lesson.objects.select_related("course__teacher").get(id=data["lesson_id"])
        except Lesson.DoesNotExist:
            raise serializers.ValidationError({"lesson_id": "Занятие не найдено."})

        has_attendance = AttendanceMark.objects.filter(
            lesson=lesson,
            student=user,
            status="present",
        ).exists()

        if not has_attendance:
            raise serializers.ValidationError(
                "Отзыв можно оставить только после посещения занятия."
            )

        if TeacherReview.objects.filter(author_user=user, lesson=lesson).exists():
            raise serializers.ValidationError("Вы уже оставили отзыв по этому занятию.")

        data["lesson"] = lesson
        data["teacher"] = lesson.course.teacher
        return data


class TeacherListSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id")
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    middle_name = serializers.CharField(source="user.middle_name")
    avatar = serializers.URLField(source="user.avatar")
    city = serializers.SerializerMethodField()

    class Meta:
        model = TeacherProfile
        fields = (
            "id",
            "user_id",
            "first_name",
            "last_name",
            "middle_name",
            "avatar",
            "city",
            "experience_years",
            "specializations",
            "rating_avg",
            "rating_count",
        )

    def get_city(self, obj):
        if obj.user.city:
            return {"id": obj.user.city.id, "name": obj.user.city.name}
        return None


class TeacherDetailSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id")
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    middle_name = serializers.CharField(source="user.middle_name")
    avatar = serializers.URLField(source="user.avatar")
    city = serializers.SerializerMethodField()
    reviews = TeacherReviewSerializer(many=True, read_only=True)

    class Meta:
        model = TeacherProfile
        fields = (
            "id",
            "user_id",
            "first_name",
            "last_name",
            "middle_name",
            "avatar",
            "city",
            "bio",
            "experience_years",
            "images",
            "achievements",
            "specializations",
            "rating_avg",
            "rating_count",
            "reviews",
        )

    def get_city(self, obj):
        if obj.user.city:
            return {"id": obj.user.city.id, "name": obj.user.city.name}
        return None


class TeacherProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherProfile
        fields = ("bio", "experience_years", "images", "achievements", "specializations")


class TeacherCourseListSerializer(serializers.Serializer):
    """Compact course list for teacher profile page."""
    id = serializers.IntegerField()
    name = serializers.CharField()
    dance_style = serializers.SerializerMethodField()
    level = serializers.CharField()
    status = serializers.CharField()
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    image_cover = serializers.URLField()

    def get_dance_style(self, obj):
        return {"id": obj.dance_style.id, "name": obj.dance_style.name}


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

class FavoriteCourseSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()
    course_name = serializers.CharField()


class FavoriteTeacherSerializer(serializers.Serializer):
    teacher_id = serializers.IntegerField()
    teacher_name = serializers.CharField()


class FavoritesResponseSerializer(serializers.Serializer):
    courses = FavoriteCourseSerializer(many=True)
    teachers = FavoriteTeacherSerializer(many=True)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

class CourseRecommendationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    dance_style = serializers.SerializerMethodField()
    teacher = serializers.SerializerMethodField()
    studio = serializers.SerializerMethodField()
    level = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    image_cover = serializers.URLField()

    def get_dance_style(self, obj):
        return {"id": obj.dance_style.id, "name": obj.dance_style.name, "slug": obj.dance_style.slug}

    def get_teacher(self, obj):
        u = obj.teacher.user
        return {"id": obj.teacher.id, "first_name": u.first_name, "last_name": u.last_name, "avatar": u.avatar}

    def get_studio(self, obj):
        if obj.studio:
            return {"id": obj.studio.id, "name": obj.studio.name}
        return None


# ---------------------------------------------------------------------------
# My courses (compact)
# ---------------------------------------------------------------------------

class MyCourseSerializer(serializers.Serializer):
    course = serializers.SerializerMethodField()
    status = serializers.CharField()

    def get_course(self, obj):
        return {"id": obj.course_id}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class CourseDashboardItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    dance_style = serializers.SerializerMethodField()
    image_cover = serializers.URLField()
    next_lesson_date = serializers.SerializerMethodField()

    def get_dance_style(self, obj):
        return obj.dance_style.name

    def get_next_lesson_date(self, obj):
        today = timezone.localdate()
        lesson = obj.lessons.filter(lesson_date__gte=today, status="scheduled").order_by("lesson_date", "time_from").first()
        return lesson.lesson_date if lesson else None


class LessonDashboardItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    course_id = serializers.IntegerField(source="course.id")
    course_name = serializers.CharField(source="course.name")
    dance_style = serializers.SerializerMethodField()
    lesson_date = serializers.DateField()
    time_from = serializers.TimeField()
    time_to = serializers.TimeField()
    hall = serializers.CharField()
    location_text = serializers.CharField()

    def get_dance_style(self, obj):
        return obj.course.dance_style.name


class StudentDashboardSerializer(serializers.Serializer):
    enrolled_courses_count = serializers.IntegerField()
    upcoming_lessons = LessonDashboardItemSerializer(many=True)
    favorite_courses_count = serializers.IntegerField()


class TeacherDashboardSerializer(serializers.Serializer):
    active_courses_count = serializers.IntegerField()
    total_students = serializers.IntegerField()
    upcoming_lessons = LessonDashboardItemSerializer(many=True)
