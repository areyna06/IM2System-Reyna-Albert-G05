import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

DEMO_USERS = [
    # username, email, first, last, role, password env var
    ("admin", "admin@example.com", "Ada", "Admin", "ADMIN", "DEMO_ADMIN_PASSWORD"),
    ("member", "member@example.com", "Mark", "Member", "MEMBER", "DEMO_MEMBER_PASSWORD"),
]


class Command(BaseCommand):
    help = "Create (or reset) one demo Admin and one demo Member. Passwords come from .env."

    def handle(self, *args, **options):
        User = get_user_model()
        for username, email, first, last, role, env_name in DEMO_USERS:
            password = os.getenv(env_name)
            if not password:
                raise CommandError(f"Set {env_name} in your .env file first.")
            user, created = User.objects.get_or_create(username=username, defaults={"email": email})
            user.email, user.first_name, user.last_name, user.role = email, first, last, role
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Reset'} {role.lower()} account: {username}"))
