"""Агрегированная посещаемость по курсу для страницы «Статистика»."""

from datetime import date
from typing import Any, Optional

from django.db.models import QuerySet

from apps.courses.lesson_utils import lesson_has_ended
from apps.courses.models import Attendance, Course, Enrollment, EnrollmentStatus, Lesson, LessonStatus


def _presence_statuses_present(status: str) -> bool:
    return status in ("present", "late")


def build_course_attendance_stats(
    course: Course,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> dict[str, Any]:
    """
    Считает метрики в разрезе периода (фильтр по lesson.lesson_date).
    «Проведённые» занятия — не отменённые и уже закончившиеся по дате/времени (как завершённые в интерфейсе).
    """
    qs: QuerySet[Lesson] = Lesson.objects.filter(course=course)

    if date_from is not None:
        qs = qs.filter(lesson_date__gte=date_from)

    if date_to is not None:
        qs = qs.filter(lesson_date__lte=date_to)

    lessons_ordered = list(qs.order_by("lesson_date", "time_from", "id"))
    cancelled_lessons_count = sum(1 for ln in lessons_ordered if ln.status == LessonStatus.CANCELLED)
    conducted: list[Lesson] = [
        ln
        for ln in lessons_ordered
        if ln.status != LessonStatus.CANCELLED and lesson_has_ended(ln)
    ]

    enrollees = (
        Enrollment.objects.select_related("user")
        .filter(
            course=course,
            status__in=[
                EnrollmentStatus.PENDING,
                EnrollmentStatus.ACTIVE,
                EnrollmentStatus.COMPLETED,
            ],
        )
        .order_by("user__last_name", "user__first_name")
    )

    enrollment_list = list(enrollees)
    student_count = len(enrollment_list)

    att_qs: QuerySet[Attendance] = Attendance.objects.filter(lesson__course=course)

    if date_from is not None:
        att_qs = att_qs.filter(lesson__lesson_date__gte=date_from)

    if date_to is not None:
        att_qs = att_qs.filter(lesson__lesson_date__lte=date_to)

    attendance_records = list(att_qs.select_related("lesson", "student"))

    per_lesson: list[dict[str, Any]] = []

    for lesson in conducted:
        lesson_att = [a for a in attendance_records if a.lesson_id == lesson.id]
        present_count = sum(1 for a in lesson_att if _presence_statuses_present(a.status))
        denom = student_count
        absent_count = max(0, denom - present_count)
        pct = round((present_count / denom) * 100) if denom > 0 else 0

        per_lesson.append(
            {
                "lesson_id": lesson.id,
                "date": lesson.lesson_date,
                "present": present_count,
                "absent": absent_count,
                "total": denom,
                "percent": pct,
            }
        )

    avg_attendance_percent = (
        round(sum(row["percent"] for row in per_lesson) / len(per_lesson)) if per_lesson else 0
    )

    per_student: list[dict[str, Any]] = []

    total_conducted = len(conducted)

    for enrollment in enrollment_list:
        user_obj = enrollment.user
        uid = user_obj.id
        attended = 0

        for lesson in conducted:
            match = next(
                (a for a in attendance_records if a.lesson_id == lesson.id and a.student_id == uid),
                None,
            )

            if match and _presence_statuses_present(match.status):
                attended += 1

        missed = total_conducted - attended

        pct = round((attended / total_conducted) * 100) if total_conducted > 0 else 0

        per_student.append(
            {
                "student_id": uid,
                "student_name": user_obj.get_full_name() or user_obj.email or "",
                "attended": attended,
                "missed": missed,
                "total": total_conducted,
                "percent": pct,
            }
        )

    return {
        "total_lessons": len(lessons_ordered),
        "conducted_lessons": len(conducted),
        "cancelled_lessons": cancelled_lessons_count,
        "avg_attendance_percent": avg_attendance_percent,
        "total_students": student_count,
        "per_lesson": per_lesson,
        "per_student": per_student,
    }
