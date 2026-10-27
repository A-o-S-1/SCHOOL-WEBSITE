"""Temporarily create/update a Django superuser from environment variables.

Remove this command after recovering production admin access.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Temporarily bootstrap a superuser from BOOTSTRAP_ADMIN_* environment variables."

    def handle(self, *args, **options):
        username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "").strip()
        email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip()
        password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")

        if not username or not email or not password:
            raise CommandError(
                "Set BOOTSTRAP_ADMIN_USERNAME, BOOTSTRAP_ADMIN_EMAIL, and "
                "BOOTSTRAP_ADMIN_PASSWORD in the hosting environment."
            )
        if len(password) < 12:
            raise CommandError("BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters long.")

        User = get_user_model()
        user, created = User.objects.get_or_create(
            **{User.USERNAME_FIELD: username},
            defaults={"email": email},
        )
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{action} admin account '{username}'."))
