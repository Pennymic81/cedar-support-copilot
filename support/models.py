import secrets

from django.conf import settings
from django.db import models

from core.models import Business
from knowledge.models import Chunk


def new_conversation_token() -> str:
    return secrets.token_urlsafe(24)


class Conversation(models.Model):
    """One chat session started by a customer in the widget."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ESCALATED = "escalated", "Handed to a person"
        RESOLVED = "resolved", "Resolved"

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="conversations")
    customer_ref = models.CharField(max_length=200, blank=True, help_text="Anonymous id or email")
    token = models.CharField(
        max_length=64, unique=True, default=new_conversation_token,
        help_text="Secret the widget uses to continue or read this chat",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Conversation {self.pk} ({self.get_status_display()})"


class Message(models.Model):
    class Sender(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        AI = "ai", "AI"
        AGENT = "agent", "Agent"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=10, choices=Sender.choices)
    content = models.TextField()
    confidence = models.FloatField(null=True, blank=True, help_text="Set on AI messages only")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="messages", help_text="The agent who sent it (agent messages only)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender}: {self.content[:40]}"


class MessageCitation(models.Model):
    """Which chunks an AI answer was based on, with their retrieval scores."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="citations")
    chunk = models.ForeignKey(Chunk, on_delete=models.CASCADE, related_name="citations")
    score = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "chunk"], name="unique_citation"),
        ]


class Ticket(models.Model):
    """The human handoff queue."""

    class Reason(models.TextChoices):
        LOW_CONFIDENCE = "low_confidence", "Low confidence"
        CUSTOMER_REQUESTED = "customer_requested", "Customer asked for a person"
        SENSITIVE = "sensitive", "Involves the customer's money or account"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In progress"
        CLOSED = "closed", "Closed"

    conversation = models.OneToOneField(Conversation, on_delete=models.CASCADE, related_name="ticket")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="tickets")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="tickets"
    )
    class DraftOutcome(models.TextChoices):
        APPROVED = "approved", "Sent as drafted"
        EDITED = "edited", "Edited before sending"
        WRITTEN = "written", "Agent wrote their own"

    reason = models.CharField(max_length=20, choices=Reason.choices)
    reason_detail = models.CharField(max_length=40, blank=True, help_text="e.g. which money-safety rule matched")
    summary = models.TextField(blank=True)
    suggested_reply = models.TextField(blank=True, help_text="AI draft the agent can approve or edit")
    draft_sources = models.ManyToManyField(Chunk, blank=True, related_name="drafts")
    draft_grounded = models.BooleanField(default=False, help_text="True if the draft is based on a matching policy")
    draft_outcome = models.CharField(max_length=10, choices=DraftOutcome.choices, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Ticket {self.pk}: {self.get_reason_display()}"
