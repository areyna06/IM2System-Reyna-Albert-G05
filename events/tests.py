from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentProfile

from .models import Event, EventCategory, Organization, OrganizationMember, Venue

User = get_user_model()
PASSWORD = "Str0ng-Passw0rd!"
FMT = "%Y-%m-%dT%H:%M"


def make_user(username, role=User.Role.MEMBER, student_number=None):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com", password=PASSWORD,
        first_name=username.title(), last_name="Tester", role=role,
    )
    if student_number:
        StudentProfile.objects.create(user=user, student_number=student_number, program="BSIT", year_level=2)
    return user


class EventTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organization.objects.create(name="IT Student Society", acronym="ITSS")
        cls.other_org = Organization.objects.create(name="Developers Circle", acronym="DEVC")
        cls.venue = Venue.objects.create(name="Lab 3", building="IT", capacity=40)
        cls.big_venue = Venue.objects.create(name="Auditorium", building="Main", capacity=300)
        cls.category = EventCategory.objects.create(name="Workshop")
        cls.admin = make_user("boss", role=User.Role.ADMIN)
        cls.officer = make_user("olivia", student_number="21-0001-001")
        cls.student = make_user("sam", student_number="23-0002-002")
        OrganizationMember.objects.create(
            organization=cls.org, student=cls.officer.student_profile,
            position="President", member_role=OrganizationMember.Role.OFFICER,
        )
        OrganizationMember.objects.create(organization=cls.org, student=cls.student.student_profile, position="Member")

    def make_event(self, org=None, venue=None, days=7, capacity=10, status=Event.Status.OPEN, **kw):
        start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=days)
        return Event.objects.create(
            organization=org or self.org, category=self.category, venue=venue or self.venue,
            created_by=self.officer, title=kw.pop("title", "Git Workshop"), description="Hands-on.",
            start_datetime=start, end_datetime=start + timedelta(hours=2),
            registration_deadline=kw.pop("deadline", start - timedelta(hours=1)),
            capacity=capacity, status=status, **kw,
        )

    def form_data(self, days=7, hours=2, deadline_hours=-1, **overrides):
        start = timezone.localtime() + timedelta(days=days)
        data = {
            "organization": self.org.pk, "title": "Intro to Django", "category": self.category.pk,
            "venue": self.venue.pk, "description": "Build your first app.",
            "start_datetime": start.strftime(FMT),
            "end_datetime": (start + timedelta(hours=hours)).strftime(FMT),
            "registration_deadline": (start + timedelta(hours=deadline_hours)).strftime(FMT),
            "capacity": 30, "status": Event.Status.OPEN,
        }
        data.update(overrides)
        return data


class EventManagementAccessTests(EventTestBase):
    def test_logged_out_redirects_to_login(self):
        resp = self.client.get(reverse("manage_events"))
        self.assertRedirects(resp, f"{reverse('login')}?next={reverse('manage_events')}")

    def test_plain_student_gets_403(self):
        self.client.login(username="sam", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("manage_events")).status_code, 403)
        self.assertEqual(self.client.get(reverse("event_create")).status_code, 403)

    def test_officer_and_admin_can_open_manage_page(self):
        for username in ("olivia", "boss"):
            self.client.login(username=username, password=PASSWORD)
            self.assertEqual(self.client.get(reverse("manage_events")).status_code, 200)

    def test_inactive_officer_membership_loses_access(self):
        OrganizationMember.objects.filter(student=self.officer.student_profile).update(is_active=False)
        self.client.login(username="olivia", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("manage_events")).status_code, 403)

    def test_officer_cannot_touch_other_organizations_event(self):
        event = self.make_event(org=self.other_org)
        self.client.login(username="olivia", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("event_edit", args=[event.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("event_cancel", args=[event.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("event_delete", args=[event.pk])).status_code, 403)
        self.assertTrue(Event.objects.filter(pk=event.pk, status=Event.Status.OPEN).exists())

    def test_officer_only_sees_own_organization_events(self):
        self.make_event(title="Ours")
        self.make_event(org=self.other_org, venue=self.big_venue, title="Theirs")
        self.client.login(username="olivia", password=PASSWORD)
        resp = self.client.get(reverse("manage_events"))
        self.assertContains(resp, "Ours")
        self.assertNotContains(resp, "Theirs")

    def test_manage_link_only_on_organizer_dashboard(self):
        self.client.login(username="olivia", password=PASSWORD)
        self.assertContains(self.client.get(reverse("member_dashboard")), reverse("manage_events"))
        self.client.login(username="sam", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("member_dashboard")), reverse("manage_events"))


class EventCrudTests(EventTestBase):
    def setUp(self):
        self.client.login(username="olivia", password=PASSWORD)

    def test_create_event_saves_and_links_creator(self):
        resp = self.client.post(reverse("event_create"), self.form_data(), follow=True)
        self.assertRedirects(resp, reverse("manage_events"))
        self.assertContains(resp, "created.")
        event = Event.objects.get(title="Intro to Django")
        self.assertEqual(event.created_by, self.officer)
        self.assertEqual(event.organization, self.org)

    def test_required_fields(self):
        resp = self.client.post(reverse("event_create"), {})
        form = resp.context["form"]
        for f in ("organization", "title", "category", "venue", "description",
                  "start_datetime", "end_datetime", "registration_deadline", "capacity"):
            self.assertIn(f, form.errors)
        self.assertContains(resp, "Please fix the errors below.")
        self.assertFalse(Event.objects.exists())

    def test_officer_cannot_create_for_other_organization(self):
        resp = self.client.post(reverse("event_create"), self.form_data(organization=self.other_org.pk))
        self.assertIn("organization", resp.context["form"].errors)

    def test_business_rules(self):
        cases = [
            (self.form_data(hours=-1), "end_datetime"),                   # BR-11
            (self.form_data(deadline_hours=1), "registration_deadline"),  # BR-12
            (self.form_data(capacity=41), "capacity"),                    # BR-10
            (self.form_data(capacity=0), "capacity"),                     # BR-09
            (self.form_data(days=-1), "start_datetime"),                  # must be in the future
        ]
        for data, field in cases:
            with self.subTest(field=field):
                resp = self.client.post(reverse("event_create"), data)
                self.assertIn(field, resp.context["form"].errors)
        self.assertFalse(Event.objects.exists())

    def test_venue_overlap_rejected_unless_cancelled(self):  # BR-23
        existing = self.make_event(days=7)
        start = timezone.localtime(existing.start_datetime) + timedelta(minutes=30)
        data = self.form_data(
            start_datetime=start.strftime(FMT),
            end_datetime=(start + timedelta(hours=2)).strftime(FMT),
            registration_deadline=(start - timedelta(hours=2)).strftime(FMT),
        )
        resp = self.client.post(reverse("event_create"), data)
        self.assertIn("venue", resp.context["form"].errors)
        existing.status = Event.Status.CANCELLED
        existing.save()
        resp = self.client.post(reverse("event_create"), data)
        self.assertEqual(resp.status_code, 302)

    def test_edit_event(self):
        event = self.make_event()
        self.assertEqual(self.client.get(reverse("event_edit", args=[event.pk])).status_code, 200)
        data = self.form_data(title="Renamed workshop")
        data["start_datetime"] = timezone.localtime(event.start_datetime).strftime(FMT)
        data["end_datetime"] = timezone.localtime(event.end_datetime).strftime(FMT)
        data["registration_deadline"] = timezone.localtime(event.registration_deadline).strftime(FMT)
        resp = self.client.post(reverse("event_edit", args=[event.pk]), data, follow=True)
        self.assertContains(resp, "updated")
        event.refresh_from_db()
        self.assertEqual(event.title, "Renamed workshop")

    def test_cancel_event(self):
        event = self.make_event()
        self.assertEqual(self.client.get(reverse("event_cancel", args=[event.pk])).status_code, 405)
        resp = self.client.post(reverse("event_cancel", args=[event.pk]), follow=True)
        self.assertContains(resp, "was cancelled")
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CANCELLED)
        resp = self.client.get(reverse("event_edit", args=[event.pk]), follow=True)
        self.assertContains(resp, "can no longer be edited")

    def test_delete_event_without_registrations(self):
        event = self.make_event()
        self.assertContains(self.client.get(reverse("event_delete", args=[event.pk])), "Delete event?")
        resp = self.client.post(reverse("event_delete", args=[event.pk]), follow=True)
        self.assertContains(resp, "deleted")
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_admin_can_manage_any_organization(self):
        event = self.make_event(org=self.other_org)
        self.client.login(username="boss", password=PASSWORD)
        self.assertEqual(self.client.get(reverse("event_edit", args=[event.pk])).status_code, 200)
        resp = self.client.post(reverse("event_create"), self.form_data(organization=self.other_org.pk, days=9))
        self.assertEqual(resp.status_code, 302)
