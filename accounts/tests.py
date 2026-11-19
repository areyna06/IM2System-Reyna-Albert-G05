import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

User = get_user_model()
PASSWORD = "Str0ng-Passw0rd!"


def make_user(username, role=User.Role.MEMBER, email=None):
    return User.objects.create_user(
        username=username,
        email=email or f"{username}@example.com",
        password=PASSWORD,
        first_name=username.title(),
        last_name="Tester",
        role=role,
    )


def register_data(**overrides):
    data = {
        "first_name": "Juan",
        "last_name": "Dela Cruz",
        "username": "juan",
        "email": "juan@example.com",
        "password1": PASSWORD,
        "password2": PASSWORD,
    }
    data.update(overrides)
    return data


class RegistrationTests(TestCase):
    def test_register_success_hashes_password_and_sets_member_role(self):
        resp = self.client.post(reverse("register"), register_data(), follow=True)
        self.assertRedirects(resp, reverse("login"))
        self.assertContains(resp, "Account created for juan")
        user = User.objects.get(username="juan")
        self.assertEqual(user.role, User.Role.MEMBER)
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        self.assertTrue(user.check_password(PASSWORD))

    def test_required_fields(self):
        resp = self.client.post(reverse("register"), {})
        self.assertEqual(resp.status_code, 200)
        form = resp.context["form"]
        for field in ("first_name", "last_name", "username", "email", "password1", "password2"):
            self.assertIn(field, form.errors)
        self.assertContains(resp, "Please fix the errors below.")
        self.assertEqual(User.objects.count(), 0)

    def test_invalid_email_format(self):
        resp = self.client.post(reverse("register"), register_data(email="not-an-email"))
        self.assertIn("email", resp.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)

    def test_duplicate_username_case_insensitive(self):
        make_user("juan")
        resp = self.client.post(reverse("register"), register_data(username="JUAN", email="other@example.com"))
        self.assertContains(resp, "That username is already taken.")
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_email_case_insensitive(self):
        make_user("someone", email="juan@example.com")
        resp = self.client.post(reverse("register"), register_data(email="JUAN@Example.com"))
        self.assertContains(resp, "An account with this email already exists.")
        self.assertEqual(User.objects.count(), 1)

    def test_password_confirmation_must_match(self):
        resp = self.client.post(reverse("register"), register_data(password2="Different-Pass9!"))
        self.assertIn("password2", resp.context["form"].errors)
        self.assertEqual(User.objects.count(), 0)

    def test_cannot_self_register_as_admin(self):
        self.client.post(reverse("register"), register_data(role="ADMIN"))
        self.assertEqual(User.objects.get(username="juan").role, User.Role.MEMBER)


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.member = make_user("maria")
        self.admin = make_user("boss", role=User.Role.ADMIN)

    def test_login_with_username_goes_to_member_dashboard(self):
        resp = self.client.post(reverse("login"), {"username": "maria", "password": PASSWORD}, follow=True)
        self.assertRedirects(resp, reverse("member_dashboard"))

    def test_login_with_email_goes_to_admin_dashboard(self):
        resp = self.client.post(reverse("login"), {"username": "BOSS@example.com", "password": PASSWORD}, follow=True)
        self.assertRedirects(resp, reverse("admin_dashboard"))

    def test_invalid_credentials_show_error(self):
        resp = self.client.post(reverse("login"), {"username": "maria", "password": "wrong"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid username/email or password.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_user_shows_error(self):
        resp = self.client.post(reverse("login"), {"username": "ghost", "password": PASSWORD})
        self.assertContains(resp, "Invalid username/email or password.")

    def test_logout_ends_session(self):
        self.client.force_login(self.member)
        resp = self.client.post(reverse("logout"), follow=True)
        self.assertRedirects(resp, reverse("login"))
        self.assertContains(resp, "You have been logged out.")
        self.assertNotIn("_auth_user_id", self.client.session)
        resp = self.client.get(reverse("member_dashboard"))
        self.assertRedirects(resp, f"{reverse('login')}?next={reverse('member_dashboard')}")

    def test_logged_in_user_visiting_login_or_register_is_redirected(self):
        self.client.force_login(self.member)
        self.assertRedirects(self.client.get(reverse("login")), reverse("dashboard"), target_status_code=302)
        self.assertRedirects(self.client.get(reverse("register")), reverse("dashboard"), target_status_code=302)


class ProtectedPageTests(TestCase):
    def test_logged_out_users_are_sent_to_login(self):
        for name in ("dashboard", "admin_dashboard", "member_dashboard", "profile", "profile_edit", "password_change"):
            url = reverse(name)
            resp = self.client.get(url)
            self.assertRedirects(resp, f"{reverse('login')}?next={url}", msg_prefix=name)


class RoleDashboardTests(TestCase):
    def setUp(self):
        self.member = make_user("maria")
        self.admin = make_user("boss", role=User.Role.ADMIN)

    def test_member_cannot_open_admin_dashboard(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(resp.status_code, 403)
        self.assertContains(resp, "Access denied", status_code=403)

    def test_admin_cannot_open_member_dashboard(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("member_dashboard")).status_code, 403)

    def test_member_cannot_open_django_admin(self):
        self.client.force_login(self.member)
        resp = self.client.get("/django-admin/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/django-admin/login/", resp["Location"])

    def test_each_dashboard_shows_role_content(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_dashboard"))
        self.assertContains(resp, "Admin dashboard")
        self.assertContains(resp, "Recent sign-ups")
        self.assertContains(resp, "Manage users")

        self.client.force_login(self.member)
        resp = self.client.get(reverse("member_dashboard"))
        self.assertContains(resp, "Profile completeness")
        self.assertNotContains(resp, "Manage users")

    def test_dashboard_router(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("admin_dashboard"))
        self.client.force_login(self.member)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("member_dashboard"))

    def test_superuser_is_always_admin(self):
        su = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        self.assertEqual(su.role, User.Role.ADMIN)

    def test_role_controls_user_management_access(self):
        self.assertTrue(self.admin.is_staff and self.admin.is_superuser)
        self.assertFalse(self.member.is_staff or self.member.is_superuser)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/django-admin/accounts/user/").status_code, 200)
        # Demoting an Admin to Member removes access.
        self.admin.role = User.Role.MEMBER
        self.admin.save()
        self.assertFalse(self.admin.is_staff or self.admin.is_superuser)
        self.assertEqual(self.client.get("/django-admin/accounts/user/").status_code, 302)


@override_settings(MEDIA_ROOT="test_media_tmp")
class ProfileTests(TestCase):
    def setUp(self):
        self.user = make_user("maria")
        self.other = make_user("pedro")
        self.client.force_login(self.user)

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree("test_media_tmp", ignore_errors=True)
        super().tearDownClass()

    def edit_data(self, **overrides):
        data = {"first_name": "Maria", "last_name": "Clara", "email": "maria@example.com", "contact_number": "0917 123 4567"}
        data.update(overrides)
        return data

    def test_profile_shows_only_own_data(self):
        resp = self.client.get(reverse("profile"))
        self.assertContains(resp, "maria@example.com")
        self.assertNotContains(resp, "pedro@example.com")

    def test_update_profile(self):
        resp = self.client.post(reverse("profile_edit"), self.edit_data(), follow=True)
        self.assertRedirects(resp, reverse("profile"))
        self.assertContains(resp, "Profile updated.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, "Clara")
        self.assertEqual(self.user.contact_number, "0917 123 4567")

    def test_update_only_touches_own_account(self):
        # Even if someone injects another user's id, the form edits request.user only.
        self.client.post(reverse("profile_edit"), self.edit_data(id=self.other.pk, username="hacked"))
        self.other.refresh_from_db()
        self.assertEqual(self.other.username, "pedro")
        self.assertEqual(self.other.last_name, "Tester")

    def test_cannot_take_another_users_email(self):
        resp = self.client.post(reverse("profile_edit"), self.edit_data(email="PEDRO@example.com"))
        self.assertContains(resp, "Another account already uses this email.")

    def test_invalid_contact_number(self):
        resp = self.client.post(reverse("profile_edit"), self.edit_data(contact_number="call me"))
        self.assertIn("contact_number", resp.context["form"].errors)

    def test_upload_photo(self):
        buf = io.BytesIO()
        Image.new("RGB", (40, 40), "blue").save(buf, "PNG")
        photo = SimpleUploadedFile("me.png", buf.getvalue(), content_type="image/png")
        resp = self.client.post(reverse("profile_edit"), {**self.edit_data(), "photo": photo}, follow=True)
        self.assertContains(resp, "Profile updated.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.photo.name.startswith("profile_photos/"))

    def test_reject_non_image_upload(self):
        fake = SimpleUploadedFile("evil.png", b"not an image", content_type="image/png")
        resp = self.client.post(reverse("profile_edit"), {**self.edit_data(), "photo": fake})
        self.assertIn("photo", resp.context["form"].errors)

    def test_change_password(self):
        resp = self.client.post(
            reverse("password_change"),
            {"old_password": PASSWORD, "new_password1": "An0ther-Str0ng!", "new_password2": "An0ther-Str0ng!"},
            follow=True,
        )
        self.assertContains(resp, "Password changed.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("An0ther-Str0ng!"))
