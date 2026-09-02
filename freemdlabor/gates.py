"""Mandatory human gates — PLAN.md §9.

A gate is a row in the `gates` table plus a `gate_<ID>.approved` marker
file, both recording the sha256 of whatever artifact was reviewed. Nothing
here can be satisfied programmatically by an agent: approve_gate() takes
`approved_by`, and the .claude/commands/gate.md slash command is the only
sanctioned way an agent should ever call it — by relaying an explicit
human decision, never on its own initiative.

check_gate_or_fail() is what the next pipeline stage calls before doing
anything: no gate file, no proceeding.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

GATE_IDS = ("G1", "G2", "G3", "G4", "G5")

GATE_DESCRIPTIONS = {
    "G1": "Protocolo — PICO, criterios, estrategia de búsqueda, plan de análisis",
    "G2": "Conflictos de cribado — desacuerdos entre pases + muestra de acuerdos",
    "G3": "Extracción — 20% de las filas contra el PDF original",
    "G4": "Interpretación — conclusiones acordes al I² y a la certeza GRADE",
    "G5": "Firma — manuscrito, checklist, declaración de IA, autoría ICMJE",
}


class GateError(RuntimeError):
    pass


@dataclass
class GateRecord:
    gate_id: str
    status: str
    artifact_path: str
    artifact_sha256: str
    approved_by: str
    notes: Optional[str]
    decided_at: str


def _sha256_of(path: str | Path) -> str:
    path = Path(path)
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def approve_gate(
    conn: sqlite3.Connection,
    gate_id: str,
    artifact_path: str | Path,
    approved_by: str,
    workspace_dir: str | Path,
    notes: Optional[str] = None,
    status: str = "approved",
) -> GateRecord:
    if gate_id not in GATE_IDS:
        raise ValueError(f"Unknown gate '{gate_id}'. Expected one of {GATE_IDS}")
    if status not in ("approved", "rejected"):
        raise ValueError("status must be 'approved' or 'rejected'")

    artifact_path = Path(artifact_path)
    if not artifact_path.exists():
        raise GateError(f"Artifact for gate {gate_id} does not exist: {artifact_path}")

    sha = _sha256_of(artifact_path)
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO gates (gate_id, status, artifact_path, artifact_sha256, approved_by, notes, decided_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(gate_id) DO UPDATE SET
             status=excluded.status, artifact_path=excluded.artifact_path,
             artifact_sha256=excluded.artifact_sha256, approved_by=excluded.approved_by,
             notes=excluded.notes, decided_at=excluded.decided_at""",
        (gate_id, status, str(artifact_path), sha, approved_by, notes, now),
    )
    conn.commit()

    marker = Path(workspace_dir) / "gates" / f"gate_{gate_id}.approved"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "gate_id": gate_id,
                "status": status,
                "artifact_path": str(artifact_path),
                "artifact_sha256": sha,
                "approved_by": approved_by,
                "notes": notes,
                "decided_at": now,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return GateRecord(gate_id, status, str(artifact_path), sha, approved_by, notes, now)


def gate_status(conn: sqlite3.Connection, gate_id: str) -> Optional[GateRecord]:
    row = conn.execute("SELECT * FROM gates WHERE gate_id = ?", (gate_id,)).fetchone()
    if row is None:
        return None
    return GateRecord(
        gate_id=row["gate_id"], status=row["status"], artifact_path=row["artifact_path"],
        artifact_sha256=row["artifact_sha256"], approved_by=row["approved_by"],
        notes=row["notes"], decided_at=row["decided_at"],
    )


def check_gate_or_fail(conn: sqlite3.Connection, gate_id: str) -> GateRecord:
    """Call this at the top of any step that a gate protects. Raises if the
    gate is missing, rejected, or if the underlying artifact has changed
    since approval (someone edited protocol.md after G1, say)."""
    record = gate_status(conn, gate_id)
    if record is None:
        raise GateError(
            f"Gate {gate_id} ({GATE_DESCRIPTIONS.get(gate_id, '')}) has not been approved yet. "
            f"Run the matching .claude/commands/gate.md step, or "
            f"`python -m freemdlabor gate approve {gate_id} <artifact> --by <name>`."
        )
    if record.status != "approved":
        raise GateError(f"Gate {gate_id} was explicitly rejected by {record.approved_by} at {record.decided_at}.")

    current_sha = _sha256_of(record.artifact_path)
    if current_sha != record.artifact_sha256:
        raise GateError(
            f"Gate {gate_id} was approved for a DIFFERENT version of {record.artifact_path} "
            f"(hash mismatch). The artifact changed after approval — re-run the gate."
        )
    return record


def all_gates_status(conn: sqlite3.Connection) -> dict[str, Optional[GateRecord]]:
    return {gid: gate_status(conn, gid) for gid in GATE_IDS}
