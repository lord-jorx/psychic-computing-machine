"""SQLite schema and access helpers for review.sqlite.

review.sqlite is the single source of truth for everything countable in a
review: what was found, what was screened, what was extracted, what was
judged for risk of bias, and what was approved at each human gate. Nothing
downstream (PRISMA counts, meta-analysis input, provenance checks) should
be computed from prose or from an agent's memory — it is always a query
against this database.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS search_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,              -- pubmed | europepmc | crossref | clinicaltrials | openalex
    query           TEXT NOT NULL,
    executed_at     TEXT NOT NULL,
    result_count    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    search_run_id   INTEGER REFERENCES search_runs(id),
    source          TEXT NOT NULL,
    source_id       TEXT,                       -- PMID / PMCID / NCT id / OpenAlex id, as given by the source
    doi             TEXT,
    title           TEXT NOT NULL,
    abstract        TEXT,
    authors         TEXT,                       -- JSON list
    journal         TEXT,
    year            INTEGER,
    url             TEXT,
    raw_json        TEXT NOT NULL,               -- untouched source response, for reproducibility
    fetched_at      TEXT NOT NULL,
    duplicate_of    INTEGER REFERENCES records(id),  -- NULL if this is the canonical record
    dedup_method    TEXT,                        -- doi | pmid | fuzzy_title | NULL
    dedup_score     REAL
);
CREATE INDEX IF NOT EXISTS idx_records_doi ON records(doi);
CREATE INDEX IF NOT EXISTS idx_records_source_id ON records(source, source_id);

CREATE TABLE IF NOT EXISTS screening_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id       INTEGER NOT NULL REFERENCES records(id),
    stage           TEXT NOT NULL,               -- title_abstract | full_text
    pass_label      TEXT NOT NULL,               -- pass_a | pass_b | human | consensus
    decision        TEXT NOT NULL,               -- include | exclude | maybe
    reason          TEXT,
    reason_code     TEXT,                        -- free-text exclusion-reason code, for PRISMA reporting
    reviewer        TEXT NOT NULL,                -- model id, or a human name
    model           TEXT,
    prompt_version  TEXT,
    decided_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_screening_record ON screening_decisions(record_id);

CREATE TABLE IF NOT EXISTS extractions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id       INTEGER NOT NULL REFERENCES records(id),
    field_name      TEXT NOT NULL,
    value           TEXT,
    quote           TEXT,                        -- verbatim source sentence backing this value
    page            TEXT,
    model           TEXT,
    extracted_at    TEXT NOT NULL,
    verified_by     TEXT,                         -- human name once checked against the PDF (gate G3)
    verified_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_extractions_record ON extractions(record_id);

CREATE TABLE IF NOT EXISTS bias_assessments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id       INTEGER NOT NULL REFERENCES records(id),
    tool            TEXT NOT NULL,               -- RoB2 | ROBINS-I | QUADAS-2 | NOS
    domain          TEXT NOT NULL,
    judgment        TEXT NOT NULL,               -- low | some_concerns | high | critical | serious | moderate
    justification   TEXT NOT NULL,
    quote           TEXT,
    model           TEXT,
    assessed_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id        TEXT NOT NULL UNIQUE,         -- referenced from the manuscript as \\provenance{claim_id}
    manuscript_value TEXT NOT NULL,
    source_table    TEXT NOT NULL,                -- extractions | bias_assessments | analysis
    source_ref      TEXT NOT NULL,                -- row id, or a key into analysis/results.json
    note            TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gates (
    gate_id         TEXT PRIMARY KEY,             -- G1 | G2 | G3 | G4 | G5
    status          TEXT NOT NULL,                -- approved | rejected
    artifact_path   TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    approved_by     TEXT NOT NULL,
    notes           TEXT,
    decided_at      TEXT NOT NULL
);
"""


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Create review.sqlite with the full schema if it doesn't exist yet."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@dataclass
class NormalizedRecord:
    """The common shape every search client must return before insertion."""

    source: str
    title: str
    source_id: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    journal: Optional[str] = None
    year: Optional[int] = None
    url: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)


def insert_search_run(conn: sqlite3.Connection, source: str, query: str) -> int:
    from datetime import datetime, timezone

    cur = conn.execute(
        "INSERT INTO search_runs (source, query, executed_at, result_count) VALUES (?, ?, ?, 0)",
        (source, query, datetime.now(timezone.utc).isoformat()),
    )
    return cur.lastrowid


def insert_records(conn: sqlite3.Connection, search_run_id: int, records: list[NormalizedRecord]) -> int:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for r in records:
        conn.execute(
            """INSERT INTO records
               (search_run_id, source, source_id, doi, title, abstract, authors,
                journal, year, url, raw_json, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                search_run_id,
                r.source,
                r.source_id,
                r.doi,
                r.title,
                r.abstract,
                json.dumps(r.authors, ensure_ascii=False),
                r.journal,
                r.year,
                r.url,
                json.dumps(r.raw, ensure_ascii=False),
                now,
            ),
        )
        n += 1
    conn.execute(
        "UPDATE search_runs SET result_count = result_count + ? WHERE id = ?",
        (n, search_run_id),
    )
    return n


def canonical_records(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Records that survive dedup: duplicate_of IS NULL."""
    return conn.execute("SELECT * FROM records WHERE duplicate_of IS NULL").fetchall()


def insert_bias_assessment(
    conn: sqlite3.Connection,
    record_id: int,
    tool: str,
    domain: str,
    judgment: str,
    justification: str,
    quote: Optional[str] = None,
    model: Optional[str] = None,
) -> int:
    """Risk-of-bias judgments are a `judgment`-role step: made by a human
    (directly, or through Claude Code reading the study interactively), so
    `model` is typically something like "human:dr_ortiz" or "claude-code",
    never a batch LLM call — see PLAN.md §3.2 and providers.py.
    """
    from datetime import datetime, timezone

    cur = conn.execute(
        """INSERT INTO bias_assessments (record_id, tool, domain, judgment, justification, quote, model, assessed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (record_id, tool, domain, judgment, justification, quote, model, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def export_bias_csv(conn: sqlite3.Connection, out_path: str | Path) -> int:
    import csv as _csv

    rows = conn.execute(
        """SELECT ba.*, r.title FROM bias_assessments ba
           JOIN records r ON r.id = ba.record_id
           ORDER BY ba.record_id, ba.tool, ba.domain"""
    ).fetchall()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f)
        writer.writerow(["record_id", "title", "tool", "domain", "judgment", "justification", "quote", "model", "assessed_at"])
        for r in rows:
            writer.writerow([
                r["record_id"], r["title"], r["tool"], r["domain"],
                r["judgment"], r["justification"], r["quote"], r["model"], r["assessed_at"],
            ])
    return len(rows)
