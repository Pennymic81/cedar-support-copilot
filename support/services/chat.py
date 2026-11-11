"""One turn of customer chat: retrieve, check confidence, answer or hand off."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction

from knowledge.services.ingest import search
from support.models import Conversation, Message, MessageCitation, Ticket

from . import sensitive
from .drafts import draft_for_ticket
from .llm import LLMError, get_answerer

log = logging.getLogger(__name__)

HANDOFF_REPLY = (
    "I'm not sure about that one, so I've passed it to our team. "
    "A person will reply right here."
)
SENSITIVE_REPLY = (
    "Because this involves your money or account, I've passed it to our team. "
    "A person will check it and reply right here."
)
PERSON_REPLY = "Of course. I've passed you to our team, and a person will reply right here."
WAITING_REPLY = "Thanks, a member of our team has your conversation and will reply here."
HUMAN_REQUEST = re.compile(r"\b(human|person|agent|someone|representative|real people)\b", re.I)
HUMAN_VERBS = re.compile(r"\b(talk|speak|chat|connect|get|want|need)\b", re.I)


@dataclass
class ChatResult:
    conversation: Conversation
    reply: Message
    handed_off: bool
    citations: list = field(default_factory=list)


def wants_a_person(text: str) -> bool:
    return bool(HUMAN_REQUEST.search(text) and HUMAN_VERBS.search(text))


def _hand_off(
    convo: Conversation, reason: str, confidence: float | None, text: str = HANDOFF_REPLY, detail: str = ""
) -> Message:
    convo.status = Conversation.Status.ESCALATED
    convo.save(update_fields=["status"])
    reply = Message.objects.create(
        conversation=convo, sender=Message.Sender.AI, content=text, confidence=confidence
    )
    ticket, created = Ticket.objects.get_or_create(
        conversation=convo, defaults={"business": convo.business, "reason": reason, "reason_detail": detail}
    )
    if not created:  # the chat was handed off before and closed: reopen the same ticket
        ticket.reason, ticket.reason_detail = reason, detail
        ticket.status, ticket.closed_at, ticket.draft_outcome = Ticket.Status.PENDING, None, ""
        ticket.save(update_fields=["reason", "reason_detail", "status", "closed_at", "draft_outcome"])
    draft_for_ticket(ticket)
    return reply


def handle_customer_message(convo: Conversation, text: str) -> ChatResult:
    business = convo.business
    history = list(convo.messages.all())
    Message.objects.create(conversation=convo, sender=Message.Sender.CUSTOMER, content=text)

    # Already with a person: the AI stays quiet.
    if convo.status == Conversation.Status.ESCALATED:
        reply = Message.objects.create(conversation=convo, sender=Message.Sender.AI, content=WAITING_REPLY)
        return ChatResult(convo, reply, handed_off=True)

    # A resolved chat that gets a new message is back with the AI.
    if convo.status == Conversation.Status.RESOLVED:
        convo.status = Conversation.Status.OPEN
        convo.save(update_fields=["status"])

    # Money-safety rule: these always go to a person, however confident retrieval is.
    category = sensitive.detect(text)
    if category:
        with transaction.atomic():
            reply = _hand_off(convo, Ticket.Reason.SENSITIVE, None, SENSITIVE_REPLY, category)
        return ChatResult(convo, reply, handed_off=True)

    if wants_a_person(text):
        with transaction.atomic():
            reply = _hand_off(convo, Ticket.Reason.CUSTOMER_REQUESTED, None, PERSON_REPLY)
        return ChatResult(convo, reply, handed_off=True)

    chunks = search(business, text, k=settings.RETRIEVAL_TOP_K)
    confidence = round(chunks[0].score, 3) if chunks else 0.0

    if confidence < business.effective_threshold:
        with transaction.atomic():
            reply = _hand_off(convo, Ticket.Reason.LOW_CONFIDENCE, confidence)
        return ChatResult(convo, reply, handed_off=True)

    try:
        draft = get_answerer().answer(business.name, text, chunks, history)
    except LLMError:
        log.exception("Answer generation failed; handing off")
        draft = None

    if draft is None or not draft.answered:
        with transaction.atomic():
            reply = _hand_off(convo, Ticket.Reason.LOW_CONFIDENCE, confidence)
        return ChatResult(convo, reply, handed_off=True)

    cited = [chunks[i - 1] for i in draft.cited]
    with transaction.atomic():
        reply = Message.objects.create(
            conversation=convo, sender=Message.Sender.AI, content=draft.text, confidence=confidence
        )
        MessageCitation.objects.bulk_create(
            MessageCitation(message=reply, chunk=c, score=round(c.score, 3)) for c in cited
        )
    return ChatResult(convo, reply, handed_off=False, citations=cited)
