import sqlite3

from freemdlabor.db import NormalizedRecord, init_db, insert_records, insert_search_run
from freemdlabor.dedup import deduplicate


def _seed(conn, records):
    run_id = insert_search_run(conn, "pubmed", "fake query")
    insert_records(conn, run_id, records)
    conn.commit()


def test_dedup_exact_doi_match(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    _seed(conn, [
        NormalizedRecord(source="pubmed", doi="10.1001/FAKE.2024.001", title="Fake Trial of Widget X", year=2024),
        NormalizedRecord(source="europepmc", doi="10.1001/fake.2024.001", title="Fake Trial of Widget X (EuropePMC copy)", year=2024),
        NormalizedRecord(source="openalex", doi="10.1001/other.2024.999", title="Unrelated Fake Study", year=2024),
    ])

    stats = deduplicate(conn)
    assert stats.total_records == 3
    assert stats.duplicates_by_doi == 1
    assert stats.canonical_remaining == 2

    rows = conn.execute("SELECT id, duplicate_of, dedup_method FROM records ORDER BY id").fetchall()
    assert rows[0]["duplicate_of"] is None  # canonical (first-seen)
    assert rows[1]["duplicate_of"] == rows[0]["id"]
    assert rows[1]["dedup_method"] == "doi"
    assert rows[2]["duplicate_of"] is None
    conn.close()


def test_dedup_fuzzy_title_within_year(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    _seed(conn, [
        NormalizedRecord(source="pubmed", doi=None, title="Laparoscopic versus open appendectomy: a randomized trial", year=2023),
        NormalizedRecord(source="crossref", doi=None, title="Laparoscopic vs. open appendectomy: a randomized trial", year=2023),
        NormalizedRecord(source="openalex", doi=None, title="Completely different study about wound healing", year=2023),
    ])

    stats = deduplicate(conn, title_threshold=85.0)
    assert stats.duplicates_by_fuzzy_title == 1
    assert stats.canonical_remaining == 2
    conn.close()


def test_dedup_no_false_positive_across_different_years(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    _seed(conn, [
        NormalizedRecord(source="pubmed", doi=None, title="Outcomes after hip fracture surgery", year=2010),
        NormalizedRecord(source="pubmed", doi=None, title="Outcomes after hip fracture surgery", year=2023),
    ])
    # Same title, 13 years apart — the year-block window (+/-1) must not merge these.
    stats = deduplicate(conn)
    assert stats.canonical_remaining == 2
    conn.close()
