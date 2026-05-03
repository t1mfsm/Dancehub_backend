from django.core.management.base import BaseCommand, CommandError

from apps.common.choices import UserRole
from apps.users.models import User
from apps.users.notifications import create_promo_notifications_for_users


class Command(BaseCommand):
    help = "Send promo code notifications to selected users."

    def add_arguments(self, parser):
        parser.add_argument("--code", required=True)
        parser.add_argument("--body", required=True)
        parser.add_argument("--title", default="Промокод")
        parser.add_argument("--all-users", action="store_true")
        parser.add_argument("--user-id", type=int, action="append", dest="user_ids")
        parser.add_argument("--role", choices=[UserRole.STUDENT, UserRole.TEACHER])

    def handle(self, *args, **options):
        queryset = User.objects.all().order_by("id")

        role = options.get("role")
        if role:
            queryset = queryset.filter(role=role)

        user_ids = options.get("user_ids") or []
        if user_ids:
            queryset = queryset.filter(id__in=user_ids)
        elif not options["all_users"]:
            raise CommandError("Pass --all-users or at least one --user-id.")

        created = create_promo_notifications_for_users(
            users=list(queryset),
            code=options["code"],
            body=options["body"],
            title=options["title"],
        )

        self.stdout.write(self.style.SUCCESS(f"Sent promo notifications: {created}."))
