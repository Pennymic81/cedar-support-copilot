"""Prompt-injection guard for uploaded documents.

Document text is reference material, never instructions. Lines that read like
orders to an AI model are removed before chunking and counted on the document,
so they can never reach the model as part of the context.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SUSPICIOUS_PATTERNS = [
    r"\bignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|rules|prompts?)\b",
    r"\bdisregard (all |any )?(the )?(previous|prior|above|system) (instructions|rules|prompts?)\b",
    r"\byou are now\b",
    r"\bact as (an? )?(different|new|unrestricted)\b",
    r"\b(system|developer) prompt\b",
    r"\bnew instructions?:",
    r"\bdo not (tell|inform) the (user|customer)\b",
    r"\b(reveal|print|show) (your|the) (instructions|prompt|system prompt)\b",
    r"\bjailbreak\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in SUSPICIOUS_PATTERNS]


@dataclass
class GuardResult:
    clean_text: str
    flagged_lines: list[str] = field(default_factory=list)


def scan(text: str) -> GuardResult:
    kept, flagged = [], []
    for line in text.split("\n"):
        if any(p.search(line) for p in _COMPILED):
            flagged.append(line.strip())
        else:
            kept.append(line)
    return GuardResult(clean_text="\n".join(kept).strip(), flagged_lines=flagged)
