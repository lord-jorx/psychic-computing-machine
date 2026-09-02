"""Shared HTTP plumbing for search clients.

Every client in this package returns a list of NormalizedRecord — never a
raw provider payload — so dedup.py and db.py don't need to know which
source a record came from. Every client also keeps the untouched provider
response (as `raw`) so a search is reproducible from review.sqlite alone.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import requests

USER_AGENT = "freeMDlabor/0.1 (systematic-review tooling; mailto:{contact})"


class SearchClientError(RuntimeError):
    pass


def get_json(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
    max_retries: int = 3,
) -> Any:
    """GET with a couple of retries on 429/5xx. Raises on anything else."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 ** attempt
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(2 ** attempt)
    raise SearchClientError(f"GET {url} failed after {max_retries} attempts: {last_exc}")
