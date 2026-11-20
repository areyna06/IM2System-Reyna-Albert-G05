from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import EventForm
from .models import Event
from .permissions import can_manage_event, officer_organizations, organizer_required


def _get_managed_event(request, pk):
    event = get_object_or_404(Event.objects.select_related("organization", "venue", "category"), pk=pk)
    if not can_manage_event(request.user, event):
        raise PermissionDenied
    return event


# ---------------------------------------------------------------- organizer side

@organizer_required
def manage_events(request):
    events = Event.objects.select_related("organization", "venue", "category").filter(
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
