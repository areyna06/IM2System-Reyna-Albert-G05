from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from events.models import Event, EventRegistration, Organization, sync_event_statuses

from .decorators import role_required
from .forms import LoginForm, ProfileForm, RegistrationForm, StudentProfileForm
from .models import StudentProfile, User


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Account created for {user.username}. You can now log in.")
            return redirect("login")
        messages.error(request, "Please fix the errors below.")
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(60 * 60 * 24 * 14)  # two weeks
        messages.success(self.request, f"Welcome back, {self.request.user.first_name or self.request.user.username}!")
        return response


class LogoutView(auth_views.LogoutView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "You have been logged out.")
        return response


@login_required
def dashboard(request):
    """Send each user to the dashboard for their role."""
    return redirect(request.user.dashboard_url_name)


@role_required(User.Role.ADMIN)
def admin_dashboard(request):
    sync_event_statuses()
    users = User.objects.order_by("-date_joined")
    context = {
        "total_users": users.count(),
        "admin_count": users.filter(role=User.Role.ADMIN).count(),
        "member_count": users.filter(role=User.Role.MEMBER).count(),
        "recent_users": users[:10],
        "event_count": Event.objects.exclude(status=Event.Status.CANCELLED).count(),
        "open_event_count": Event.objects.filter(status=Event.Status.OPEN).count(),
        "organization_count": Organization.objects.filter(is_active=True).count(),
        "registration_count": EventRegistration.objects.filter(status=EventRegistration.Status.REGISTERED).count(),
    }
    return render(request, "accounts/admin_dashboard.html", context)


@role_required(User.Role.MEMBER)
def member_dashboard(request):
    sync_event_statuses()
    user = request.user
    checks = [user.first_name, user.last_name, user.email, user.contact_number, user.photo]
    completeness = round(100 * sum(bool(c) for c in checks) / len(checks))
    upcoming = (
        EventRegistration.objects.filter(
            student__user=user, status=EventRegistration.Status.REGISTERED, event__end_datetime__gte=timezone.now()
        )
        .exclude(event__status=Event.Status.CANCELLED)
        .select_related("event", "event__venue")
        .order_by("event__start_datetime")
    )
    return render(request, "accounts/member_dashboard.html", {
        "completeness": completeness,
        "upcoming": upcoming[:3],
        "upcoming_count": upcoming.count(),
        "open_events": Event.objects.filter(status=Event.Status.OPEN, registration_deadline__gte=timezone.now()).count(),
        "has_student_profile": StudentProfile.objects.filter(user=user).exists(),
    })


@login_required
def profile(request):
    # No user id in the URL: everyone can only ever see their own profile.
    student = StudentProfile.objects.filter(user=request.user).first()
    return render(request, "accounts/profile.html", {"profile_user": request.user, "student": student})


@role_required(User.Role.MEMBER)
def student_profile_edit(request):
    """Add or update the student details needed to register for events."""
    student = StudentProfile.objects.filter(user=request.user).first()
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = ""
    if request.method == "POST":
        form = StudentProfileForm(request.POST, instance=student)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            messages.success(request, "Student details saved.")
            return redirect(next_url or "profile")
        messages.error(request, "Please fix the errors below.")
    else:
        form = StudentProfileForm(instance=student)
    return render(request, "accounts/student_profile_edit.html", {"form": form, "next": next_url})


@login_required
def profile_edit(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")
        messages.error(request, "Please fix the errors below.")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile_edit.html", {"form": form})


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("profile")

    def form_valid(self, form):
        messages.success(self.request, "Password changed.")
        return super().form_valid(form)
