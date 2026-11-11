"""Turn a document source (PDF, web page or text) into plain text."""
from __future__ import annotations

import io
import re

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

FETCH_TIMEOUT_SECONDS = 15
MAX_FETCH_BYTES = 5 * 1024 * 1024


class ExtractionError(Exception):
    """Raised when a source can't be read."""


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf raises many error types
        raise ExtractionError(f"Could not read PDF: {exc}") from exc
    text = normalize_whitespace("\n\n".join(pages))
    if not text:
        raise ExtractionError("The PDF has no readable text (it may be a scanned image).")
    return text


def extract_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "svg", "form"]):
        tag.decompose()
    blocks = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"]):
        line = el.get_text(" ", strip=True)
        if line:
            blocks.append(line)
    text = normalize_whitespace("\n\n".join(blocks) or soup.get_text("\n"))
    if not text:
        raise ExtractionError("The page has no readable text.")
    return text


def fetch_url(url: str) -> str:
    try:
        resp = requests.get(
            url,
            timeout=FETCH_TIMEOUT_SECONDS,
            headers={"User-Agent": "CedarSupportCopilot/1.0"},
            stream=True,
        )
        resp.raise_for_status()
        content = resp.raw.read(MAX_FETCH_BYTES + 1, decode_content=True)
    except requests.RequestException as exc:
        raise ExtractionError(f"Could not fetch {url}: {exc}") from exc
    if len(content) > MAX_FETCH_BYTES:
        raise ExtractionError("The page is too large (over 5 MB).")
    if "pdf" in resp.headers.get("Content-Type", ""):
        return extract_pdf(content)
    return extract_html(content.decode(resp.encoding or "utf-8", errors="replace"))
