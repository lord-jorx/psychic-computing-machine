"""Deterministic deduplication. No LLM involved — DOI/PMID exact match,
then fuzzy title matching within a year-nearby block. Reproducible and
free, unlike asking a model to spot duplicates.

Writes results directly onto records.duplicate_of / dedup_method /
dedup_score so every downstream query (PRISMA counts, screening batches)
just filters `WHERE duplicate_of IS NULL`.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass

from rapidfuzz import fuzz

DEFAULT_TITLE_THRESHOLD = 92.0


@dataclass
class DedupStats:
    total_records: int
    duplicates_by_doi: int
    duplicates_by_pmid: int
    duplicates_by_fuzzy_title: int
    canonical_remaining: int


class _UnionFind:
    def __init__(self, ids: list[int]):
        self.parent = {i: i for i in ids}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # keep the lower id as root so "canonical" is stably the first-found record
        if ra < rb:
            self.parent[rb] = ra
        else:
            self.parent[ra] = rb


def _normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip().lower()
    doi = doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
    return doi or None


def _pmid_of(row: sqlite3.Row) -> str | None:
    if row["source"] == "pubmed" and row["source_id"]:
        return str(row["source_id"])
    try:
        raw = json.loads(row["raw_json"])
    except (TypeError, ValueError):
        return None
    pmid = raw.get("pmid")
    return str(pmid) if pmid else None


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalize_title(title: str) -> str:
    t = title.lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def deduplicate(
    conn: sqlite3.Connection,
    title_threshold: float = DEFAULT_TITLE_THRESHOLD,
) -> DedupStats:
    rows = conn.execute(
        "SELECT id, source, source_id, doi, title, year, raw_json FROM records ORDER BY id"
    ).fetchall()
    if not rows:
        return DedupStats(0, 0, 0, 0, 0)

    ids = [r["id"] for r in rows]
    uf = _UnionFind(ids)
    by_id = {r["id"]: r for r in rows}

    # Pass 1: exact DOI
    doi_groups: dict[str, list[int]] = {}
    for r in rows:
        d = _normalize_doi(r["doi"])
        if d:
            doi_groups.setdefault(d, []).append(r["id"])
    doi_dupe_count = 0
    for group in doi_groups.values():
        if len(group) > 1:
            for other in group[1:]:
                uf.union(group[0], other)
            doi_dupe_count += len(group) - 1

    # Pass 2: exact PMID (catches pubmed vs. europepmc copies of the same article)
    pmid_groups: dict[str, list[int]] = {}
    for r in rows:
        p = _pmid_of(r)
        if p:
            pmid_groups.setdefault(p, []).append(r["id"])
    pmid_dupe_count = 0
    for group in pmid_groups.values():
        if len(group) > 1:
            roots = {uf.find(g) for g in group}
            if len(roots) > 1:
                pmid_dupe_count += len(roots) - 1
            for other in group[1:]:
                uf.union(group[0], other)

    # Pass 3: fuzzy title match, blocked by publication year (+/- 1) to keep
    # this roughly O(n) instead of O(n^2) on a full-sized review.
    by_year: dict[int | None, list[sqlite3.Row]] = {}
    for r in rows:
        by_year.setdefault(r["year"], []).append(r)

    years = sorted(y for y in by_year if y is not None)
    fuzzy_dupe_count = 0
    norm_title_cache = {r["id"]: _normalize_title(r["title"]) for r in rows}

    def candidates_for_year(y: int) -> list[sqlite3.Row]:
        block = list(by_year.get(y, []))
        block += by_year.get(y - 1, [])
        block += by_year.get(y + 1, [])
        return block

    seen_pairs: set[tuple[int, int]] = set()
    for y in years:
        block = candidates_for_year(y)
        for i in range(len(block)):
            for j in range(i + 1, len(block)):
                a, b = block[i]["id"], block[j]["id"]
                if a == b:
                    continue
                pair = (min(a, b), max(a, b))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                if uf.find(a) == uf.find(b):
                    continue  # already merged via DOI/PMID
                score = fuzz.token_sort_ratio(norm_title_cache[a], norm_title_cache[b])
                if score >= title_threshold:
                    uf.union(a, b)
                    fuzzy_dupe_count += 1

    # Materialize clusters and write back.
    clusters: dict[int, list[int]] = {}
    for i in ids:
        clusters.setdefault(uf.find(i), []).append(i)

    for canonical_id, members in clusters.items():
        for m in members:
            if m == canonical_id:
                continue
            row = by_id[m]
            doi_a, doi_b = _normalize_doi(row["doi"]), _normalize_doi(by_id[canonical_id]["doi"])
            pmid_a, pmid_b = _pmid_of(row), _pmid_of(by_id[canonical_id])
            if doi_a and doi_a == doi_b:
                method = "doi"
            elif pmid_a and pmid_a == pmid_b:
                method = "pmid"
            else:
                method = "fuzzy_title"
            score = (
                None
                if method != "fuzzy_title"
                else fuzz.token_sort_ratio(norm_title_cache[m], norm_title_cache[canonical_id])
            )
            conn.execute(
                "UPDATE records SET duplicate_of = ?, dedup_method = ?, dedup_score = ? WHERE id = ?",
                (canonical_id, method, score, m),
            )

    conn.commit()

    total_dupes = sum(len(v) - 1 for v in clusters.values())
    return DedupStats(
        total_records=len(rows),
        duplicates_by_doi=doi_dupe_count,
        duplicates_by_pmid=pmid_dupe_count,
        duplicates_by_fuzzy_title=fuzzy_dupe_count,
        canonical_remaining=len(rows) - total_dupes,
    )
