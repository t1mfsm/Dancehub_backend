"""
Management command to populate the database with course data from frontend cards.ts.
"""
import uuid
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.db import connection
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.courses.models import (
    Course,
    CourseSchedule,
    CourseStatus,
    DanceStyle,
    Studio,
)
from apps.courses.seed_data import COURSES_DATA
from apps.courses.services import generate_course_lessons
from apps.locations.models import City
from apps.users.models import DanceLevel, TeacherProfile, User, Weekday

# Map frontend image keys to local asset files. The command stores these files
# through Django storage, so with USE_S3=True they are uploaded to MinIO.
COURSE_IMAGES_MAP = {
    "highHeels1": "courses/high-heels-1.jpg",
    "highHeels2": "courses/high-heels-2.jpg",
    "contemporary": "courses/contemporary.jpg",
    "jazzFunk": "courses/jazz-funk.jpg",
    "vogue": "courses/vogue.jpg",
    "hipHop": "courses/hip-hop.jpg",
    "dancehall": "courses/dancehall.jpeg",
    "frameUp": "courses/frame-up.jpg",
    "stretching": "courses/stretching.png",
    "ladyStyle": "courses/lady-style.jpg",
}

TEACHER_IMAGES_MAP = {
    "woman": "teachers/woman.jpg",
    "woman2": "teachers/w2.avif",
    "man": "teachers/man.png",
}

LEVEL_MAP = {
    "Начинающие": DanceLevel.BEGINNER,
    "Средний уровень": DanceLevel.INTERMEDIATE,
    "Продвинутые": DanceLevel.ADVANCED,
    "Любой уровень": DanceLevel.BEGINNER,
}

WEEKDAY_MAP = {
    "Пн": Weekday.MONDAY,
    "Вт": Weekday.TUESDAY,
    "Ср": Weekday.WEDNESDAY,
    "Чт": Weekday.THURSDAY,
    "Пт": Weekday.FRIDAY,
    "Сб": Weekday.SATURDAY,
    "Вс": Weekday.SUNDAY,
}

COURSE_ASSET_EXTENSIONS = {".avif", ".jpeg", ".jpg", ".png", ".webp"}


def parse_short_date(short: str, year: int | None = None) -> date:
    """Parse '17.02' -> date (год по умолчанию — текущий календарный год)."""
    day, month = map(int, short.split("."))
    y = year if year is not None else timezone.localdate().year
    return datetime(y, month, day).date()

class Command(BaseCommand):
    help = "Populate database with course data from frontend cards.ts"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing courses, teachers, studios before populating",
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            if options["clear"]:
                self._clear_data()

            cities = self._ensure_cities()
            dance_styles = self._ensure_dance_styles()
            self._store_all_course_assets()
            teachers_map = self._ensure_teachers(cities)
            studios_map = self._ensure_studios(cities)
            self._create_courses(dance_styles, teachers_map, studios_map)
            self._sync_course_id_sequence()

        self.stdout.write(self.style.SUCCESS("Successfully populated database with %d courses" % len(COURSES_DATA)))

    def _clear_data(self):
        Course.objects.all().delete()
        TeacherProfile.objects.all().delete()
        User.objects.filter(email__startswith="teacher_").delete()
        Studio.objects.all().delete()
        DanceStyle.objects.all().delete()
        self.stdout.write("Cleared existing data")

    def _ensure_cities(self):
        result = {}
        for name in ("Москва", "Санкт-Петербург"):
            city, _ = City.objects.get_or_create(name=name)
            result[name] = city
        return result

    def _ensure_dance_styles(self):
        result = {}
        styles = set(c["type"] for c in COURSES_DATA)
        for name in sorted(styles):
            slug = slugify(name.replace(" ", "-").replace("'", ""))
            style, _ = DanceStyle.objects.get_or_create(slug=slug, defaults={"name": name})
            if style.name != name:
                style.name = name
                style.save(update_fields=["name"])
            result[name] = style
        return result

    def _ensure_teachers(self, cities):
        result = {}
        seen_teachers = {}
        for card in COURSES_DATA:
            t = card["teacher"]
            name = t["name"]
            if name in seen_teachers:
                result[(name, card["id"])] = seen_teachers[name]
                continue

            parts = name.split(" ", 1)
            first_name = parts[0] if parts else name
            last_name = parts[1] if len(parts) > 1 else ""
            email = f"teacher_{uuid.uuid5(uuid.NAMESPACE_DNS, name).hex[:12]}@dancehub.local"

            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": "teacher",
                },
            )
            user.first_name = first_name
            user.last_name = last_name
            user.role = "teacher"
            user.city = cities.get(card["city"])
            teacher_image_urls = [
                self._store_seed_asset(TEACHER_IMAGES_MAP[image_key])
                for image_key in t.get("images", [])
                if image_key in TEACHER_IMAGES_MAP
            ]
            user.avatar = teacher_image_urls[0] if teacher_image_urls else user.avatar
            user.save(update_fields=["first_name", "last_name", "role", "city", "avatar"])

            profile, _ = TeacherProfile.objects.get_or_create(
                user=user,
                defaults={
                    "bio": t["bio"],
                    "images": teacher_image_urls,
                    "achievements": t.get("achievements", []),
                    "specializations": t.get("specializations", []),
                    "experience_years": t["experience"],
                    "rating_avg": t["rating"],
                    "rating_count": len(t["reviews"]),
                },
            )
            profile.bio = t["bio"]
            profile.images = teacher_image_urls
            profile.achievements = t.get("achievements", [])
            profile.specializations = t.get("specializations", [])
            profile.experience_years = t["experience"]
            profile.rating_avg = t["rating"]
            profile.rating_count = len(t["reviews"])
            profile.save()

            seen_teachers[name] = profile
            result[(name, card["id"])] = profile

        return result

    def _ensure_studios(self, cities):
        result = {}
        for card in COURSES_DATA:
            studio_name = card["studio"]
            city_name = card["city"]
            location = card.get("location", "")
            key = (studio_name, city_name)
            if key in result:
                continue

            city = cities[city_name]
            studio, created = Studio.objects.get_or_create(
                name=studio_name,
                city=city,
                defaults={
                    "address": location or studio_name,
                    "metro": location or "",
                    "halls_count": 1,
                },
            )
            if not created:
                studio.metro = location or studio.metro
                if studio.halls_count == 0:
                    studio.halls_count = 1
                studio.save(update_fields=["metro", "halls_count"])
            result[key] = studio

        return result

    def _parse_time(self, s: str):
        h, m = map(int, s.split(":"))
        return datetime(2000, 1, 1, h, m).time()

    def _create_courses(self, dance_styles, teachers_map, studios_map):
        for card in COURSES_DATA:
            teacher = teachers_map[(card["teacher"]["name"], card["id"])]
            city = card["city"]
            studio = studios_map[(card["studio"], city)]
            dance_style = dance_styles[card["type"]]
            level = LEVEL_MAP.get(card["level"], "any")

            image_urls = [
                self._store_seed_asset(COURSE_IMAGES_MAP[img_key])
                for img_key in card.get("images", [])
                if img_key in COURSE_IMAGES_MAP
            ]
            cover_url = image_urls[0] if image_urls else ""

            course, created = Course.objects.update_or_create(
                id=card["id"],
                defaults={
                    "teacher": teacher,
                    "dance_style": dance_style,
                    "studio": studio,
                    "name": card["name"],
                    "description": card["description"],
                    "level": level,
                    "price": card["price"],
                    "capacity": card["capacity"],
                    "date_from": parse_short_date(card["dateFrom"]),
                    "date_to": parse_short_date(card["dateTo"]),
                    "status": CourseStatus.PUBLISHED,
                    "images": image_urls,
                    "image_cover": cover_url,
                    "music_artist": card["music"]["artist"],
                    "music_track": card["music"]["track"],
                    "music_url": card["music"]["url"],
                },
            )

            CourseSchedule.objects.filter(course=course).delete()
            if "schedule" in card:
                for entry in card["schedule"]:
                    weekdays_str = entry["weekday"]
                    for part in weekdays_str.replace("，", ",").split(","):
                        wd = part.strip()
                        if wd in WEEKDAY_MAP:
                            CourseSchedule.objects.create(
                                course=course,
                                weekday=WEEKDAY_MAP[wd],
                                time_from=self._parse_time(entry["timeFrom"]),
                                time_to=self._parse_time(entry["timeTo"]),
                                location_text=entry.get("location", ""),
                            )
            elif "weekdays" in card:
                for wd in card["weekdays"]:
                    if wd in WEEKDAY_MAP:
                        CourseSchedule.objects.create(
                            course=course,
                            weekday=WEEKDAY_MAP[wd],
                            time_from=self._parse_time(card["timeFrom"]),
                            time_to=self._parse_time(card["timeTo"]),
                            location_text=card.get("location", ""),
                        )

            generate_course_lessons(course)

    def _store_seed_asset(self, relative_path: str) -> str:
        source_path = Path(settings.FRONTEND_ASSETS_ROOT) / "images" / relative_path
        if not source_path.exists():
            raise FileNotFoundError(f"Frontend asset not found: {source_path}")

        storage_path = f"seed/{relative_path}"
        if not default_storage.exists(storage_path):
            with source_path.open("rb") as source:
                default_storage.save(storage_path, File(source, name=source_path.name))

        return default_storage.url(storage_path)

    def _store_all_course_assets(self) -> None:
        courses_dir = Path(settings.FRONTEND_ASSETS_ROOT) / "images" / "courses"
        if not courses_dir.exists():
            raise FileNotFoundError(f"Frontend course assets directory not found: {courses_dir}")

        for source_path in sorted(courses_dir.iterdir()):
            if source_path.is_file() and source_path.suffix.lower() in COURSE_ASSET_EXTENSIONS:
                self._store_seed_asset(f"courses/{source_path.name}")

    def _sync_course_id_sequence(self):
        """Bring PostgreSQL sequence in sync after explicit id inserts."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT setval(
                    pg_get_serial_sequence('courses', 'id'),
                    COALESCE((SELECT MAX(id) FROM courses), 1),
                    true
                )
                """
            )
