from django.contrib import admin

from .models import Conversation, Message, MessageCitation, Ticket


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("sender", "content", "confidence", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "business", "customer_ref", "status", "created_at")
    list_filter = ("business", "status")
    inlines = [MessageInline]


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "business", "reason", "reason_detail", "status", "assigned_to", "draft_outcome", "created_at")
    list_filter = ("business", "reason", "status", "draft_outcome")
    readonly_fields = ("summary", "suggested_reply", "draft_grounded", "draft_outcome", "created_at", "closed_at")
    filter_horizontal = ("draft_sources",)


@admin.register(MessageCitation)
class MessageCitationAdmin(admin.ModelAdmin):
    list_display = ("message", "chunk", "score")
