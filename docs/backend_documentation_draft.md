# Документация по backend проекта DanceHub

## 1. Назначение проекта

DanceHub backend — это серверная часть сервиса для:

- регистрации и аутентификации пользователей;
- хранения профилей учеников и преподавателей;
- прохождения пользовательского опроса и хранения предпочтений;
- публикации каталога танцевальных курсов;
- записи на курсы и отмены записи;
- работы с календарём и занятиями;
- отметки посещаемости преподавателем;
- хранения избранного;
- построения персональных рекомендаций;
- уведомлений о важных событиях;
- публикации данных для карты студий.

Проект написан на `Django 5.1` + `Django REST Framework` и работает поверх PostgreSQL.

---

## 2. Технологический стек

- `Python 3.12`
- `Django 5.1.8`
- `Django REST Framework 3.15.2`
- `drf-spectacular 0.28.0` для OpenAPI / Swagger
- `PyJWT` через собственную реализацию JWT-аутентификации
- `PostgreSQL`
- `django-cors-headers`
- `django-storages` + `boto3` для S3/MinIO
- `Pillow` для работы с изображениями
- `Docker` / `Docker Compose`

Файл зависимостей:
- [requirements.txt](/c:/Диплом/dancehub_backend/backend/requirements.txt)

---

## 3. Структура проекта

```text
dancehub_backend/
  backend/
    apps/
      common/
      courses/
      locations/
      recommendations/
      users/
    config/
    manage.py
    requirements.txt
    Dockerfile
  diagrams/
  docs/
    backend_documentation_draft.md
  docker-compose.yml
  README.md
```

Ключевые каталоги:

- `backend/apps/common` — общие enum-ы, утилиты, работа с файлами и медиассылками.
- `backend/apps/users` — пользователи, преподаватели, опрос, навыки, избранные преподаватели, отзывы, уведомления.
- `backend/apps/courses` — стили, студии, курсы, расписание, занятия, записи, посещаемость, статистика.
- `backend/apps/locations` — города.
- `backend/apps/recommendations` — просмотры курсов, профиль предпочтений, сохранённые рекомендации, скоринг.
- `backend/config` — Django settings, URL-маршрутизация, auth, OpenAPI schema.

---

## 4. Архитектурные особенности

### 4.1. Важная особенность схемы данных

Почти все доменные модели объявлены с:

- `managed = False`

Это означает:

- Django не владеет схемой таблиц в обычном режиме;
- модели отражают уже существующую структуру PostgreSQL;
- проект очень завязан на реальную структуру БД;
- изменения в схеме иногда требуют ручных SQL-скриптов, а не только Django migrations.

### 4.2. Отключённые migration-модули

В [settings.py](/c:/Диплом/dancehub_backend/backend/config/settings.py) указано:

```python
MIGRATION_MODULES = {
    "users": None,
    "courses": None,
    "locations": None,
    "recommendations": None,
}
```

Практический смысл:

- `migrate` использует базовую схему/состояние проекта;
- backend опирается на существующую БД;
- для части доработок могут использоваться ручные SQL-изменения;
- это нетипичный для Django проект: тут важно документировать именно БД, а не только Python-код.

### 4.3. Смешанный стиль доступа к данным

В проекте используются:

- обычные Django ORM-модели;
- прямые SQL-вставки/апдейты через `connection.cursor()`;
- сериализаторы DRF;
- domain-service функции;
- вычисляемые lifecycle-статусы на уровне Python.

Это значит, что документация должна описывать не только API, но и скрытые бизнес-правила.

---

## 5. Конфигурация и окружение

Основной конфиг:
- [settings.py](/c:/Диплом/dancehub_backend/backend/config/settings.py)

Ключевые настройки:

- `LANGUAGE_CODE = "ru-ru"`
- `TIME_ZONE = "Europe/Moscow"`
- `USE_TZ = True`
- backend работает в московской таймзоне

### 5.1. Подключение к БД

Используется PostgreSQL:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`

### 5.2. CORS / CSRF

По умолчанию разрешены:

- `http://localhost:8080`
- `http://127.0.0.1:8080`
- `https://localhost:8080`
- `https://127.0.0.1:8080`

### 5.3. Медиа

Поддерживаются 2 режима:

1. локальные файлы через `MEDIA_ROOT`
2. S3-совместимое хранилище через `MinIO`

Если `USE_S3=True`, подключается `django-storages`.

### 5.4. JWT

Токены реализованы вручную в:
- [authentication.py](/c:/Диплом/dancehub_backend/backend/config/authentication.py)

Параметры:

- access token lifetime: `30 минут`
- refresh token lifetime: `7 дней`
- заголовок: `Authorization: Bearer <token>`

---

## 6. Запуск проекта

### 6.1. Docker Compose

Файл:
- [docker-compose.yml](/c:/Диплом/dancehub_backend/docker-compose.yml)

Сервисы:

- `db` — PostgreSQL
- `web` — Django backend
- `scheduler` — периодическая отправка reminder-уведомлений
- `minio` — S3-совместимое хранилище
- `minio-init` — инициализация bucket-а

Порты:

- backend API: `8000`
- PostgreSQL: `15432`
- MinIO API: `9000`
- MinIO Console: `9001`

### 6.2. Dockerfile

Файл:
- [Dockerfile](/c:/Диплом/dancehub_backend/backend/Dockerfile)

При старте контейнера выполняется:

- `python manage.py migrate`
- `python manage.py runserver 0.0.0.0:8000`

В `docker-compose` для `web` дополнительно запускается:

- `python manage.py ensure_admin_views`

---

## 7. Аутентификация

Реализация:
- [authentication.py](/c:/Диплом/dancehub_backend/backend/config/authentication.py)

### 7.1. Как работает

- backend принимает JWT в Bearer-заголовке;
- если заголовка нет, пользователь считается анонимным;
- если токен невалиден, поднимается `AuthenticationFailed`;
- `request.user` получает объект модели `User`.

Используется собственный класс:

- `OptionalJWTAuthentication`

Это важно:

- многие публичные endpoint-ы работают и для анонима, и для авторизованного пользователя;
- при наличии токена поведение некоторых endpoint-ов меняется: например, каталог курсов скрывает собственные курсы и курсы, на которые пользователь уже записан.

---

## 8. Общие enum-ы и статусы

Файл:
- [choices.py](/c:/Диплом/dancehub_backend/backend/apps/common/choices.py)

### 8.1. Роли пользователя

- `student`
- `teacher`

### 8.2. Уровни танцев

- `beginner`
- `intermediate`
- `advanced`

Отдельно в курсах разрешено ещё значение:

- `any`

Оно добавлено в `COURSE_LEVEL_CHOICES` в [models.py](/c:/Диплом/dancehub_backend/backend/apps/courses/models.py).

### 8.3. Дни недели

- `mon`
- `tue`
- `wed`
- `thu`
- `fri`
- `sat`
- `sun`

### 8.4. Статусы курса

- `published`
- `active`
- `completed`
- `cancelled`

### 8.5. Статусы занятия

- `scheduled`
- `cancelled`

При этом для API есть ещё вычисляемое значение:

- `completed`

Оно вычисляется функцией, а не хранится напрямую в enum `LessonStatus`.

### 8.6. Статусы записи

- `active`
- `completed`
- `cancelled`
- `pending`

### 8.7. Статусы посещаемости

- `present`
- `absent`

---

## 9. Общие утилиты

Файл:
- [utils.py](/c:/Диплом/dancehub_backend/backend/apps/common/utils.py)

Ключевые функции:

- `normalize_media_reference` — нормализует путь/URL до медиафайла;
- `build_full_name` — собирает ФИО;
- `course_lifecycle_status` — вычисляет жизненный статус курса по датам и базовому статусу;
- `lesson_lifecycle_status` — вычисляет статус занятия, включая `completed`;
- `lesson_start_at` — собирает timezone-aware datetime начала занятия;
- `first_lesson_start_at` — ищет первое неотменённое занятие;
- `has_hours_before` — проверяет дедлайн относительно текущего времени;
- `absolutize_media_url` — делает абсолютный URL для клиента.

### 9.1. Важное поведение lifecycle-логики

#### course_lifecycle_status

Курс считается:

- `cancelled`, если сохранённый статус `cancelled`
- `completed`, если статус `completed` или `date_to < today`
- `published`, если `date_from > today`
- `active` во всех остальных случаях

#### lesson_lifecycle_status

Занятие считается:

- `cancelled`, если оно отменено
- `completed`, если уже прошло время окончания
- `scheduled`, если ещё не закончилось

---

## 10. Доменные приложения

### 10.1. `apps.locations`

Назначение:

- справочник городов.

Модель:

- `City`

Поля:

- `id`
- `name`

Endpoint:

- `GET /api/cities/`

Файлы:
- [models.py](/c:/Диплом/dancehub_backend/backend/apps/locations/models.py)
- [views.py](/c:/Диплом/dancehub_backend/backend/apps/locations/views.py)
- [urls.py](/c:/Диплом/dancehub_backend/backend/apps/locations/urls.py)

### 10.2. `apps.users`

Назначение:

- аккаунты;
- преподавательские профили;
- опрос и предпочтения;
- навыки;
- избранные преподаватели;
- отзывы преподавателям;
- уведомления.

### 10.3. `apps.courses`

Назначение:

- стили;
- студии;
- курсы;
- расписание;
- занятия;
- записи на курс;
- отметки посещаемости;
- статистика по посещаемости;
- карта и календарь;
- отзывы по завершённому курсу.

### 10.4. `apps.recommendations`

Назначение:

- хранение событий просмотра курсов;
- агрегация поведенческого профиля пользователя;
- вычисление скора рекомендаций;
- кеширование результата рекомендаций.

---

## 11. Модель данных

## 11.1. Пользователи и преподаватели

Файл:
- [users/models.py](/c:/Диплом/dancehub_backend/backend/apps/users/models.py)

### `User`

Главная таблица пользователей.

Ключевые поля:

- `email`
- `username`
- `first_name`
- `middle_name`
- `last_name`
- `password_hash`
- `avatar`
- `city_id`
- `dance_level`
- `role`
- `survey_completed`
- `preferred_time_from`
- `preferred_time_to`
- `preferred_weekdays`
- `preferred_dance_styles`
- `price_from`
- `price_to`

Это одновременно:

- аккаунт;
- профиль ученика;
- источник предпочтений для рекомендаций;
- связь с преподавательским профилем.

### `TeacherProfile`

One-to-one над `User`.

Поля:

- `user_id`
- `bio`
- `experience_years`
- `images`
- `achievements`
- `specializations`

### `UserSkill`

Навык пользователя по конкретному стилю:

- `user_id`
- `dance_style_id`
- `level`

### `UserFlag`

Произвольные boolean-флаги:

- `user_id`
- `name`
- `value`

### `FavoriteTeacher`

Избранные преподаватели:

- `user_id`
- `teacher_id`

### `TeacherReview`

Отзыв преподавателю на уровне курса.

Поля:

- `user_id` — кто оставил отзыв
- `teacher_id`
- `course_id`
- `lesson_id` — nullable, опциональная привязка к занятию
- `rating`
- `text`
- `created_at`

Уникальность:

- один пользователь может оставить только один отзыв по одному курсу

### `Notification`

Уведомление пользователя.

Поля:

- `user_id`
- `kind`
- `title`
- `body`
- `course_id`
- `lesson_id`
- `read_at`
- `created_at`

---

## 11.2. Курсы и занятия

Файл:
- [courses/models.py](/c:/Диплом/dancehub_backend/backend/apps/courses/models.py)

### `DanceStyle`

Поля:

- `id`
- `name`
- `slug`

### `Studio`

Поля:

- `id`
- `name`
- `city_id`
- `address`
- `metro`
- `lat`
- `lng`
- `image`
- `halls_count`

### `Course`

Поля:

- `teacher_id`
- `dance_style_id`
- `studio_id`
- `name`
- `description`
- `music_artist`
- `music_track`
- `music_url`
- `level`
- `price`
- `capacity`
- `date_from`
- `date_to`
- `status`
- `images`
- `image_cover`

Важно:

- у курса есть базовая студия `studio_id`;
- но строки расписания и занятия тоже могут иметь собственную `studio_id`;
- это позволяет поддерживать разные студии внутри одного курса.

### `CourseSchedule`

Правило расписания курса.

Поля:

- `course_id`
- `studio_id`
- `weekday`
- `time_from`
- `time_to`
- `location_text`

Это шаблон, из которого разворачиваются реальные занятия.

### `Lesson`

Конкретное занятие курса.

Поля:

- `course_id`
- `studio_id`
- `schedule_id`
- `lesson_date`
- `time_from`
- `time_to`
- `location_text`
- `status`
- `hall`

### `Enrollment`

Запись пользователя на курс.

Поля:

- `user_id`
- `course_id`
- `status`
- `enrolled_at`

Ограничение:

- один пользователь — одна запись на курс

### `AttendanceMark`

Отметка посещаемости.

Поля:

- `lesson_id`
- `student_id`
- `status`
- `marked_at`

Ограничение:

- одна отметка на пользователя в рамках одного занятия

### `FavoriteCourse`

Избранные курсы:

- `user_id`
- `course_id`

---

## 11.3. Рекомендательная подсистема

Файл:
- [recommendations/models.py](/c:/Диплом/dancehub_backend/backend/apps/recommendations/models.py)

### `CourseView`

Событие просмотра курса:

- `user_id`
- `course_id`
- `viewed_at`
- `source`

### `UserRecommendationProfile`

Агрегированный профиль предпочтений и поведения пользователя.

Содержит:

- город;
- уровень;
- предпочитаемые стили;
- предпочитаемые дни;
- предпочитаемое время;
- бюджет;
- поведенческие веса по стилям;
- поведенческие веса по преподавателям;
- поведенческие веса по студиям;
- поведенческие веса по городам;
- итоговый `behavior_weight`;
- дату последнего релевантного события.

### `UserCourseRecommendation`

Сохранённая рекомендация:

- `user_id`
- `course_id`
- `score`
- `reasons_json`
- `factors_json`
- `computed_at`

---

## 12. API: общий обзор

Корневой роутинг:
- [config/urls.py](/c:/Диплом/dancehub_backend/backend/config/urls.py)

Основные группы endpoint-ов:

- `/api/auth/*`
- `/api/user/*`
- `/api/teachers/*`
- `/api/cities/`
- `/api/dance-styles/`
- `/api/studios/*`
- `/api/map/points/`
- `/api/calendar/`
- `/api/courses/*`
- `/api/lessons/*`
- `/api/enrollments/`
- `/api/recommendations/*`
- `/api/course-views/*`
- `/api/notifications/*`

Дополнительно:

- `/api/health/`
- `/api/schema/`
- `/api/docs/`

---

## 13. API: users / auth

Файл:
- [users/urls.py](/c:/Диплом/dancehub_backend/backend/apps/users/urls.py)

## 13.1. `POST /api/auth/register/`

Регистрация пользователя.

Тело:

```json
{
  "email": "user@example.com",
  "username": "user123",
  "first_name": "Иван",
  "middle_name": "Иванович",
  "last_name": "Петров",
  "password": "password123",
  "password_confirm": "password123"
}
```

Валидации:

- пароль и подтверждение должны совпадать;
- email должен быть уникален;
- username должен быть уникален.

Ответ:

- объект `user`
- `access`
- `refresh`

## 13.2. `POST /api/auth/login/`

Вход по email и паролю.

Тело:

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

Ответ:

- объект `user`
- `access`
- `refresh`

Примечание:

- логин идёт именно по `email`, не по `username`.

## 13.3. `POST /api/auth/refresh/`

Обновление access-токена по refresh-токену.

Тело:

```json
{
  "refresh": "<jwt>"
}
```

## 13.4. `POST /api/auth/logout/`

Фактически stateless logout.

Тело:

```json
{
  "refresh": "<jwt>"
}
```

Ответ:

```json
{
  "detail": "ok"
}
```

Важно:

- refresh-токены не хранятся и не blacklist-ятся;
- logout здесь нужен скорее фронту как semantic endpoint.

---

## 14. API: профиль пользователя

## 14.1. `GET /api/user/`

Возвращает текущего пользователя.

В ответе есть:

- базовые поля профиля;
- город;
- роль;
- данные опроса;
- teacher summary, если у пользователя есть профиль преподавателя;
- `favorite_course_ids`
- `favorite_teacher_ids`
- `favorite_teacher_names`
- `favorite_teacher_avatars`

## 14.2. `PATCH /api/user/`

Частичное обновление профиля.

Поддерживаемые поля:

- `username`
- `first_name`
- `middle_name`
- `last_name`
- `survey_completed`
- `avatar_file`
- `city`
- `dance_level`
- `role`

Особенности:

- `city` приходит строкой по имени города, а не `city_id`;
- `avatar_file` сохраняется через `save_uploaded_file(..., "avatars")`;
- username проверяется на уникальность.

---

## 15. API: опрос, предпочтения, навыки, флаги

## 15.1. `PATCH /api/user/survey/`

Обновляет ответы опроса и ставит:

- `survey_completed = true`

Поддерживаемые поля:

- `city`
- `level`
- `preferred_weekdays`
- `preferred_time_from`
- `preferred_time_to`
- `price_from`
- `price_to`
- `preferred_dance_styles`
- `role`

После обновления:

- пересчитываются рекомендации через `refresh_recommendations_for_user(user)`

## 15.2. `PATCH /api/user/preferences/`

То же самое, но без принудительной установки `survey_completed = true`.

## 15.3. `PUT /api/user/skills/`

Полная замена списка навыков пользователя.

Тело — массив:

```json
[
  {
    "dance_style_id": 1,
    "level": "beginner"
  }
]
```

Особенность:

- перед вставкой backend удаляет все старые `user_skills`;
- значение `level = "any"` насильно преобразуется в `beginner`.

## 15.4. `POST /api/user/flag/`

Устанавливает или обновляет произвольный boolean-флаг.

Тело:

```json
{
  "name": "survey_shown",
  "value": true
}
```

---

## 16. API: преподаватели

## 16.1. `GET /api/teachers/`

Фильтры:

- `city`
- `search`
- `style`

Возвращает краткий список преподавателей:

- `id`
- `full_name`
- `bio`
- `experience_years`
- `rating_avg`
- `rating_count`
- `city`

## 16.2. `POST /api/teachers/`

Создаёт teacher profile для текущего пользователя, если его ещё нет.

Дополнительно:

- если роль пользователя ещё не `teacher`, backend переключает её в `teacher`.

## 16.3. `GET /api/teachers/<id>/`

Подробная карточка преподавателя.

Возвращает:

- profile-данные;
- аватар;
- рейтинг;
- специализации;
- достижения;
- отзывы;
- список курсов преподавателя.

В отзывах уже есть:

- `course_name`

## 16.4. `PUT /api/teachers/<id>/`

Обновляет собственный профиль преподавателя.

Поддерживаемые поля:

- `bio`
- `images`
- `achievements`
- `experience`
- `specializations`

Особенности:

- редактировать можно только свой teacher profile;
- `images` проходят через `persist_image_reference`.

## 16.5. `GET /api/teachers/<id>/courses/`

Возвращает курсы преподавателя.

Опциональный фильтр:

- `status`

Статус фильтруется уже по вычисленному lifecycle-статусу.

---

## 17. API: мои курсы, мои записи, избранное, уведомления

## 17.1. `GET /api/my-teaching-courses/`

Возвращает курсы текущего преподавателя в расширенном формате `serialize_course_detail(...)`.

## 17.2. `GET /api/enrollments/`

Возвращает курсы, на которые записан текущий пользователь.

Важная деталь:

- используются только `Enrollment(status=active)`;
- в `viewer_context` дополнительно подмешиваются:
  - `viewer_enrollment_status`
  - `can_leave_review`

## 17.3. `GET /api/my-courses/`

Алиас к `EnrollmentListAPIView`.

## 17.4. `POST /api/favorite-courses/<course_id>/`

Добавляет курс в избранное.

## 17.5. `DELETE /api/favorite-courses/<course_id>/`

Удаляет курс из избранного.

## 17.6. `POST /api/favorite-teachers/<teacher_id>/`

Добавляет преподавателя в избранное.

## 17.7. `DELETE /api/favorite-teachers/<teacher_id>/`

Удаляет преподавателя из избранного.

Важно:

- после изменения избранного backend пересчитывает рекомендации.

## 17.8. `GET /api/notifications/`

Список уведомлений текущего пользователя.

## 17.9. `POST /api/notifications/read-all/`

Помечает все непрочитанные как прочитанные.

## 17.10. `PATCH /api/notifications/<id>/`

Тело:

```json
{
  "read": true
}
```

## 17.11. `DELETE /api/notifications/<id>/`

Удаляет конкретное уведомление.

---

## 18. API: города, стили, студии, карта

## 18.1. `GET /api/cities/`

Список городов.

## 18.2. `GET /api/dance-styles/`

Список танцевальных стилей:

- `id`
- `name`
- `slug`

## 18.3. `GET /api/studios/`

Фильтр:

- `city`

Ответ:

- `id`
- `name`
- `city`
- `address`
- `metro`

## 18.4. `GET /api/studios/<id>/`

Карточка студии.

## 18.5. `GET /api/map/points/`

Фильтры:

- `city`
- `metro`
- `studio`
- `style`

Ответ по студии:

- координаты;
- изображение;
- количество активных курсов;
- стили танцев, доступные в активных курсах.

Важно:

- image на карте нормализуется в абсолютный или корректный медиа URL;
- подсчёт активных курсов делается через annotation.

---

## 19. API: календарь

## 19.1. `GET /api/calendar/`

Требует авторизацию.

Параметры:

- `mode=all|teaching|enrolled`
- `course_id`
- `date_from`
- `date_to`

Возвращает занятия, релевантные пользователю.

Каждый элемент содержит:

- курс;
- преподавателя;
- стиль;
- уровень;
- дату;
- время;
- start/end;
- студию;
- город;
- location_text;
- вычисленный статус занятия.

---

## 20. API: каталог курсов

## 20.1. `GET /api/courses/`

Основной каталог.

Поддерживает фильтры:

- `city`
- `level`
- `status`
- `studio`
- `style`
- `teacher`

### 20.1.1. Как работает видимость курса в каталоге

Если `status` явно не передан, backend показывает только курсы, которые:

- не `completed`
- не `cancelled`
- имеют минимум 24 часа до первого занятия
- имеют свободные места
- не являются собственным курсом пользователя
- не являются курсом, на который пользователь уже записан

Эта логика живёт в:
- `is_course_visible_in_catalog(...)`

### 20.1.2. Сортировка каталога

- для анонима — обычный список по `-id` после фильтрации;
- для авторизованного пользователя — после фильтрации курсы дополнительно сортируются через `sort_courses_for_user(...)`.

### 20.1.3. Формат элемента каталога

`serialize_course_list_item(...)` возвращает:

- базовые поля курса;
- преподавателя;
- стиль;
- город;
- студию;
- массив `schedule`;
- `spots_left`
- `can_enroll`
- `can_cancel_enrollment`
- `can_edit`
- `first_lesson_at`
- `can_leave_review` (по умолчанию `false`, может быть переопределён контекстом)

## 20.2. `POST /api/courses/`

Создание курса преподавателем.

Тело включает:

- `dance_style_id`
- `studio_id` или `studio_id` в строках расписания
- `name`
- `description`
- `music_artist`
- `music_track`
- `music_url`
- `level`
- `price`
- `capacity`
- `date_from`
- `date_to`
- `status`
- `schedule`
- `ordered_image_urls`
- `image_cover`
- `image_files`

### 20.2.1. Важные правила создания курса

- создать курс может только пользователь с teacher profile;
- `studio_id` можно указать либо у курса, либо хотя бы в одной строке расписания;
- расписание валидируется и дедуплицируется по `weekday + time_from + time_to`;
- из расписания разворачиваются реальные занятия через `expand_lessons_for_schedule(...)`;
- после создания курса автоматически вызывается:
  - `auto_enroll_minimum_course_students(course, exclude_user_ids={teacher.user_id})`

### 20.2.2. Автозапись демо-учеников

После создания курса backend автоматически добирает минимум `50%` заполненности курса.

Назначение:

- создание заглушки для статистики и attendance-сценариев.

Файл:
- [seed_course_students.py](/c:/Диплом/dancehub_backend/backend/apps/courses/seed_course_students.py)

---

## 21. API: курс по id

## 21.1. `GET /api/courses/<id>/`

Возвращает детальную карточку курса.

Если пользователь авторизован:

- трекается просмотр курса через `track_course_view(...)`;
- затем могут обновляться рекомендации.

В `viewer_context` подмешиваются:

- `viewer_enrollment_status`
- `is_own_course`
- `can_leave_review`

## 21.2. `PATCH /api/courses/<id>/`

Редактирование курса преподавателем.

Ограничение:

- редактирование закрывается за `48 часов` до первого занятия.

Если меняются критичные поля или расписание:

- могут быть пересозданы строки расписания;
- старые `CourseSchedule` и `Lesson` удаляются;
- новые `Lesson` создаются заново;
- активным ученикам отправляются уведомления об обновлении курса.

## 21.3. `DELETE /api/courses/<id>/`

Удаляет курс целиком.

---

## 22. API: отзывы по курсу / преподавателю

## 22.1. `POST /api/courses/<id>/review/`

Оставление отзыва после завершения курса.

Тело:

```json
{
  "rating": 5,
  "text": "Очень понравилось"
}
```

### 22.1.1. Условия, когда отзыв разрешён

Логика в `build_review_context(...)`:

- пользователь должен быть авторизован;
- пользователь не должен быть автором курса;
- курс должен быть `completed`;
- у пользователя должна быть хотя бы одна отметка `AttendanceMark(status='present')` по этому курсу;
- пользователь ещё не оставлял отзыв по этому курсу.

### 22.1.2. Как хранится отзыв

Сейчас отзыв хранится как `TeacherReview`, то есть:

- отзыв формально относится к преподавателю;
- но право на отзыв определяется через посещение курса;
- уникальность тоже считается по `user + course`.

То есть рейтинг преподавателя — это среднее по отзывам, оставленным после курсов.

---

## 23. API: ученики, занятия, посещаемость

## 23.1. `GET /api/courses/<id>/students/`

Доступен преподавателю-владельцу курса.

Возвращает enrollments со статусами:

- `active`
- `completed`

Это важно для завершённых курсов: преподаватель всё ещё может видеть учеников.

## 23.2. `GET /api/courses/<id>/lessons/`

Список занятий курса.

Каждое занятие содержит:

- `status`
- `start_at`
- `can_mark_attendance`

`can_mark_attendance = timezone.now() >= starts_at`

## 23.3. `GET /api/courses/<id>/attendance/`

Список всех attendance marks курса.

## 23.4. `GET /api/courses/<id>/attendance-stats/`

Агрегированная статистика посещаемости курса.

Опциональные фильтры:

- `date_from`
- `date_to`

Возвращает:

- `total_lessons`
- `conducted_lessons`
- `cancelled_lessons`
- `avg_attendance_percent`
- `total_students`
- `per_lesson`
- `per_student`

Логика реализована в:
- [stats_service.py](/c:/Диплом/dancehub_backend/backend/apps/courses/stats_service.py)

## 23.5. `POST /api/lessons/<lesson_id>/cancel/`

Отмена занятия преподавателем.

Побочный эффект:

- рассылаются уведомления ученикам.

## 23.6. `PATCH /api/lessons/<lesson_id>/`

Редактирование конкретного занятия.

Поддерживаемые поля:

- `lesson_date`
- `time_from`
- `time_to`
- `location_text`
- `hall`
- `status`

При изменении отправляются уведомления ученикам.

## 23.7. `GET /api/lessons/<lesson_id>/attendance/`

Список attendance marks по конкретному занятию.

## 23.8. `POST /api/lessons/<lesson_id>/attendance/mark/`

Отметка посещаемости.

Тело:

```json
{
  "student_id": 42,
  "status": "present"
}
```

### 23.8.1. Ограничение по времени

Attendance можно отмечать только после начала занятия:

```python
if timezone.now() < lesson_start_at(...):
    raise ValidationError({"detail": "Attendance can be marked only after the lesson starts."})
```

Это важное фронтовое правило: UI должен либо скрывать действие, либо показывать предупреждение.

---

## 24. API: запись на курс

## 24.1. `POST /api/courses/<course_id>/enroll/`

Записывает текущего пользователя на курс.

Условия:

- курс существует;
- lifecycle курса должен быть `published`;
- до первого занятия должно оставаться минимум `24 часа`;
- преподаватель не может записаться на свой курс;
- пользователь не должен быть уже активно записан;
- должны быть свободные места.

Если у пользователя уже была запись, но она `cancelled`:

- запись реактивируется;
- `enrolled_at` обновляется.

Побочные эффекты:

- уведомление преподавателю;
- уведомление ученику.

## 24.2. `DELETE /api/courses/<course_id>/enroll/`

Отмена записи.

Ограничение:

- отмена тоже закрывается за `24 часа` до первого занятия.

Если запись была активной:

- меняется статус на `cancelled`;
- отправляются уведомления обеим сторонам.

---

## 25. Рекомендательная система

Файлы:

- [views.py](/c:/Диплом/dancehub_backend/backend/apps/recommendations/views.py)
- [services.py](/c:/Диплом/dancehub_backend/backend/apps/recommendations/services.py)

## 25.1. Endpoint-ы

### `GET /api/recommendations/?limit=12`

Возвращает список рекомендованных курсов.

Каждый элемент:

- `score`
- `reasons`
- `factors`
- `course`

### `POST /api/recommendations/rebuild/`

Принудительная пересборка recommendation profile.

### `POST /api/course-views/<course_id>/`

Трекинг просмотра курса.

Просмотры дедуплицируются окном:

- `30 минут`

---

## 25.2. Из чего строятся рекомендации

Рекомендации используют 2 источника:

1. контентные предпочтения из анкеты
2. поведенческие сигналы из действий пользователя

### Контентные данные

Из `User` берутся:

- выбранный город
- уровень
- любимые стили
- предпочитаемые дни недели
- предпочитаемое время
- бюджет

### Поведенческие данные

Из активности пользователя берутся:

- активные записи на курсы
- посещённые занятия
- оставленные отзывы
- избранные преподаватели
- просмотры курсов

На основе этого строится `UserRecommendationProfile`.

---

## 25.3. Весовая модель рекомендаций

Текущая логика на момент написания документа:

### Анкета / explicit preferences

- любимый стиль: `35 * content_weight`
- уровень: `15 * content_weight`
- город совпал: `24 * content_weight`
- город не совпал: `-18 * content_weight`
- цена в полном диапазоне: `10 * content_weight`
- цена только по одной границе: `8 * content_weight`
- день недели: `5 * content_weight`
- время: `5 * content_weight`

### Поведение / implicit signals

- похожий стиль по истории: `min(style_weight, 20) * behavior_multiplier`
- интерес к преподавателю: `min(teacher_weight, 14) * behavior_multiplier`
- интерес к студии: `min(studio_weight, 8) * behavior_multiplier`
- интерес к городу по истории:
  - только если в анкете не указан город
  - `min(city_weight, 8) * behavior_multiplier`

### Популярность

- `min(active_enrollments, 10) * 0.35`

### Поведенческий вклад по событиям

- активная запись: стиль `+5`, преподаватель `+5`, студия `+4`, город `+3`
- посещение: стиль `+3`, преподаватель `+3`, студия `+2`, город `+2`
- отзыв: преподаватель `+4`
- избранный преподаватель: преподаватель `+6`
- просмотр курса: всё по `+1`

### Адаптивные коэффициенты

- `behavior_weight` растёт до `0.65`
- `content_weight` уменьшается, если у пользователя накопилось много поведенческих данных

Идея алгоритма:

- в начале сильнее влияют ответы анкеты;
- по мере накопления действий сильнее начинает влиять поведение;
- город из опроса сейчас учитывается явно и существенно.

---

## 26. Уведомления

Файл:
- [notifications.py](/c:/Диплом/dancehub_backend/backend/apps/users/notifications.py)

Типовые сценарии:

- новая запись ученика на курс;
- отмена записи;
- курс изменён;
- занятие изменено;
- у избранного преподавателя появился новый курс;
- reminder за 24 часа до занятия;
- промокод.

### Важная особенность

Есть `create_notification_once(...)`, который не создаёт дубликаты с тем же набором:

- `user`
- `kind`
- `title`
- `body`
- `course`
- `lesson`

Это помогает не заспамить reminder-ами и промокодами.

---

## 27. Команды management

### `ensure_admin_views`

Создаёт/обновляет вспомогательные admin views.

### `send_lesson_reminders`

Используется scheduler-сервисом для отправки напоминаний о занятиях.

### `send_promo_notifications`

Массовая рассылка промокодов.

### `populate_cards`

Сидирование/заполнение карточек курсов.

### `populate_course_lessons`

Заполнение уроков по расписанию.

### `populate_course_students`

Заполнение учеников курса.

---

## 28. Работа с медиа

Файл:
- [files.py](/c:/Диплом/dancehub_backend/backend/apps/common/files.py)

Backend поддерживает:

- прямую загрузку файла (`ImageField`, multipart);
- сохранение ссылки;
- сохранение `data:` URL как файла.

Ключевые функции:

- `save_uploaded_file(...)`
- `save_data_url(...)`
- `persist_image_reference(...)`

Это используется для:

- аватаров;
- изображений преподавателя;
- изображений курсов.

---

## 29. Что важно учитывать при документировании и развитии проекта

### 29.1. Проект сильно опирается на БД

Это не “чистый Django CRUD”. Здесь:

- много `managed=False`;
- есть raw SQL;
- часть бизнес-ограничений живёт в самой БД;
- изменения схемы нужно проверять особенно внимательно.

### 29.2. Есть вычисляемые статусы

Нельзя слепо смотреть только на поле `status`:

- у курса есть lifecycle по датам;
- у занятия есть lifecycle по времени окончания.

### 29.3. Каталог — не просто список всех курсов

Для каталога действуют скрытые фильтры:

- нет завершённых;
- нет отменённых;
- нет уже начавшихся “впритык” курсов;
- нет заполненных курсов;
- нет собственных курсов преподавателя;
- нет уже записанных курсов.

### 29.4. Рекомендации не только читаются, но и влияют на выдачу каталога

`sort_courses_for_user(...)` переупорядочивает каталог даже вне `/api/recommendations/`.

Это важно для продуктовой логики:

- “каталог” и “рекомендации” частично используют одну и ту же модель ранжирования.

### 29.5. Отзыв — это гибридная сущность

На уровне интерфейса:

- отзыв оставляется о курсе

На уровне бизнес-результата:

- отзыв влияет на рейтинг преподавателя

На уровне модели:

- хранится как `TeacherReview`, привязанный к `teacher` и `course`

---

## 30. Риски и технический долг

По коду видно несколько зон, которые стоит отдельно описать в будущей полноценной документации:

### 30.1. Кодировка строк

В нескольких файлах видны следы битой кириллицы в `verbose_name` и части текстов.

Это не всегда ломает runtime, но:

- портит кодовую базу;
- усложняет поддержку;
- мешает автогенерации читаемой документации.

### 30.2. Legacy-файлы

В проекте есть файлы, которые выглядят как старые/неиспользуемые слои, например:

- [apps/courses/services.py](/c:/Диплом/dancehub_backend/backend/apps/courses/services.py)

По содержимому он похож на старую логику генерации занятий и, вероятно, не является текущим основным источником правды.

Перед дальнейшей документацией стоит отметить:

- что реально используется в runtime;
- а что осталось как legacy.

### 30.3. Отключённые migrations

Если проект продолжит активно развиваться, будет полезно решить:

- оставить ли ручное управление схемой;
- или постепенно вернуть управляемые миграции на часть таблиц.

---

## 31. Рекомендованный план для финальной официальной документации

Если из этого черновика делать уже “чистовую” документацию, я бы разбил её на 5 документов:

1. `architecture.md`
   Описание модулей, слоёв, зависимостей и жизненных циклов сущностей.

2. `database.md`
   Полная схема БД: таблицы, связи, ограничения, enum-ы, триггеры, ручные SQL-миграции.

3. `api.md`
   Endpoint-ы, методы, права доступа, request/response examples.

4. `recommendations.md`
   Отдельный документ по рекомендательной системе: признаки, веса, пересборка, сценарии.

5. `operations.md`
   Docker, env, запуск, backup/dump БД, MinIO, scheduler, сидирование, reminder-команды.

---

## 32. Быстрые ссылки на код

### Конфиг

- [settings.py](/c:/Диплом/dancehub_backend/backend/config/settings.py)
- [urls.py](/c:/Диплом/dancehub_backend/backend/config/urls.py)
- [authentication.py](/c:/Диплом/dancehub_backend/backend/config/authentication.py)
- [schema.py](/c:/Диплом/dancehub_backend/backend/config/schema.py)

### Общие вещи

- [choices.py](/c:/Диплом/dancehub_backend/backend/apps/common/choices.py)
- [utils.py](/c:/Диплом/dancehub_backend/backend/apps/common/utils.py)
- [files.py](/c:/Диплом/dancehub_backend/backend/apps/common/files.py)

### Users

- [models.py](/c:/Диплом/dancehub_backend/backend/apps/users/models.py)
- [serializers.py](/c:/Диплом/dancehub_backend/backend/apps/users/serializers.py)
- [views.py](/c:/Диплом/dancehub_backend/backend/apps/users/views.py)
- [notifications.py](/c:/Диплом/dancehub_backend/backend/apps/users/notifications.py)
- [urls.py](/c:/Диплом/dancehub_backend/backend/apps/users/urls.py)

### Courses

- [models.py](/c:/Диплом/dancehub_backend/backend/apps/courses/models.py)
- [serializers.py](/c:/Диплом/dancehub_backend/backend/apps/courses/serializers.py)
- [views.py](/c:/Диплом/dancehub_backend/backend/apps/courses/views.py)
- [stats_service.py](/c:/Диплом/dancehub_backend/backend/apps/courses/stats_service.py)
- [seed_course_students.py](/c:/Диплом/dancehub_backend/backend/apps/courses/seed_course_students.py)
- [urls.py](/c:/Диплом/dancehub_backend/backend/apps/courses/urls.py)

### Locations

- [models.py](/c:/Диплом/dancehub_backend/backend/apps/locations/models.py)
- [views.py](/c:/Диплом/dancehub_backend/backend/apps/locations/views.py)
- [urls.py](/c:/Диплом/dancehub_backend/backend/apps/locations/urls.py)

### Recommendations

- [models.py](/c:/Диплом/dancehub_backend/backend/apps/recommendations/models.py)
- [views.py](/c:/Диплом/dancehub_backend/backend/apps/recommendations/views.py)
- [services.py](/c:/Диплом/dancehub_backend/backend/apps/recommendations/services.py)
- [urls.py](/c:/Диплом/dancehub_backend/backend/apps/recommendations/urls.py)

---

## 33. Итог

Этот файл — подробный технический черновик по текущему состоянию backend-а DanceHub.

Его можно использовать как основу для:

- дипломной документации;
- внутренней документации проекта;
- описания API для фронтенда;
- подготовки финального README;
- подготовки раздела “архитектура backend” в отчёте.
