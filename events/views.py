from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import StudentProfile, User

from .forms import EventFilterForm, EventForm
from .models import Event, EventRegistration, with_registered_count
from .permissions import can_manage_event, officer_organizations, organizer_required


def _get_managed_event(request, pk):
    event = get_object_or_404(Event.objects.select_related("organization", "venue", "category"), pk=pk)
    if not can_manage_event(request.user, event):
        raise PermissionDenied
    return event


# ---------------------------------------------------------------- organizer side

@organizer_required
def manage_events(request):
    events = with_registered_count(Event.objects.select_related("organization", "venue", "category")).filter(
        organization__in=officer_organizations(request.user)
    )
    status = request.GET.get("status", "")
    if status in Event.Status.values:
        events = events.filter(status=status)
    return render(request, "events/manage_list.html", {
        "events": events.order_by("-start_datetime"),
        "status": status,
        "statuses": Event.Status.choices,
        "organizations": officer_organizations(request.user),
    })


@organizer_required
def event_create(request):
    if not officer_organizations(request.user).exists():
        messages.error(request, "There are no active organizations to create events for.")
        return redirect("manage_events")
    if request.method == "POST":
        form = EventForm(request.POST, user=request.user)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()
            messages.success(request, f"Event “{event.title}” created.")
            return redirect("manage_events")
        messages.error(request, "Please fix the errors below.")
    else:
        form = EventForm(user=request.user)
    return render(request, "events/event_form.html", {"form": form})


@organizer_required
def event_edit(request, pk):
    event = _get_managed_event(request, pk)
    if event.is_cancelled:
        messages.error(request, "Cancelled events can no longer be edited.")
        return redirect("manage_events")
    if request.method == "POST":
        form = EventForm(request.POST, instance=event, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Event “{event.title}” updated.")
            return redirect("manage_events")
        messages.error(request, "Please fix the errors below.")
    else:
        form = EventForm(instance=event, user=request.user)
    return render(request, "events/event_form.html", {"form": form, "event": event})


@organizer_required
@require_POST
def event_cancel(request, pk):
    event = _get_managed_event(request, pk)
    if event.is_cancelled:
        messages.info(request, "That event is already cancelled.")
    elif event.status == Event.Status.COMPLETED:
        messages.error(request, "A completed event cannot be cancelled.")
    else:
        event.status = Event.Status.CANCELLED
        event.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Event “{event.title}” was cancelled.")
    return redirect("manage_events")


@organizer_required
def event_delete(request, pk):
    event = _get_managed_event(request, pk)
    if request.method == "POST":
        title = event.title
        try:
            event.delete()
        except ProtectedError:
            messages.error(request, f"“{title}” has registrations, so it cannot be deleted. Cancel it instead.")
            return redirect("manage_events")
        messages.success(request, f"Event “{title}” deleted.")
        return redirect("manage_events")
    return render(request, "events/event_confirm_delete.html", {"event": event})


@organizer_required
def event_participants(request, pk):
    """F-07: registered students of one event, searchable by name or student number."""
    event = _get_managed_event(request, pk)
    registrations = event.registrations.select_related("student", "student__user")
    show = request.GET.get("show", "active")
    if show != "all":
        registrations = registrations.filter(status=EventRegistration.Status.REGISTERED)
    q = request.GET.get("q", "").strip()
    if q:
        registrations = registrations.filter(
            Q(student__student_number__icontains=q)
            | Q(student__user__first_name__icontains=q)
            | Q(student__user__last_name__icontains=q)
        )
    return render(request, "events/participants.html", {
        "event": event,
        "registrations": registrations.order_by("student__user__last_name", "student__user__first_name"),
        "q": q,
        "show": show,
    })


# ---------------------------------------------------------------- student side

@login_required
def event_list(request):
    """F-03: open, upcoming events with search and filters."""
    events = with_registered_count(
        Event.objects.select_related("organization", "venue", "category").filter(
            status=Event.Status.OPEN, start_datetime__gt=timezone.now()
        )
    )
    form = EventFilterForm(request.GET or None)
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            events = events.filter(title__icontains=data["q"].strip())
        for name in ("category", "organization", "venue"):
            if data[name]:
                events = events.filter(**{name: data[name]})
        if data["date"]:
            events = events.filter(start_datetime__date=data["date"])
    my_event_ids = set(
        EventRegistration.objects.filter(
            student__user=request.user, status=EventRegistration.Status.REGISTERED
        ).values_list("event_id", flat=True)
    )
    return render(request, "events/event_list.html", {
        "events": events.order_by("start_datetime"),
        "form": form,
        "my_event_ids": my_event_ids,
        "filtered": any(request.GET.get(k) for k in ("q", "category", "organization", "venue", "date")),
    })


@login_required
def event_detail(request, pk):
    """F-04: details and remaining slots, plus the Register / Cancel button."""
    event = get_object_or_404(
        with_registered_count(Event.objects.select_related("organization", "venue", "category", "created_by")), pk=pk
    )
    manage = can_manage_event(request.user, event)
    if event.status == Event.Status.DRAFT and not manage:
        raise PermissionDenied  # drafts are visible to their organizers only
    registration = EventRegistration.objects.filter(event=event, student__user=request.user).first()
    return render(request, "events/event_detail.html", {
        "event": event,
        "registration": registration,
        "can_manage": manage,
        "is_student": request.user.is_member_role,
    })


@role_required(User.Role.MEMBER)
@require_POST
def event_register(request, pk):
    """F-05: register the logged-in student, enforcing BR-14, BR-15, BR-16 and BR-18."""
    student = StudentProfile.objects.filter(user=request.user).first()
    if student is None:
        messages.error(request, "Add your student details before registering for events.")
        return redirect(f"{reverse('student_profile_edit')}?next={reverse('event_detail', args=[pk])}")

    with transaction.atomic():
        # Lock the event row so two students can't take the last slot at the same time.
        event = get_object_or_404(Event.objects.select_for_update(), pk=pk)
        existing = EventRegistration.objects.filter(event=event, student=student).first()
        error = None
        if event.status != Event.Status.OPEN:
            error = f"Registration is closed: this event is {event.get_status_display().lower()}."
        elif timezone.now() > event.registration_deadline:
            error = "The registration deadline for this event has passed."
        elif existing and existing.is_active:
            error = "You are already registered for this event."
        elif event.registrations.filter(status=EventRegistration.Status.REGISTERED).count() >= event.capacity:
            error = "Sorry, this event is full. No slots are left."

        if error:
            messages.error(request, error)
        elif existing:  # BR-18: re-registering reactivates the cancelled record
            existing.status = EventRegistration.Status.REGISTERED
            existing.registered_at = timezone.now()
            existing.cancelled_at = None
            existing.save()
            messages.success(request, f"You are registered again for “{event.title}”.")
        else:
            EventRegistration.objects.create(event=event, student=student)
            messages.success(request, f"You are registered for “{event.title}”. See you there!")
    if event.status == Event.Status.DRAFT:
        return redirect("event_list")  # students can't open a draft's detail page
    return redirect("event_detail", pk=pk)


@role_required(User.Role.MEMBER)
@require_POST
def registration_cancel(request, pk):
    """F-09: a student cancels their own registration before the event starts."""
    registration = get_object_or_404(
        EventRegistration.objects.select_related("event"), pk=pk, student__user=request.user
    )
    if not registration.is_active:
        messages.info(request, "That registration is already cancelled.")
    elif registration.event.has_started:
        messages.error(request, "This event has already started, so the registration can no longer be cancelled.")
    else:
        registration.status = EventRegistration.Status.CANCELLED
        registration.cancelled_at = timezone.now()
        registration.save(update_fields=["status", "cancelled_at"])
        messages.success(
            request, f"Your registration for “{registration.event.title}” was cancelled. The slot is free again."
        )
    if request.POST.get("next") == "my_events":
        return redirect("my_events")
    return redirect("event_detail", pk=registration.event_id)


@role_required(User.Role.MEMBER)
def my_events(request):
    """F-10: the student's own registrations, upcoming first."""
    registrations = EventRegistration.objects.filter(student__user=request.user).select_related(
        "event", "event__venue", "event__organization"
    )
    now = timezone.now()
    upcoming = registrations.filter(event__end_datetime__gte=now).order_by("event__start_datetime")
    past = registrations.filter(event__end_datetime__lt=now).order_by("-event__start_datetime")
    return render(request, "events/my_events.html", {
        "upcoming": upcoming,
        "past": past,
        "has_student_profile": StudentProfile.objects.filter(user=request.user).exists(),
    })
