"""The agent inbox: tickets the copilot handed to a person."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import IsBusinessStaff, business_for

from .models import Conversation, Message, Ticket
from .serializers import AgentReplySerializer, TicketDetailSerializer, TicketListSerializer
from .services.drafts import NO_POLICY_DRAFT, draft_for_ticket


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
        if ticket.status == Ticket.Status.CLOSED:
            return Response({"detail": "This ticket is closed."}, status=status.HTTP_400_BAD_REQUEST)
        body = AgentReplySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data

        if data["use_draft"] and not data.get("content"):
            if not ticket.draft_grounded or ticket.suggested_reply == NO_POLICY_DRAFT:
                return Response(
                    {"detail": "There's no policy-based draft for this ticket; write the reply yourself."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            content, outcome = ticket.suggested_reply, Ticket.DraftOutcome.APPROVED
        else:
            content = data["content"]
            outcome = (
                Ticket.DraftOutcome.EDITED
                if ticket.draft_grounded and data["use_draft"]
                else Ticket.DraftOutcome.WRITTEN
            )

        with transaction.atomic():
            Message.objects.create(
                conversation=ticket.conversation, sender=Message.Sender.AGENT, content=content, author=request.user
            )
            if ticket.assigned_to is None:
                ticket.assigned_to = request.user
            ticket.status = Ticket.Status.IN_PROGRESS
            if not ticket.draft_outcome:
                ticket.draft_outcome = outcome
            ticket.save(update_fields=["assigned_to", "status", "draft_outcome"])
            if data["close"]:
                self._close(ticket)
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
        with transaction.atomic():
            self._close(ticket)
        return self._detail(ticket)

    @staticmethod
    def _close(ticket):
        ticket.status = Ticket.Status.CLOSED
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=["status", "closed_at"])
        convo = ticket.conversation
        convo.status = Conversation.Status.RESOLVED
        convo.save(update_fields=["status"])
