"""Сдвиг дат у курсов id=1 и id=2, чтобы курсы не считались завершёнными по дате."""

from datetime import date

from django.db import migrations


def forwards(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    updates = [
        (1, date(2026, 4, 15), date(2026, 8, 31)),
        (2, date(2026, 5, 1), date(2026, 9, 30)),
    ]
    for pk, date_from, date_to in updates:
        Course.objects.filter(pk=pk).update(date_from=date_from, date_to=date_to)


def backwards(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    Course.objects.filter(pk=1).update(date_from=date(2025, 2, 17), date_to=date(2025, 3, 4))
    Course.objects.filter(pk=2).update(date_from=date(2025, 2, 3), date_to=date(2025, 2, 15))


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0004_move_music_to_course"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
