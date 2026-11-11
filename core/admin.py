from django.contrib import admin

from .models import Business, StaffProfile


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "confidence_threshold", "created_at")
    readonly_fields = ("widget_key", "created_at")
    search_fields = ("name",)


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "business", "role")
    list_filter = ("business", "role")
