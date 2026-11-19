from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models


class User(AbstractUser):
    """Custom user with a role, so every account belongs to exactly one dashboard."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MEMBER = "MEMBER", "Member"

    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    contact_number = models.CharField(
        max_length=20,
        blank=True,
        validators=[
            RegexValidator(
                r"^\+?[0-9][0-9 \-]{6,18}$",
                "Enter a valid contact number (digits, spaces, dashes, optional leading +).",
            )
        ],
    )
    photo = models.ImageField(upload_to="profile_photos/", blank=True)

    def save(self, *args, **kwargs):
        # Accounts made with `createsuperuser` are always Admins.
        # Otherwise the role decides access to the user-management (Django admin) site.
        if self.is_superuser and not self.pk:
            self.role = self.Role.ADMIN
        is_admin = self.role == self.Role.ADMIN
        self.is_staff = self.is_superuser = is_admin
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    @property
    def is_member_role(self):
        return self.role == self.Role.MEMBER

    @property
    def dashboard_url_name(self):
        return "admin_dashboard" if self.is_admin_role else "member_dashboard"

    @property
    def initials(self):
        name = self.get_full_name() or self.username
        parts = name.split()
        return "".join(p[0] for p in parts[:2]).upper()
