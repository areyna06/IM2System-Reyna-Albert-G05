from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    """Lets users log in with either their username or their email address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        User = get_user_model()
        username = username.strip()
        field = "email__iexact" if "@" in username else "username__iexact"
        try:
            user = User.objects.get(**{field: username})
        except User.DoesNotExist:
            # Run the hasher anyway so response time doesn't reveal which accounts exist.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
