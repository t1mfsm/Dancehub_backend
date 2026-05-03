from django.db.models import QuerySet

from apps.common.choices import EnrollmentStatus
from apps.common.utils import build_full_name
from apps.courses.models import Course, Lesson
from apps.users.models import Notification, User


def create_notification(
    *,
    user: User,
    kind: str,
    title: str,
    body: str,
    course: Course | None = None,
    lesson: Lesson | None = None,
) -> Notification:
    return Notification.objects.create(
        user=user,
        kind=kind,
        title=title,
        body=body,
        course=course,
        lesson=lesson,
    )


def create_notification_once(
    *,
    user: User,
    kind: str,
    title: str,
    body: str,
    course: Course | None = None,
    lesson: Lesson | None = None,
) -> Notification | None:
    existing = Notification.objects.filter(
        user=user,
        kind=kind,
        title=title,
        body=body,
        course=course,
        lesson=lesson,
    ).first()
    if existing is not None:
        return None
    return create_notification(
        user=user,
        kind=kind,
        title=title,
        body=body,
        course=course,
        lesson=lesson,
    )


def _display_name(user: User) -> str:
    return build_full_name(user.last_name, user.first_name, user.middle_name) or user.email


def _active_course_students(course: Course) -> QuerySet[User]:
    return User.objects.filter(enrollments__course=course, enrollments__status=EnrollmentStatus.ACTIVE).distinct()


def create_teacher_enrollment_notification(*, course: Course, student: User) -> Notification | None:
    teacher_user = getattr(getattr(course, "teacher", None), "user", None)
    if teacher_user is None or teacher_user.id == student.id:
        return None

    student_name = _display_name(student)

    return create_notification(
        user=teacher_user,
        kind="course_enrollment_teacher",
        title="Новая запись на курс",
        body=f"{student_name} записался на курс «{course.name}».",
        course=course,
    )


def create_teacher_unenrollment_notification(*, course: Course, student: User) -> Notification | None:
    teacher_user = getattr(getattr(course, "teacher", None), "user", None)
    if teacher_user is None or teacher_user.id == student.id:
        return None

    student_name = _display_name(student)

    return create_notification(
        user=teacher_user,
        kind="course_unenrollment_teacher",
        title="Отмена записи на курс",
        body=f"{student_name} отменил запись на курс «{course.name}».",
        course=course,
    )


def create_student_enrollment_notification(*, course: Course, student: User) -> Notification:
    return create_notification(
        user=student,
        kind="course_enrollment_student",
        title="Вы записаны на курс",
        body=f"Вы успешно записаны на курс «{course.name}».",
        course=course,
    )


def create_student_unenrollment_notification(*, course: Course, student: User) -> Notification:
    return create_notification(
        user=student,
        kind="course_unenrollment_student",
        title="Запись на курс отменена",
        body=f"Вы отменили запись на курс «{course.name}».",
        course=course,
    )


def create_course_updated_notifications(*, course: Course, actor: User | None = None) -> int:
    created = 0
    for student in _active_course_students(course):
        if actor is not None and student.id == actor.id:
            continue
        create_notification(
            user=student,
            kind="course_updated_student",
            title="Курс обновлён",
            body=f"Курс «{course.name}» был изменён. Проверьте актуальные детали и расписание.",
            course=course,
        )
        created += 1
    return created


def create_lesson_changed_notifications(*, lesson: Lesson, title: str, body: str, actor: User | None = None) -> int:
    created = 0
    for student in _active_course_students(lesson.course):
        if actor is not None and student.id == actor.id:
            continue
        create_notification(
            user=student,
            kind="lesson_changed_student",
            title=title,
            body=body,
            course=lesson.course,
            lesson=lesson,
        )
        created += 1
    return created


def create_favorite_teacher_new_course_notifications(*, course: Course) -> int:
    teacher_id = course.teacher_id
    recipients = User.objects.filter(favorite_teachers__teacher_id=teacher_id).distinct()
    created = 0
    for user in recipients:
        if user.id == course.teacher.user_id:
            continue
        notification = create_notification_once(
            user=user,
            kind="favorite_teacher_new_course",
            title="Новый курс у избранного преподавателя",
            body=f"У преподавателя «{_display_name(course.teacher.user)}» появился новый курс «{course.name}».",
            course=course,
        )
        if notification is not None:
            created += 1
    return created


def create_teacher_lesson_reminder(*, lesson: Lesson) -> Notification | None:
    teacher_user = getattr(getattr(lesson.course, "teacher", None), "user", None)
    if teacher_user is None:
        return None
    return create_notification_once(
        user=teacher_user,
        kind="lesson_reminder_teacher",
        title="Напоминание о занятии",
        body=f"Через 24 часа начнётся занятие курса «{lesson.course.name}».",
        course=lesson.course,
        lesson=lesson,
    )


def create_student_lesson_reminders(*, lesson: Lesson) -> int:
    created = 0
    for student in _active_course_students(lesson.course):
        notification = create_notification_once(
            user=student,
            kind="lesson_reminder_student",
            title="Напоминание о занятии",
            body=f"Через 24 часа начнётся ваше занятие курса «{lesson.course.name}».",
            course=lesson.course,
            lesson=lesson,
        )
        if notification is not None:
            created += 1
    return created


def create_promo_notification(*, user: User, code: str, body: str, title: str = "Промокод") -> Notification | None:
    normalized_code = code.strip()
    if not normalized_code:
        return None
    return create_notification_once(
        user=user,
        kind="promo_code",
        title=title,
        body=f"{body}\nПромокод: {normalized_code}",
    )


def create_promo_notifications_for_users(*, users: QuerySet[User] | list[User], code: str, body: str, title: str = "Промокод") -> int:
    created = 0
    for user in users:
        notification = create_promo_notification(user=user, code=code, body=body, title=title)
        if notification is not None:
            created += 1
    return created
