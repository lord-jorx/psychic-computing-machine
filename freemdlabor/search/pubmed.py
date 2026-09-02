"""PubMed / MEDLINE via NCBI E-utilities. No API key required (one bumps the
rate limit from 3 to 10 req/s — set NCBI_API_KEY if you have one).
"""

from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from typing import Optional

from ..db import NormalizedRecord
from .base import get_json

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None:
        return None
    return "".join(el.itertext()).strip() or None


def _parse_article(article_el: ET.Element) -> NormalizedRecord:
    medline = article_el.find("MedlineCitation")
    pmid_el = medline.find("PMID")
    pmid = _text(pmid_el)

    art = medline.find("Article")
    title = _text(art.find("ArticleTitle")) or "[no title]"

    abstract_parts = []
    abstract_el = art.find("Abstract")
    if abstract_el is not None:
        for chunk in abstract_el.findall("AbstractText"):
            label = chunk.get("Label")
            txt = _text(chunk) or ""
            abstract_parts.append(f"{label}: {txt}" if label else txt)
    abstract = "\n".join(p for p in abstract_parts if p) or None

    authors = []
    author_list = art.find("AuthorList")
    if author_list is not None:
        for a in author_list.findall("Author"):
            last = _text(a.find("LastName"))
            fore = _text(a.find("ForeName")) or _text(a.find("Initials"))
            collective = _text(a.find("CollectiveName"))
            if collective:
                authors.append(collective)
            elif last:
                authors.append(f"{last} {fore}" if fore else last)

    journal_el = art.find("Journal")
    journal = _text(journal_el.find("Title")) if journal_el is not None else None

    year = None
    pub_date = art.find("Journal/JournalIssue/PubDate")
    if pub_date is not None:
        y = _text(pub_date.find("Year"))
        if y and y.isdigit():
            year = int(y)
        elif y:
            # e.g. "2024 Spring" or a MedlineDate range like "2023-2024"
            digits = "".join(c for c in y[:4] if c.isdigit())
            year = int(digits) if len(digits) == 4 else None

    doi = None
    for aid in art.findall("ELocationID"):
        if aid.get("EIdType") == "doi":
            doi = _text(aid)
    if doi is None:
        for aid in medline.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)

    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None

    return NormalizedRecord(
        source="pubmed",
        source_id=pmid,
        doi=doi.lower() if doi else None,
        title=title,
        abstract=abstract,
        authors=authors,
        journal=journal,
        year=year,
        url=url,
        raw={"pmid": pmid},  # full XML kept separately by the caller if needed
    )


def search_pubmed(
    query: str,
    max_results: int = 500,
    api_key: Optional[str] = None,
    contact_email: Optional[str] = None,
) -> list[NormalizedRecord]:
    api_key = api_key or os.environ.get("NCBI_API_KEY")
    contact_email = contact_email or os.environ.get("NCBI_CONTACT_EMAIL")

    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results,
    }
    if api_key:
        params["api_key"] = api_key
    if contact_email:
        params["email"] = contact_email

    result = get_json(ESEARCH_URL, params=params)
    idlist: list[str] = result.get("esearchresult", {}).get("idlist", [])
    if not idlist:
        return []

    records: list[NormalizedRecord] = []
    delay = 0.11 if api_key else 0.35  # stay under 10/s (key) or 3/s (no key)
    for batch in _chunks(idlist, 200):
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "rettype": "abstract",
            "retmode": "xml",
        }
        if api_key:
            fetch_params["api_key"] = api_key
        if contact_email:
            fetch_params["email"] = contact_email

        import requests

        resp = requests.get(EFETCH_URL, params=fetch_params, timeout=60)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for article_el in root.findall("PubmedArticle"):
            try:
                records.append(_parse_article(article_el))
            except Exception:
                continue  # malformed single record shouldn't sink the whole batch
        time.sleep(delay)

    return records
