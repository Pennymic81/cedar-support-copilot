"""Split text into overlapping chunks that keep paragraphs and headings together."""
from __future__ import annotations

import re
from dataclasses import dataclass

# Rough token estimate: ~0.75 words per token for English text.
WORDS_PER_TOKEN = 0.75


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text.split()) / WORDS_PER_TOKEN))


@dataclass
class TextChunk:
    index: int
    content: str
    token_count: int


def _split_long_paragraph(paragraph: str, max_tokens: int) -> list[str]:
    words = paragraph.split()
    step = max(1, int(max_tokens * WORDS_PER_TOKEN))
    return [" ".join(words[i : i + step]) for i in range(0, len(words), step)]


def _chunk_section(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Greedily pack one section's paragraphs into chunks of up to ``max_tokens``.

    The last paragraph(s) of each chunk, up to ``overlap_tokens``, are repeated at the
    start of the next one so an answer that spans a boundary is still retrievable.
    """
    paragraphs: list[str] = []
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if estimate_tokens(para) > max_tokens:
            paragraphs.extend(_split_long_paragraph(para, max_tokens))
        else:
            paragraphs.append(para)

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def flush():
        chunks.append("\n\n".join(current))

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        if current and current_tokens + para_tokens > max_tokens:
            flush()
            # carry over trailing paragraphs as overlap
            carry, carry_tokens = [], 0
            for prev in reversed(current):
                t = estimate_tokens(prev)
                if carry_tokens + t > overlap_tokens:
                    break
                carry.insert(0, prev)
                carry_tokens += t
            current, current_tokens = carry, carry_tokens
        current.append(para)
        current_tokens += para_tokens

    if current:
        flush()
    return chunks


HEADING = re.compile(r"^#{1,6}\s+\S")


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split Markdown-style text at headings. Returns (heading, body) pairs; heading may be ''."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.split("\n"):
        if HEADING.match(line):
            sections.append((line.strip(), []))
        else:
            sections[-1][1].append(line)
    return [(h, "\n".join(body).strip()) for h, body in sections if h or "\n".join(body).strip()]


def chunk_text(text: str, max_tokens: int = 200, overlap_tokens: int = 40) -> list[TextChunk]:
    """Chunk text section by section so each chunk stays on one topic.

    Each chunk starts with its section heading, so a paragraph about "Transfer times"
    keeps that label even when it is retrieved on its own.
    """
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")
    pieces: list[str] = []
    for heading, body in split_sections(text):
        if not body:
            continue  # a heading with nothing under it (e.g. the document title)
        budget = max_tokens - (estimate_tokens(heading) if heading else 0)
        for part in _chunk_section(body, max(budget, overlap_tokens + 1), overlap_tokens):
            pieces.append(f"{heading}\n\n{part}" if heading else part)
    return [TextChunk(index=i, content=c, token_count=estimate_tokens(c)) for i, c in enumerate(pieces)]
