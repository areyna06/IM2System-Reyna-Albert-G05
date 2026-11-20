# Student Organization Event Registration and Attendance System

IM2 project (CSIT327) by Albert Christian C. Reyna. A Django web app where students
browse and register for student-organization events, and organization officers
manage their events and see who registered. Data is stored in PostgreSQL (local or Supabase).

- **Project Development 1** – Account feature (registration, login/logout, role dashboards, profile)
- **Project Development 2** – Core feature: **Event Registration** (this increment)

## Core feature: Event Registration (PD2)

A full vertical slice — PostgreSQL tables → Django models/forms/views/URLs → templates.

| Who | What they can do | URL |
|---|---|---|
| Student (Member role) | Add student details (student number, program, year level) — required before registering | `/profile/student/` |
| Student | Browse open, upcoming events; search by title; filter by category, organization, venue and date | `/events/` |
| Student | View event details with schedule, venue and **remaining slots** | `/events/<id>/` |
| Student | **Register** for an event, **cancel** a registration, re-register later | buttons on the event page |
| Student | **My events** – own upcoming and past registrations | `/events/my/` |
| Officer (active officer of an organization) | **Create, edit, cancel and delete** their organization's events | `/events/manage/` |
| Officer | **Participant list** per event, searchable by name or student number | `/events/manage/<id>/participants/` |
| Admin | Everything officers can do, for every organization; manage organizations, members, venues and categories in Manage users (Django admin) | `/events/manage/`, `/django-admin/` |

### Business rules enforced (from the SDD)

| Rule | Where it is enforced |
|---|---|
| One registration per student per event (BR-15) | `UNIQUE (event, student)` + check in the view |
| Registrations never exceed capacity (BR-16) | Slot count checked inside a transaction with the event row locked (`select_for_update`) |
| Register only while the event is **Open** and before the deadline (BR-14) | View logic |
| Cancel only before the event starts; re-registering reactivates the same record (BR-18) | View logic |
| Event capacity > 0 and ≤ venue capacity (BR-09, BR-10) | `CHECK` constraint + form validation |
| Event ends after it starts; deadline on/before start (BR-11, BR-12) | `CHECK` constraints + form validation |
| Status values (BR-13, BR-17) | `CHECK` constraints |
| No overlapping events at the same venue (BR-23) | Form validation |
| Events with registrations can't be deleted, only cancelled (BR-22) | `ON DELETE PROTECT` + message |
| Only active officers of the organizing organization, or an Admin, manage its events (BR-08) | `events/permissions.py` — others get **403** |
| Students only see and cancel their **own** registrations | Queries filtered by the logged-in user (others get 404) |

Every form shows field errors and a "Please fix the errors below." message; every action shows a success or error message.

### Data model (follows the ERD)

```
User 1─1 StudentProfile 1─* OrganizationMember *─1 Organization
                       │                                │
                       └─1─* EventRegistration *─1 Event *─1 Organization
                                                     ├─*─1 Venue
                                                     ├─*─1 EventCategory
                                                     └─*─1 User (created_by)
```

Roles: every account is **Admin** or **Member** (student). An *organizer* is a Member
with an active **Officer** membership in an organization (`OrganizationMember.member_role = OFFICER`),
exactly as described in the SDD. Officers see **Manage events** on their dashboard and navigation bar.

## Standard features (PD1)

| Requirement | How it works |
|---|---|
| **Registration** | `/register/` — required fields, valid email, unique username and email, matching passwords, Django password rules. Passwords are hashed (PBKDF2). |
| **Login / Logout** | `/login/` accepts username **or** email. Logout is a POST. Optional "Remember me" (2 weeks). |
| **Role-based dashboards** | `/dashboard/` routes to `/dashboard/admin/` or `/dashboard/member/`. The other role's dashboard returns **403**. The member dashboard shows upcoming registrations and, for officers, organizer tools; the admin dashboard shows event and registration statistics. |
| **User profile** | `/profile/` (view), `/profile/edit/` (name, email, contact number, photo), `/profile/student/` (student details), `/profile/password/`. |

## Tech stack

- Python 3.13+, Django 5.2 (templates for the UI)
- PostgreSQL through `psycopg` 3 (Supabase works too)
- `python-dotenv` for secrets, `Pillow` for profile photos

## Setup

```powershell
git clone https://github.com/areyna06/IM2System-Reyna-Albert-G05.git
cd IM2System-Reyna-Albert-G05
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then fill in your own values
```

Create the database (local PostgreSQL):

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE DATABASE im2_db;"
```

For **Supabase**, skip that step: put the host, user, password and port from
*Project Settings → Database* into `.env` and set `DB_SSLMODE=require`.

Then:

```powershell
python manage.py migrate
python manage.py createsuperuser        # your Admin account
python manage.py create_demo_users      # demo admin + member (passwords from .env)
python manage.py seed_events            # venues, categories, 2 organizations, demo officer + student, 3 open events
python manage.py runserver
```

Open http://localhost:8000.

### Demo accounts

Created by the two commands above; passwords come from your `.env`.

| Username | Role | Use it to |
|---|---|---|
| `admin` | Admin | Admin dashboard, manage every organization's events, Manage users |
| `officer` | Member + ITSS officer | Create/edit/cancel/delete ITSS events, see participants |
| `student` | Member (student) | Browse, register, cancel, My events |
| `member` | Member without student details | See the "add student details first" rule |

### Try the core feature

1. Log in as `student` → **Events** → open *Cybersecurity Awareness Seminar* (2 slots) → **Register**. Slots drop to 1 of 2.
2. Open **My events** → **Cancel** → the slot is free again; register again to reactivate it.
3. Log in as `officer` → **Manage events** → **Participants** to see the student, or **+ New event** to add one
   (try an end time before the start, or a capacity above the venue's, to see the validation).

## Tests

```powershell
python manage.py test
```

71 tests: the 29 account tests from PD1, plus event-management permissions and business rules,
registration (duplicates, capacity, deadline, status, cancel and re-register, ownership),
participant list and student details.

## Branches

- `main` – stable releases only (merged from `develop` by pull request)
- `develop` – integration branch
- `feature/event-management` – event data model and officer event CRUD
- `feature/event-registration` – student details, browsing, registration, cancellation, My events, participants
- `feature/pd2-docs` – PD2 completion report

## Project layout

```
config/            settings (reads .env), root URLs
accounts/          User + StudentProfile models, auth/profile forms and views, role_required decorator
events/            Organization, OrganizationMember, Venue, EventCategory, Event, EventRegistration;
                   permissions (BR-08), forms, views, seed_events command, tests
templates/         base layout, accounts pages, events pages, partials
static/css/app.css styling
docs/              Project Development reports
```

## Secrets

`.env` holds the secret key and database credentials and is listed in `.gitignore`,
along with `venv/`, `__pycache__/` and uploaded `media/`. Only `.env.example`
(with placeholder values) is committed.
