from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import StudentProfile, User

MAX_PHOTO_MB = 2


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email")

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.MEMBER  # Public sign-up can never create an Admin.
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Username or email", max_length=254)
    remember_me = forms.BooleanField(required=False, label="Remember me")

    error_messages = {
        "invalid_login": "Invalid username/email or password. Please try again.",
        "inactive": "This account has been deactivated.",
    }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "contact_number", "photo")
        widgets = {"photo": forms.ClearableFileInput(attrs={"accept": "image/*"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["contact_number"].widget.attrs["placeholder"] = "e.g. 0917 123 4567"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "size") and photo.size > MAX_PHOTO_MB * 1024 * 1024:
            raise forms.ValidationError(f"Photo must be {MAX_PHOTO_MB} MB or smaller.")
        return photo


class StudentProfileForm(forms.ModelForm):
    """Student number, program and year level, required before registering for events."""

    class Meta:
        model = StudentProfile
        fields = ("student_number", "program", "year_level")
        widgets = {"year_level": forms.Select(choices=[("", "Select year level")] + [(i, f"Year {i}") for i in range(1, 6)])}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student_number"].widget.attrs["placeholder"] = "e.g. 21-1234-567"
        self.fields["program"].widget.attrs["placeholder"] = "e.g. BSIT"

    def clean_student_number(self):
        number = self.cleaned_data["student_number"].strip()
        if StudentProfile.objects.filter(student_number=number).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This student number is already registered to another account.")
        return number

    def clean_program(self):
        return self.cleaned_data["program"].strip().upper()
