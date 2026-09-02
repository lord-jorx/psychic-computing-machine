"""Europe PMC REST API. No key required. Used both as a second bibliographic
source and, via query="OPEN_ACCESS:Y", to locate full-text OA articles for
the eligibility and extraction stages.
"""

from __future__ import annotations

from typing import Optional

from ..db import NormalizedRecord
from .base import get_json

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def search_europepmc(query: str, max_results: int = 500, page_size: int = 100) -> list[NormalizedRecord]:
    records: list[NormalizedRecord] = []
    cursor = "*"
    while len(records) < max_results:
        params = {
            "query": query,
            "format": "json",
            "pageSize": min(page_size, max_results - len(records)),
            "cursorMark": cursor,
            "resultType": "core",
        }
        data = get_json(SEARCH_URL, params=params)
        hits = data.get("resultList", {}).get("result", [])
        if not hits:
            break
        for h in hits:
            authors = []
            author_list = h.get("authorList", {}).get("author", [])
            for a in author_list:
                name = a.get("fullName") or a.get("collectiveName")
                if name:
                    authors.append(name)

            year = None
            pub_year = h.get("pubYear")
            if pub_year and str(pub_year).isdigit():
                year = int(pub_year)

            oa = h.get("isOpenAccess") == "Y"
            pmcid = h.get("pmcid")
            full_text_url = None
            if oa and pmcid:
                full_text_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/"

            records.append(
                NormalizedRecord(
                    source="europepmc",
                    source_id=h.get("id"),
                    doi=(h.get("doi") or "").lower() or None,
                    title=h.get("title", "[no title]"),
                    abstract=h.get("abstractText"),
                    authors=authors,
                    journal=h.get("journalTitle"),
                    year=year,
                    url=full_text_url or h.get("pageInfo"),
                    raw={
                        "pmid": h.get("pmid"),
                        "pmcid": pmcid,
                        "is_open_access": oa,
                        "full_text_url": full_text_url,
                    },
                )
            )
        cursor = data.get("nextCursorMark", cursor)
        if cursor is None or len(hits) < params["pageSize"]:
            break
    return records[:max_results]
