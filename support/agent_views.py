"""The agent inbox: tickets the copilot handed to a person."""
from django.contrib.auth import get_user_model
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from core.permissions import IsBusinessStaff, business_for

from .models import Ticket
from .serializers import AgentReplySerializer, TicketDetailSerializer, TicketListSerializer
from .services.analytics import summary
from .services.agent import AgentActionError, close_ticket, send_reply
from .services.drafts import draft_for_ticket


class TicketViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """List with ?status=pending|in_progress|closed and ?mine=true. Oldest first, so nobody waits longest."""

    permission_classes = [IsBusinessStaff]

    def get_serializer_class(self):
        return TicketListSerializer if self.action == "list" else TicketDetailSerializer

    def get_queryset(self):
        qs = (
            Ticket.objects.filter(business=business_for(self.request))
            .select_related("conversation", "assigned_to")
            .prefetch_related("draft_sources__document")
        )
        if s := self.request.query_params.get("status"):
            qs = qs.filter(status=s)
        if self.request.query_params.get("mine") == "true":
            qs = qs.filter(assigned_to=self.request.user)
        return qs.order_by("created_at")

    def _detail(self, ticket):
        return Response(TicketDetailSerializer(self.get_queryset().get(pk=ticket.pk)).data)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Assign to yourself, or to {"user_id": n} in the same business."""
        ticket = self.get_object()
        user = request.user
        if "user_id" in request.data:
            user = get_user_model().objects.filter(
                pk=request.data["user_id"], staff__business=business_for(request)
            ).first()
            if user is None:
                return Response({"detail": "That user isn't on your team."}, status=status.HTTP_400_BAD_REQUEST)
        ticket.assigned_to = user
        if ticket.status == Ticket.Status.PENDING:
            ticket.status = Ticket.Status.IN_PROGRESS
        ticket.save(update_fields=["assigned_to", "status"])
        return self._detail(ticket)

    @action(detail=True, methods=["post"])
    def reply(self, request, pk=None):
        """Send a reply to the customer: {"use_draft": true} sends the suggestion as is,
        {"content": "..."} sends your own or edited text. Add "close": true to resolve the chat."""
        ticket = self.get_object()
        body = AgentReplySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            send_reply(ticket, request.user, data.get("content", ""), data["use_draft"], data["close"])
        except AgentActionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self._detail(ticket)

    @action(detail=True, methods=["post"])
    def redraft(self, request, pk=None):
        """Regenerate the summary and suggested reply (e.g. after the customer added details)."""
        ticket = draft_for_ticket(self.get_object())
        return self._detail(ticket)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """Resolve: the chat goes back to the AI if the customer writes again."""
        ticket = self.get_object()
        close_ticket(ticket)
        return self._detail(ticket)


@api_view(["GET"])
@permission_classes([IsBusinessStaff])
def analytics(request):
    """Dashboard metrics for the last ?days=30 (1-365)."""
    try:
        days = min(max(int(request.query_params.get("days", 30)), 1), 365)
    except ValueError:
        days = 30
    return Response(summary(business_for(request), days))
