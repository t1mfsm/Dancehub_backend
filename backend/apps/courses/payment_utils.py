from __future__ import annotations

from apps.common.choices import EnrollmentStatus
from apps.courses.models import Course, Enrollment


def build_spots_left_map(courses: list[Course]) -> dict[int, int]:
    spots_left_map: dict[int, int] = {}

    for course in courses:
        active_enrollments = getattr(course, "active_enrollments", None)
        if active_enrollments is None:
            active_enrollments = Enrollment.objects.filter(
                course=course,
                status=EnrollmentStatus.ACTIVE,
            ).count()

        spots_left_map[course.id] = max(course.capacity - active_enrollments, 0)

    return spots_left_map


def get_spots_left(course: Course) -> int:
    return build_spots_left_map([course]).get(course.id, 0)
