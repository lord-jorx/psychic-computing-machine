"""Double-pass screening. Two independent LLM passes (or a human pass) per
record; agreement is measured with Cohen's kappa; disagreements are written
to conflicts.csv for the human gate (G2) rather than auto-resolved.

Calibrate before trusting this at scale: screen ~100 records yourself,
run pass_a/pass_b over the same 100, and check kappa against a manual gold
standard, not just inter-pass agreement — see PLAN.md F2.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import RoleConfig
from .db import canonical_records
from .prompts.screening_prompt import build_full_text_prompt, build_screening_prompt
from .providers import call_llm_json


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _already_decided_ids(conn: sqlite3.Connection, stage: str, pass_label: str) -> set[int]:
    rows = conn.execute(
        "SELECT record_id FROM screening_decisions WHERE stage = ? AND pass_label = ?",
        (stage, pass_label),
    ).fetchall()
    return {r["record_id"] for r in rows}


def run_title_abstract_pass(
    conn: sqlite3.Connection,
    role_cfg: RoleConfig,
    protocol_text: str,
    pass_label: str,
    batch_size: int = 20,
) -> int:
    """Runs one full pass (pass_a or pass_b) over every canonical record that
    doesn't already have a decision for that pass. Returns records decided.
    """
    records = canonical_records(conn)
    done = _already_decided_ids(conn, "title_abstract", pass_label)
    todo = [dict(r) for r in records if r["id"] not in done]
    if not todo:
        return 0

    decided = 0
    now_fn = lambda: datetime.now(timezone.utc).isoformat()
    for batch in _chunks(todo, batch_size):
        batch_input = [{"id": r["id"], "title": r["title"], "abstract": r["abstract"]} for r in batch]
        system, user = build_screening_prompt(protocol_text, batch_input)
        result = call_llm_json(role_cfg, system, user, data_sensitivity="public")
        if not isinstance(result, list):
            raise ValueError(f"Expected a JSON array from screening call, got: {type(result)}")

        by_id = {item["id"]: item for item in batch_input}
        for item in result:
            rid = item.get("id")
            if rid not in by_id:
                continue  # model invented or dropped an id; skip rather than corrupt the DB
            conn.execute(
                """INSERT INTO screening_decisions
                   (record_id, stage, pass_label, decision, reason, reason_code, reviewer, model, prompt_version, decided_at)
                   VALUES (?, 'title_abstract', ?, ?, ?, ?, ?, ?, 'v1', ?)""",
                (
                    rid,
                    pass_label,
                    item.get("decision", "maybe"),
                    item.get("reason"),
                    item.get("reason_code"),
                    role_cfg.model or role_cfg.provider,
                    role_cfg.model,
                    now_fn(),
                ),
            )
            decided += 1
        conn.commit()
    return decided


def run_full_text_pass(
    conn: sqlite3.Connection,
    role_cfg: RoleConfig,
    protocol_text: str,
    record_id: int,
    full_text: str,
    pass_label: str = "pass_a",
) -> dict:
    row = conn.execute("SELECT title FROM records WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise ValueError(f"No record with id {record_id}")
    system, user = build_full_text_prompt(protocol_text, row["title"], full_text)
    result = call_llm_json(role_cfg, system, user, data_sensitivity="public")
    conn.execute(
        """INSERT INTO screening_decisions
           (record_id, stage, pass_label, decision, reason, reason_code, reviewer, model, prompt_version, decided_at)
           VALUES (?, 'full_text', ?, ?, ?, ?, ?, ?, 'v1', ?)""",
        (
            record_id,
            pass_label,
            result.get("decision", "exclude"),
            result.get("reason"),
            result.get("reason_code"),
            role_cfg.model or role_cfg.provider,
            role_cfg.model,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return result


@dataclass
class KappaResult:
    n_compared: int
    observed_agreement: float
    expected_agreement: float
    kappa: float


def cohen_kappa(pairs: list[tuple[str, str]]) -> KappaResult:
    """pairs: list of (decision_a, decision_b) for the same record, both
    passes present. Implemented from scratch — no sklearn dependency.
    """
    if not pairs:
        return KappaResult(0, 0.0, 0.0, 0.0)
    categories = sorted({c for pair in pairs for c in pair})
    n = len(pairs)
    agree = sum(1 for a, b in pairs if a == b)
    observed = agree / n

    a_counts = {c: 0 for c in categories}
    b_counts = {c: 0 for c in categories}
    for a, b in pairs:
        a_counts[a] += 1
        b_counts[b] += 1
    expected = sum((a_counts[c] / n) * (b_counts[c] / n) for c in categories)

    kappa = 0.0 if expected == 1.0 else (observed - expected) / (1 - expected)
    return KappaResult(n_compared=n, observed_agreement=observed, expected_agreement=expected, kappa=kappa)


def compute_screening_kappa(conn: sqlite3.Connection, stage: str = "title_abstract") -> KappaResult:
    rows = conn.execute(
        "SELECT record_id, pass_label, decision FROM screening_decisions WHERE stage = ? AND pass_label IN ('pass_a','pass_b')",
        (stage,),
    ).fetchall()
    by_record: dict[int, dict[str, str]] = {}
    for r in rows:
        by_record.setdefault(r["record_id"], {})[r["pass_label"]] = r["decision"]
    pairs = [
        (d["pass_a"], d["pass_b"])
        for d in by_record.values()
        if "pass_a" in d and "pass_b" in d
    ]
    return cohen_kappa(pairs)


def export_conflicts(conn: sqlite3.Connection, out_path: str | Path, stage: str = "title_abstract") -> int:
    """Records where pass_a and pass_b disagree and no consensus/human
    decision has been recorded yet. This file is what gate G2 reviews.
    """
    rows = conn.execute(
        """SELECT r.id, r.title, r.abstract,
                  a.decision AS decision_a, a.reason AS reason_a,
                  b.decision AS decision_b, b.reason AS reason_b
           FROM records r
           JOIN screening_decisions a ON a.record_id = r.id AND a.stage = ? AND a.pass_label = 'pass_a'
           JOIN screening_decisions b ON b.record_id = r.id AND b.stage = ? AND b.pass_label = 'pass_b'
           LEFT JOIN screening_decisions c ON c.record_id = r.id AND c.stage = ? AND c.pass_label IN ('consensus','human')
           WHERE a.decision != b.decision AND c.id IS NULL
           ORDER BY r.id""",
        (stage, stage, stage),
    ).fetchall()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["record_id", "title", "abstract", "decision_a", "reason_a", "decision_b", "reason_b", "resolution"])
        for r in rows:
            writer.writerow([
                r["id"], r["title"], (r["abstract"] or "")[:500],
                r["decision_a"], r["reason_a"], r["decision_b"], r["reason_b"], "",
            ])
    return len(rows)


def resolve_conflict(
    conn: sqlite3.Connection,
    record_id: int,
    decision: str,
    reviewer: str,
    reason: str | None = None,
    stage: str = "title_abstract",
) -> None:
    """Records the human's resolution of a pass_a/pass_b conflict as the
    'human' pass — this is what makes _final_decisions() in prisma.py treat
    the record as resolved.
    """
    conn.execute(
        """INSERT INTO screening_decisions
           (record_id, stage, pass_label, decision, reason, reason_code, reviewer, model, prompt_version, decided_at)
           VALUES (?, ?, 'human', ?, ?, NULL, ?, NULL, 'v1', ?)""",
        (record_id, stage, decision, reason, reviewer, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
