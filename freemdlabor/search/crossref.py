"""Crossref REST API. No key required. Used both for supplementary search
and — critically — as the citation-resolution authority in integrity.py:
a reference only enters references.bib if Crossref (or PubMed) confirms it
exists.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..db import NormalizedRecord
from .base import get_json

WORKS_URL = "https://api.crossref.org/works"


def _polite_headers() -> dict[str, str]:
    contact = os.environ.get("NCBI_CONTACT_EMAIL", "")
    ua = "freeMDlabor/0.1 (systematic-review tooling)"
    if contact:
        ua += f" mailto:{contact}"
    return {"User-Agent": ua}


def search_crossref(query: str, max_results: int = 500, rows: int = 100) -> list[NormalizedRecord]:
    records: list[NormalizedRecord] = []
    offset = 0
    while len(records) < max_results:
        params = {
            "query.bibliographic": query,
            "rows": min(rows, max_results - len(records)),
            "offset": offset,
            "select": "DOI,title,author,container-title,published,abstract,URL",
        }
        data = get_json(WORKS_URL, params=params, headers=_polite_headers())
        items = data.get("message", {}).get("items", [])
        if not items:
            break
        for it in items:
            records.append(_normalize_work(it))
        offset += len(items)
        if len(items) < params["rows"]:
            break
    return records[:max_results]


def resolve_doi(doi: str) -> Optional[dict[str, Any]]:
    """Look up a single DOI. Returns the raw Crossref work, or None if it
    does not resolve — the hard-fail signal used by integrity.py.
    """
    doi = doi.strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")
    try:
        data = get_json(f"{WORKS_URL}/{doi}", headers=_polite_headers(), max_retries=2)
    except Exception:
        return None
    return data.get("message")


def _normalize_work(item: dict[str, Any]) -> NormalizedRecord:
    title_list = item.get("title") or []
    title = title_list[0] if title_list else "[no title]"

    authors = []
    for a in item.get("author", []) or []:
        given = a.get("given", "")
        family = a.get("family", "")
        name = f"{family} {given}".strip() if family else a.get("name")
        if name:
            authors.append(name)

    year = None
    for date_field in ("published", "published-print", "published-online"):
        parts = item.get(date_field, {}).get("date-parts")
        if parts and parts[0]:
            year = parts[0][0]
            break

    journal_list = item.get("container-title") or []
    journal = journal_list[0] if journal_list else None

    return NormalizedRecord(
        source="crossref",
        source_id=item.get("DOI"),
        doi=(item.get("DOI") or "").lower() or None,
        title=title,
        abstract=item.get("abstract"),
        authors=authors,
        journal=journal,
        year=year,
        url=item.get("URL"),
        raw=item,
    )
