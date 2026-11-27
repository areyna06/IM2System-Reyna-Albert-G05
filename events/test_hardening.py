"""PD3 hardening tests for the core feature (Event Registration).

Covers valid input, invalid input, login required, blocked access to another
user's record, wrong role, POST-only actions, CSRF, error pages and database
constraints.
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.views.defaults import server_error

from .models import Event, EventRegistration
from .tests import FMT, PASSWORD, EventTestBase, make_user


class CoreFeatureHardeningTests(EventTestBase):
    def setUp(self):
        self.event = self.make_event(capacity=2)

    def login(self, username):
        self.client.login(username=username, password=PASSWORD)

    # ------------------------------------------------------------ valid input
    def test_register_valid_creates_registration(self):
        self.login("sam")
        resp = self.client.post(reverse("event_register", args=[self.event.pk]), follow=True)
        self.assertRedirects(resp, reverse("event_detail", args=[self.event.pk]))
        self.assertContains(resp, "You are registered for")
        self.assertTrue(
            EventRegistration.objects.filter(
                event=self.event, student=self.student.student_profile, status=EventRegistration.Status.REGISTERED
            ).exists()
        )

    def test_create_event_valid_saves_and_redirects(self):
        self.login("olivia")
        resp = self.client.post(reverse("event_create"), self.form_data(title="Hardening Talk", venue=self.big_venue.pk))
        self.assertRedirects(resp, reverse("manage_events"))
        self.assertTrue(Event.objects.filter(title="Hardening Talk", created_by=self.officer).exists())

    # ---------------------------------------------------------- invalid input
    def test_create_event_end_before_start_rejected(self):
        self.login("olivia")
        resp = self.client.post(reverse("event_create"), self.form_data(hours=-1, title="Backwards"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "The event must end after it starts.")
        self.assertFalse(Event.objects.filter(title="Backwards").exists())

    def test_create_event_in_the_past_rejected(self):
        self.login("olivia")
        resp = self.client.post(reverse("event_create"), self.form_data(days=-2, title="Old news"))
        self.assertContains(resp, "The event must start in the future.")
        self.assertFalse(Event.objects.filter(title="Old news").exists())

    def test_capacity_above_venue_rejected(self):
        self.login("olivia")
        resp = self.client.post(reverse("event_create"), self.form_data(capacity=999, title="Too big"))
        self.assertContains(resp, "only holds 40 people")
        self.assertFalse(Event.objects.filter(title="Too big").exists())

    def test_open_status_after_deadline_rejected(self):
        self.login("olivia")
        start = timezone.localtime() + timedelta(days=2)
        data = self.form_data(title="Late opener", venue=self.big_venue.pk)
        data["registration_deadline"] = (timezone.localtime() - timedelta(hours=1)).strftime(FMT)
        data["start_datetime"] = start.strftime(FMT)
        resp = self.client.post(reverse("event_create"), data)
        self.assertContains(resp, "deadline has already passed")
        self.assertFalse(Event.objects.filter(title="Late opener").exists())

    def test_completed_status_before_end_rejected(self):
        self.login("olivia")
        data = self.form_data(title="Too early", venue=self.big_venue.pk, status=Event.Status.COMPLETED)
        resp = self.client.post(reverse("event_create"), data)
        self.assertContains(resp, "only be marked Completed after it ends")

    def test_venue_double_booking_rejected(self):
        self.login("olivia")
        start = timezone.localtime(self.event.start_datetime) + timedelta(minutes=30)
        data = self.form_data(title="Clash")
        data["start_datetime"] = start.strftime(FMT)
        data["end_datetime"] = (start + timedelta(hours=1)).strftime(FMT)
        data["registration_deadline"] = (start - timedelta(hours=2)).strftime(FMT)
        resp = self.client.post(reverse("event_create"), data)
        self.assertContains(resp, "is already booked")
        self.assertFalse(Event.objects.filter(title="Clash").exists())

    def test_duplicate_registration_rejected(self):
        self.login("sam")
        url = reverse("event_register", args=[self.event.pk])
        self.client.post(url)
        resp = self.client.post(url, follow=True)
        self.assertContains(resp, "You are already registered for this event.")
        self.assertEqual(EventRegistration.objects.filter(event=self.event).count(), 1)

    def test_full_event_rejected(self):
        self.event.capacity = 1
        self.event.save()
        EventRegistration.objects.create(event=self.event, student=self.officer.student_profile)
        self.login("sam")
        resp = self.client.post(reverse("event_register", args=[self.event.pk]), follow=True)
        self.assertContains(resp, "this event is full")
        self.assertFalse(EventRegistration.objects.filter(student=self.student.student_profile).exists())

    def test_cannot_move_event_with_registrations_back_to_draft(self):
        EventRegistration.objects.create(event=self.event, student=self.student.student_profile)
        self.login("olivia")
        data = self.form_data(status=Event.Status.DRAFT)
        data["start_datetime"] = timezone.localtime(self.event.start_datetime).strftime(FMT)
        data["end_datetime"] = timezone.localtime(self.event.end_datetime).strftime(FMT)
        data["registration_deadline"] = timezone.localtime(self.event.registration_deadline).strftime(FMT)
        resp = self.client.post(reverse("event_edit", args=[self.event.pk]), data)
        self.assertContains(resp, "cannot go back to Draft")
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.Status.OPEN)

    # --------------------------------------------------------- login required
    def test_core_pages_require_login(self):
        urls = [
            reverse("event_list"), reverse("event_detail", args=[self.event.pk]), reverse("my_events"),
            reverse("manage_events"), reverse("event_create"), reverse("event_edit", args=[self.event.pk]),
            reverse("event_participants", args=[self.event.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertRedirects(resp, f"{reverse('login')}?next={url}", fetch_redirect_response=False)

    def test_register_requires_login(self):
        resp = self.client.post(reverse("event_register", args=[self.event.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp["Location"])
        self.assertFalse(EventRegistration.objects.exists())

    # ------------------------------------------ another user's record / roles
    def test_cannot_cancel_another_students_registration(self):
        reg = EventRegistration.objects.create(event=self.event, student=self.officer.student_profile)
        self.login("sam")
        resp = self.client.post(reverse("registration_cancel", args=[reg.pk]))
        self.assertEqual(resp.status_code, 404)
        reg.refresh_from_db()
        self.assertEqual(reg.status, EventRegistration.Status.REGISTERED)

    def test_officer_cannot_edit_another_organizations_event(self):
        other = self.make_event(org=self.other_org, venue=self.big_venue, title="DEVC Night")
        self.login("olivia")
        self.assertEqual(self.client.get(reverse("event_edit", args=[other.pk])).status_code, 403)
        resp = self.client.post(reverse("event_edit", args=[other.pk]), self.form_data(title="Hijacked"))
        self.assertEqual(resp.status_code, 403)
        other.refresh_from_db()
        self.assertEqual(other.title, "DEVC Night")

    def test_officer_cannot_view_another_organizations_participants(self):
        other = self.make_event(org=self.other_org, venue=self.big_venue)
        self.login("olivia")
        self.assertEqual(self.client.get(reverse("event_participants", args=[other.pk])).status_code, 403)

    def test_student_role_blocked_from_organizer_actions(self):
        self.login("sam")
        self.assertEqual(self.client.post(reverse("event_cancel", args=[self.event.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("event_delete", args=[self.event.pk])).status_code, 403)
        self.assertTrue(Event.objects.filter(pk=self.event.pk, status=Event.Status.OPEN).exists())

    def test_admin_cannot_register_as_student(self):
        self.login("boss")
        resp = self.client.post(reverse("event_register", args=[self.event.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_student_cannot_see_draft_event(self):
        draft = self.make_event(status=Event.Status.DRAFT, venue=self.big_venue)
        self.login("sam")
        self.assertEqual(self.client.get(reverse("event_detail", args=[draft.pk])).status_code, 403)

    # ------------------------------------------------ POST only, CSRF, delete
    def test_state_changing_actions_reject_get(self):
        self.login("olivia")
        self.assertEqual(self.client.get(reverse("event_cancel", args=[self.event.pk])).status_code, 405)
        self.login("sam")
        self.assertEqual(self.client.get(reverse("event_register", args=[self.event.pk])).status_code, 405)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.Status.OPEN)

    def test_delete_get_only_shows_confirmation(self):
        self.login("olivia")
        resp = self.client.get(reverse("event_delete", args=[self.event.pk]))
        self.assertContains(resp, "Delete event?")
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_event_with_registrations_cannot_be_deleted(self):
        EventRegistration.objects.create(event=self.event, student=self.student.student_profile)
        self.login("olivia")
        resp = self.client.post(reverse("event_delete", args=[self.event.pk]), follow=True)
        self.assertContains(resp, "cannot be deleted")
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_post_without_csrf_token_rejected(self):
        client = Client(enforce_csrf_checks=True)
        client.login(username="sam", password=PASSWORD)
        resp = client.post(reverse("event_register", args=[self.event.pk]))
        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, "Form expired", status_code=403)
        self.assertFalse(EventRegistration.objects.exists())

    # ------------------------------------------------------------ error pages
    def test_unknown_event_id_shows_custom_404(self):
        self.login("sam")
        resp = self.client.get(reverse("event_detail", args=[999999]))
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, "Page not found", status_code=404)
        self.assertNotContains(resp, "Traceback", status_code=404)

    def test_invalid_filter_values_do_not_crash(self):
        self.login("sam")
        resp = self.client.get(reverse("event_list"), {"category": "abc", "date": "not-a-date", "venue": "-1"})
        self.assertEqual(resp.status_code, 200)

    def test_custom_500_page(self):
        resp = server_error(RequestFactory().get("/"))
        self.assertEqual(resp.status_code, 500)
        self.assertIn(b"Something went wrong", resp.content)

    # ----------------------------------------------------- database integrity
    def test_database_blocks_duplicate_registration(self):
        EventRegistration.objects.create(event=self.event, student=self.student.student_profile)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EventRegistration.objects.create(event=self.event, student=self.student.student_profile)

    def test_database_blocks_cancelled_registration_without_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            EventRegistration.objects.create(
                event=self.event, student=self.student.student_profile, status=EventRegistration.Status.CANCELLED
            )

    def test_database_blocks_end_before_start(self):
        start = timezone.now() + timedelta(days=5)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Event.objects.create(
                organization=self.org, category=self.category, venue=self.big_venue, created_by=self.officer,
                title="Bad dates", description="x", start_datetime=start, end_datetime=start - timedelta(hours=1),
                registration_deadline=start - timedelta(days=1), capacity=5,
            )
