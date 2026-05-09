import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.courses.models import PaymentOrder


logger = logging.getLogger(__name__)


def send_payment_receipt_email(order: PaymentOrder) -> None:
    receipt_email = (order.receipt_email or "").strip()
    if not receipt_email:
        return

    course = order.enrollment.course
    user = order.enrollment.user
    full_name = user.get_full_name() or user.email
    subject = f"Чек по оплате заказа {order.order_number}"
    message = (
        f"Здравствуйте, {full_name}!\n\n"
        f"Оплата прошла успешно.\n"
        f"Номер заказа: {order.order_number}\n"
        f"Курс: {course.name}\n"
        f"Сумма: {order.amount} ₽\n"
        f"Способ оплаты: {order.payment_method or '-'}\n"
        f"Дата оплаты: {order.paid_at.isoformat() if order.paid_at else '-'}\n"
    )

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [receipt_email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send payment receipt email for order %s", order.order_number)
