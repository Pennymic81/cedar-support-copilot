import secrets

from django.conf import settings
from django.db import models


def new_widget_key() -> str:
    return f"wk_{secrets.token_urlsafe(24)}"


class Business(models.Model):
    """A company using the copilot. Everything else belongs to one business."""

    name = models.CharField(max_length=200)
    widget_key = models.CharField(max_length=64, unique=True, default=new_widget_key)
    confidence_threshold = models.FloatField(
        null=True,
        blank=True,
        help_text="Minimum retrieval score to answer without a person. Blank = the provider's default.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "businesses"

    def __str__(self) -> str:
        return self.name

    @property
    def effective_threshold(self) -> float:
        if self.confidence_threshold is not None:
            return self.confidence_threshold
        return settings.DEFAULT_CONFIDENCE_THRESHOLD


class StaffProfile(models.Model):
    """Links a Django user to the business they support."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        AGENT = "agent", "Agent"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="staff")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.AGENT)

    def __str__(self) -> str:
        return f"{self.user} ({self.business}, {self.role})"
