from .permissions import is_organizer


def nav(request):
    user = getattr(request, "user", None)
    return {"is_organizer": bool(user and is_organizer(user))}
