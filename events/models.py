from django.conf import settings
from django.core.validators import MinLengthValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from accounts.models import StudentProfile


class Organization(models.Model):
    """A recognized student organization that holds events."""

    name = models.CharField(max_length=150, unique=True)
    acronym = models.CharField(
        max_length=20,
        unique=True,
        validators=[RegexValidator(r"^[A-Z0-9&\-]{2,20}$", "Use 2-20 capital letters, digits, & or -.")],
    )
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
    title = models.CharField(max_length=150, validators=[MinLengthValidator(3)])
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
    def registered_count(self):
        """Active registrations. Uses the `num_registered` annotation when the queryset has it."""
        if hasattr(self, "num_registered"):
            return self.num_registered
        return self.registrations.filter(status=EventRegistration.Status.REGISTERED).count()

    @property
    def remaining_slots(self):
        return max(self.capacity - self.registered_count, 0)

    @property
    def is_full(self):
        return self.remaining_slots == 0

    @property
    def registration_is_open(self):
        """BR-14: Open status and the deadline has not passed."""
        return self.status == self.Status.OPEN and timezone.now() <= self.registration_deadline

    @property
    def has_started(self):
        return timezone.now() >= self.start_datetime


class EventRegistration(models.Model):
    """A student's registration for an event (SDD table event_registrations)."""

    class Status(models.TextChoices):
        REGISTERED = "REGISTERED", "Registered"
        CANCELLED = "CANCELLED", "Cancelled"

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="registrations")
    student = models.ForeignKey(StudentProfile, on_delete=models.PROTECT, related_name="registrations")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REGISTERED)
    registered_at = models.DateTimeField(default=timezone.now)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-registered_at"]
        constraints = [
            models.UniqueConstraint(fields=["event", "student"], name="unique_event_registration"),
            models.CheckConstraint(
                condition=Q(status__in=["REGISTERED", "CANCELLED"]), name="registration_status_valid"
            ),
            # A cancelled registration always records when; an active one never has a cancel date.
            models.CheckConstraint(
                condition=(Q(status="REGISTERED", cancelled_at__isnull=True) | Q(status="CANCELLED", cancelled_at__isnull=False)),
                name="registration_cancelled_at_matches_status",
            ),
            models.CheckConstraint(
                condition=Q(cancelled_at__isnull=True) | Q(cancelled_at__gte=models.F("registered_at")),
                name="registration_cancelled_after_registered",
            ),
        ]

    def __str__(self):
        return f"{self.student} → {self.event} ({self.get_status_display()})"

    @property
    def is_active(self):
        return self.status == self.Status.REGISTERED

    @property
    def can_cancel(self):
        """BR-18: only before the event starts."""
        return self.is_active and not self.event.has_started


def sync_event_statuses(now=None):
    """Move events along their life cycle based on the clock (PD2 issue ISS-01).

    * Open events whose registration deadline has passed become Closed.
    * Open or Closed events that have ended become Completed.

    Draft and Cancelled events are left alone. Runs as two UPDATE queries in one
    transaction, so it is cheap enough to call before pages that list events.
    Returns (closed_count, completed_count).
    """
    from django.db import transaction

    now = now or timezone.now()
    with transaction.atomic():
        completed = Event.objects.filter(
            status__in=[Event.Status.OPEN, Event.Status.CLOSED], end_datetime__lte=now
        ).update(status=Event.Status.COMPLETED, updated_at=now)
        closed = Event.objects.filter(
            status=Event.Status.OPEN, registration_deadline__lt=now
        ).update(status=Event.Status.CLOSED, updated_at=now)
    return closed, completed


def with_registered_count(queryset):
    """Annotate events with their number of active registrations (`num_registered`)."""
    return queryset.annotate(
        num_registered=models.Count(
            "registrations", filter=Q(registrations__status=EventRegistration.Status.REGISTERED)
        )
    )
