"""Pluggable text embeddings.

EMBEDDING_PROVIDER=local   -> offline hashing embedder. No key, no network. Development and tests.
EMBEDDING_PROVIDER=gemini  -> Gemini's native embeddings API (gemini-embedding-001), sized to
                              EMBEDDING_DIMENSIONS, with separate document and query modes.
EMBEDDING_PROVIDER=openai  -> any OpenAI-compatible /embeddings API.

If a provider needs a key and none is set, it falls back to local (with a warning) rather than failing.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

import requests
from django.conf import settings

from core.http import post_json

log = logging.getLogger(__name__)

DOCUMENT, QUERY = "document", "query"


class EmbeddingError(Exception):
    pass


class Embedder(Protocol):
    dimensions: int
    signature: str  # identifies the vector space; vectors from different signatures can't be compared

    def embed(self, texts: list[str], kind: str = DOCUMENT) -> list[list[float]]: ...


def _normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class LocalHashEmbedder:
    """Bag-of-words hashed into a fixed-size vector, L2-normalised.

    Texts that share words get similar vectors, so retrieval behaves sensibly
    in development without calling any external service.
    """

    _word = re.compile(r"[a-z0-9]+")
    _stop = frozenset(
        "a an and are as at be by can do does for from has have how i if in is it its me my of on or our "
        "so that the their this to was we what when where which who will with you your".split()
    )

    def __init__(self, dimensions: int):
        self.dimensions = dimensions
        self.signature = f"local-hash:{dimensions}"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        words = [w for w in self._word.findall(text.lower()) if w not in self._stop]
        counts: dict[str, int] = {}
        for word in words:
            # light stemming so "transfer" matches "transfers"/"transferred"
            for suffix in ("ing", "ed", "es", "s"):
                if len(word) > 4 and word.endswith(suffix):
                    word = word[: -len(suffix)]
                    break
            counts[word] = counts.get(word, 0) + 1
        for word, count in counts.items():
            # sub-linear weighting so one word repeated many times doesn't dominate
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            vec[h % self.dimensions] += 1.0 + math.log(count)
        return _normalise(vec)

    def embed(self, texts: list[str], kind: str = DOCUMENT) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class GeminiEmbedder:
    """Gemini's native embeddings API: batchEmbedContents with outputDimensionality and task types."""

    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
    TASKS = {DOCUMENT: "RETRIEVAL_DOCUMENT", QUERY: "RETRIEVAL_QUERY"}

    def __init__(self, api_key: str, model: str, dimensions: int, batch_size: int = 50):
        self.api_key, self.model, self.dimensions, self.batch_size = api_key, model, dimensions, batch_size
        self.signature = f"gemini:{model}:{dimensions}"

    def embed(self, texts: list[str], kind: str = DOCUMENT) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            payload = {
                "requests": [
                    {
                        "model": f"models/{self.model}",
                        "content": {"parts": [{"text": t}]},
                        "taskType": self.TASKS[kind],
                        "outputDimensionality": self.dimensions,
                    }
                    for t in batch
                ]
            }
            try:
                data = post_json(
                    self.URL.format(model=self.model),
                    headers={"x-goog-api-key": self.api_key},
                    payload=payload,
                    # A customer is waiting on a query; document indexing can wait longer.
                    max_wait=settings.LLM_RETRY_SECONDS if kind == QUERY else 90,
                )
            except requests.RequestException as exc:
                raise EmbeddingError(f"Gemini embedding request failed: {exc}") from exc
            vectors.extend(_normalise(e["values"]) for e in data["embeddings"])
        _check_dims(vectors, self.dimensions)
        return vectors


class OpenAICompatibleEmbedder:
    def __init__(self, api_key: str, model: str, base_url: str, dimensions: int, batch_size: int = 64):
        self.api_key, self.model, self.dimensions, self.batch_size = api_key, model, dimensions, batch_size
        self.base_url = base_url.rstrip("/")
        self.signature = f"openai:{base_url}:{model}:{dimensions}"

    def embed(self, texts: list[str], kind: str = DOCUMENT) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            try:
                data = post_json(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    payload={"model": self.model, "input": batch, "dimensions": self.dimensions},
                    max_wait=settings.LLM_RETRY_SECONDS if kind == QUERY else 90,
                )
            except requests.RequestException as exc:
                raise EmbeddingError(f"Embedding request failed: {exc}") from exc
            vectors.extend(d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"]))
        _check_dims(vectors, self.dimensions)
        return vectors


def _check_dims(vectors, expected):
    for v in vectors:
        if len(v) != expected:
            raise EmbeddingError(f"Model returned {len(v)} dimensions but EMBEDDING_DIMENSIONS is {expected}.")


def get_embedder() -> Embedder:
    provider = settings.EMBEDDING_PROVIDER
    dims = settings.EMBEDDING_DIMENSIONS
    if provider in {"gemini", "openai"} and not settings.LLM_API_KEY:
        log.warning("EMBEDDING_PROVIDER=%s but LLM_API_KEY is empty; using the offline embedder.", provider)
        provider = "local"
    if provider == "local":
        return LocalHashEmbedder(dims)
    if provider == "gemini":
        return GeminiEmbedder(settings.LLM_API_KEY, settings.EMBEDDING_MODEL, dims)
    if provider == "openai":
        return OpenAICompatibleEmbedder(settings.LLM_API_KEY, settings.EMBEDDING_MODEL, settings.LLM_API_BASE, dims)
    raise EmbeddingError(f"Unknown EMBEDDING_PROVIDER: {provider!r} (use 'local', 'gemini' or 'openai').")
