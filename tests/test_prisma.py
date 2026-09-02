import sqlite3
from datetime import datetime, timezone

from freemdlabor.db import NormalizedRecord, init_db, insert_records, insert_search_run
from freemdlabor.prisma import compute_counts, render_svg


def _seed_records(conn, n, source="pubmed"):
    run_id = insert_search_run(conn, source, "fake query")
    records = [
        NormalizedRecord(source=source, doi=f"10.1/fake.{i}", title=f"Fake Study {i}", year=2024)
        for i in range(n)
    ]
    insert_records(conn, run_id, records)
    conn.commit()


def _decide(conn, record_id, stage, pass_label, decision, reason_code=None):
    conn.execute(
        """INSERT INTO screening_decisions
           (record_id, stage, pass_label, decision, reason, reason_code, reviewer, model, prompt_version, decided_at)
           VALUES (?, ?, ?, ?, NULL, ?, 'test', NULL, 'v1', ?)""",
        (record_id, stage, pass_label, decision, reason_code, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def test_prisma_counts_basic_flow(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    _seed_records(conn, 5)  # ids 1..5, all canonical (no dedup run -> nothing marked duplicate)

    # Records 1-3: both passes agree "include"; record 4: both agree "exclude";
    # record 5: passes disagree -> unresolved conflict.
    for rid in (1, 2, 3):
        _decide(conn, rid, "title_abstract", "pass_a", "include")
        _decide(conn, rid, "title_abstract", "pass_b", "include")
    _decide(conn, 4, "title_abstract", "pass_a", "exclude", reason_code="wrong_population")
    _decide(conn, 4, "title_abstract", "pass_b", "exclude", reason_code="wrong_population")
    _decide(conn, 5, "title_abstract", "pass_a", "include")
    _decide(conn, 5, "title_abstract", "pass_b", "exclude")

    counts = compute_counts(conn)
    assert counts.identified_total == 5
    assert counts.duplicates_removed == 0
    assert counts.screened == 5
    assert counts.sought_for_retrieval == 3
    assert counts.excluded_at_screening == 1
    assert counts.unresolved_screening_conflicts == 1
    conn.close()


def test_prisma_full_text_eligibility_and_svg(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    _seed_records(conn, 3)
    for rid in (1, 2, 3):
        _decide(conn, rid, "title_abstract", "consensus", "include")
    _decide(conn, 1, "full_text", "human", "include")
    _decide(conn, 2, "full_text", "human", "exclude", reason_code="wrong_outcome")
    _decide(conn, 3, "full_text", "human", "exclude", reason_code="wrong_outcome")

    counts = compute_counts(conn)
    assert counts.assessed_for_eligibility == 3
    assert counts.included == 1
    assert counts.excluded_at_eligibility_total == 2
    assert counts.excluded_at_eligibility_reasons == {"wrong_outcome": 2}

    out = render_svg(counts, tmp_path / "flow.svg", review_title="Fake Review")
    svg_text = out.read_text(encoding="utf-8")
    assert "<svg" in svg_text
    assert "n = 3" in svg_text  # identified count appears somewhere in a box
    conn.close()
