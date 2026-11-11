"""Support metrics for the dashboard."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from statistics import median

from django.db.models import Avg, Count, Min, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from evals.models import EvalRun
from knowledge.services.llm_helpers import section_title
from support.models import Conversation, Message, MessageCitation, Ticket


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def summary(business, days: int = 30) -> dict:
    since = timezone.now() - timedelta(days=days)
    convos = Conversation.objects.filter(business=business, created_at__gte=since)
    tickets = Ticket.objects.filter(business=business, created_at__gte=since)
    total = convos.count()
    handed_off = convos.filter(ticket__isnull=False).count()

    # Daily volume: conversations, and how many of them needed a person
    daily = (
        convos.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"), handed_off=Count("id", filter=Q(ticket__isnull=False)))
        .order_by("day")
    )

    # Handoff reasons, with money-safety rules broken out
    reasons = Counter()
    for t in tickets.values("reason", "reason_detail"):
        reasons[t["reason_detail"] or t["reason"]] += 1

    # Top topics: the policy section behind each AI answer
    topics = Counter()
    answered_ids = Message.objects.filter(
        conversation__in=convos, sender=Message.Sender.AI, citations__isnull=False
    ).values_list("id", flat=True).distinct()
    best = {}
    for c in MessageCitation.objects.filter(message_id__in=answered_ids).select_related("chunk__document"):
        if c.message_id not in best or c.score > best[c.message_id].score:
            best[c.message_id] = c
    for c in best.values():
        topics[f"{c.chunk.document.title} › {section_title(c.chunk.content) or 'general'}"] += 1

    # Drafts: how agents used them
    outcomes = Counter(tickets.exclude(draft_outcome="").values_list("draft_outcome", flat=True))
    replied = sum(outcomes.values())

    # Time from handoff to first agent reply
    waits = []
    for t in tickets.annotate(
        first_reply=Min("conversation__messages__created_at", filter=Q(conversation__messages__sender="agent"))
    ).exclude(first_reply=None):
        waits.append((t.first_reply - t.created_at).total_seconds() / 60)

    ai_conf = Message.objects.filter(
        conversation__in=convos, sender=Message.Sender.AI, confidence__isnull=False
    ).aggregate(avg=Avg("confidence"))["avg"]

    evals = list(
        EvalRun.objects.filter(business=business)
        .order_by("created_at")
        .values("label", "accuracy", "routing_accuracy", "citation_accuracy", "unsafe_answers", "created_at")
    )

    return {
        "period_days": days,
        "conversations": total,
        "resolved_by_ai": total - handed_off,
        "handed_off": handed_off,
        "ai_resolution_rate": _rate(total - handed_off, total),
        "handoff_rate": _rate(handed_off, total),
        "open_tickets": tickets.exclude(status=Ticket.Status.CLOSED).count(),
        "avg_ai_confidence": round(ai_conf, 3) if ai_conf is not None else None,
        "median_minutes_to_agent_reply": round(median(waits), 1) if waits else None,
        "handoff_reasons": dict(reasons.most_common()),
        "top_topics": [{"topic": k, "count": v} for k, v in topics.most_common(8)],
        "drafts": {
            "replied": replied,
            "approved": outcomes.get("approved", 0),
            "edited": outcomes.get("edited", 0),
            "written": outcomes.get("written", 0),
            # of tickets that had a policy-based draft, how many were sent unchanged
            "approval_rate": _rate(outcomes.get("approved", 0), outcomes.get("approved", 0) + outcomes.get("edited", 0)),
        },
        "daily": [{"day": d["day"].isoformat(), "total": d["total"], "handed_off": d["handed_off"]} for d in daily],
        "eval_runs": [{**r, "created_at": r["created_at"].isoformat()} for r in evals],
    }
