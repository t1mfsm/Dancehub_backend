import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import IntegrityError
from django.utils import timezone

from apps.courses.models import Course, Enrollment, EnrollmentStatus, Lesson, LessonStatus
from apps.notifications.models import Notification, NotificationKind

logger = logging.getLogger(__name__)

# Окно «за сколько до начала занятия» напоминание может быть создано при первом попадании в интервал.
# Диапазон шире 23–25 ч: так «завтра в 12» попадает вечером накануне (≈15–18 ч до начала).
LESSON_REMINDER_HOURS_MIN = 6.0
LESSON_REMINDER_HOURS_MAX = 42.0

_LESSON_REMINDER_SCAN_CACHE_KEY = 'notifications:lesson_reminder_scan'
_LESSON_REMINDER_SCAN_SECONDS = 900


def _lesson_local_start(lesson: Lesson) -> datetime:
    tz = timezone.get_current_timezone()
    naive = datetime.combine(lesson.lesson_date, lesson.time_from)
    return timezone.make_aware(naive, tz)


def _send_email_if_enabled(subject: str, body: str, recipient: str) -> None:
    if not recipient:
        return
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Не удалось отправить email-уведомление на %s', recipient)


def create_notification(
    *,
    user,
    kind: str,
    title: str,
    body: str,
    course: Course | None = None,
    lesson: Lesson | None = None,
    email_subject: str | None = None,
    skip_duplicate_lesson: bool = False,
) -> Notification | None:
    """
    Создаёт запись уведомления и при включённой почте дублирует письмом.
    Для напоминаний по занятию при skip_duplicate_lesson ловит UniqueViolation и возвращает None.
    """
    try:
        notification = Notification.objects.create(
            user=user,
            kind=kind,
            title=title,
            body=body,
            course=course,
            lesson=lesson,
        )
    except IntegrityError:
        if skip_duplicate_lesson:
            return None
        raise

    subject = email_subject or title
    _send_email_if_enabled(subject, body, user.email)
    return notification


def notify_enrollment_success(*, student, course: Course) -> None:
    title = 'Вы записаны на курс'
    body = (
        f'Вы успешно записались на курс «{course.name}». '
        f'Начало программы: {course.date_from.strftime("%d.%m.%Y")}. '
        f'Ждём вас на занятиях!'
    )
    create_notification(
        user=student,
        kind=NotificationKind.ENROLLMENT_CONFIRMED,
        title=title,
        body=body,
        course=course,
        email_subject=f'DanceHub: {title}',
    )

    teacher_user = course.teacher.user
    t_title = 'Новая запись на курс'
    t_body = (
        f'На ваш курс «{course.name}» записался ученик '
        f'{student.get_full_name() or student.email}.'
    )
    create_notification(
        user=teacher_user,
        kind=NotificationKind.NEW_STUDENT_FOR_TEACHER,
        title=t_title,
        body=t_body,
        course=course,
        email_subject=f'DanceHub: {t_title}',
    )


def notify_enrollment_cancelled(*, student, course: Course) -> None:
    title = 'Запись на курс отменена'
    body = f'Вы отменили запись на курс «{course.name}».'
    create_notification(
        user=student,
        kind=NotificationKind.ENROLLMENT_CANCELLED,
        title=title,
        body=body,
        course=course,
        email_subject=f'DanceHub: {title}',
    )


def notify_lesson_cancelled(*, lesson: Lesson) -> None:
    course = lesson.course
    enrollments = Enrollment.objects.filter(
        course=course,
        status__in=[EnrollmentStatus.ACTIVE, EnrollmentStatus.PENDING],
    ).select_related('user')

    location = lesson.location_text or (course.studio.name if course.studio else 'студия уточняется')
    lesson_label = lesson.lesson_date.strftime('%d.%m.%Y')
    for enrollment in enrollments:
        title = 'Занятие отменено'
        body = (
            f'Занятие курса «{course.name}» {lesson_label} ({lesson.time_from.strftime("%H:%M")}) '
            f'отменено. Место: {location}.'
        )
        create_notification(
            user=enrollment.user,
            kind=NotificationKind.LESSON_CANCELLED,
            title=title,
            body=body,
            course=course,
            lesson=lesson,
            email_subject=f'DanceHub: {title}',
        )


def maybe_send_lesson_reminders() -> None:
    """
    Раз в _LESSON_REMINDER_SCAN_SECONDS секунд создаёт напоминания по занятиям в окне
    LESSON_REMINDER_HOURS_MIN…LESSON_REMINDER_HOURS_MAX. Вызывается при GET /notifications/.
    """
    if not cache.add(_LESSON_REMINDER_SCAN_CACHE_KEY, 1, _LESSON_REMINDER_SCAN_SECONDS):
        return
    send_lesson_reminders_for_window(
        hours_min=LESSON_REMINDER_HOURS_MIN,
        hours_max=LESSON_REMINDER_HOURS_MAX,
    )


def send_lesson_reminders_for_window(
    *,
    hours_min: float = LESSON_REMINDER_HOURS_MIN,
    hours_max: float = LESSON_REMINDER_HOURS_MAX,
) -> int:
    """
    Находит занятия в окне «через hours_min…hours_max часов» от текущего момента
    и создаёт напоминания ученикам (по одному на пару user+lesson) и преподавателю курса.
    Статусы записей совпадают с фильтром календаря: active, pending, completed.
    """
    now = timezone.now()
    window_start = now + timedelta(hours=hours_min)
    window_end = now + timedelta(hours=hours_max)

    lessons = Lesson.objects.filter(status=LessonStatus.SCHEDULED).select_related(
        'course',
        'course__studio',
        'course__teacher__user',
    )
    sent = 0

    enrollment_reminder_statuses = [
        EnrollmentStatus.ACTIVE,
        EnrollmentStatus.PENDING,
        EnrollmentStatus.COMPLETED,
    ]

    for lesson in lessons:
        start_at = _lesson_local_start(lesson)
        if not (window_start <= start_at <= window_end):
            continue

        course = lesson.course
        enrollments = Enrollment.objects.filter(
            course=course,
            status__in=enrollment_reminder_statuses,
        ).select_related('user')

        studio_name = course.studio.name if course.studio else ''
        location = lesson.location_text or studio_name or 'уточняется у преподавателя'
        title = 'Напоминание о занятии'
        body = (
            f'Занятие по курсу «{course.name}»: '
            f'{lesson.lesson_date.strftime("%d.%m.%Y")} с {lesson.time_from.strftime("%H:%M")} '
            f'до {lesson.time_to.strftime("%H:%M")}. Место: {location}.'
        )

        for enrollment in enrollments:
            created = create_notification(
                user=enrollment.user,
                kind=NotificationKind.LESSON_REMINDER_24H,
                title=title,
                body=body,
                course=course,
                lesson=lesson,
                email_subject=f'DanceHub: напоминание о занятии',
                skip_duplicate_lesson=True,
            )
            if created is not None:
                sent += 1

        teacher_user = course.teacher.user
        created_teacher = create_notification(
            user=teacher_user,
            kind=NotificationKind.LESSON_REMINDER_24H,
            title=title,
            body=body,
            course=course,
            lesson=lesson,
            email_subject=f'DanceHub: напоминание о занятии',
            skip_duplicate_lesson=True,
        )
        if created_teacher is not None:
            sent += 1

    return sent
