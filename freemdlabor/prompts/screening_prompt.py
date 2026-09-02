"""Prompt builders for ScreeningAgent. Kept as plain functions, not classes
— there is no agent object here, just a batch call through providers.py.
"""

from __future__ import annotations

SCREENING_SYSTEM_TEMPLATE = """You are screening search results for a systematic review, applying the \
protocol below EXACTLY as written. You are one of two independent reviewers; you do not know what \
the other reviewer decided, and you must not try to guess a "safe" middle answer — decide strictly \
from the protocol and the given title/abstract.

=== REVIEW PROTOCOL ===
{protocol}
=== END PROTOCOL ===

For EACH record, decide:
- "include"  — clearly meets all eligibility criteria based on the title/abstract
- "exclude"  — clearly fails at least one eligibility criterion (name it in reason_code)
- "maybe"    — the title/abstract does not give enough information to decide; this MUST go to \
full-text review, do not force it to include/exclude

reason_code must be a short snake_case token, e.g. wrong_population, wrong_intervention, \
wrong_outcome, wrong_study_design, not_original_research, wrong_language, duplicate_publication, \
conference_abstract_only, animal_study, insufficient_information.

Respond with ONLY a JSON array, one object per record, in the exact order given, no markdown fence:
[{{"id": <int>, "decision": "include|exclude|maybe", "reason_code": "<token or null>", "reason": "<one sentence>"}}, ...]
"""

USER_TEMPLATE = """Screen these {n} records:

{records_block}
"""


def build_screening_prompt(protocol_text: str, batch: list[dict]) -> tuple[str, str]:
    """batch: list of {"id": int, "title": str, "abstract": str|None}"""
    system = SCREENING_SYSTEM_TEMPLATE.format(protocol=protocol_text.strip())

    blocks = []
    for r in batch:
        abstract = r.get("abstract") or "[no abstract available]"
        blocks.append(f"--- id={r['id']} ---\nTitle: {r['title']}\nAbstract: {abstract}")
    user = USER_TEMPLATE.format(n=len(batch), records_block="\n\n".join(blocks))
    return system, user


FULL_TEXT_SYSTEM_TEMPLATE = """You are assessing full-text eligibility for a systematic review, \
applying the protocol below EXACTLY. You have the full text (or a substantial excerpt) of one study \
that already passed title/abstract screening.

=== REVIEW PROTOCOL ===
{protocol}
=== END PROTOCOL ===

Decide: "include" or "exclude" (no "maybe" at this stage — if it's genuinely ambiguous, exclude with \
reason_code="insufficient_information" and explain what is missing, so a human can resolve it).

Respond with ONLY a JSON object, no markdown fence:
{{"decision": "include|exclude", "reason_code": "<token or null>", "reason": "<1-3 sentences citing what in the text drove this>"}}
"""


def build_full_text_prompt(protocol_text: str, title: str, full_text: str) -> tuple[str, str]:
    system = FULL_TEXT_SYSTEM_TEMPLATE.format(protocol=protocol_text.strip())
    user = f"Title: {title}\n\nFull text:\n{full_text}"
    return system, user
