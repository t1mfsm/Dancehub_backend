from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.courses.models import (
    Attendance,
    AttendanceStatus,
    Course,
    CourseScheduleRule,
    CourseStatus,
    DanceStyle,
    Enrollment,
    EnrollmentStatus,
    FavoriteCourse,
    Hall,
    Lesson,
    LessonStatus,
    Studio,
)
from apps.locations.models import City
from apps.users.models import (
    DanceLevel,
    FavoriteTeacher,
    TeacherProfile,
    TeacherReview,
    User,
    UserDanceStyleSkill,
    UserRole,
    Weekday,
)


DEMO_EMAIL_DOMAIN = "dancehub.demo"
DEFAULT_PASSWORD = "DemoPass123!"

FIRST_NAMES_FEMALE = [
    "Анна", "Мария", "Екатерина", "Софья", "Дарья", "Полина", "Виктория", "Алина", "Вероника", "Анастасия",
    "Ксения", "Елизавета", "Ольга", "Татьяна", "Юлия", "Валерия", "Наталья", "Диана", "Арина", "Милана",
]
LAST_NAMES_FEMALE = [
    "Иванова", "Петрова", "Смирнова", "Кузнецова", "Попова", "Васильева", "Соколова", "Морозова", "Новикова",
    "Федорова", "Волкова", "Алексеева", "Лебедева", "Семенова", "Егорова", "Павлова", "Козлова", "Степанова",
]
MIDDLE_NAMES_FEMALE = [
    "Александровна", "Ивановна", "Дмитриевна", "Сергеевна", "Андреевна", "Максимовна", "Павловна", "Олеговна",
]
FIRST_NAMES_MALE = [
    "Алексей", "Дмитрий", "Илья", "Никита", "Кирилл", "Максим", "Артем", "Егор", "Сергей", "Михаил",
]
LAST_NAMES_MALE = [
    "Иванов", "Петров", "Смирнов", "Кузнецов", "Попов", "Васильев", "Соколов", "Морозов", "Новиков", "Федоров",
]
MIDDLE_NAMES_MALE = [
    "Александрович", "Иванович", "Дмитриевич", "Сергеевич", "Андреевич", "Максимович", "Павлович", "Олегович",
]

BIO_TEMPLATES = [
    "Преподаю {style} и работаю с техникой, музыкальностью и уверенностью в движении.",
    "Веду группы по {style}, люблю понятную структуру занятий и тёплую атмосферу.",
    "Помогаю ученикам расти в {style}: от базовой техники до уверенной подачи.",
    "Ставлю хореографию по {style}, уделяю внимание телу, пластике и сценическому образу.",
]
ACHIEVEMENTS = [
    "Участник российских танцевальных фестивалей",
    "Победитель городского баттла 2024",
    "Постановщик коммерческих шоу-номеров",
    "Член судейской команды локальных чемпионатов",
    "Участник интенсивов европейских хореографов",
]
REVIEW_PHRASES = [
    "Очень понятная подача и много внимания к технике.",
    "После курса стало намного спокойнее на занятиях и на съёмках.",
    "Сильная атмосфера в группе и правда заметный прогресс.",
    "Преподаватель мягко, но точно исправляет ошибки.",
    "Классный баланс базы, хореографии и музыкальности.",
    "Хочется возвращаться на занятия снова и снова.",
]
MUSIC_ARTISTS = [
    "Tinashe", "Doja Cat", "The Weeknd", "Beyonce", "Ariana Grande", "SZA", "Rosalia", "Dua Lipa", "Raye", "Jorja Smith",
]
MUSIC_TRACKS = [
    "Needs", "Agora Hills", "Starboy", "Alien Superstar", "yes, and?", "Snooze", "Despecha", "Houdini", "Escapism", "Little Things",
]
COURSE_ADJECTIVES = [
    "Base", "Flow", "Intensive", "Choreo", "Lab", "Weekend", "Practice", "Pro", "Start", "Session",
]
STUDIO_PREFIXES = ["Dance", "Move", "Rhythm", "Frame", "Pulse", "Urban", "Balance", "Stage", "House", "Groove"]
STUDIO_SUFFIXES = ["Space", "Point", "Loft", "Hub", "Base", "Room", "District", "Factory", "Line", "Place"]

CITY_DATA = [
    {
        "name": "Москва",
        "lat": Decimal("55.7558"),
        "lng": Decimal("37.6173"),
        "metros": ["Павелецкая", "Таганская", "Белорусская", "Курская", "Бауманская", "Савеловская", "Дмитровская"],
        "districts": ["Пресненский", "Таганский", "Басманный", "Даниловский", "Савеловский"],
        "streets": ["Лесная", "Большая Почтовая", "Новослободская", "Нижняя Красносельская", "Электрозаводская"],
    },
    {
        "name": "Санкт-Петербург",
        "lat": Decimal("59.9343"),
        "lng": Decimal("30.3351"),
        "metros": ["Площадь Восстания", "Лиговский проспект", "Петроградская", "Чкаловская", "Фрунзенская"],
        "districts": ["Центральный", "Петроградский", "Адмиралтейский", "Василеостровский"],
        "streets": ["Лиговский проспект", "Кронверкский проспект", "Марата", "Большой проспект", "Гороховая"],
    },
    {
        "name": "Казань",
        "lat": Decimal("55.7961"),
        "lng": Decimal("49.1064"),
        "metros": ["Кремлевская", "Суконная слобода", "Аметьево", "Козья слобода"],
        "districts": ["Вахитовский", "Приволжский", "Ново-Савиновский"],
        "streets": ["Баумана", "Пушкина", "Петербургская", "Чистопольская", "Спартаковская"],
    },
    {
        "name": "Екатеринбург",
        "lat": Decimal("56.8389"),
        "lng": Decimal("60.6057"),
        "metros": ["Геологическая", "Площадь 1905 года", "Динамо", "Чкаловская"],
        "districts": ["Ленинский", "Октябрьский", "Кировский", "Железнодорожный"],
        "streets": ["Малышева", "8 Марта", "Белинского", "Луначарского", "Куйбышева"],
    },
]
STYLE_NAMES = [
    "High Heels", "Contemporary", "Jazz Funk", "Vogue", "Hip-Hop", "Dancehall", "Frame Up", "Stretching",
    "Lady Style", "House", "Waacking", "Commercial",
]


@dataclass
class PersonName:
    first_name: str
    last_name: str
    middle_name: str
    gender: str


class Command(BaseCommand):
    help = "Populate the database with realistic demo data for DanceHub."

    def add_arguments(self, parser):
        parser.add_argument("--students", type=int, default=50, help="Number of student users to create.")
        parser.add_argument("--teachers", type=int, default=20, help="Number of teachers to create.")
        parser.add_argument("--courses", type=int, default=200, help="Number of courses to create.")
        parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic generation.")
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete previously generated demo data before seeding.",
        )
        parser.add_argument(
            "--clear-all",
            action="store_true",
            help="Delete all domain data (courses, users, studios, reviews, enrollments) before seeding.",
        )

    def handle(self, *args, **options):
        self.random = random.Random(options["seed"])
        self.today = timezone.localdate()
        self.stdout.write("Seeding demo data...")

        with transaction.atomic():
            if options["clear_all"]:
                self._clear_all_domain_data()
            elif options["clear"]:
                self._clear_demo_data()

            cities = self._ensure_cities()
            styles = self._ensure_styles()
            studios = self._ensure_studios(cities)
            halls = self._ensure_halls(studios)
            teachers = self._ensure_teachers(options["teachers"], cities, styles)
            students = self._ensure_students(options["students"], cities, styles)
            courses = self._ensure_courses(options["courses"], teachers, styles, studios, halls)
            self._ensure_enrollments_and_attendance(courses, students)
            self._ensure_favorites(students, teachers, courses)
            self._ensure_teacher_reviews(teachers, students)

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        self.stdout.write(
            f"Created/updated: {len(cities)} cities, {len(styles)} styles, {len(studios)} studios, "
            f"{len(halls)} halls, {len(teachers)} teachers, {len(students)} students, {len(courses)} courses."
        )
        self.stdout.write(f"Demo users password: {DEFAULT_PASSWORD}")

    def _clear_demo_data(self):
        demo_users = User.objects.filter(email__iendswith=f"@{DEMO_EMAIL_DOMAIN}")
        demo_teacher_profiles = TeacherProfile.objects.filter(user__in=demo_users)
        demo_courses = Course.objects.filter(teacher__in=demo_teacher_profiles)

        Attendance.objects.filter(lesson__course__in=demo_courses).delete()
        FavoriteCourse.objects.filter(course__in=demo_courses).delete()
        Enrollment.objects.filter(course__in=demo_courses).delete()
        Lesson.objects.filter(course__in=demo_courses).delete()
        CourseScheduleRule.objects.filter(course__in=demo_courses).delete()
        demo_courses.delete()
        TeacherReview.objects.filter(teacher__in=demo_teacher_profiles).delete()
        FavoriteTeacher.objects.filter(teacher__in=demo_teacher_profiles).delete()
        UserDanceStyleSkill.objects.filter(user__in=demo_users).delete()
        demo_teacher_profiles.delete()
        Hall.objects.filter(studio__name__startswith="Studio ").delete()
        Studio.objects.filter(name__startswith="Studio ").delete()
        demo_users.delete()

    def _clear_all_domain_data(self):
        Attendance.objects.all().delete()
        FavoriteCourse.objects.all().delete()
        FavoriteTeacher.objects.all().delete()
        TeacherReview.objects.all().delete()
        Enrollment.objects.all().delete()
        Lesson.objects.all().delete()
        CourseScheduleRule.objects.all().delete()
        Course.objects.all().delete()
        Hall.objects.all().delete()
        Studio.objects.all().delete()
        UserDanceStyleSkill.objects.all().delete()
        TeacherProfile.objects.all().delete()
        User.objects.exclude(is_superuser=True).delete()
        DanceStyle.objects.all().delete()
        City.objects.all().delete()

    def _ensure_cities(self) -> list[City]:
        cities: list[City] = []
        for city_info in CITY_DATA:
            city, _ = City.objects.get_or_create(name=city_info["name"])
            cities.append(city)
        return cities

    def _ensure_styles(self) -> list[DanceStyle]:
        styles: list[DanceStyle] = []
        for name in STYLE_NAMES:
            style, _ = DanceStyle.objects.get_or_create(
                slug=slugify(name),
                defaults={"name": name},
            )
            if style.name != name:
                style.name = name
                style.save(update_fields=["name"])
            styles.append(style)
        return styles

    def _ensure_studios(self, cities: list[City]) -> list[Studio]:
        studios: list[Studio] = []
        for city_index, city in enumerate(cities):
            city_info = CITY_DATA[city_index]
            for studio_index in range(6):
                prefix = STUDIO_PREFIXES[(city_index * 3 + studio_index) % len(STUDIO_PREFIXES)]
                suffix = STUDIO_SUFFIXES[(city_index * 5 + studio_index) % len(STUDIO_SUFFIXES)]
                district = city_info["districts"][studio_index % len(city_info["districts"])]
                street = city_info["streets"][studio_index % len(city_info["streets"])]
                house_number = 5 + studio_index * 3
                name = f"Studio {prefix} {suffix} {district}"
                metro = city_info["metros"][studio_index % len(city_info["metros"])]
                lat = city_info["lat"] + Decimal(str(self.random.uniform(-0.08, 0.08))).quantize(Decimal("0.000001"))
                lng = city_info["lng"] + Decimal(str(self.random.uniform(-0.08, 0.08))).quantize(Decimal("0.000001"))

                studio, _ = Studio.objects.get_or_create(
                    name=name,
                    city=city,
                    defaults={
                        "address": f"ул. {street}, {house_number}",
                        "metro": metro,
                        "lat": lat,
                        "lng": lng,
                        "image": "",
                    },
                )
                studio.address = f"ул. {street}, {house_number}"
                studio.metro = metro
                studio.lat = lat
                studio.lng = lng
                studio.image = ""
                studio.save(update_fields=["address", "metro", "lat", "lng", "image"])
                studios.append(studio)
        return studios

    def _ensure_halls(self, studios: list[Studio]) -> list[Hall]:
        halls: list[Hall] = []
        for studio in studios:
            desired_count = self.random.randint(2, 4)
            studio_halls = []
            for index in range(desired_count):
                hall, _ = Hall.objects.get_or_create(
                    studio=studio,
                    name=f"Зал {index + 1}",
                )
                studio_halls.append(hall)
            halls.extend(studio_halls)
        return halls

    def _ensure_teachers(self, count: int, cities: list[City], styles: list[DanceStyle]) -> list[TeacherProfile]:
        teachers: list[TeacherProfile] = []
        for index in range(count):
            name = self._build_person(index, teacher=True)
            city = cities[index % len(cities)]
            email = f"teacher{index + 1}@{DEMO_EMAIL_DOMAIN}"
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": f"teacher_{index + 1}",
                    "first_name": name.first_name,
                    "middle_name": name.middle_name,
                    "last_name": name.last_name,
                    "phone": self._phone(index),
                    "role": UserRole.TEACHER,
                },
            )
            user.username = f"teacher_{index + 1}"
            user.first_name = name.first_name
            user.middle_name = name.middle_name
            user.last_name = name.last_name
            user.phone = self._phone(index)
            user.city = city
            user.role = UserRole.TEACHER
            user.dance_level = DanceLevel.ADVANCED
            user.survey_completed = True
            user.flags = {"onboarding_seen": True, "profile_completed": True}
            user.set_password(DEFAULT_PASSWORD)
            user.save()

            teacher_styles = self.random.sample(styles, k=self.random.randint(2, 4))
            profile, _ = TeacherProfile.objects.get_or_create(user=user)
            profile.bio = self.random.choice(BIO_TEMPLATES).format(style=teacher_styles[0].name)
            profile.images = []
            profile.achievements = self.random.sample(ACHIEVEMENTS, k=self.random.randint(2, 4))
            profile.specializations = [style.name for style in teacher_styles]
            profile.experience_years = self.random.randint(3, 12)
            profile.rating_avg = Decimal(str(round(self.random.uniform(4.4, 5.0), 2)))
            profile.rating_count = 0
            profile.save()

            UserDanceStyleSkill.objects.filter(user=user).delete()
            UserDanceStyleSkill.objects.bulk_create(
                [
                    UserDanceStyleSkill(user=user, dance_style=style, level=DanceLevel.ADVANCED)
                    for style in teacher_styles
                ]
            )
            teachers.append(profile)
        return teachers

    def _ensure_students(self, count: int, cities: list[City], styles: list[DanceStyle]) -> list[User]:
        students: list[User] = []
        for index in range(count):
            name = self._build_person(index, teacher=False)
            city = cities[index % len(cities)]
            email = f"student{index + 1}@{DEMO_EMAIL_DOMAIN}"
            user, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": f"student_{index + 1}",
                    "first_name": name.first_name,
                    "middle_name": name.middle_name,
                    "last_name": name.last_name,
                    "phone": self._phone(index + 100),
                    "role": UserRole.STUDENT,
                },
            )
            preferred_styles = self.random.sample(styles, k=self.random.randint(1, 4))
            preferred_weekdays = self.random.sample([choice for choice, _ in Weekday.choices], k=self.random.randint(2, 4))
            level = self.random.choice([DanceLevel.BEGINNER, DanceLevel.INTERMEDIATE, DanceLevel.ADVANCED])

            user.username = f"student_{index + 1}"
            user.first_name = name.first_name
            user.middle_name = name.middle_name
            user.last_name = name.last_name
            user.phone = self._phone(index + 100)
            user.city = city
            user.role = UserRole.STUDENT
            user.dance_level = level
            user.survey_completed = True
            user.preferred_time_from = self.random.choice([time(10, 0), time(12, 0), time(18, 0), time(19, 30)])
            user.preferred_time_to = self.random.choice([time(14, 0), time(20, 0), time(21, 30), time(23, 0)])
            user.preferred_weekdays = preferred_weekdays
            user.preferred_dance_styles = [style.name for style in preferred_styles]
            user.survey_preferences = {
                "price_from": self.random.choice([3000, 5000, 7000]),
                "price_to": self.random.choice([12000, 15000, 18000, 22000]),
            }
            user.flags = {"onboarding_seen": True}
            user.set_password(DEFAULT_PASSWORD)
            user.save()

            UserDanceStyleSkill.objects.filter(user=user).delete()
            UserDanceStyleSkill.objects.bulk_create(
                [
                    UserDanceStyleSkill(
                        user=user,
                        dance_style=style,
                        level=self.random.choice([DanceLevel.BEGINNER, DanceLevel.INTERMEDIATE]),
                    )
                    for style in preferred_styles
                ]
            )
            students.append(user)
        return students

    def _ensure_courses(
        self,
        count: int,
        teachers: list[TeacherProfile],
        styles: list[DanceStyle],
        studios: list[Studio],
        halls: list[Hall],
    ) -> list[Course]:
        courses: list[Course] = []
        halls_by_studio: dict[int, list[Hall]] = {}
        for hall in halls:
            halls_by_studio.setdefault(hall.studio_id, []).append(hall)

        for index in range(count):
            teacher = teachers[index % len(teachers)]
            style = self.random.choice(styles)
            city_studios = [studio for studio in studios if studio.city_id == teacher.user.city_id]
            studio = self.random.choice(city_studios or studios)
            status, date_from, date_to = self._course_timeline(index)
            capacity = self.random.choice([12, 14, 16, 18, 20, 24])
            adjective = COURSE_ADJECTIVES[index % len(COURSE_ADJECTIVES)]
            name = f"{style.name} {adjective} {index + 1}"

            course, _ = Course.objects.get_or_create(
                teacher=teacher,
                name=name,
                date_from=date_from,
                defaults={
                    "dance_style": style,
                    "studio": studio,
                    "description": self._course_description(style.name, teacher.user.first_name),
                    "level": self.random.choice(
                        [DanceLevel.BEGINNER, DanceLevel.INTERMEDIATE, DanceLevel.ADVANCED, DanceLevel.ANY]
                    ),
                    "price": Decimal(str(self.random.choice([4500, 6000, 7500, 9000, 12000, 15000]))),
                    "capacity": capacity,
                    "spots_left": capacity,
                    "date_to": date_to,
                    "status": status,
                    "music_artist": self.random.choice(MUSIC_ARTISTS),
                    "music_track": self.random.choice(MUSIC_TRACKS),
                    "music_url": "",
                    "image_cover": "",
                },
            )
            course.dance_style = style
            course.studio = studio
            course.description = self._course_description(style.name, teacher.user.first_name)
            course.level = self.random.choice(
                [DanceLevel.BEGINNER, DanceLevel.INTERMEDIATE, DanceLevel.ADVANCED, DanceLevel.ANY]
            )
            course.price = Decimal(str(self.random.choice([4500, 6000, 7500, 9000, 12000, 15000])))
            course.capacity = capacity
            course.date_to = date_to
            course.status = status
            course.music_artist = self.random.choice(MUSIC_ARTISTS)
            course.music_track = self.random.choice(MUSIC_TRACKS)
            course.music_url = ""
            course.image_cover = ""
            course.save()

            course.schedule_rules.all().delete()
            course.lessons.all().delete()
            self._create_schedule_rules(course, halls_by_studio.get(studio.id, []))
            self._create_lessons(course)
            courses.append(course)

        return courses

    def _create_schedule_rules(self, course: Course, studio_halls: list[Hall]):
        weekday_groups = [
            [Weekday.MONDAY, Weekday.WEDNESDAY],
            [Weekday.TUESDAY, Weekday.THURSDAY],
            [Weekday.FRIDAY],
            [Weekday.SATURDAY],
            [Weekday.SUNDAY],
        ]
        selected_days = self.random.choice(weekday_groups)
        if self.random.random() < 0.35:
            extra_day = self.random.choice([Weekday.FRIDAY, Weekday.SATURDAY, Weekday.SUNDAY])
            if extra_day not in selected_days:
                selected_days = selected_days + [extra_day]

        start_time = self.random.choice([time(10, 0), time(12, 0), time(18, 0), time(19, 30), time(20, 0)])
        duration_minutes = self.random.choice([60, 90])
        end_time = (datetime.combine(date.today(), start_time) + timedelta(minutes=duration_minutes)).time()
        location_text = f"м. {course.studio.metro}" if course.studio and course.studio.metro else course.studio.address
        hall = self.random.choice(studio_halls) if studio_halls else None

        for weekday in selected_days:
            CourseScheduleRule.objects.create(
                course=course,
                hall=hall,
                weekday=weekday,
                time_from=start_time,
                time_to=end_time,
                location_text=location_text,
            )

    def _create_lessons(self, course: Course):
        weekday_to_index = {code: index for index, (code, _) in enumerate(Weekday.choices)}
        for rule in course.schedule_rules.all():
            current = course.date_from
            while current <= course.date_to:
                if current.weekday() == weekday_to_index[rule.weekday]:
                    status = self._lesson_status(course, current)
                    Lesson.objects.update_or_create(
                        course=course,
                        lesson_date=current,
                        time_from=rule.time_from,
                        defaults={
                            "schedule_rule": rule,
                            "hall": rule.hall,
                            "time_to": rule.time_to,
                            "location_text": rule.location_text,
                            "status": status,
                        },
                    )
                current += timedelta(days=1)

    def _ensure_enrollments_and_attendance(self, courses: list[Course], students: list[User]):
        for course in courses:
            Attendance.objects.filter(lesson__course=course).delete()
            Enrollment.objects.filter(course=course).delete()
            if course.status == CourseStatus.DRAFT:
                course.spots_left = course.capacity
                course.save(update_fields=["spots_left"])
                continue

            max_students = min(len(students), max(5, course.capacity - self.random.randint(0, 4)))
            enrolled_students = self.random.sample(students, k=max_students)
            active_count = 0
            for student in enrolled_students:
                enrollment_status = self._enrollment_status(course)
                if enrollment_status == EnrollmentStatus.ACTIVE:
                    active_count += 1
                enrolled_at = course.date_from - timedelta(days=self.random.randint(3, 45))
                enrollment, _ = Enrollment.objects.update_or_create(
                    user=student,
                    course=course,
                    defaults={
                        "enrolled_at": enrolled_at,
                        "status": enrollment_status,
                        "paid": enrollment_status in {EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED},
                        "cancelled_at": timezone.now() if enrollment_status == EnrollmentStatus.CANCELLED else None,
                    },
                )
                self._ensure_attendance_for_enrollment(course, enrollment)

            course.spots_left = max(0, course.capacity - active_count)
            course.save(update_fields=["spots_left"])

    def _ensure_attendance_for_enrollment(self, course: Course, enrollment: Enrollment):
        if enrollment.status not in {EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED}:
            return

        lessons = course.lessons.filter(
            lesson_date__lt=self.today,
            status__in=[LessonStatus.COMPLETED, LessonStatus.SCHEDULED],
        )
        attendance_probability = 0.78 if enrollment.user.dance_level != DanceLevel.BEGINNER else 0.68
        for lesson in lessons:
            status = AttendanceStatus.PRESENT if self.random.random() < attendance_probability else AttendanceStatus.ABSENT
            Attendance.objects.update_or_create(
                lesson=lesson,
                student=enrollment.user,
                defaults={"status": status},
            )

    def _ensure_favorites(self, students: list[User], teachers: list[TeacherProfile], courses: list[Course]):
        published_courses = [course for course in courses if course.status in {CourseStatus.PUBLISHED, CourseStatus.COMPLETED}]
        for student in students:
            FavoriteCourse.objects.filter(user=student).delete()
            FavoriteTeacher.objects.filter(user=student).delete()
            for course in self.random.sample(published_courses, k=min(len(published_courses), self.random.randint(2, 6))):
                FavoriteCourse.objects.get_or_create(user=student, course=course)
            for teacher in self.random.sample(teachers, k=min(len(teachers), self.random.randint(1, 4))):
                FavoriteTeacher.objects.get_or_create(user=student, teacher=teacher)

    def _ensure_teacher_reviews(self, teachers: list[TeacherProfile], students: list[User]):
        for teacher in teachers:
            TeacherReview.objects.filter(teacher=teacher).delete()
            reviewers = self.random.sample(students, k=min(len(students), self.random.randint(5, 12)))
            ratings = []
            for reviewer in reviewers:
                rating = self.random.choice([4, 4, 5, 5, 5])
                review, _ = TeacherReview.objects.update_or_create(
                    author_user=reviewer,
                    teacher=teacher,
                    defaults={
                        "rating": rating,
                        "text": self.random.choice(REVIEW_PHRASES),
                    },
                )
                ratings.append(review.rating)

            if ratings:
                teacher.rating_count = len(ratings)
                teacher.rating_avg = Decimal(str(round(sum(ratings) / len(ratings), 2)))
                teacher.save(update_fields=["rating_count", "rating_avg"])

    def _build_person(self, index: int, teacher: bool) -> PersonName:
        female = index % 4 != 0 or teacher
        if female:
            return PersonName(
                first_name=FIRST_NAMES_FEMALE[index % len(FIRST_NAMES_FEMALE)],
                last_name=LAST_NAMES_FEMALE[(index * 3) % len(LAST_NAMES_FEMALE)],
                middle_name=MIDDLE_NAMES_FEMALE[(index * 5) % len(MIDDLE_NAMES_FEMALE)],
                gender="f",
            )
        return PersonName(
            first_name=FIRST_NAMES_MALE[index % len(FIRST_NAMES_MALE)],
            last_name=LAST_NAMES_MALE[(index * 3) % len(LAST_NAMES_MALE)],
            middle_name=MIDDLE_NAMES_MALE[(index * 5) % len(MIDDLE_NAMES_MALE)],
            gender="m",
        )

    def _phone(self, index: int) -> str:
        return f"+79{900000000 + index:09d}"

    def _course_timeline(self, index: int) -> tuple[str, date, date]:
        bucket = index % 10
        if bucket <= 5:
            start = self.today - timedelta(days=self.random.randint(14, 45))
            end = self.today + timedelta(days=self.random.randint(20, 90))
            return CourseStatus.PUBLISHED, start, end
        if bucket <= 7:
            start = self.today - timedelta(days=self.random.randint(120, 220))
            end = start + timedelta(days=self.random.randint(45, 90))
            return CourseStatus.COMPLETED, start, end
        if bucket == 8:
            start = self.today + timedelta(days=self.random.randint(10, 40))
            end = start + timedelta(days=self.random.randint(45, 90))
            return CourseStatus.DRAFT, start, end
        start = self.today - timedelta(days=self.random.randint(10, 30))
        end = self.today + timedelta(days=self.random.randint(20, 70))
        return CourseStatus.CANCELLED, start, end

    def _course_description(self, style_name: str, teacher_name: str) -> str:
        return (
            f"Курс по направлению {style_name} с упором на технику, музыкальность и уверенную подачу. "
            f"Программу ведёт {teacher_name}, занятия подходят для регулярной практики и роста."
        )

    def _lesson_status(self, course: Course, lesson_date: date) -> str:
        if course.status == CourseStatus.CANCELLED and self.random.random() < 0.6:
            return LessonStatus.CANCELLED
        if lesson_date < self.today:
            return LessonStatus.CANCELLED if self.random.random() < 0.08 else LessonStatus.COMPLETED
        return LessonStatus.SCHEDULED

    def _enrollment_status(self, course: Course) -> str:
        if course.status == CourseStatus.COMPLETED:
            return self.random.choice([EnrollmentStatus.COMPLETED, EnrollmentStatus.COMPLETED, EnrollmentStatus.CANCELLED])
        if course.status == CourseStatus.CANCELLED:
            return self.random.choice([EnrollmentStatus.CANCELLED, EnrollmentStatus.CANCELLED, EnrollmentStatus.ACTIVE])
        return self.random.choice([EnrollmentStatus.ACTIVE, EnrollmentStatus.ACTIVE, EnrollmentStatus.ACTIVE, EnrollmentStatus.PENDING])
