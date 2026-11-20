from django.urls import path

from . import views

urlpatterns = [
    # Students
    path("", views.event_list, name="event_list"),
    path("<int:pk>/", views.event_detail, name="event_detail"),
    path("<int:pk>/register/", views.event_register, name="event_register"),
    path("registrations/<int:pk>/cancel/", views.registration_cancel, name="registration_cancel"),
    path("my/", views.my_events, name="my_events"),
    # Organizers (active officers and admins)
    path("manage/", views.manage_events, name="manage_events"),
    path("manage/new/", views.event_create, name="event_create"),
    path("manage/<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("manage/<int:pk>/cancel/", views.event_cancel, name="event_cancel"),
    path("manage/<int:pk>/delete/", views.event_delete, name="event_delete"),
    path("manage/<int:pk>/participants/", views.event_participants, name="event_participants"),
]
