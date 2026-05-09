from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from django.db import connection
from django.db.models import Count
from django.utils import timezone

from apps.common.choices import EnrollmentStatus, PaymentOrderStatus
from apps.courses.models import Course, Enrollment, PaymentOrder


PAYMENT_ORDER_TTL = timedelta(minutes=15)


def generate_payment_order_number() -> str:
    return f"DH-{timezone.now():%Y%m%d}-{uuid4().hex[:8].upper()}"


def generate_payment_public_token() -> str:
    return uuid4().hex


def payment_orders_table_exists() -> bool:
    try:
        return "payment_orders" in connection.introspection.table_names()
    except Exception:
        return False


def get_pending_reservation_counts(course_ids: list[int]) -> dict[int, int]:
    if not course_ids:
        return {}
    if not payment_orders_table_exists():
        return {}

    rows = (
        PaymentOrder.objects.filter(
            enrollment__course_id__in=course_ids,
            enrollment__status=EnrollmentStatus.PENDING,
            status=PaymentOrderStatus.PENDING,
            expires_at__gt=timezone.now(),
        )
        .values("enrollment__course_id")
        .annotate(total=Count("enrollment_id", distinct=True))
    )
    return {row["enrollment__course_id"]: row["total"] for row in rows}


def build_spots_left_map(courses: list[Course]) -> dict[int, int]:
    pending_counts = get_pending_reservation_counts([course.id for course in courses])
    spots_left_map: dict[int, int] = {}

    for course in courses:
        active_enrollments = getattr(course, "active_enrollments", None)
        if active_enrollments is None:
            active_enrollments = Enrollment.objects.filter(
                course=course,
                status=EnrollmentStatus.ACTIVE,
            ).count()

        reserved_count = active_enrollments + pending_counts.get(course.id, 0)
        spots_left_map[course.id] = max(course.capacity - reserved_count, 0)

    return spots_left_map


def get_spots_left(course: Course) -> int:
    return build_spots_left_map([course]).get(course.id, 0)


def get_live_pending_payment_order(enrollment: Enrollment) -> PaymentOrder | None:
    if not payment_orders_table_exists():
        return None
    return (
        PaymentOrder.objects.filter(
            enrollment=enrollment,
            status=PaymentOrderStatus.PENDING,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at", "-id")
        .first()
    )


def expire_stale_payment_orders_for_enrollment(enrollment: Enrollment) -> int:
    if not payment_orders_table_exists():
        return 0
    now = timezone.now()
    expired_count = PaymentOrder.objects.filter(
        enrollment=enrollment,
        status=PaymentOrderStatus.PENDING,
        expires_at__lte=now,
    ).update(status=PaymentOrderStatus.EXPIRED, updated_at=now)

    has_live_order = PaymentOrder.objects.filter(
        enrollment=enrollment,
        status=PaymentOrderStatus.PENDING,
        expires_at__gt=now,
    ).exists()

    if enrollment.status == EnrollmentStatus.PENDING and not has_live_order:
        enrollment.status = EnrollmentStatus.CANCELLED
        enrollment.save(update_fields=["status"])

    return expired_count


def expire_payment_order_if_needed(order: PaymentOrder) -> PaymentOrder:
    if not payment_orders_table_exists():
        return order
    if order.status == PaymentOrderStatus.PENDING and order.expires_at <= timezone.now():
        order.status = PaymentOrderStatus.EXPIRED
        order.updated_at = timezone.now()
        order.save(update_fields=["status", "updated_at"])
        expire_stale_payment_orders_for_enrollment(order.enrollment)
    return order


def cancel_pending_payment_orders(enrollment: Enrollment) -> int:
    if not payment_orders_table_exists():
        return 0
    return PaymentOrder.objects.filter(
        enrollment=enrollment,
        status=PaymentOrderStatus.PENDING,
    ).update(status=PaymentOrderStatus.CANCELLED, updated_at=timezone.now())
