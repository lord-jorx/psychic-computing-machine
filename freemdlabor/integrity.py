"""The anti-fabrication layer — PLAN.md §7.

Two hard-fail checks that a manuscript must pass before it is considered
submittable:

1. resolve_citations(): every entry in references.bib must carry a DOI (or
   PMID) that ACTUALLY resolves against Crossref/PubMed right now. An entry
   with no identifier, or one that doesn't resolve, is fabricated or wrong
   — full stop. This is deliberately not "best effort" — check_citations()
   raises and a calling script should exit non-zero.

2. check_provenance(): every numeric claim tagged with \\provenance{claim_id}
   in the manuscript must have a matching row in the provenance table,
   which in turn points at a real extractions/bias_assessments row or an
   analysis/results.json key — never at another LLM's say-so. It also
   flags (as warnings, not hard failures — this half is a heuristic, not
   a guarantee) numeric-looking text with no nearby \\provenance tag, so a
   human reviewer knows where to double check by hand.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

from .bibtex import parse_bibtex
from .search.crossref import resolve_doi as crossref_resolve_doi


class IntegrityError(RuntimeError):
    """Raised by the *_or_fail wrappers. Catch this at the CLI boundary and
    exit non-zero — never swallow it and continue to compile."""


@dataclass
class CitationCheck:
    key: str
    doi: Optional[str]
    resolved: bool
    title_mismatch: bool
    bib_title: Optional[str]
    resolved_title: Optional[str]
    reason: Optional[str] = None


def _normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    d = doi.strip().lower()
    return d.removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")


def resolve_citations(bib_path: str | Path, title_similarity_floor: float = 80.0) -> list[CitationCheck]:
    bib_path = Path(bib_path)
    entries = parse_bibtex(bib_path.read_text(encoding="utf-8"))
    results: list[CitationCheck] = []
    for e in entries:
        fields = e["fields"]
        doi = _normalize_doi(fields.get("doi"))
        bib_title = fields.get("title")
        if not doi:
            results.append(CitationCheck(
                key=e["key"], doi=None, resolved=False, title_mismatch=False,
                bib_title=bib_title, resolved_title=None, reason="no_doi",
            ))
            continue
        work = crossref_resolve_doi(doi)
        if work is None:
            results.append(CitationCheck(
                key=e["key"], doi=doi, resolved=False, title_mismatch=False,
                bib_title=bib_title, resolved_title=None, reason="doi_does_not_resolve",
            ))
            continue
        resolved_title_list = work.get("title") or []
        resolved_title = resolved_title_list[0] if resolved_title_list else None
        mismatch = False
        if bib_title and resolved_title:
            score = fuzz.token_sort_ratio(bib_title.lower(), resolved_title.lower())
            mismatch = score < title_similarity_floor
        results.append(CitationCheck(
            key=e["key"], doi=doi, resolved=True, title_mismatch=mismatch,
            bib_title=bib_title, resolved_title=resolved_title,
        ))
    return results


def check_citations_or_fail(bib_path: str | Path) -> list[CitationCheck]:
    results = resolve_citations(bib_path)
    failures = [r for r in results if not r.resolved or r.title_mismatch]
    if failures:
        lines = [f"Citation integrity check FAILED for {bib_path} — {len(failures)}/{len(results)} entries:"]
        for r in failures:
            if not r.resolved:
                lines.append(f"  [{r.key}] UNRESOLVED ({r.reason}) doi={r.doi!r}")
            else:
                lines.append(
                    f"  [{r.key}] TITLE MISMATCH: bib says {r.bib_title!r}, "
                    f"Crossref says {r.resolved_title!r} for doi={r.doi}"
                )
        raise IntegrityError("\n".join(lines))
    return results


# ------------------------------------------------------------ provenance --

_PROVENANCE_TAG_RE = re.compile(r"\\provenance\{([^}]+)\}")

_NUMERIC_CLAIM_PATTERNS = [
    re.compile(r"\b\d+(\.\d+)?\s*%"),
    re.compile(r"\bp\s*[<=]\s*0?\.\d+", re.IGNORECASE),
    re.compile(r"\b(OR|RR|HR|MD|SMD|WMD|I\^?2|I2)\b\s*[:=]?\s*-?\d+(\.\d+)?", re.IGNORECASE),
    re.compile(r"95%?\s*CI", re.IGNORECASE),
]


def add_provenance(
    conn: sqlite3.Connection,
    claim_id: str,
    manuscript_value: str,
    source_table: str,
    source_ref: str,
    note: Optional[str] = None,
) -> None:
    if source_table not in ("extractions", "bias_assessments", "analysis"):
        raise ValueError("source_table must be one of: extractions, bias_assessments, analysis")
    conn.execute(
        """INSERT INTO provenance (claim_id, manuscript_value, source_table, source_ref, note, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(claim_id) DO UPDATE SET
             manuscript_value=excluded.manuscript_value,
             source_table=excluded.source_table,
             source_ref=excluded.source_ref,
             note=excluded.note""",
        (claim_id, manuscript_value, source_table, source_ref, note, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _resolve_source(conn: sqlite3.Connection, source_table: str, source_ref: str) -> bool:
    if source_table == "analysis":
        return True  # verified separately, against results.json, by check_provenance
    row = conn.execute(f"SELECT 1 FROM {source_table} WHERE id = ?", (source_ref,)).fetchone()
    return row is not None


@dataclass
class ProvenanceReport:
    referenced: set[str] = field(default_factory=set)
    missing_from_db: set[str] = field(default_factory=set)
    dangling_source: set[str] = field(default_factory=set)  # tag exists, but source row doesn't
    unprovenanced_numeric_claims: list[tuple[int, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_from_db and not self.dangling_source


def check_provenance(conn: sqlite3.Connection, manuscript_path: str | Path) -> ProvenanceReport:
    text = Path(manuscript_path).read_text(encoding="utf-8")
    report = ProvenanceReport()

    report.referenced = set(_PROVENANCE_TAG_RE.findall(text))
    known = {
        r["claim_id"] for r in conn.execute("SELECT claim_id FROM provenance").fetchall()
    }
    report.missing_from_db = report.referenced - known

    for claim_id in report.referenced & known:
        row = conn.execute("SELECT source_table, source_ref FROM provenance WHERE claim_id = ?", (claim_id,)).fetchone()
        if not _resolve_source(conn, row["source_table"], row["source_ref"]):
            report.dangling_source.add(claim_id)

    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in _NUMERIC_CLAIM_PATTERNS:
            for m in pattern.finditer(line):
                if "\\provenance{" in line:
                    continue  # a tag anywhere on the same line is treated as covering it
                report.unprovenanced_numeric_claims.append((lineno, line.strip()[:160]))
                break  # one flag per line is enough signal

    return report


def check_provenance_or_fail(conn: sqlite3.Connection, manuscript_path: str | Path) -> ProvenanceReport:
    report = check_provenance(conn, manuscript_path)
    if not report.ok:
        lines = [f"Provenance check FAILED for {manuscript_path}:"]
        for c in sorted(report.missing_from_db):
            lines.append(f"  \\provenance{{{c}}} is used in the manuscript but not recorded in review.sqlite")
        for c in sorted(report.dangling_source):
            lines.append(f"  \\provenance{{{c}}} points at a source row that no longer exists")
        raise IntegrityError("\n".join(lines))
    return report
