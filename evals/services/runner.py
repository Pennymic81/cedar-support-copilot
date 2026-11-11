"""Run the eval set through the real chat pipeline and score it.

Every question runs in its own transaction that is rolled back, so evals never
leave conversations, messages or tickets behind.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.test.utils import override_settings

from core.models import Business
from evals.models import EvalQuestion, EvalResult, EvalRun, Outcome
from knowledge.services.llm_helpers import section_title
from support.models import Conversation, Ticket
from support.services.chat import handle_customer_message

DEFAULT_FIXTURE = Path(settings.BASE_DIR) / "evals" / "fixtures" / "cedar_pay_evals.json"


def load_questions(business: Business, path: Path = DEFAULT_FIXTURE, replace: bool = True) -> int:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    with transaction.atomic():
        if replace:
            business.eval_questions.all().delete()
        EvalQuestion.objects.bulk_create(EvalQuestion(business=business, **row) for row in rows)
    return len(rows)


@dataclass
class Observed:
    outcome: str
    reason: str
    answer: str
    confidence: float | None
    cited_document: str
    cited_section: str


class _Rollback(Exception):
    pass


def observe(business: Business, question: str) -> Observed:
    """Ask one question exactly as a customer would, then undo everything it wrote."""
    observed = None
    try:
        with transaction.atomic():
            convo = Conversation(business=business, customer_ref="eval")
            convo.save()
            result = handle_customer_message(convo, question)
            reason = ""
            if result.handed_off:
                ticket = Ticket.objects.filter(conversation=convo).first()
                reason = ticket.reason if ticket else ""
            top = result.citations[0] if result.citations else None
            observed = Observed(
                outcome=Outcome.HANDOFF if result.handed_off else Outcome.ANSWER,
                reason=reason,
                answer=result.reply.content,
                confidence=result.reply.confidence,
                cited_document=top.document.title if top else "",
                cited_section=section_title(top.content) if top else "",
            )
            raise _Rollback
    except _Rollback:
        pass
    return observed


def score(q: EvalQuestion, o: Observed) -> dict:
    routing_correct = o.outcome == q.expected_outcome
    citation_correct = keywords_found = None
    notes = []

    if q.expected_outcome == Outcome.HANDOFF:
        if not routing_correct:
            notes.append("UNSAFE: answered instead of handing off")
        elif q.expected_reason and o.reason != q.expected_reason:
            routing_correct = False
            notes.append(f"handed off as {o.reason}, expected {q.expected_reason}")
        correct = routing_correct
    else:
        if not routing_correct:
            notes.append(f"handed off ({o.reason}) instead of answering")
            correct = False
        else:
            citation_correct = o.cited_document == q.expected_document_title and (
                not q.expected_section or o.cited_section == q.expected_section
            )
            if not citation_correct:
                notes.append(f"cited {o.cited_document} › {o.cited_section}")
            text = o.answer.lower()
            missing = [k for k in q.expected_keywords if k.lower() not in text]
            keywords_found = not missing
            if missing:
                notes.append(f"answer missing {', '.join(missing)}")
            correct = citation_correct and keywords_found

    return {
        "routing_correct": routing_correct,
        "citation_correct": citation_correct,
        "keywords_found": keywords_found,
        "correct": correct,
        "note": "; ".join(notes)[:300],
    }


def current_config(business: Business, threshold: float | None = None) -> dict:
    """What an eval run's result depends on. A run with a different config is stale."""
    from knowledge.services.embeddings import get_embedder
    from support.services.llm import llm_enabled

    return {
        "embedding": get_embedder().signature,
        "llm": settings.LLM_CHAT_MODEL if llm_enabled() else "local",
        "threshold": threshold if threshold is not None else business.effective_threshold,
        "top_k": settings.RETRIEVAL_TOP_K,
    }


def run(business: Business, label: str, threshold: float | None = None, save: bool = True) -> EvalRun:
    questions = list(business.eval_questions.all())
    if not questions:
        raise ValueError("No eval questions. Run load_evals first.")

    original = business.confidence_threshold
    if threshold is not None:
        business.confidence_threshold = threshold  # in memory only, never saved
    try:
        rows = []
        # No customer is waiting, so ride out free-tier rate limits instead of handing off.
        with override_settings(LLM_RETRY_SECONDS=120):
            for q in questions:
                o = observe(business, q.question)
                rows.append((q, o, score(q, o)))
    finally:
        business.confidence_threshold = original

    answers = [r for r in rows if r[0].expected_outcome == Outcome.ANSWER and r[1].outcome == Outcome.ANSWER]
    run_obj = EvalRun(
        business=business,
        label=label,
        config=current_config(business, threshold),
        total=len(rows),
        accuracy=sum(r[2]["correct"] for r in rows) / len(rows),
        routing_accuracy=sum(r[2]["routing_correct"] for r in rows) / len(rows),
        citation_accuracy=(sum(bool(r[2]["citation_correct"]) for r in answers) / len(answers)) if answers else None,
        handoff_rate=sum(r[1].outcome == Outcome.HANDOFF for r in rows) / len(rows),
        unsafe_answers=sum(
            r[0].expected_outcome == Outcome.HANDOFF and r[1].outcome == Outcome.ANSWER for r in rows
        ),
        missed_answers=sum(
            r[0].expected_outcome == Outcome.ANSWER and r[1].outcome == Outcome.HANDOFF for r in rows
        ),
    )
    if save:
        with transaction.atomic():
            run_obj.save()
            EvalResult.objects.bulk_create(
                EvalResult(
                    run=run_obj,
                    question=q,
                    outcome=o.outcome,
                    reason=o.reason,
                    answer=o.answer,
                    confidence=o.confidence,
                    cited_document=o.cited_document,
                    cited_section=o.cited_section,
                    **s,
                )
                for q, o, s in rows
            )
    run_obj._rows = rows  # for reporting without a second query
    return run_obj
