"""Pick a confidence threshold from retrieval scores alone (no chat model calls).

Uses the eval set: questions the copilot should answer must score at or above the
threshold; off-topic questions (expected low-confidence handoffs) must score below it.
Picks the cut that gets the most of them right, then the widest margin between the two groups.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from pgvector.django import CosineDistance

from evals.models import Outcome
from knowledge.models import Chunk, Document

from .embeddings import QUERY, get_embedder


@dataclass
class Calibration:
    threshold: float
    correct: int
    total: int
    answer_scores: list[float]
    off_topic_scores: list[float]


def top_scores(business, questions: list[str]) -> list[float]:
    embedder = get_embedder()
    vectors = embedder.embed(questions, kind=QUERY)  # one batched call
    chunks = Chunk.objects.filter(
        business=business,
        document__status=Document.Status.READY,
        document__embedding_signature=embedder.signature,
    )
    scores = []
    for v in vectors:
        best = chunks.annotate(d=CosineDistance("embedding", v)).order_by("d").values_list("d", flat=True).first()
        scores.append(0.0 if best is None else max(0.0, 1.0 - best))
    return scores


def calibrate(business) -> Calibration:
    qs = list(business.eval_questions.all())
    answer_q = [q.question for q in qs if q.expected_outcome == Outcome.ANSWER]
    off_q = [q.question for q in qs if q.expected_outcome == Outcome.HANDOFF and q.expected_reason == "low_confidence"]
    if not answer_q or not off_q:
        raise ValueError("Calibration needs eval questions that should be answered and off-topic ones.")
    scores = top_scores(business, answer_q + off_q)
    a, o = scores[: len(answer_q)], scores[len(answer_q):]

    points = sorted(set(a + o))
    candidates = [(x + y) / 2 for x, y in zip(points, points[1:])] or [points[0]]
    best = None
    for t in candidates:
        correct = sum(s >= t for s in a) + sum(s < t for s in o)
        margin = min([abs(s - t) for s in a + o])
        key = (correct, margin)
        if best is None or key > best[0]:
            best = (key, t)
    (correct, _), t = best
    return Calibration(round(t, 3), correct, len(a) + len(o), sorted(a), sorted(o))
