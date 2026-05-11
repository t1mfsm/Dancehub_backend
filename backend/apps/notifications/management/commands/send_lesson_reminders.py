from django.core.management.base import BaseCommand

from apps.notifications.services import (
    LESSON_REMINDER_HOURS_MAX,
    LESSON_REMINDER_HOURS_MIN,
    send_lesson_reminders_for_window,
)


class Command(BaseCommand):
    help = (
        'Создаёт напоминания о занятиях, если начало занятия через '
        f'{LESSON_REMINDER_HOURS_MIN:.0f}–{LESSON_REMINDER_HOURS_MAX:.0f} ч (по умолчанию). '
        'В обычном режиме это также выполняется при GET /api/notifications/ (не чаще чем раз в 15 мин). '
        'Команду можно повесить на cron для надёжности.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours-min',
            type=float,
            default=LESSON_REMINDER_HOURS_MIN,
            help='Нижняя граница окна «через сколько часов начало занятия»',
        )
        parser.add_argument(
            '--hours-max',
            type=float,
            default=LESSON_REMINDER_HOURS_MAX,
            help='Верхняя граница окна',
        )

    def handle(self, *args, **options):
        sent = send_lesson_reminders_for_window(
            hours_min=options['hours_min'],
            hours_max=options['hours_max'],
        )
        self.stdout.write(self.style.SUCCESS(f'Создано напоминаний: {sent}'))
