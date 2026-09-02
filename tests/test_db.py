from freemdlabor.db import (
    NormalizedRecord,
    canonical_records,
    init_db,
    insert_records,
    insert_search_run,
)


def test_init_db_creates_all_tables(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    expected = {
        "search_runs", "records", "screening_decisions", "extractions",
        "bias_assessments", "provenance", "gates",
    }
    assert expected.issubset(tables)
    conn.close()


def test_insert_search_run_and_records_roundtrip(tmp_path):
    import sqlite3

    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row

    run_id = insert_search_run(conn, "pubmed", "appendectomy AND laparoscopic")
    records = [
        NormalizedRecord(source="pubmed", source_id="123", doi="10.1/abc", title="Fake Study One"),
        NormalizedRecord(source="pubmed", source_id="456", doi="10.1/def", title="Fake Study Two"),
    ]
    n = insert_records(conn, run_id, records)
    assert n == 2

    canon = canonical_records(conn)
    assert len(canon) == 2
    titles = {r["title"] for r in canon}
    assert titles == {"Fake Study One", "Fake Study Two"}

    run_row = conn.execute("SELECT result_count FROM search_runs WHERE id = ?", (run_id,)).fetchone()
    assert run_row["result_count"] == 2
    conn.close()
