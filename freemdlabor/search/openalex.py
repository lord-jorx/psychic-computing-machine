"""OpenAlex REST API. No key required (add a mailto: param for the polite
pool — faster, more reliable). Used as the broad-coverage citation-graph
source freephdlabor used Semantic Scholar for; unlike S2, OpenAlex needs
no API key at all.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..db import NormalizedRecord
from .base import get_json

WORKS_URL = "https://api.openalex.org/works"


def _reconstruct_abstract(inverted_index: Optional[dict[str, list[int]]]) -> Optional[str]:
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


def search_openalex(query: str, max_results: int = 500, per_page: int = 100) -> list[NormalizedRecord]:
    mailto = os.environ.get("NCBI_CONTACT_EMAIL")
    records: list[NormalizedRecord] = []
    cursor = "*"
    while len(records) < max_results:
        params = {
            "search": query,
            "per-page": min(per_page, max_results - len(records)),
            "cursor": cursor,
        }
        if mailto:
            params["mailto"] = mailto
        data = get_json(WORKS_URL, params=params)
        results = data.get("results", [])
        if not results:
            break
        for w in results:
            records.append(_normalize_work(w))
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
    return records[:max_results]


def _normalize_work(w: dict[str, Any]) -> NormalizedRecord:
    authors = []
    for a in w.get("authorships", []) or []:
        name = a.get("author", {}).get("display_name")
        if name:
            authors.append(name)

    doi = w.get("doi")
    if doi:
        doi = doi.replace("https://doi.org/", "").lower()

    primary_loc = w.get("primary_location") or {}
    source_name = (primary_loc.get("source") or {}).get("display_name")

    return NormalizedRecord(
        source="openalex",
        source_id=w.get("id"),
        doi=doi,
        title=w.get("display_name") or "[no title]",
        abstract=_reconstruct_abstract(w.get("abstract_inverted_index")),
        authors=authors,
        journal=source_name,
        year=w.get("publication_year"),
        url=primary_loc.get("landing_page_url") or w.get("id"),
        raw={
            "cited_by_count": w.get("cited_by_count"),
            "is_oa": (w.get("open_access") or {}).get("is_oa"),
            "oa_url": (w.get("open_access") or {}).get("oa_url"),
            "type": w.get("type"),
        },
    )
