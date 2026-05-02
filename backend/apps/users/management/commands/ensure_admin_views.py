from django.core.management.base import BaseCommand
from django.db import connection


SQL_STATEMENTS = [
    """
    CREATE OR REPLACE VIEW admin_user_flags_view AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY uf.user_id, uf.name) AS id,
        uf.user_id,
        uf.name,
        uf.value
    FROM user_flags uf
    """,
    """
    CREATE OR REPLACE VIEW admin_user_skills_view AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY us.user_id, us.dance_style_id) AS id,
        us.user_id,
        us.dance_style_id,
        us.level::text AS level
    FROM user_skills us
    """,
    """
    CREATE OR REPLACE VIEW admin_favorite_courses_view AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY fc.user_id, fc.course_id) AS id,
        fc.user_id,
        fc.course_id
    FROM favorite_courses fc
    """,
    """
    CREATE OR REPLACE VIEW admin_favorite_teachers_view AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY ft.user_id, ft.teacher_id) AS id,
        ft.user_id,
        ft.teacher_id
    FROM favorite_teachers ft
    """,
]


class Command(BaseCommand):
    help = "Creates or refreshes read-only SQL views used by Django admin."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            for statement in SQL_STATEMENTS:
                cursor.execute(statement)
        self.stdout.write(self.style.SUCCESS("Admin SQL views are ready."))
