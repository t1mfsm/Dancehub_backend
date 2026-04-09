"""
Management command to populate the database with course data from frontend cards.ts.
"""
import uuid
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import connection
from django.db import transaction
from django.utils.text import slugify

from apps.courses.models import (
    Course,
    CourseImage,
    CourseMusic,
    CourseScheduleRule,
    CourseStatus,
    DanceStyle,
    Hall,
    Studio,
    TeacherSpecialization,
)
from apps.courses.seed_data import COURSES_DATA
from apps.locations.models import City
from apps.users.models import DanceLevel, TeacherAchievement, TeacherProfile, TeacherReview, User, Weekday

# Map frontend image keys to URL paths (frontend serves from /assets/images/...)
COURSE_IMAGES_MAP = {
    "highHeels1": "/assets/images/courses/high-heels-1.jpg",
    "highHeels2": "/assets/images/courses/high-heels-2.jpg",
    "contemporary": "/assets/images/courses/contemporary.jpg",
    "jazzFunk": "/assets/images/courses/jazz-funk.jpg",
    "vogue": "/assets/images/courses/vogue.jpg",
    "hipHop": "/assets/images/courses/hip-hop.jpg",
    "dancehall": "/assets/images/courses/dancehall.jpeg",
    "frameUp": "/assets/images/courses/frame-up.jpg",
    "stretching": "/assets/images/courses/stretching.png",
    "ladyStyle": "/assets/images/courses/lady-style.jpg",
}

TEACHER_IMAGES_MAP = {
    "woman": "/assets/images/teachers/woman.jpg",
    "woman2": "/assets/images/teachers/w2.avif",
    "man": "/assets/images/teachers/man.png",
}

LEVEL_MAP = {
    "Начинающие": DanceLevel.BEGINNER,
    "Средний уровень": DanceLevel.INTERMEDIATE,
    "Продвинутые": DanceLevel.ADVANCED,
    "Любой уровень": DanceLevel.ANY,
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


def parse_short_date(short: str, year: int = 2025) -> datetime:
    """Parse '17.02' -> date(2025, 2, 17)."""
    day, month = map(int, short.split("."))
    return datetime(year, month, day).date()

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
            teachers_map = self._ensure_teachers(cities)
            studios_map = self._ensure_studios(cities)
            self._create_courses(dance_styles, teachers_map, studios_map)
            self._sync_course_id_sequence()

        self.stdout.write(self.style.SUCCESS("Successfully populated database with %d courses" % len(COURSES_DATA)))

    def _clear_data(self):
        Course.objects.all().delete()
        TeacherProfile.objects.all().delete()
        User.objects.filter(email__startswith="teacher_").delete()
        User.objects.filter(email__startswith="reviewer_").delete()
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
                    "is_teacher_enabled": True,
                },
            )
            user.first_name = first_name
            user.last_name = last_name
            user.role = "teacher"
            user.is_teacher_enabled = True
            user.city = cities.get(card["city"])
            teacher_image_urls = [
                TEACHER_IMAGES_MAP.get(image_key, f"/assets/images/teachers/{image_key}.jpg")
                for image_key in t.get("images", [])
            ]
            user.avatar = teacher_image_urls[0] if teacher_image_urls else user.avatar
            user.save(update_fields=["first_name", "last_name", "role", "is_teacher_enabled", "city", "avatar"])

            profile, _ = TeacherProfile.objects.get_or_create(
                user=user,
                defaults={
                    "bio": t["bio"],
                    "images": teacher_image_urls,
                    "experience_years": t["experience"],
                    "rating_avg": t["rating"],
                    "rating_count": len(t["reviews"]),
                },
            )
            profile.bio = t["bio"]
            profile.images = teacher_image_urls
            profile.experience_years = t["experience"]
            profile.rating_avg = t["rating"]
            profile.rating_count = len(t["reviews"])
            profile.save()

            for ach in t["achievements"]:
                TeacherAchievement.objects.get_or_create(teacher=profile, title=ach, defaults={"description": ""})

            for spec_name in t["specializations"]:
                style = None
                for ds in DanceStyle.objects.all():
                    if ds.name == spec_name or spec_name in ds.name:
                        style = ds
                        break
                if style:
                    TeacherSpecialization.objects.get_or_create(
                        teacher=profile,
                        dance_style=style,
                    )

            seen_teachers[name] = profile
            result[(name, card["id"])] = profile

            reviewer_users = self._ensure_reviewers(t["reviews"])
            for rev_data, author_user in zip(t["reviews"], reviewer_users):
                TeacherReview.objects.get_or_create(
                    author_user=author_user,
                    teacher=profile,
                    defaults={
                        "rating": rev_data["rating"],
                        "text": rev_data["text"],
                    },
                )

        return result

    def _ensure_reviewers(self, reviews):
        users = []
        for r in reviews:
            author = r["author"]
            email = f"reviewer_{uuid.uuid5(uuid.NAMESPACE_DNS, author).hex[:12]}@dancehub.local"
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "first_name": author,
                    "last_name": "",
                },
            )
            users.append(user)
        return users

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
            studio, _ = Studio.objects.get_or_create(
                name=studio_name,
                city=city,
                defaults={
                    "address": location or studio_name,
                    "metro": location or "",
                },
            )
            studio.metro = location or studio.metro
            studio.save(update_fields=["metro"])
            result[key] = studio

            hall, _ = Hall.objects.get_or_create(
                studio=studio,
                name="Основной зал",
                defaults={"capacity": card["capacity"]},
            )

        return result

    def _parse_time(self, s: str):
        h, m = map(int, s.split(":"))
        return datetime(2000, 1, 1, h, m).time()

    def _create_courses(self, dance_styles, teachers_map, studios_map):
        for card in COURSES_DATA:
            teacher = teachers_map[(card["teacher"]["name"], card["id"])]
            city = card["city"]
            studio = studios_map[(card["studio"], city)]
            hall = studio.halls.first()
            dance_style = dance_styles[card["type"]]
            level = LEVEL_MAP.get(card["level"], DanceLevel.ANY)

            course, created = Course.objects.update_or_create(
                id=card["id"],
                defaults={
                    "teacher": teacher,
                    "dance_style": dance_style,
                    "studio": studio,
                    "hall": hall,
                    "name": card["name"],
                    "description": card["description"],
                    "level": level,
                    "price": card["price"],
                    "capacity": card["capacity"],
                    "spots_left": card["spotsLeft"],
                    "date_from": parse_short_date(card["dateFrom"]),
                    "date_to": parse_short_date(card["dateTo"]),
                    "status": CourseStatus.PUBLISHED,
                    "image_cover": COURSE_IMAGES_MAP.get(
                        card["images"][0] if card["images"] else "",
                        "/assets/images/courses/placeholder.jpg",
                    ),
                },
            )

            CourseImage.objects.filter(course=course).delete()
            for i, img_key in enumerate(card["images"]):
                url = COURSE_IMAGES_MAP.get(img_key, f"/assets/images/courses/{img_key}.jpg")
                CourseImage.objects.create(course=course, image=url, sort_order=i)

            CourseMusic.objects.filter(course=course).delete()
            CourseMusic.objects.create(
                course=course,
                artist=card["music"]["artist"],
                track=card["music"]["track"],
                url=card["music"]["url"],
            )

            CourseScheduleRule.objects.filter(course=course).delete()
            if "schedule" in card:
                for entry in card["schedule"]:
                    weekdays_str = entry["weekday"]
                    for part in weekdays_str.replace("，", ",").split(","):
                        wd = part.strip()
                        if wd in WEEKDAY_MAP:
                            CourseScheduleRule.objects.create(
                                course=course,
                                weekday=WEEKDAY_MAP[wd],
                                time_from=self._parse_time(entry["timeFrom"]),
                                time_to=self._parse_time(entry["timeTo"]),
                                location_text=entry.get("location", ""),
                            )
            elif "weekdays" in card:
                for wd in card["weekdays"]:
                    if wd in WEEKDAY_MAP:
                        CourseScheduleRule.objects.create(
                            course=course,
                            weekday=WEEKDAY_MAP[wd],
                            time_from=self._parse_time(card["timeFrom"]),
                            time_to=self._parse_time(card["timeTo"]),
                            location_text=card.get("location", ""),
                        )

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
