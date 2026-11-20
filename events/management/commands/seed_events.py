import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import StudentProfile
from events.models import Event, EventCategory, Organization, OrganizationMember, Venue

VENUES = [
    ("Main Auditorium", "Academic Building", "", 300),
    ("Audio-Visual Room 1", "Engineering Building", "EN-201", 80),
    ("Computer Lab 3", "IT Building", "IT-303", 40),
]
CATEGORIES = [
    ("Seminar", "Talks and lectures"),
    ("Workshop", "Hands-on sessions"),
    ("Orientation", "Introductions for new members and students"),
    ("Training", "Skills training"),
]
ORGS = [
    ("Information Technology Student Society", "ITSS", "Prof. Maria Santos"),
    ("Developers Circle", "DEVC", "Engr. Jose Ramos"),
]
# username, email, first, last, password env var, student number, program, year
STUDENTS = [
    ("officer", "officer@example.com", "Olivia", "Officer", "DEMO_OFFICER_PASSWORD", "21-0001-001", "BSIT", 3),
    ("student", "student@example.com", "Sam", "Student", "DEMO_STUDENT_PASSWORD", "23-0002-002", "BSCS", 2),
]


class Command(BaseCommand):
    help = "Create demo venues, categories, organizations, an officer, a student and sample events."

    def handle(self, *args, **options):
        User = get_user_model()
        venues = {}
        for name, building, room, cap in VENUES:
            venues[name], _ = Venue.objects.get_or_create(
                name=name, defaults={"building": building, "room_number": room, "capacity": cap}
            )
        cats = {}
        for name, desc in CATEGORIES:
            cats[name], _ = EventCategory.objects.get_or_create(name=name, defaults={"description": desc})
        orgs = {}
        for name, acronym, adviser in ORGS:
            orgs[acronym], _ = Organization.objects.get_or_create(
                acronym=acronym, defaults={"name": name, "adviser_name": adviser}
            )

        profiles = {}
        for username, email, first, last, env_name, number, program, year in STUDENTS:
            password = os.getenv(env_name)
            if not password:
                raise CommandError(f"Set {env_name} in your .env file first.")
            user, _ = User.objects.get_or_create(username=username, defaults={"email": email})
            user.email, user.first_name, user.last_name, user.role = email, first, last, User.Role.MEMBER
            user.set_password(password)
            user.save()
            profiles[username], _ = StudentProfile.objects.get_or_create(
                user=user, defaults={"student_number": number, "program": program, "year_level": year}
            )

        OrganizationMember.objects.update_or_create(
            organization=orgs["ITSS"], student=profiles["officer"],
            defaults={"position": "President", "member_role": OrganizationMember.Role.OFFICER, "is_active": True},
        )
        OrganizationMember.objects.get_or_create(
            organization=orgs["ITSS"], student=profiles["student"], defaults={"position": "Member"},
        )

        officer = profiles["officer"].user
        base = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0)
        samples = [
            ("Intro to Git and GitHub", "Workshop", "Computer Lab 3", 7, 3, 30,
             "Learn branching, pull requests and code review. Bring a laptop."),
            ("Freshmen IT Orientation", "Orientation", "Main Auditorium", 10, 2, 250,
             "Welcome program for first-year IT students: org officers, programs and campus tour."),
            ("Cybersecurity Awareness Seminar", "Seminar", "Audio-Visual Room 1", 14, 4, 2,
             "Guest speaker talk on phishing, passwords and safe browsing. Only 2 slots, for demoing a full event."),
        ]
        for title, cat, venue, days, hours, cap, desc in samples:
            start = base + timedelta(days=days)
            Event.objects.get_or_create(
                title=title, organization=orgs["ITSS"],
                defaults={
                    "category": cats[cat], "venue": venues[venue], "created_by": officer, "description": desc,
                    "start_datetime": start, "end_datetime": start + timedelta(hours=hours),
                    "registration_deadline": start - timedelta(days=1), "capacity": cap,
                    "status": Event.Status.OPEN,
                },
            )
        self.stdout.write(self.style.SUCCESS(
            "Seeded venues, categories, ITSS/DEVC, demo accounts 'officer' (ITSS officer) and 'student', and 3 open events."
        ))
