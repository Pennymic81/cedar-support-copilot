"""What an agent can do with a ticket. Shared by the API and the Inbox page."""
from django.db import transaction
from django.utils import timezone

from support.models import Conversation, Message, Ticket

from .drafts import NO_POLICY_DRAFT


class AgentActionError(Exception):
    pass


def has_policy_draft(ticket: Ticket) -> bool:
    return ticket.draft_grounded and ticket.suggested_reply != NO_POLICY_DRAFT


def send_reply(ticket: Ticket, user, content: str = "", use_draft: bool = False, close: bool = False) -> Message:
    """Send an agent reply. use_draft with no content sends the suggestion as is;
    use_draft with content records an edited draft; content alone is the agent's own reply."""
    if ticket.status == Ticket.Status.CLOSED:
        raise AgentActionError("This ticket is closed.")
    content = (content or "").strip()
    if use_draft and not content:
        if not has_policy_draft(ticket):
            raise AgentActionError("There's no policy-based draft for this ticket; write the reply yourself.")
        content, outcome = ticket.suggested_reply, Ticket.DraftOutcome.APPROVED
    elif content:
        outcome = Ticket.DraftOutcome.EDITED if use_draft and has_policy_draft(ticket) else Ticket.DraftOutcome.WRITTEN
    else:
        raise AgentActionError("Write a reply, or send the suggested one.")

    with transaction.atomic():
        msg = Message.objects.create(
            conversation=ticket.conversation, sender=Message.Sender.AGENT, content=content, author=user
        )
        if ticket.assigned_to is None:
            ticket.assigned_to = user
        ticket.status = Ticket.Status.IN_PROGRESS
        if not ticket.draft_outcome:
            ticket.draft_outcome = outcome
        ticket.save(update_fields=["assigned_to", "status", "draft_outcome"])
        if close:
            close_ticket(ticket)
    return msg


def close_ticket(ticket: Ticket) -> None:
    """Resolve the ticket; the chat goes back to the AI if the customer writes again."""
    with transaction.atomic():
        ticket.status = Ticket.Status.CLOSED
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=["status", "closed_at"])
        Conversation.objects.filter(pk=ticket.conversation_id).update(status=Conversation.Status.RESOLVED)
        ticket.conversation.status = Conversation.Status.RESOLVED
