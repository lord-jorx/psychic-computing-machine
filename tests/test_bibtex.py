from freemdlabor.bibtex import parse_bibtex

SAMPLE = r"""
@article{fake_key_2024,
  title = {A {Fake} Study About Widgets},
  author = {Doe, Jane and Smith, John},
  doi = {10.1001/fake.2024.001},
  journal = {Journal of Fake Studies},
  year = {2024},
}

@article{another_fake,
  title = "A second fake entry, with a comma in the title",
  doi = {10.1001/fake.2024.002},
  year = {2023}
}
"""


def test_parse_bibtex_extracts_entries_and_fields():
    entries = parse_bibtex(SAMPLE)
    assert len(entries) == 2

    first = entries[0]
    assert first["type"] == "article"
    assert first["key"] == "fake_key_2024"
    assert first["fields"]["doi"] == "10.1001/fake.2024.001"
    # this reader only balances braces to find field boundaries — it does not
    # strip BibTeX's capitalization-protection braces from the value, that's
    # a deliberate non-goal (see the module docstring)
    assert first["fields"]["title"] == "A {Fake} Study About Widgets"
    assert first["fields"]["year"] == "2024"

    second = entries[1]
    assert second["key"] == "another_fake"
    assert second["fields"]["title"] == "A second fake entry, with a comma in the title"
    assert second["fields"]["doi"] == "10.1001/fake.2024.002"


def test_parse_bibtex_handles_no_entries_gracefully():
    assert parse_bibtex("just some prose, no @ entries here") == []
