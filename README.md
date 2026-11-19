# IM2 System — Account Feature

Project Development 1 for IM2: the Account Feature of a full-stack Django app
(Django templates for the frontend, PostgreSQL for the database).

> "IM2 System" is a placeholder name. Change `SITE_NAME` in `.env` to rename it everywhere.

## Features

| Requirement | How it works |
|---|---|
| **Registration** | `/register/` — required fields, valid email format, unique username and email (case-insensitive), matching password confirmation, Django password strength rules. Passwords are hashed by Django (PBKDF2). Success and error messages are shown. |
| **Login / Logout** | `/login/` accepts a username **or** email. Wrong credentials show an error. Logout (`POST /logout/`) ends the session. Optional "Remember me" keeps the session for 2 weeks; otherwise it ends when the browser closes. |
| **Protected pages** | All dashboard and profile pages use `@login_required`; logged-out visitors go to the login page with a `?next=` link back. |
| **Role-based dashboards** | Two roles: **Admin** and **Member**. `/dashboard/` routes each user to their own dashboard. `/dashboard/admin/` shows user statistics, recent sign-ups and user management; `/dashboard/member/` shows profile completeness and account details. Opening the other role's dashboard by URL returns **403 Access denied**. |
| **User profile** | `/profile/` shows the logged-in user's own details; `/profile/edit/` updates name, email, contact number and profile photo; `/profile/password/` changes the password. URLs contain no user ID, so users can only ever see and edit their own profile. |

Public sign-up always creates a **Member**. Admins are created with `createsuperuser`
or by an existing Admin in **Manage users** (the Django admin at `/django-admin/`).
A user's role controls their access to Manage users.

## Tech stack

- Python 3.13, Django 5.2 (templates for the UI)
- PostgreSQL 17 through `psycopg` 3 (Supabase works too; it is PostgreSQL)
- `python-dotenv` for secrets, `Pillow` for profile photos

## Setup

```powershell
git clone <this-repo-url>
cd <repo-folder>
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then fill in your own values
```

Create the database (local PostgreSQL):

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "CREATE DATABASE im2_db;"
```

For **Supabase**, skip that step: put the host, user, password and port from
*Project Settings → Database* into `.env` and set `DB_SSLMODE=require`.

Then:

```powershell
python manage.py migrate
python manage.py createsuperuser        # your Admin account
python manage.py create_demo_users      # optional: demo admin + member (passwords from .env)
python manage.py runserver
```

Open http://localhost:8000.

## Tests

```powershell
python manage.py test accounts
```

29 tests cover registration validation, password hashing, login/logout,
protected pages, role access (including typing the other role's URL),
and profile viewing, editing, photo upload and password change.

## Project layout

```
config/            settings (reads .env), root URLs
accounts/          custom User model (role, contact number, photo), forms, views,
                   role_required decorator, username-or-email login backend, tests
templates/         base layout, auth pages, dashboards, profile pages, 403/404
static/css/app.css styling
```

## Secrets

`.env` holds the secret key and database credentials and is listed in `.gitignore`,
along with `venv/`, `__pycache__/` and uploaded `media/`. Only `.env.example`
(with placeholder values) is committed.
