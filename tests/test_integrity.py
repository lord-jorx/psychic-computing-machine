import sqlite3

import pytest

import freemdlabor.integrity as integrity
from freemdlabor.db import init_db


def test_check_provenance_flags_missing_tag(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    integrity.add_provenance(conn, "ssi_or", "OR 0.62", "analysis", "results_ssi.json:estimate_exp")

    manuscript = tmp_path / "main.tex"
    manuscript.write_text(
        r"""
        The pooled odds ratio was 0.62 (95\% CI 0.44-0.87) \provenance{ssi_or}.
        A second, un-sourced claim states an unrelated 42% result with no tag.
        """,
        encoding="utf-8",
    )

    report = integrity.check_provenance(conn, manuscript)
    assert report.referenced == {"ssi_or"}
    assert report.missing_from_db == set()
    assert report.ok
    # the second numeric-looking line has no \provenance{} tag -> flagged as a warning
    assert any("42%" in snippet for _, snippet in report.unprovenanced_numeric_claims)
    conn.close()


def test_check_provenance_or_fail_raises_on_unresolved_tag(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    manuscript = tmp_path / "main.tex"
    manuscript.write_text(r"An orphan claim \provenance{never_recorded}.", encoding="utf-8")

    with pytest.raises(integrity.IntegrityError):
        integrity.check_provenance_or_fail(conn, manuscript)
    conn.close()


def test_add_provenance_rejects_unknown_source_table(tmp_path):
    conn = init_db(tmp_path / "review.sqlite")
    conn.row_factory = sqlite3.Row
    with pytest.raises(ValueError):
        integrity.add_provenance(conn, "x", "1", "not_a_real_table", "1")
    conn.close()


def test_check_citations_or_fail_no_doi(tmp_path, monkeypatch):
    bib = tmp_path / "references.bib"
    bib.write_text(
        r"""
        @article{no_doi_entry,
          title = {A fake entry with no DOI at all},
          year = {2024}
        }
        """,
        encoding="utf-8",
    )
    with pytest.raises(integrity.IntegrityError, match="no_doi"):
        integrity.check_citations_or_fail(bib)


def test_check_citations_or_fail_passes_when_doi_resolves(tmp_path, monkeypatch):
    bib = tmp_path / "references.bib"
    bib.write_text(
        r"""
        @article{fake_but_resolves,
          title = {A Fake Study About Widgets},
          doi = {10.1001/fake.2024.001},
          year = {2024}
        }
        """,
        encoding="utf-8",
    )

    def fake_resolve_doi(doi):
        return {"title": ["A Fake Study About Widgets"], "DOI": doi}

    monkeypatch.setattr(integrity, "crossref_resolve_doi", fake_resolve_doi)
    results = integrity.check_citations_or_fail(bib)
    assert len(results) == 1
    assert results[0].resolved is True
    assert results[0].title_mismatch is False
