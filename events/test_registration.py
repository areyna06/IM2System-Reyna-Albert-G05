from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentProfile

from .models import Event, EventRegistration
from .tests import PASSWORD, EventTestBase, make_user


class BrowseAndDetailTests(EventTestBase):
    def setUp(self):
        self.client.login(username="sam", password=PASSWORD)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(reverse("event_list"))
        self.assertRedirects(resp, f"{reverse('login')}?next={reverse('event_list')}")

    def test_only_open_upcoming_events_are_listed(self):
        self.make_event(title="Open one")
        self.make_event(title="Draft one", status=Event.Status.DRAFT, venue=self.big_venue)
        self.make_event(title="Cancelled one", status=Event.Status.CANCELLED, days=3)
        resp = self.client.get(reverse("event_list"))
        self.assertContains(resp, "Open one")
        self.assertNotContains(resp, "Draft one")
        self.assertNotContains(resp, "Cancelled one")

    def test_search_and_filters(self):
        self.make_event(title="Git Basics")
        self.make_event(title="Python Night", org=self.other_org, venue=self.big_venue)
        resp = self.client.get(reverse("event_list"), {"q": "git"})
        self.assertContains(resp, "Git Basics")
        self.assertNotContains(resp, "Python Night")
        resp = self.client.get(reverse("event_list"), {"organization": self.other_org.pk})
        self.assertContains(resp, "Python Night")
        self.assertNotContains(resp, "Git Basics")
        resp = self.client.get(reverse("event_list"), {"q": "nothing-like-this"})
        self.assertContains(resp, "No events match your search.")

    def test_detail_shows_remaining_slots(self):
        event = self.make_event(capacity=5)
        EventRegistration.objects.create(event=event, student=self.officer.student_profile)
        resp = self.client.get(reverse("event_detail", args=[event.pk]))
        self.assertContains(resp, "4 of 5 left")
        self.assertContains(resp, "Register for this event")

    def test_draft_hidden_from_students_but_visible_to_officer(self):
        event = self.make_event(status=Event.Status.DRAFT)
        self.assertEqual(self.client.get(reverse("event_detail", args=[event.pk])).status_code, 403)
        self.client.login(username="olivia", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("event_detail", args=[event.pk])).status_code, 200)


class RegistrationTests(EventTestBase):
    def setUp(self):
        self.client.login(username="sam", password=PASSWORD)
        self.event = self.make_event(capacity=2)

    def register(self, event=None):
        return self.client.post(reverse("event_register", args=[(event or self.event).pk]), follow=True)

    def test_register_success_links_student(self):
        resp = self.register()
        self.assertContains(resp, "You are registered for")
        reg = EventRegistration.objects.get()
        self.assertEqual(reg.student, self.student.student_profile)
        self.assertEqual(reg.student.user, self.student)
        self.assertEqual(reg.status, EventRegistration.Status.REGISTERED)
        self.assertContains(resp, "Cancel my registration")

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(reverse("event_register", args=[self.event.pk])).status_code, 405)

    def test_duplicate_registration_blocked(self):  # BR-15
        self.register()
        resp = self.register()
        self.assertContains(resp, "already registered")
        self.assertEqual(EventRegistration.objects.count(), 1)

    def test_database_rejects_duplicate_row(self):
        EventRegistration.objects.create(event=self.event, student=self.student.student_profile)
        with self.assertRaises(IntegrityError):
            EventRegistration.objects.create(event=self.event, student=self.student.student_profile)

    def test_capacity_enforced(self):  # BR-16
        EventRegistration.objects.create(event=self.event, student=self.officer.student_profile)
        third = make_user("tina", student_number="22-0003-003")
        EventRegistration.objects.create(event=self.event, student=third.student_profile)
        resp = self.register()
        self.assertContains(resp, "this event is full")
        self.assertFalse(EventRegistration.objects.filter(student=self.student.student_profile).exists())

    def test_cancelled_registrations_free_a_slot(self):
        EventRegistration.objects.create(event=self.event, student=self.officer.student_profile)
        third = make_user("tina", student_number="22-0003-003")
        EventRegistration.objects.create(
            event=self.event, student=third.student_profile,
            status=EventRegistration.Status.CANCELLED,
            registered_at=timezone.now() - timedelta(minutes=1), cancelled_at=timezone.now(),
        )
        self.assertContains(self.register(), "You are registered for")

    def test_only_open_events(self):  # BR-14
        for status in (Event.Status.DRAFT, Event.Status.CLOSED, Event.Status.CANCELLED):
            with self.subTest(status=status):
                Event.objects.filter(pk=self.event.pk).update(status=status)
                self.assertContains(self.register(), "Registration is closed")
        self.assertFalse(EventRegistration.objects.exists())

    def test_deadline_enforced(self):  # BR-14
        Event.objects.filter(pk=self.event.pk).update(registration_deadline=timezone.now() - timedelta(minutes=1))
        self.assertContains(self.register(), "deadline for this event has passed")
        self.assertFalse(EventRegistration.objects.exists())

    def test_student_profile_required(self):
        make_user("nora")  # no student profile
        self.client.login(username="nora", password=PASSWORD)
        resp = self.client.post(reverse("event_register", args=[self.event.pk]))
        self.assertRedirects(
            resp, f"{reverse('student_profile_edit')}?next={reverse('event_detail', args=[self.event.pk])}"
        )
        self.assertFalse(EventRegistration.objects.exists())

    def test_admin_cannot_register(self):
        self.client.login(username="boss", password=PASSWORD)
        self.assertEqual(self.client.post(reverse("event_register", args=[self.event.pk])).status_code, 403)

    def test_cancel_and_reregister_reuses_record(self):  # F-09, BR-18
        self.register()
        reg = EventRegistration.objects.get()
        resp = self.client.post(reverse("registration_cancel", args=[reg.pk]), follow=True)
        self.assertContains(resp, "was cancelled")
        reg.refresh_from_db()
        self.assertEqual(reg.status, EventRegistration.Status.CANCELLED)
        self.assertIsNotNone(reg.cancelled_at)
        self.assertEqual(self.event.registered_count, 0)
        resp = self.register()
        self.assertContains(resp, "registered again")
        self.assertEqual(EventRegistration.objects.count(), 1)
        reg.refresh_from_db()
        self.assertEqual(reg.status, EventRegistration.Status.REGISTERED)
        self.assertIsNone(reg.cancelled_at)

    def test_cannot_cancel_after_event_started(self):  # BR-18
        started = self.make_event(venue=self.big_venue, days=-1, deadline=timezone.now() - timedelta(days=2))
        reg = EventRegistration.objects.create(event=started, student=self.student.student_profile)
        resp = self.client.post(reverse("registration_cancel", args=[reg.pk]), follow=True)
        self.assertContains(resp, "already started")
        reg.refresh_from_db()
        self.assertEqual(reg.status, EventRegistration.Status.REGISTERED)

    def test_cannot_cancel_someone_elses_registration(self):
        reg = EventRegistration.objects.create(event=self.event, student=self.officer.student_profile)
        self.assertEqual(self.client.post(reverse("registration_cancel", args=[reg.pk])).status_code, 404)
        reg.refresh_from_db()
        self.assertEqual(reg.status, EventRegistration.Status.REGISTERED)

    def test_my_events_lists_only_own_registrations(self):
        EventRegistration.objects.create(event=self.event, student=self.student.student_profile)
        other = self.make_event(title="Officer only", venue=self.big_venue)
        EventRegistration.objects.create(event=other, student=self.officer.student_profile)
        resp = self.client.get(reverse("my_events"))
        self.assertContains(resp, self.event.title)
        self.assertNotContains(resp, "Officer only")

    def test_dashboard_shows_upcoming_registration(self):
        self.register()
        self.assertContains(self.client.get(reverse("member_dashboard")), self.event.title)


class OrganizerRegistrationTests(EventTestBase):
    def setUp(self):
        self.event = self.make_event(capacity=5)
        EventRegistration.objects.create(event=self.event, student=self.student.student_profile)

    def test_participant_list_and_search(self):  # F-07
        self.client.login(username="olivia", password=PASSWORD)
        url = reverse("event_participants", args=[self.event.pk])
        resp = self.client.get(url)
        self.assertContains(resp, "23-0002-002")
        self.assertContains(resp, "1 of 5 slots taken")
        self.assertNotContains(self.client.get(url, {"q": "nobody"}), "23-0002-002")
        self.assertContains(self.client.get(url, {"q": "0002"}), "23-0002-002")

    def test_students_cannot_see_participants(self):
        self.client.login(username="sam", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("event_participants", args=[self.event.pk])).status_code, 403)

    def test_event_with_registrations_cannot_be_deleted(self):  # BR-22
        self.client.login(username="olivia", password=PASSWORD)
        resp = self.client.post(reverse("event_delete", args=[self.event.pk]), follow=True)
        self.assertContains(resp, "cannot be deleted")
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    def test_capacity_cannot_drop_below_registrations(self):
        self.client.login(username="olivia", password=PASSWORD)
        EventRegistration.objects.create(event=self.event, student=self.officer.student_profile)
        data = self.form_data(capacity=1)
        for f in ("start_datetime", "end_datetime", "registration_deadline"):
            data[f] = timezone.localtime(getattr(self.event, f)).strftime("%Y-%m-%dT%H:%M")
        resp = self.client.post(reverse("event_edit", args=[self.event.pk]), data)
        self.assertIn("capacity", resp.context["form"].errors)


class StudentProfileTests(TestCase):
    def test_add_student_details_and_unique_number(self):
        make_user("ana", student_number="21-1111-111")
        make_user("ben")
        self.client.login(username="ben", password=PASSWORD)
        url = reverse("student_profile_edit")
        resp = self.client.post(url, {"student_number": "21-1111-111", "program": "bsit", "year_level": 2})
        self.assertIn("student_number", resp.context["form"].errors)
        resp = self.client.post(url, {"student_number": "21-2222-222", "program": "bsit", "year_level": 6})
        self.assertIn("year_level", resp.context["form"].errors)
        resp = self.client.post(url, {"student_number": "21-2222-222", "program": "bsit", "year_level": 2}, follow=True)
        self.assertContains(resp, "Student details saved.")
        profile = StudentProfile.objects.get(user__username="ben")
        self.assertEqual(profile.program, "BSIT")

    def test_admins_have_no_student_details_page(self):
        from accounts.models import User
        make_user("root", role=User.Role.ADMIN)
        self.client.login(username="root", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("student_profile_edit")).status_code, 403)
