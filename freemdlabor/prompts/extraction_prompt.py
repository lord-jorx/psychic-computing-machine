"""Prompt builder for ExtractionAgent. Every field must come with a verbatim
quote — this is what makes gate G3 (spot-check 20% against the PDF) fast
instead of a full re-read, and it's what integrity.py's provenance check
ultimately traces manuscript numbers back to.
"""

from __future__ import annotations

import json

EXTRACTION_SYSTEM_TEMPLATE = """You are extracting structured data from ONE study's full text for a \
systematic review / meta-analysis. Extract ONLY what this document states — never infer, \
estimate, or fill in a plausible-looking number that is not written in the text.

For each field below, extract:
- "value": the extracted value (or null if not reported in this document — do not guess)
- "quote": the EXACT verbatim sentence(s) from the text that this value comes from (or null if value is null)
- "page": a page number or section name if identifiable, else null

Fields to extract:
{fields_block}

Respond with ONLY a JSON object, no markdown fence:
{{"fields": {{"<field_name>": {{"value": ..., "quote": "...", "page": "..."}}, ...}}}}
"""

USER_TEMPLATE = """Study title: {title}

Full text:
{full_text}
"""


def build_extraction_prompt(schema: list[dict], title: str, full_text: str) -> tuple[str, str]:
    fields_block = "\n".join(
        f"- {f['name']} ({f.get('type', 'string')}): {f.get('description', '')}" for f in schema
    )
    system = EXTRACTION_SYSTEM_TEMPLATE.format(fields_block=fields_block)
    user = USER_TEMPLATE.format(title=title, full_text=full_text)
    return system, user
