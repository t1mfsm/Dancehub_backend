"""
Management command to populate the database with course data from frontend cards.ts.
"""
from datetime import datetime

from django.core.management.base import BaseCommand
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


COURSES_DATA = [
    {
        "id": 1,
        "name": "High Heels PRO Intensive",
        "type": "High Heels",
        "teacher": {
            "name": "Карпова Ксения",
            "bio": "Хореограф и основатель студии. Более 10 лет в танцевальной индустрии.",
            "achievements": [
                "Финалист Dance Parade 2023",
                "Судья танцевальных баттлов",
                "Обучила более 500 учеников",
            ],
            "experience": 10,
            "specializations": ["High Heels", "Frame Up", "Lady Style"],
            "images": ["woman2", "woman"],
            "rating": 4.9,
            "reviews": [
                {"author": "Алина", "date": "12.01.2025", "text": "Ксения — невероятный педагог! После её интенсива я наконец почувствовала уверенность на каблуках.", "rating": 5},
                {"author": "Виктория", "date": "28.12.2024", "text": "Очень структурированные занятия, всё по делу. Прогресс заметен уже после первой недели.", "rating": 5},
                {"author": "Марина", "date": "15.11.2024", "text": "Энергетика на занятиях потрясающая. Ксения умеет мотивировать и находит подход к каждому.", "rating": 4},
            ],
        },
        "level": "Продвинутые",
        "dateFrom": "17.02",
        "dateTo": "04.03",
        "price": 15000,
        "images": ["highHeels1", "highHeels2"],
        "studio": "ТанцХаб",
        "city": "Москва",
        "description": "Интенсив с плавающим расписанием. Подходит для занятых танцоров.",
        "location": "м. Павелецкая",
        "capacity": 20,
        "spotsLeft": 6,
        "schedule": [
            {"weekday": "Пн, Вт", "timeFrom": "20:00", "timeTo": "21:00", "location": "м. Павелецкая"},
            {"weekday": "Ср", "timeFrom": "18:00", "timeTo": "19:00", "location": "м. Курская"},
            {"weekday": "Пт", "timeFrom": "21:00", "timeTo": "22:30", "location": "м. Павелецкая"},
        ],
        "music": {"artist": "Tinashe", "track": "Needs", "url": "https://open.spotify.com/track/1cUq5d1b0KfH7lPp7sGzvC"},
    },
    {
        "id": 2,
        "name": "High Heels с нуля",
        "type": "High Heels",
        "teacher": {
            "name": "Иванова Мария",
            "bio": "Педагог по High Heels с фокусом на работу с начинающими.",
            "achievements": ["Призёр Hip Hop International Russia", "Сертифицированный преподаватель FIDS"],
            "experience": 6,
            "specializations": ["High Heels", "Strip Plastic"],
            "images": ["woman", "woman", "woman"],
            "rating": 4.5,
            "reviews": [
                {"author": "Дарья", "date": "20.01.2025", "text": "Мария отлично объясняет базу. Я пришла с нуля и уже через месяц могла танцевать связки!", "rating": 5},
                {"author": "Екатерина", "date": "05.01.2025", "text": "Терпеливый и внимательный педагог. Всегда подскажет, поправит технику.", "rating": 4},
            ],
        },
        "level": "Начинающие",
        "dateFrom": "03.02",
        "dateTo": "15.02",
        "price": 8000,
        "images": ["highHeels2", "highHeels2", "highHeels2"],
        "studio": "DanceLab",
        "city": "Москва",
        "description": "Первый шаг в мир каблуков.",
        "location": "м. Курская",
        "capacity": 30,
        "spotsLeft": 12,
        "weekdays": ["Вт", "Чт"],
        "timeFrom": "18:00",
        "timeTo": "19:30",
        "music": {"artist": "Beyoncé", "track": "Partition", "url": "https://open.spotify.com/track/6RX5iL93VZ5fKmyvNXvF1r"},
    },
    {
        "id": 3,
        "name": "Основы Contemporary",
        "type": "Contemporary",
        "teacher": {
            "name": "Смирнова Анна",
            "bio": "Танцовщица и хореограф современного танца. Выступала на международных фестивалях.",
            "achievements": ["Участник Open Look Festival", "Стипендиат программы DanceWeb"],
            "experience": 8,
            "specializations": ["Contemporary", "Modern", "Импровизация"],
            "images": ["woman", "woman", "woman"],
            "rating": 4.7,
            "reviews": [
                {"author": "Полина", "date": "18.01.2025", "text": "Анна раскрывает танец с другой стороны. Много работы с импровизацией — это бесценно.", "rating": 5},
                {"author": "Олег", "date": "02.01.2025", "text": "Глубокий подход к движению. После курса стал совсем иначе чувствовать своё тело.", "rating": 5},
                {"author": "Настя", "date": "10.12.2024", "text": "Хороший курс, но хотелось бы больше техники и меньше импровизации.", "rating": 4},
            ],
        },
        "level": "Средний уровень",
        "dateFrom": "05.02",
        "dateTo": "20.02",
        "price": 9500,
        "images": ["contemporary", "contemporary", "contemporary"],
        "studio": "Студия движения",
        "city": "Москва",
        "description": "Импровизация и работа с телом.",
        "location": "м. Чистые пруды",
        "capacity": 25,
        "spotsLeft": 8,
        "weekdays": ["Пн", "Ср"],
        "timeFrom": "17:00",
        "timeTo": "18:30",
        "music": {"artist": "Ludovico Einaudi", "track": "Experience", "url": "https://open.spotify.com/track/1BncfTJAWxrsxyT9culBrj"},
    },
    {
        "id": 4,
        "name": "Jazz Funk для начинающих",
        "type": "Jazz Funk",
        "teacher": {
            "name": "Орлова Дарья",
            "bio": "Энергичный тренер с уникальным стилем преподавания. Работает с детскими и взрослыми группами.",
            "achievements": ["Победитель Groove Dance Champ 2022", "Танцовщица клипов российских артистов"],
            "experience": 5,
            "specializations": ["Jazz Funk", "Hip-Hop", "Commercial"],
            "images": ["woman", "woman", "woman"],
            "rating": 4.3,
            "reviews": [
                {"author": "Кристина", "date": "22.01.2025", "text": "Дарья заряжает энергией! Занятия пролетают незаметно, хочется ещё и ещё.", "rating": 5},
                {"author": "Софья", "date": "08.01.2025", "text": "Классные связки, много драйва. Иногда темп слишком быстрый для новичков.", "rating": 4},
            ],
        },
        "level": "Начинающие",
        "dateFrom": "10.02",
        "dateTo": "22.02",
        "price": 7000,
        "images": ["jazzFunk", "jazzFunk", "jazzFunk"],
        "studio": "Арт-пространство",
        "city": "Санкт-Петербург",
        "description": "Яркие связки и музыкальность.",
        "location": "м. Таганская",
        "capacity": 35,
        "spotsLeft": 18,
        "weekdays": ["Вт", "Чт", "Сб"],
        "timeFrom": "12:00",
        "timeTo": "13:30",
        "music": {"artist": "Doja Cat", "track": "Woman", "url": "https://open.spotify.com/track/6Uj1ctrBOjOas8xZXGqKk4"},
    },
    {
        "id": 5,
        "name": "Vogue: продвинутый уровень",
        "type": "Vogue",
        "teacher": {
            "name": "Кузнецов Артём",
            "bio": "Один из ведущих vogue-танцоров России. Регулярный участник ballroom-сцены.",
            "achievements": [
                "Чемпион Vogue Ball Moscow 2023",
                "Основатель House of Phantom",
                "Судья международных баллов",
            ],
            "experience": 9,
            "specializations": ["Vogue", "Waacking", "Ballroom"],
            "images": ["man", "man", "man"],
            "rating": 4.8,
            "reviews": [
                {"author": "Денис", "date": "25.01.2025", "text": "Артём — легенда vogue-сцены. Учиться у него — это отдельный уровень вдохновения.", "rating": 5},
                {"author": "Лера", "date": "14.01.2025", "text": "Сложно, но очень круто. Артём требовательный, но справедливый. Результат того стоит.", "rating": 5},
                {"author": "Игорь", "date": "30.12.2024", "text": "Курс помог подготовиться к первому баллу. Спасибо за веру в учеников!", "rating": 4},
            ],
        },
        "level": "Продвинутые",
        "dateFrom": "15.02",
        "dateTo": "28.02",
        "price": 12000,
        "images": ["vogue", "vogue", "vogue"],
        "studio": "Грация",
        "city": "Москва",
        "description": "Подготовка к баттлам.",
        "location": "м. Новослободская",
        "capacity": 20,
        "spotsLeft": 5,
        "weekdays": ["Ср", "Пт"],
        "timeFrom": "20:00",
        "timeTo": "21:30",
        "music": {"artist": "Kevin Aviance", "track": "Cunty", "url": "https://open.spotify.com/track/2Yk4HhPpG9S2kT2tG9kX7R"},
    },
    {
        "id": 6,
        "name": "Hip-Hop: новая волна",
        "type": "Hip-Hop",
        "teacher": {
            "name": "Павлова Елена",
            "bio": "Хореограф новой школы хип-хопа. Ставит номера для шоу и концертов.",
            "achievements": ["Финалист SDK Europe", "Хореограф шоу «Танцы»"],
            "experience": 7,
            "specializations": ["Hip-Hop", "New Style", "Popping"],
            "images": ["woman", "woman", "woman"],
            "rating": 4.6,
            "reviews": [
                {"author": "Максим", "date": "19.01.2025", "text": "Елена разбирает каждое движение детально. Отличный баланс теории и практики.", "rating": 5},
                {"author": "Аня", "date": "03.01.2025", "text": "Очень крутая атмосфера на занятиях. Чувствуешь себя частью команды.", "rating": 4},
            ],
        },
        "level": "Средний уровень",
        "dateFrom": "16.02",
        "dateTo": "28.02",
        "price": 9000,
        "images": ["hipHop", "hipHop", "hipHop"],
        "studio": "ТанцХаб",
        "city": "Санкт-Петербург",
        "description": "Грув и актуальные стили.",
        "location": "м. Павелецкая",
        "capacity": 40,
        "spotsLeft": 22,
        "weekdays": ["Пн", "Чт"],
        "timeFrom": "18:00",
        "timeTo": "19:30",
        "music": {"artist": "Travis Scott", "track": "FE!N", "url": "https://open.spotify.com/track/42VsgItocQwOQC3XWZ8JNA"},
    },
    {
        "id": 7,
        "name": "Dancehall: первые шаги",
        "type": "Dancehall",
        "teacher": {
            "name": "Мельникова Ольга",
            "bio": "Амбассадор dancehall-культуры в России. Проводит мастер-классы по всей стране.",
            "achievements": ["Победитель Dancehall Queen Contest 2021", "Обучение на Ямайке"],
            "experience": 6,
            "specializations": ["Dancehall", "Afro", "Reggaeton"],
            "images": ["woman", "woman", "woman"],
            "rating": 4.4,
            "reviews": [
                {"author": "Юлия", "date": "16.01.2025", "text": "Ольга передаёт настоящий вайб dancehall. После занятий хочется танцевать везде!", "rating": 5},
                {"author": "Карина", "date": "29.12.2024", "text": "Весёлые и позитивные уроки. Ольга умеет создать расслабленную атмосферу.", "rating": 4},
                {"author": "Светлана", "date": "12.12.2024", "text": "Хотелось бы чуть больше разбора техники отдельных степов.", "rating": 4},
            ],
        },
        "level": "Начинающие",
        "dateFrom": "18.02",
        "dateTo": "28.02",
        "price": 7500,
        "images": ["dancehall", "dancehall", "dancehall"],
        "studio": "DanceLab",
        "city": "Москва",
        "description": "Ямайские ритмы.",
        "location": "м. Курская",
        "capacity": 30,
        "spotsLeft": 15,
        "weekdays": ["Вт", "Сб"],
        "timeFrom": "14:00",
        "timeTo": "15:30",
        "music": {"artist": "Sean Paul", "track": "Temperature", "url": "https://open.spotify.com/track/0k2GOhqsrxDTAbFFSdNJjT"},
    },
    {
        "id": 8,
        "name": "Frame Up: мастерский класс",
        "type": "Frame Up",
        "teacher": {
            "name": "Карпова Ксения",
            "bio": "Хореограф и основатель студии. Более 10 лет в танцевальной индустрии.",
            "achievements": [
                "Финалист Dance Parade 2023",
                "Судья танцевальных баттлов",
                "Обучила более 500 учеников",
            ],
            "experience": 10,
            "specializations": ["High Heels", "Frame Up", "Lady Style"],
            "images": ["woman", "woman", "woman"],
            "rating": 4.9,
            "reviews": [
                {"author": "Алина", "date": "12.01.2025", "text": "Ксения — невероятный педагог! После её интенсива я наконец почувствовала уверенность на каблуках.", "rating": 5},
                {"author": "Виктория", "date": "28.12.2024", "text": "Очень структурированные занятия, всё по делу. Прогресс заметен уже после первой недели.", "rating": 5},
                {"author": "Марина", "date": "15.11.2024", "text": "Энергетика на занятиях потрясающая. Ксения умеет мотивировать и находит подход к каждому.", "rating": 4},
            ],
        },
        "level": "Продвинутые",
        "dateFrom": "20.02",
        "dateTo": "05.03",
        "price": 13000,
        "images": ["frameUp", "frameUp", "frameUp"],
        "studio": "Арт-пространство",
        "city": "Москва",
        "description": "Сценическая подача.",
        "location": "м. Таганская",
        "capacity": 25,
        "spotsLeft": 7,
        "weekdays": ["Пн", "Ср", "Пт"],
        "timeFrom": "20:00",
        "timeTo": "21:30",
        "music": {"artist": "The Weeknd", "track": "The Hills", "url": "https://open.spotify.com/track/7fBv7CLKzipRk6EC6TWHOB"},
    },
    {
        "id": 9,
        "name": "Stretching для начинающих",
        "type": "Stretching",
        "teacher": {
            "name": "Лебедева Ирина",
            "bio": "Мастер спорта по художественной гимнастике. Специалист по растяжке и гибкости.",
            "achievements": ["Мастер спорта по художественной гимнастике", "Сертификат PNF Stretching"],
            "experience": 12,
            "specializations": ["Stretching", "Гибкость", "Художественная гимнастика"],
            "images": ["woman", "woman", "woman"],
            "rating": 5.0,
            "reviews": [
                {"author": "Наталья", "date": "24.01.2025", "text": "Ирина — волшебница! За месяц я села на шпагат, хотя думала, что это невозможно.", "rating": 5},
                {"author": "Оксана", "date": "10.01.2025", "text": "Очень бережный подход к растяжке. Никакой боли, только прогресс.", "rating": 5},
                {"author": "Елена", "date": "22.12.2024", "text": "Лучший преподаватель по стретчингу. Всё объясняет с точки зрения анатомии.", "rating": 5},
            ],
        },
        "level": "Начинающие",
        "dateFrom": "18.02",
        "dateTo": "04.03",
        "price": 6000,
        "images": ["stretching", "stretching", "stretching"],
        "studio": "Студия движения",
        "city": "Санкт-Петербург",
        "description": "Мягкая растяжка.",
        "location": "м. Чистые пруды",
        "capacity": 20,
        "spotsLeft": 10,
        "weekdays": ["Вт", "Чт", "Сб"],
        "timeFrom": "10:00",
        "timeTo": "11:30",
        "music": {"artist": "Enya", "track": "Only Time", "url": "https://open.spotify.com/track/6FLwmdmW77N1Pxb1aWsZmO"},
    },
    {
        "id": 10,
        "name": "Lady Style: грация и пластика",
        "type": "Lady Style",
        "teacher": {
            "name": "Соколова Полина",
            "bio": "Танцовщица и модель. Развивает направление Lady Style в России.",
            "achievements": ["Призёр Lady Dance Cup 2022", "Хореограф модных показов"],
            "experience": 7,
            "specializations": ["Lady Style", "High Heels", "Strip Plastic"],
            "images": ["woman", "woman", "woman"],
            "rating": 4.6,
            "reviews": [
                {"author": "Ирина", "date": "21.01.2025", "text": "Полина учит не просто движениям, а женственности и подаче. Это меняет всё!", "rating": 5},
                {"author": "Мила", "date": "06.01.2025", "text": "Красивые постановки, приятная музыка. Чувствуешь себя звездой на каждом занятии.", "rating": 5},
                {"author": "Александра", "date": "18.12.2024", "text": "Хороший курс, но хотелось бы больше внимания технике рук.", "rating": 4},
            ],
        },
        "level": "Средний уровень",
        "dateFrom": "19.02",
        "dateTo": "06.03",
        "price": 9000,
        "images": ["ladyStyle", "ladyStyle", "ladyStyle"],
        "studio": "Грация",
        "city": "Москва",
        "description": "Плавность и женственность.",
        "location": "м. Новослободская",
        "capacity": 30,
        "spotsLeft": 14,
        "weekdays": ["Пн", "Ср"],
        "timeFrom": "19:00",
        "timeTo": "20:30",
        "music": {"artist": "Lana Del Rey", "track": "West Coast", "url": "https://open.spotify.com/track/2nMeu6UenVvwUktBCpLMK9"},
    },
]


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
            email = f"teacher_{slugify(name)}@dancehub.local"

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
            user.save(update_fields=["first_name", "last_name"])

            profile, _ = TeacherProfile.objects.get_or_create(
                user=user,
                defaults={
                    "bio": t["bio"],
                    "experience_years": t["experience"],
                    "rating_avg": t["rating"],
                    "rating_count": len(t["reviews"]),
                },
            )
            profile.bio = t["bio"]
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
            email = f"reviewer_{slugify(author)}@dancehub.local"
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
