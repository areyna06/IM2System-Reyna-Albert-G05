"""PD2 issue ISS-01: event status follows the clock without an officer editing it."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from .models import Event, sync_event_statuses
from .tests import EventTestBase


class EventStatusSyncTests(EventTestBase):
    def test_open_event_past_deadline_becomes_closed(self):
        event = self.make_event(days=1, deadline=timezone.now() - timedelta(minutes=5))
        sync_event_statuses()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CLOSED)

    def test_ended_event_becomes_completed(self):
        event = self.make_event(days=-1, deadline=timezone.now() - timedelta(days=2))
        sync_event_statuses()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.COMPLETED)

    def test_upcoming_open_event_stays_open(self):
        event = self.make_event(days=3)
        sync_event_statuses()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.OPEN)

    def test_draft_and_cancelled_events_are_not_touched(self):
        draft = self.make_event(days=-1, status=Event.Status.DRAFT, deadline=timezone.now() - timedelta(days=2))
        cancelled = self.make_event(
            days=-1, venue=self.big_venue, status=Event.Status.CANCELLED, deadline=timezone.now() - timedelta(days=2)
        )
        sync_event_statuses()
        draft.refresh_from_db()
        cancelled.refresh_from_db()
        self.assertEqual(draft.status, Event.Status.DRAFT)
        self.assertEqual(cancelled.status, Event.Status.CANCELLED)

    def test_opening_a_page_updates_statuses(self):
        event = self.make_event(days=1, deadline=timezone.now() - timedelta(minutes=5))
        self.client.force_login(self.student)
        self.client.get(reverse("event_list"))
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CLOSED)

    def test_management_command(self):
        event = self.make_event(days=-1, deadline=timezone.now() - timedelta(days=2))
        out = StringIO()
        call_command("update_event_statuses", stdout=out)
        self.assertIn("1 event(s) completed", out.getvalue())
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.COMPLETED)
