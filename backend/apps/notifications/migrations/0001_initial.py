import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('courses', '0005_fix_two_courses_dates_not_expired'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'kind',
                    models.CharField(
                        choices=[
                            ('enrollment_confirmed', 'Подтверждение записи на курс'),
                            ('lesson_reminder_24h', 'Напоминание за 24 часа до занятия'),
                            ('enrollment_cancelled', 'Отмена записи на курс'),
                            ('new_student_for_teacher', 'Новый ученик на курсе'),
                            ('lesson_cancelled', 'Отмена занятия'),
                        ],
                        max_length=64,
                    ),
                ),
                ('title', models.CharField(max_length=255)),
                ('body', models.TextField()),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'course',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='notifications',
                        to='courses.course',
                    ),
                ),
                (
                    'lesson',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='notifications',
                        to='courses.lesson',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='notifications',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'Уведомление',
                'verbose_name_plural': 'Уведомления',
                'db_table': 'notifications',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.UniqueConstraint(
                condition=models.Q(lesson__isnull=False),
                fields=('user', 'lesson', 'kind'),
                name='unique_lesson_notification_per_user_kind',
            ),
        ),
    ]
