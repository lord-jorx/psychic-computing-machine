import sqlite3

import pytest

from freemdlabor.db import init_db
from freemdlabor.gates import GateError, approve_gate, check_gate_or_fail, gate_status


def test_check_gate_or_fail_raises_when_missing(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    with pytest.raises(GateError):
        check_gate_or_fail(conn, "G1")
    conn.close()


def test_approve_and_check_gate_roundtrip(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    workspace = tmp_path
    artifact = workspace / "protocol.md"
    artifact.write_text("# Fake protocol\nPICO: fake population, fake intervention.", encoding="utf-8")

    record = approve_gate(conn, "G1", artifact, "dr_fake", workspace)
    assert record.status == "approved"
    assert (workspace / "gates" / "gate_G1.approved").exists()

    checked = check_gate_or_fail(conn, "G1")
    assert checked.approved_by == "dr_fake"
    conn.close()


def test_gate_invalidated_if_artifact_changes_after_approval(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    workspace = tmp_path
    artifact = workspace / "protocol.md"
    artifact.write_text("original content", encoding="utf-8")

    approve_gate(conn, "G1", artifact, "dr_fake", workspace)
    artifact.write_text("someone edited the protocol after approval", encoding="utf-8")

    with pytest.raises(GateError):
        check_gate_or_fail(conn, "G1")
    conn.close()


def test_rejected_gate_fails_check(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    workspace = tmp_path
    artifact = workspace / "protocol.md"
    artifact.write_text("draft", encoding="utf-8")

    approve_gate(conn, "G1", artifact, "dr_fake", workspace, status="rejected", notes="not ready")
    status = gate_status(conn, "G1")
    assert status.status == "rejected"
    with pytest.raises(GateError):
        check_gate_or_fail(conn, "G1")
    conn.close()
