"""A small, dependency-free BibTeX reader — just enough to pull key/type/
fields back out of entries this pipeline (or a human) wrote. No attempt at
full BibTeX-the-language (string macros, @comment, crossref inheritance);
if you need that, this is the seam to swap in a real parser.
"""

from __future__ import annotations

from typing import Any


def parse_bibtex(text: str) -> list[dict[str, Any]]:
    entries = []
    i, n = 0, len(text)
    while True:
        at = text.find("@", i)
        if at == -1:
            break
        brace = text.find("{", at)
        if brace == -1:
            break
        etype = text[at + 1 : brace].strip().lower()
        if etype in ("comment", "string", "preamble"):
            # skip past this construct's balanced braces without treating it as an entry
            _, j = _read_braced(text, brace)
            i = j
            continue
        body, j = _read_braced(text, brace)
        comma = body.find(",")
        if comma == -1:
            i = j
            continue
        key = body[:comma].strip()
        fields = _parse_fields(body[comma + 1 :])
        entries.append({"type": etype, "key": key, "fields": fields})
        i = j
    return entries


def _read_braced(text: str, open_brace_idx: int) -> tuple[str, int]:
    """text[open_brace_idx] == '{'. Returns (contents, index just past the
    matching closing brace)."""
    depth = 1
    j = open_brace_idx + 1
    n = len(text)
    while j < n and depth > 0:
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
        j += 1
    return text[open_brace_idx + 1 : j - 1], j


def _parse_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\n\r,":
            i += 1
        if i >= n:
            break
        eq = text.find("=", i)
        if eq == -1:
            break
        name = text[i:eq].strip().lower()
        i = eq + 1
        while i < n and text[i] in " \t\n\r":
            i += 1
        if i < n and text[i] == "{":
            value, i = _read_braced(text, i)
        elif i < n and text[i] == '"':
            j = text.find('"', i + 1)
            if j == -1:
                j = n
            value = text[i + 1 : j]
            i = j + 1
        else:
            j = text.find(",", i)
            if j == -1:
                j = n
            value = text[i:j].strip()
            i = j
        fields[name] = " ".join(value.split())
    return fields
