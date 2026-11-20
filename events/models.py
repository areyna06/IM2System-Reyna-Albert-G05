from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from accounts.models import StudentProfile


class Organization(models.Model):
    """A recognized student organization that holds events."""

    name = models.CharField(max_length=150, unique=True)
    acronym = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    adviser_name = models.CharField(max_length=100, blank=True)
    contact_email = models.EmailField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["acronym"]

    def __str__(self):
        return self.acronym


class OrganizationMember(models.Model):
    class Role(models.TextChoices):
        OFFICER = "OFFICER", "Officer"
        MEMBER = "MEMBER", "Member"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="memberships")
    position = models.CharField(max_length=50, help_text="e.g. President, Secretary, Member")
    member_role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    date_joined = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "student"], name="unique_org_member"),
            models.CheckConstraint(condition=Q(member_role__in=["OFFICER", "MEMBER"]), name="member_role_valid"),
        ]

    def __str__(self):
        return f"{self.student} – {self.organization} ({self.get_member_role_display()})"


class Venue(models.Model):
    name = models.CharField(max_length=100, unique=True)
    building = models.CharField(max_length=100)
    room_number = models.CharField(max_length=20, blank=True)
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.CheckConstraint(condition=Q(capacity__gt=0), name="venue_capacity_positive")]

    def __str__(self):
        return f"{self.name} (cap. {self.capacity})"


class EventCategory(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "event categories"

    def __str__(self):
        return self.name


class Event(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="events")
    category = models.ForeignKey(EventCategory, on_delete=models.PROTECT, related_name="events")
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name="events")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="events_created")
    title = models.CharField(max_length=150)
    description = models.TextField()
    start_datetime = models.DateTimeField("starts")
    end_datetime = models.DateTimeField("ends")
    registration_deadline = models.DateTimeField()
    capacity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_datetime"]
        constraints = [
            models.CheckConstraint(condition=Q(capacity__gt=0), name="event_capacity_positive"),
            models.CheckConstraint(condition=Q(end_datetime__gt=models.F("start_datetime")), name="event_end_after_start"),
            models.CheckConstraint(
                condition=Q(registration_deadline__lte=models.F("start_datetime")),
                name="event_deadline_before_start",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["DRAFT", "OPEN", "CLOSED", "COMPLETED", "CANCELLED"]),
                name="event_status_valid",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_cancelled(self):
        return self.status == self.Status.CANCELLED

    @property
    def has_started(self):
        return timezone.now() >= self.start_datetime
