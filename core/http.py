"""HTTP calls to AI providers with retry on rate limits and temporary errors."""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)
RETRY_STATUSES = {429, 500, 502, 503, 504}


def post_json(url: str, *, headers: dict, payload: dict, timeout: int = 60, max_wait: float = 60.0) -> dict:
    """POST and return JSON. Retries rate limits (429) and server errors with backoff,
    honouring Retry-After, until ``max_wait`` seconds of waiting are used up."""
    waited, delay = 0.0, 2.0
    while True:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code not in RETRY_STATUSES:
            resp.raise_for_status()
            return resp.json()
        try:
            pause = float(resp.headers.get("Retry-After", delay))
        except ValueError:
            pause = delay
        if waited + pause > max_wait:
            resp.raise_for_status()
        log.warning("%s returned %s; retrying in %.0fs", url.split("?")[0], resp.status_code, pause)
        time.sleep(pause)
        waited += pause
        delay = min(delay * 2, 30)
