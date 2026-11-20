from django.urls import path

from . import views

urlpatterns = [
    path("manage/", views.manage_events, name="manage_events"),
    path("manage/new/", views.event_create, name="event_create"),
    path("manage/<int:pk>/edit/", views.event_edit, name="event_edit"),
    path("manage/<int:pk>/cancel/", views.event_cancel, name="event_cancel"),
    path("manage/<int:pk>/delete/", views.event_delete, name="event_delete"),
]
