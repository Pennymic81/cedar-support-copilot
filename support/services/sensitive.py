"""Money-safety rule: some messages always go to a person, however confident retrieval is.

A policy can say "reversals arrive within 24 hours", but only a person can check
what happened to *this* customer's money. These patterns catch those cases.
"""
from __future__ import annotations

import re

_RULES: list[tuple[str, list[str]]] = [
    (
        "money_missing",
        [
            r"\b(charged|debited|deducted|taken|withdrawn)\b.*\b(fail|failed|didn'?t (go|arrive|work)|not (received|arrived)|missing|declined|reversed?)\b",
            r"\b(fail|failed|declined)\b.*\b(charged|debited|deducted|taken)\b",
            r"\bwhere(?:'s| is) my (money|refund|funds)\b",
            r"\b(money|funds|transfer|payment) (is |are )?(missing|lost|stuck|gone)\b",
            r"\b(never|still (hasn'?t|has not|not)) (arrived|received|got|come|came)\b",
            r"\bdouble (charged|debited)|charged twice\b",
        ],
    ),
    (
        "fraud",
        [
            r"\b(fraud|fraudulent|scam|scammed|stolen|hacked|phishing)\b",
            r"\b(unauthori[sz]ed|didn'?t (make|authori[sz]e)|not me|someone (used|accessed|logged))\b",
        ],
    ),
    ("refund_dispute", [r"\b(refund|chargeback|dispute)\b"]),
    (
        "account_access",
        [
            r"\b(account|card|wallet)\b.*\b(blocked|frozen|locked|suspended|restricted|closed)\b",
            r"\b(blocked|frozen|locked|suspended)\b.*\b(account|card|wallet)\b",
            r"\b(lost|stolen) (my )?card\b",
        ],
    ),
]
_COMPILED = [(name, [re.compile(p, re.IGNORECASE) for p in pats]) for name, pats in _RULES]

LABELS = {
    "money_missing": "Money missing or a failed charge",
    "fraud": "Possible fraud or unauthorised activity",
    "refund_dispute": "Refund or dispute",
    "account_access": "Blocked or restricted account or card",
}


def detect(text: str) -> str | None:
    """Return the matched category name, or None if the message is safe for the AI."""
    for name, patterns in _COMPILED:
        if any(p.search(text) for p in patterns):
            return name
    return None
