from django.contrib import admin

from .models import Event, EventCategory, EventRegistration, Organization, OrganizationMember, Venue


class MemberInline(admin.TabularInline):
    model = OrganizationMember
    extra = 1
    autocomplete_fields = ("student",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("acronym", "name", "adviser_name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "acronym")
    inlines = [MemberInline]


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = ("student", "organization", "position", "member_role", "is_active")
    list_filter = ("organization", "member_role", "is_active")
    autocomplete_fields = ("student",)


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ("name", "building", "room_number", "capacity", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "building")


@admin.register(EventCategory)
class EventCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "organization", "venue", "start_datetime", "capacity", "status")
    list_filter = ("status", "organization", "category")
    search_fields = ("title",)


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = ("event", "student", "status", "registered_at", "cancelled_at")
    list_filter = ("status", "event__organization")
    search_fields = ("event__title", "student__student_number", "student__user__last_name")
