from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
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


class StudentProfile(models.Model):
    """School details of a student account (SDD table student_profiles). Admins have none."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="student_profile")
    student_number = models.CharField(
        max_length=20,
        unique=True,
        validators=[RegexValidator(r"^[0-9][0-9\-]{3,19}$", "Use digits and dashes only, e.g. 21-1234-567.")],
    )
    program = models.CharField(max_length=100, help_text="Degree program, e.g. BSIT.")
    year_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(year_level__gte=1, year_level__lte=5),
                name="student_year_level_1_to_5",
            ),
        ]

    def __str__(self):
        return f"{self.student_number} · {self.user.get_full_name() or self.user.username}"
