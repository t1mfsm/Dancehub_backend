"""Aggregated attendance stats for the teacher statistics page."""

from datetime import date
from typing import Any

from django.db.models import QuerySet

from apps.common.choices import EnrollmentStatus
from apps.common.utils import course_lifecycle_status
from apps.courses.lesson_utils import lesson_has_ended
from apps.courses.models import AttendanceMark, Course, Enrollment, Lesson, LessonStatus


def _is_present(status: str) -> bool:
    return status == "present"


def build_course_attendance_stats(
    course: Course,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    qs: QuerySet[Lesson] = Lesson.objects.filter(course=course)

    if date_from is not None:
        qs = qs.filter(lesson_date__gte=date_from)

    if date_to is not None:
        qs = qs.filter(lesson_date__lte=date_to)

    lessons_ordered = list(qs.order_by("lesson_date", "time_from", "id"))
    cancelled_lessons_count = sum(1 for lesson in lessons_ordered if lesson.status == LessonStatus.CANCELLED)
    conducted_lessons = [
        lesson
        for lesson in lessons_ordered
        if lesson.status != LessonStatus.CANCELLED and lesson_has_ended(lesson)
    ]

    enrollment_qs = Enrollment.objects.none()
    lifecycle_status = course_lifecycle_status(course.status, course.date_from, course.date_to)
    if lifecycle_status != "published":
        enrollment_qs = (
            Enrollment.objects.select_related("user")
            .filter(course=course, status=EnrollmentStatus.ACTIVE)
            .order_by("user__last_name", "user__first_name")
        )

    enrollment_list = list(enrollment_qs)
    student_count = len(enrollment_list)

    attendance_qs: QuerySet[AttendanceMark] = AttendanceMark.objects.filter(lesson__course=course)

    if date_from is not None:
        attendance_qs = attendance_qs.filter(lesson__lesson_date__gte=date_from)

    if date_to is not None:
        attendance_qs = attendance_qs.filter(lesson__lesson_date__lte=date_to)

    attendance_records = list(attendance_qs.select_related("lesson", "student"))  # type: ignore[assignment]

    per_lesson: list[dict[str, Any]] = []
    for lesson in conducted_lessons:
        lesson_attendance = [record for record in attendance_records if record.lesson_id == lesson.id]
        present_count = sum(1 for record in lesson_attendance if _is_present(record.status))
        absent_count = max(0, student_count - present_count)
        percent = round((present_count / student_count) * 100, 2) if student_count > 0 else 0

        per_lesson.append(
            {
                "lesson_id": lesson.id,
                "date": lesson.lesson_date.isoformat(),
                "present": present_count,
                "absent": absent_count,
                "total": student_count,
                "percent": percent,
            }
        )

    avg_attendance_percent = (
        round(sum(row["percent"] for row in per_lesson) / len(per_lesson), 2) if per_lesson else 0
    )

    total_conducted = len(conducted_lessons)
    per_student: list[dict[str, Any]] = []
    for enrollment in enrollment_list:
        user = enrollment.user
        attended = 0

        for lesson in conducted_lessons:
            match = next(
                (
                    record
                    for record in attendance_records
                    if record.lesson_id == lesson.id and record.student_id == user.id
                ),
                None,
            )
            if match and _is_present(match.status):
                attended += 1

        missed = total_conducted - attended
        percent = round((attended / total_conducted) * 100, 2) if total_conducted > 0 else 0

        per_student.append(
            {
                "student_id": user.id,
                "student_name": user.get_full_name() or user.email or "",
                "attended": attended,
                "missed": missed,
                "total": total_conducted,
                "percent": percent,
            }
        )

    return {
        "total_lessons": len(lessons_ordered),
        "conducted_lessons": len(conducted_lessons),
        "cancelled_lessons": cancelled_lessons_count,
        "avg_attendance_percent": avg_attendance_percent,
        "total_students": student_count,
        "per_lesson": per_lesson,
        "per_student": per_student,
    }
