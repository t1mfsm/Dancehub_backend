from django.conf import settings
from django.db import models
from django.db.models import Q


class NotificationKind(models.TextChoices):
    ENROLLMENT_CONFIRMED = 'enrollment_confirmed', 'Подтверждение записи на курс'
    LESSON_REMINDER_24H = 'lesson_reminder_24h', 'Напоминание за 24 часа до занятия'
    ENROLLMENT_CANCELLED = 'enrollment_cancelled', 'Отмена записи на курс'
    NEW_STUDENT_FOR_TEACHER = 'new_student_for_teacher', 'Новый ученик на курсе'
    LESSON_CANCELLED = 'lesson_cancelled', 'Отмена занятия'


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    kind = models.CharField(max_length=64, choices=NotificationKind.choices)
    title = models.CharField(max_length=255)
    body = models.TextField()
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    lesson = models.ForeignKey(
        'courses.Lesson',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'lesson', 'kind'),
                condition=Q(lesson__isnull=False),
                name='unique_lesson_notification_per_user_kind',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.kind} → {self.user_id}'
