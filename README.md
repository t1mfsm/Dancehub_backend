# DanceHub Backend

Базовый backend-проект на Django + PostgreSQL в Docker.

## Быстрый старт

1. Проверь файл `.env`
2. Запусти:

```bash
docker compose up --build
```

3. Проверка:

- API health: `http://localhost:8000/api/health/`
- Django admin: `http://localhost:8000/admin/`
- PostgreSQL: `localhost:5432`

## pgAdmin

Подключение:

- Host: `localhost`
- Port: `5432`
- Database: значение `POSTGRES_DB`
- Username: значение `POSTGRES_USER`
- Password: значение `POSTGRES_PASSWORD`

## Локальный запуск без Docker

Если запускаешь проект через Docker, `venv` не нужен.

Если хочешь запускать Django локально, тогда:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
cd backend
python manage.py runserver
```

PostgreSQL при этом можно оставить в Docker.

## Домены

- `apps.users` - пользователи, преподаватели, предпочтения
- `apps.locations` - города
- `apps.courses` - стили, студии, курсы, занятия, записи, посещаемость
