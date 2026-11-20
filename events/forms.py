from django import forms
from django.utils import timezone

from .models import Event, EventCategory, Venue
from .permissions import officer_organizations

DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        super().__init__(format=DATETIME_FORMAT, **kwargs)


class EventForm(forms.ModelForm):
    """Add / edit an event. Enforces SDD rules BR-09 to BR-12 and BR-23."""

    class Meta:
        model = Event
        fields = (
            "organization", "title", "category", "venue", "description",
            "start_datetime", "end_datetime", "registration_deadline", "capacity", "status",
        )
        widgets = {
            "start_datetime": DateTimeLocalInput(),
            "end_datetime": DateTimeLocalInput(),
            "registration_deadline": DateTimeLocalInput(),
            "description": forms.Textarea(attrs={"rows": 5}),
        }
        labels = {"start_datetime": "Starts", "end_datetime": "Ends"}
        help_texts = {
            "capacity": "Number of slots. Cannot be more than the venue's capacity.",
            "status": "Students can only register while the event is Open. Use the Cancel button to cancel an event.",
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("start_datetime", "end_datetime", "registration_deadline"):
            self.fields[name].input_formats = [DATETIME_FORMAT]
        self.fields["organization"].queryset = officer_organizations(user)
        self.fields["category"].queryset = EventCategory.objects.all()
        venues = Venue.objects.filter(is_active=True)
        if self.instance.pk:
            venues = venues | Venue.objects.filter(pk=self.instance.venue_id)
        self.fields["venue"].queryset = venues.distinct()
        # Cancelling is a separate action, so it is not offered in the dropdown.
        self.fields["status"].choices = [c for c in Event.Status.choices if c[0] != Event.Status.CANCELLED]
        self.fields["title"].widget.attrs["placeholder"] = "e.g. Intro to Git Workshop"

    def clean_capacity(self):
        capacity = self.cleaned_data["capacity"]
        if capacity is not None and capacity < 1:
            raise forms.ValidationError("Capacity must be at least 1.")
        return capacity

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_datetime")
        end = cleaned.get("end_datetime")
        deadline = cleaned.get("registration_deadline")
        venue = cleaned.get("venue")
        capacity = cleaned.get("capacity")

        start_changed = not self.instance.pk or "start_datetime" in self.changed_data
        if start and start_changed and start <= timezone.now():
            self.add_error("start_datetime", "The event must start in the future.")
        if start and end and end <= start:
            self.add_error("end_datetime", "The event must end after it starts.")
        if start and deadline and deadline > start:
            self.add_error("registration_deadline", "The registration deadline must be on or before the start.")
        if venue and capacity and capacity > venue.capacity:
            self.add_error("capacity", f"{venue.name} only holds {venue.capacity} people.")

        if venue and start and end and end > start:
            clash = (
                Event.objects.filter(venue=venue, start_datetime__lt=end, end_datetime__gt=start)
                .exclude(status=Event.Status.CANCELLED)
                .exclude(pk=self.instance.pk)
                .first()
            )
            if clash:
                self.add_error(
                    "venue",
                    f"{venue.name} is already booked for “{clash.title}” "
                    f"({timezone.localtime(clash.start_datetime):%b %d, %I:%M %p} – "
                    f"{timezone.localtime(clash.end_datetime):%I:%M %p}).",
                )
        return cleaned
