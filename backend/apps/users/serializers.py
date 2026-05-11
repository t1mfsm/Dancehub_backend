from django.contrib.auth.hashers import make_password
from django.db import connection
from rest_framework import serializers

from apps.common.choices import DanceLevel, UserRole, WeekdayCode
from apps.common.files import persist_image_reference
from apps.common.utils import absolutize_media_url, build_full_name
from apps.courses.models import DanceStyle
from apps.users.models import Notification, TeacherProfile, User


def create_user_record(
    *,
    email: str,
    username: str,
    first_name: str,
    middle_name: str = "",
    last_name: str,
    password_hash: str,
    role: str = UserRole.STUDENT,
    survey_completed: bool = False,
    avatar: str | None = None,
    city_id: int | None = None,
    dance_level: str | None = None,
    preferred_time_from=None,
    preferred_time_to=None,
    preferred_weekdays: list[str] | None = None,
    preferred_dance_styles: list[str] | None = None,
    price_from: int | None = None,
    price_to: int | None = None,
) -> User:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO users (
                email,
                username,
                first_name,
                middle_name,
                last_name,
                password_hash,
                avatar,
                city_id,
                dance_level,
                role,
                survey_completed,
                preferred_time_from,
                preferred_time_to,
                preferred_weekdays,
                preferred_dance_styles,
                price_from,
                price_to
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::weekday_code[],
                %s::text[],
                %s, %s
            )
            RETURNING id
            """,
            [
                email,
                username,
                first_name,
                middle_name,
                last_name,
                password_hash,
                avatar,
                city_id,
                dance_level,
                role,
                survey_completed,
                preferred_time_from,
                preferred_time_to,
                preferred_weekdays or [],
                preferred_dance_styles or [],
                price_from,
                price_to,
            ],
        )
        user_id = cursor.fetchone()[0]
    return User.objects.select_related("city").get(id=user_id)


def update_user_preferences_record(user_id: int, **fields) -> User:
    assignments: list[str] = []
    params: list[object] = []

    field_mapping = {
        "city_id": "city_id = %s",
        "dance_level": "dance_level = %s",
        "preferred_time_from": "preferred_time_from = %s",
        "preferred_time_to": "preferred_time_to = %s",
        "price_from": "price_from = %s",
        "price_to": "price_to = %s",
        "role": "role = %s",
        "survey_completed": "survey_completed = %s",
    }

    for key, sql in field_mapping.items():
        if key in fields:
            assignments.append(sql)
            params.append(fields[key])

    if "preferred_weekdays" in fields:
        assignments.append("preferred_weekdays = %s::weekday_code[]")
        params.append(fields["preferred_weekdays"] or [])

    if "preferred_dance_styles" in fields:
        assignments.append("preferred_dance_styles = %s::text[]")
        params.append(fields["preferred_dance_styles"] or [])

    if assignments:
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE users SET {', '.join(assignments)} WHERE id = %s",
                [*params, user_id],
            )

    return User.objects.select_related("city").get(id=user_id)


def normalize_pg_text_array(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped in ("", "{}"):
            return []
        if stripped.startswith("{") and stripped.endswith("}"):
            inner = stripped[1:-1]
            if not inner:
                return []
            return [item.strip().strip('"') for item in inner.split(",") if item.strip()]
    return []


def normalize_teacher_specializations(values: list[str] | None) -> list[str]:
    raw_values = [str(value).strip() for value in (values or []) if str(value).strip()]
    if not raw_values:
        return []

    slug_to_name = {
        style.slug.strip().lower(): style.name
        for style in DanceStyle.objects.all().only("slug", "name")
    }

    normalized: list[str] = []
    for value in raw_values:
        normalized.append(slug_to_name.get(value.lower(), value))
    return normalized


def serialize_teacher_profile_summary(teacher: TeacherProfile, request=None, rating: float = 0) -> dict:
    return {
        "bio": teacher.bio or "",
        "images": [absolutize_media_url(request, image) for image in (teacher.images or [])],
        "achievements": teacher.achievements or [],
        "experience": teacher.experience_years,
        "specializations": normalize_teacher_specializations(teacher.specializations),
        "rating": round(float(rating or 0), 2),
    }


def serialize_user(user: User, request=None, teacher: TeacherProfile | None = None, teacher_rating: float = 0) -> dict:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT course_id
            FROM favorite_courses
            WHERE user_id = %s
            ORDER BY course_id
            """,
            [user.id],
        )
        favorite_course_ids = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT ft.teacher_id, u.first_name, u.middle_name, u.last_name, u.email
            FROM favorite_teachers ft
            JOIN teachers t ON t.id = ft.teacher_id
            JOIN users u ON u.id = t.user_id
            WHERE ft.user_id = %s
            ORDER BY ft.teacher_id
            """,
            [user.id],
        )
        favorite_teacher_rows = cursor.fetchall()
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "middle_name": user.middle_name or "",
        "last_name": user.last_name,
        "avatar": absolutize_media_url(request, user.avatar) or None,
        "city": user.city.name if user.city else None,
        "dance_level": user.dance_level or "",
        "role": user.role,
        "survey_completed": user.survey_completed,
        "teacher": (
            serialize_teacher_profile_summary(teacher, request=request, rating=teacher_rating)
            if teacher is not None
            else None
        ),
        "favorite_course_ids": favorite_course_ids,
        "favorite_teacher_ids": [row[0] for row in favorite_teacher_rows],
        "favorite_teacher_names": [
            build_full_name(row[3], row[1], row[2]) or row[4]
            for row in favorite_teacher_rows
        ],
        "preferred_time_from": user.preferred_time_from.isoformat() if user.preferred_time_from else None,
        "preferred_time_to": user.preferred_time_to.isoformat() if user.preferred_time_to else None,
        "price_from": user.price_from,
        "price_to": user.price_to,
        "preferred_weekdays": normalize_pg_text_array(user.preferred_weekdays),
        "preferred_dance_styles": normalize_pg_text_array(user.preferred_dance_styles),
    }


def serialize_notification(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "kind": notification.kind,
        "title": notification.title,
        "body": notification.body,
        "course_id": notification.course_id,
        "lesson_id": notification.lesson_id,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat(),
    }


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField()
    first_name = serializers.CharField()
    middle_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField()
    password = serializers.CharField(min_length=8)
    password_confirm = serializers.CharField(min_length=8)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": ["Passwords do not match."]})
        if User.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError({"email": ["A user with this email already exists."]})
        if User.objects.filter(username=attrs["username"]).exists():
            raise serializers.ValidationError({"username": ["A user with this username already exists."]})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        raw_password = validated_data.pop("password")
        return create_user_record(
            email=validated_data["email"],
            username=validated_data["username"],
            first_name=validated_data["first_name"],
            middle_name=validated_data.get("middle_name", ""),
            last_name=validated_data["last_name"],
            password_hash=make_password(raw_password),
            role=UserRole.STUDENT,
            survey_completed=False,
        )


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=False, allow_blank=True)


class UserUpdateSerializer(serializers.Serializer):
    username = serializers.CharField(required=False)
    first_name = serializers.CharField(required=False)
    middle_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False)
    survey_completed = serializers.BooleanField(required=False)
    avatar_file = serializers.ImageField(required=False)
    city = serializers.CharField(required=False, allow_blank=True)
    dance_level = serializers.ChoiceField(required=False, choices=DanceLevel.choices)
    role = serializers.ChoiceField(required=False, choices=UserRole.choices)


class UserPreferencesSerializer(serializers.Serializer):
    city = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    level = serializers.ChoiceField(required=False, allow_null=True, choices=[("any", "any"), *DanceLevel.choices])
    preferred_weekdays = serializers.ListField(
        child=serializers.ChoiceField(choices=WeekdayCode.choices),
        required=False,
    )
    preferred_time_from = serializers.TimeField(required=False, allow_null=True)
    preferred_time_to = serializers.TimeField(required=False, allow_null=True)
    price_from = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    price_to = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    preferred_dance_styles = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )
    role = serializers.ChoiceField(required=False, choices=UserRole.choices)

    def validate(self, attrs):
        time_from = attrs.get("preferred_time_from")
        time_to = attrs.get("preferred_time_to")
        if time_from and time_to and time_from >= time_to:
            raise serializers.ValidationError({"preferred_time_to": ["Must be later than preferred_time_from."]})
        price_from = attrs.get("price_from")
        price_to = attrs.get("price_to")
        if price_from is not None and price_to is not None and price_from > price_to:
            raise serializers.ValidationError({"price_to": ["Must be greater than or equal to price_from."]})
        return attrs


class UserSkillItemSerializer(serializers.Serializer):
    dance_style_id = serializers.IntegerField()
    level = serializers.ChoiceField(choices=[("any", "any"), *DanceLevel.choices])


class UserFlagSerializer(serializers.Serializer):
    name = serializers.CharField()
    value = serializers.BooleanField()


class TeacherProfileUpdateSerializer(serializers.Serializer):
    bio = serializers.CharField(required=False, allow_blank=True)
    images = serializers.ListField(child=serializers.CharField(), required=False)
    achievements = serializers.ListField(child=serializers.CharField(), required=False)
    experience = serializers.IntegerField(required=False, min_value=0)
    specializations = serializers.ListField(child=serializers.CharField(), required=False)

    def normalize_images(self, folder: str) -> list[str]:
        raw_images = self.validated_data.get("images", [])
        return [persist_image_reference(image, folder) for image in raw_images if image]


class NotificationReadSerializer(serializers.Serializer):
    read = serializers.BooleanField()
