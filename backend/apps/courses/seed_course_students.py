"""Демозапись 10–20 учеников на новый курс: пул пользователей с русскими ФИО и аватарами seed/teachers (MinIO)."""

import random
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import transaction

from apps.courses.models import Course, Enrollment, EnrollmentStatus
from apps.users.models import DanceLevel, User, UserRole

SEED_TEACHER_AVATAR_KEYS: tuple[str, ...] = (
    "teachers/woman.jpg",
    "teachers/w2.avif",
    "teachers/man.png",
)

SEED_STUDENT_IDENTITIES: tuple[tuple[str, str], ...] = (
    ("Александр", "Волков"),
    ("Анна", "Зайцева"),
    ("Григорий", "Ефремов"),
    ("Даниил", "Новиков"),
    ("Дарья", "Кузнецова"),
    ("Елизавета", "Павлова"),
    ("Екатерина", "Соловьева"),
    ("Иван", "Мишин"),
    ("Ирина", "Белова"),
    ("Кирилл", "Тихонов"),
    ("Людмила", "Орлова"),
    ("Марк", "Комаров"),
    ("Мария", "Васильева"),
    ("Михаил", "Алексеев"),
    ("Наталья", "Григорьева"),
    ("Олег", "Макаров"),
    ("Ольга", "Романова"),
    ("Пётр", "Соколов"),
    ("Полина", "Жукова"),
    ("Роман", "Лебедев"),
    ("Светлана", "Шестакова"),
    ("Сергей", "Морозов"),
    ("София", "Николаева"),
    ("Татьяна", "Андреева"),
    ("Тимофей", "Данилов"),
    ("Ульяна", "Назарова"),
    ("Вадим", "Крылов"),
    ("Валерия", "Тарасова"),
    ("Вера", "Семёнова"),
    ("Виктория", "Фадеева"),
    ("Вячеслав", "Борисов"),
    ("Яна", "Мельникова"),
    ("Юлия", "Киселёва"),
    ("Юрий", "Пономарёв"),
    ("Алексей", "Богданов"),
    ("Валентин", "Гусев"),
    ("Вероника", "Дроздова"),
    ("Галина", "Захарова"),
    ("Денис", "Ильин"),
    ("Диана", "Ковалёва"),
    ("Евгений", "Львов"),
)

SEED_EMAIL_DOMAIN = "students.seed.dancehub.local"
POOL_SIZE = len(SEED_STUDENT_IDENTITIES)
POOL_PASSWORD_HASH = make_password("StudentSeedDemo1")

_AVATAR_PUBLIC_URL_CACHE: dict[str, str] = {}


def _store_seed_teacher_avatar(relative_under_images: str) -> str:
    """
    Публичный URL аватара в MinIO: ключ `seed/teachers/...` в бакете default storage.

    Сначала проверяем объект в bucket; если нет — копируем из FRONTEND_ASSETS_ROOT/images/…
    (как management command populate_cards). После сохранения — default_storage.url().
    """
    storage_path = f"seed/{relative_under_images}"

    if default_storage.exists(storage_path):
        return default_storage.url(storage_path)

    assets_root = getattr(settings, "FRONTEND_ASSETS_ROOT", None)
    if assets_root is not None:
        source_path = Path(assets_root) / "images" / relative_under_images
        if source_path.is_file():
            with source_path.open("rb") as source:
                default_storage.save(storage_path, File(source, name=source_path.name))

    if default_storage.exists(storage_path):
        return default_storage.url(storage_path)

    return ""


def _avatar_public_url_cached(relative_under_images: str) -> str:
    if relative_under_images not in _AVATAR_PUBLIC_URL_CACHE:
        url = _store_seed_teacher_avatar(relative_under_images)
        _AVATAR_PUBLIC_URL_CACHE[relative_under_images] = url

    return _AVATAR_PUBLIC_URL_CACHE[relative_under_images]


def _pool_email(pool_index: int) -> str:
    return f"seed.student.{pool_index:03d}@{SEED_EMAIL_DOMAIN}"


def _ensure_demo_student(pool_index: int) -> User:
    first_name_s, last_name_s = SEED_STUDENT_IDENTITIES[pool_index % POOL_SIZE]
    email = _pool_email(pool_index)
    avatar_relative = SEED_TEACHER_AVATAR_KEYS[pool_index % len(SEED_TEACHER_AVATAR_KEYS)]
    avatar_url = _avatar_public_url_cached(avatar_relative)

    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "username": email,
            "first_name": first_name_s,
            "last_name": last_name_s,
            "role": UserRole.STUDENT,
            "dance_level": random.choice(
                (
                    DanceLevel.BEGINNER,
                    DanceLevel.INTERMEDIATE,
                    DanceLevel.ADVANCED,
                )
            ),
            "survey_completed": True,
            "avatar": avatar_url,
            "password": POOL_PASSWORD_HASH,
        },
    )

    if not created:
        update_fields: list[str] = []
        if user.first_name != first_name_s:
            user.first_name = first_name_s
            update_fields.append("first_name")
        if user.last_name != last_name_s:
            user.last_name = last_name_s
            update_fields.append("last_name")
        if user.role != UserRole.STUDENT:
            user.role = UserRole.STUDENT
            update_fields.append("role")
        if avatar_url and user.avatar != avatar_url:
            user.avatar = avatar_url
            update_fields.append("avatar")
        if update_fields:
            user.save(update_fields=update_fields)

    return user


def enroll_random_demo_students(course: Course) -> int:
    """
    Выбирает случайное количество 10–20 демопользователей из пула и создаёт записи Enrollment со статусом active.

    Ограничивается полем capacity курса; не более POOL_SIZE уникальных лиц за один курс.
    """
    if not getattr(settings, "ENROLL_RANDOM_STUDENTS_ON_COURSE_CREATION", True):
        return 0

    if course.capacity <= 0:
        return 0

    desired = random.randint(10, 20)
    target = min(desired, course.capacity, POOL_SIZE)

    if target <= 0:
        return 0

    for avatar_key in SEED_TEACHER_AVATAR_KEYS:
        _avatar_public_url_cached(avatar_key)

    pool_indices = random.sample(range(POOL_SIZE), k=target)

    with transaction.atomic():
        enrolled = 0

        for pid in pool_indices:
            student = _ensure_demo_student(pid)
            enrollment, created_flag = Enrollment.objects.get_or_create(
                user=student,
                course=course,
                defaults={
                    "enrolled_at": course.date_from,
                    "status": EnrollmentStatus.ACTIVE,
                    "paid": True,
                },
            )

            if not created_flag:
                update_fields: list[str] = []
                if enrollment.status != EnrollmentStatus.ACTIVE:
                    enrollment.status = EnrollmentStatus.ACTIVE
                    update_fields.append("status")
                if not enrollment.paid:
                    enrollment.paid = True
                    update_fields.append("paid")
                if update_fields:
                    enrollment.save(update_fields=update_fields)

            enrolled += 1

    return enrolled
