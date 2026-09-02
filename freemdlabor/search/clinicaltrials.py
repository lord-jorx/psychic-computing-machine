"""ClinicalTrials.gov API v2. No key required.

Primary use in this pipeline: detect publication bias by finding trials
registered for a condition/intervention that never produced a matched
publication in the screened set — the ScreeningAgent/BiasAgent step that
freephdlabor's arXiv-only search had no equivalent for.
"""

from __future__ import annotations

from typing import Any, Optional

from ..db import NormalizedRecord
from .base import get_json

STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"


def search_clinicaltrials(query: str, max_results: int = 500, page_size: int = 100) -> list[NormalizedRecord]:
    records: list[NormalizedRecord] = []
    page_token: Optional[str] = None
    while len(records) < max_results:
        params = {
            "query.term": query,
            "pageSize": min(page_size, max_results - len(records)),
            "format": "json",
        }
        if page_token:
            params["pageToken"] = page_token
        data = get_json(STUDIES_URL, params=params)
        studies = data.get("studies", [])
        if not studies:
            break
        for s in studies:
            records.append(_normalize_study(s))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return records[:max_results]


def _normalize_study(study: dict[str, Any]) -> NormalizedRecord:
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    design = proto.get("designModule", {})
    desc = proto.get("descriptionModule", {})
    sponsor = proto.get("sponsorCollaboratorsModule", {})

    nct_id = ident.get("nctId")
    title = ident.get("officialTitle") or ident.get("briefTitle") or "[no title]"

    year = None
    start_date = status.get("startDateStruct", {}).get("date")
    if start_date and len(start_date) >= 4 and start_date[:4].isdigit():
        year = int(start_date[:4])

    lead_sponsor = sponsor.get("leadSponsor", {}).get("name")

    return NormalizedRecord(
        source="clinicaltrials",
        source_id=nct_id,
        doi=None,
        title=title,
        abstract=desc.get("briefSummary"),
        authors=[lead_sponsor] if lead_sponsor else [],
        journal=None,
        year=year,
        url=f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None,
        raw={
            "overall_status": status.get("overallStatus"),
            "has_results": status.get("hasResults", False) or "resultsSection" in study,
            "phases": design.get("phases"),
        },
    )
