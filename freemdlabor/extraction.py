"""Schema-driven data extraction. The schema is locked (extraction/schema.json)
before extraction starts — deciding what to extract after seeing the data
is how outcome-switching creeps into a review.

Every cell is stored with its source quote (Regla 3 in PLAN.md §7): that's
what turns a 30-minute re-read into a 30-second spot check at gate G3.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import RoleConfig
from .prompts.extraction_prompt import build_extraction_prompt
from .providers import call_llm_json


def load_schema(path: str | Path) -> list[dict]:
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    if not isinstance(schema, list) or not all("name" in f for f in schema):
        raise ValueError(f"{path} must be a JSON array of objects each with a 'name' key")
    return schema


def extract_study(
    conn: sqlite3.Connection,
    role_cfg: RoleConfig,
    schema: list[dict],
    record_id: int,
    full_text: str,
) -> dict:
    row = conn.execute("SELECT title FROM records WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise ValueError(f"No record with id {record_id}")

    system, user = build_extraction_prompt(schema, row["title"], full_text)
    result = call_llm_json(role_cfg, system, user, data_sensitivity="public")
    fields = result.get("fields", {})

    now = datetime.now(timezone.utc).isoformat()
    for f in schema:
        name = f["name"]
        cell = fields.get(name, {})
        conn.execute(
            """INSERT INTO extractions (record_id, field_name, value, quote, page, model, extracted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id,
                name,
                _stringify(cell.get("value")),
                cell.get("quote"),
                cell.get("page"),
                role_cfg.model,
                now,
            ),
        )
    conn.commit()
    return fields


def _stringify(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def latest_extractions(conn: sqlite3.Connection, record_id: int) -> dict[str, sqlite3.Row]:
    """Most recent extraction row per field_name for one record (re-running
    extraction on a study should not silently duplicate rows in studies.csv).
    """
    rows = conn.execute(
        "SELECT * FROM extractions WHERE record_id = ? ORDER BY extracted_at",
        (record_id,),
    ).fetchall()
    latest: dict[str, sqlite3.Row] = {}
    for r in rows:
        latest[r["field_name"]] = r  # later rows overwrite earlier ones
    return latest


def export_studies_csv(conn: sqlite3.Connection, schema: list[dict], out_path: str | Path) -> int:
    field_names = [f["name"] for f in schema]
    included_ids = [
        r["id"]
        for r in conn.execute(
            """SELECT DISTINCT record_id AS id FROM screening_decisions
               WHERE stage = 'full_text' AND decision = 'include'"""
        ).fetchall()
    ]

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        header = ["record_id", "title"] + field_names + [f"{name}__verified" for name in field_names]
        writer = csv.writer(f)
        writer.writerow(header)
        for record_id in included_ids:
            title_row = conn.execute("SELECT title FROM records WHERE id = ?", (record_id,)).fetchone()
            extractions = latest_extractions(conn, record_id)
            if not extractions:
                continue
            row = [record_id, title_row["title"]]
            row += [extractions[name]["value"] if name in extractions else None for name in field_names]
            row += [bool(extractions[name]["verified_by"]) if name in extractions else False for name in field_names]
            writer.writerow(row)
            n += 1
    return n


def verify_field(conn: sqlite3.Connection, record_id: int, field_name: str, verified_by: str) -> None:
    """Marks one extracted cell as spot-checked against the source PDF —
    the mechanism behind gate G3 (20% of rows against the original).
    """
    conn.execute(
        """UPDATE extractions SET verified_by = ?, verified_at = ?
           WHERE record_id = ? AND field_name = ?
           AND id = (SELECT id FROM extractions WHERE record_id = ? AND field_name = ? ORDER BY extracted_at DESC LIMIT 1)""",
        (verified_by, datetime.now(timezone.utc).isoformat(), record_id, field_name, record_id, field_name),
    )
    conn.commit()
