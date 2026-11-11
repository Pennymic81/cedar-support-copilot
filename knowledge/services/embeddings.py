"""Pluggable text embeddings.

EMBEDDING_PROVIDER=openai  -> any OpenAI-compatible /embeddings API (OpenAI, Azure,
                              Together, a local server...). Needs LLM_API_KEY.
EMBEDDING_PROVIDER=local   -> an offline hashing embedder. No API key, no network.
                              Good enough for development and tests, not for production quality.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import requests
from django.conf import settings


class EmbeddingError(Exception):
    pass


class Embedder(Protocol):
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


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
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class OpenAICompatibleEmbedder:
    def __init__(self, api_key: str, model: str, base_url: str, dimensions: int, batch_size: int = 64):
        if not api_key:
            raise EmbeddingError("LLM_API_KEY is not set.")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.dimensions = dimensions
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            try:
                resp = requests.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input": batch, "dimensions": self.dimensions},
                    timeout=60,
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                raise EmbeddingError(f"Embedding request failed: {exc}") from exc
            data = sorted(resp.json()["data"], key=lambda d: d["index"])
            vectors.extend(d["embedding"] for d in data)
        for v in vectors:
            if len(v) != self.dimensions:
                raise EmbeddingError(
                    f"Model returned {len(v)} dimensions but EMBEDDING_DIMENSIONS is {self.dimensions}."
                )
        return vectors


def get_embedder() -> Embedder:
    provider = settings.EMBEDDING_PROVIDER
    if provider == "local":
        return LocalHashEmbedder(settings.EMBEDDING_DIMENSIONS)
    if provider == "openai":
        return OpenAICompatibleEmbedder(
            api_key=settings.LLM_API_KEY,
            model=settings.EMBEDDING_MODEL,
            base_url=settings.LLM_API_BASE,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
    raise EmbeddingError(f"Unknown EMBEDDING_PROVIDER: {provider!r} (use 'local' or 'openai').")
