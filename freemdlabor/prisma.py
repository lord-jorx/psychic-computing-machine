"""PRISMA 2020 flow counts and diagram — computed from review.sqlite, never
typed by hand or recalled from an agent's memory.

Screening/eligibility decisions can have two independent passes (pass_a,
pass_b) plus a human resolution. `_final_decisions` picks, per record: a
recorded consensus/human decision if present, else the two passes if they
agree, else "unresolved" (which counts as still-pending, not as a silent
include or exclude — an unresolved conflict must show up in G2, not
disappear into a total).
"""

from __future__ import annotations

import json
import sqlite3
import textwrap
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PrismaCounts:
    identified_total: int
    identified_by_source: dict[str, int]
    duplicates_removed: int
    screened: int
    excluded_at_screening: int
    unresolved_screening_conflicts: int
    sought_for_retrieval: int
    not_retrieved: int
    assessed_for_eligibility: int
    excluded_at_eligibility_total: int
    excluded_at_eligibility_reasons: dict[str, int]
    unresolved_eligibility_conflicts: int
    included: int

    def to_dict(self) -> dict:
        return {
            "identified_total": self.identified_total,
            "identified_by_source": self.identified_by_source,
            "duplicates_removed": self.duplicates_removed,
            "screened": self.screened,
            "excluded_at_screening": self.excluded_at_screening,
            "unresolved_screening_conflicts": self.unresolved_screening_conflicts,
            "sought_for_retrieval": self.sought_for_retrieval,
            "not_retrieved": self.not_retrieved,
            "assessed_for_eligibility": self.assessed_for_eligibility,
            "excluded_at_eligibility_total": self.excluded_at_eligibility_total,
            "excluded_at_eligibility_reasons": self.excluded_at_eligibility_reasons,
            "unresolved_eligibility_conflicts": self.unresolved_eligibility_conflicts,
            "included": self.included,
        }


def _final_decisions(conn: sqlite3.Connection, stage: str) -> tuple[dict[int, dict], int]:
    """One resolved decision per record_id for the given stage, or omitted
    entirely if still unresolved (two passes disagree and no consensus/
    human decision has been recorded yet).
    """
    rows = conn.execute(
        "SELECT record_id, pass_label, decision, reason_code FROM screening_decisions WHERE stage = ?",
        (stage,),
    ).fetchall()

    by_record: dict[int, dict[str, dict]] = {}
    for r in rows:
        by_record.setdefault(r["record_id"], {})[r["pass_label"]] = {
            "decision": r["decision"],
            "reason_code": r["reason_code"],
        }

    resolved: dict[int, dict] = {}
    for record_id, passes in by_record.items():
        if "consensus" in passes:
            resolved[record_id] = passes["consensus"]
        elif "human" in passes:
            resolved[record_id] = passes["human"]
        elif "pass_a" in passes and "pass_b" in passes:
            if passes["pass_a"]["decision"] == passes["pass_b"]["decision"]:
                resolved[record_id] = passes["pass_a"]
            # else: unresolved conflict, intentionally excluded from `resolved`
        elif "pass_a" in passes and "pass_b" not in passes:
            pass  # single pass so far, not yet resolvable
        elif "pass_b" in passes and "pass_a" not in passes:
            pass
    unresolved_count = 0
    for record_id, passes in by_record.items():
        if record_id in resolved:
            continue
        if "pass_a" in passes and "pass_b" in passes and passes["pass_a"]["decision"] != passes["pass_b"]["decision"]:
            unresolved_count += 1

    return resolved, unresolved_count


def compute_counts(conn: sqlite3.Connection) -> PrismaCounts:
    identified_total = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    by_source_rows = conn.execute("SELECT source, COUNT(*) AS n FROM records GROUP BY source").fetchall()
    identified_by_source = {r["source"]: r["n"] for r in by_source_rows}

    duplicates_removed = conn.execute(
        "SELECT COUNT(*) FROM records WHERE duplicate_of IS NOT NULL"
    ).fetchone()[0]

    screened = identified_total - duplicates_removed

    ta_resolved, ta_unresolved = _final_decisions(conn, "title_abstract")
    sought = sum(1 for d in ta_resolved.values() if d["decision"] == "include")
    excluded_at_screening = sum(1 for d in ta_resolved.values() if d["decision"] == "exclude")

    ft_resolved, ft_unresolved = _final_decisions(conn, "full_text")
    assessed = len(ft_resolved)
    included = sum(1 for d in ft_resolved.values() if d["decision"] == "include")
    excluded_reasons: dict[str, int] = {}
    excluded_total = 0
    for d in ft_resolved.values():
        if d["decision"] == "exclude":
            excluded_total += 1
            code = d["reason_code"] or "unspecified"
            excluded_reasons[code] = excluded_reasons.get(code, 0) + 1

    not_retrieved = max(0, sought - assessed - ta_unresolved) if sought else 0
    # not_retrieved is a lower bound: full-text records genuinely unobtainable
    # (paywalled, no OA copy) should instead be logged explicitly as
    # full_text decisions with reason_code="not_retrieved" via ScreeningAgent;
    # this fallback only covers the gap when that hasn't been done yet.
    not_retrieved_explicit = excluded_reasons.pop("not_retrieved", 0)
    not_retrieved = not_retrieved_explicit or not_retrieved

    return PrismaCounts(
        identified_total=identified_total,
        identified_by_source=identified_by_source,
        duplicates_removed=duplicates_removed,
        screened=screened,
        excluded_at_screening=excluded_at_screening,
        unresolved_screening_conflicts=ta_unresolved,
        sought_for_retrieval=sought,
        not_retrieved=not_retrieved,
        assessed_for_eligibility=assessed,
        excluded_at_eligibility_total=excluded_total,
        excluded_at_eligibility_reasons=excluded_reasons,
        unresolved_eligibility_conflicts=ft_unresolved,
        included=included,
    )


# ---------------------------------------------------------------- SVG ----

_FONT = "IBM Plex Sans, Helvetica, Arial, sans-serif"
_MONO = "IBM Plex Mono, ui-monospace, monospace"


@dataclass
class _Box:
    x: int
    y: int
    w: int
    lines: list[str]
    fill: str = "#FFFFFF"
    stroke: str = "#1F2937"
    text_color: str = "#111827"
    line_h: int = 18
    pad: int = 14

    @property
    def h(self) -> int:
        return self.pad * 2 + self.line_h * len(self.lines)

    def svg(self) -> str:
        rect = (
            f'<rect x="{self.x}" y="{self.y}" width="{self.w}" height="{self.h}" '
            f'rx="4" fill="{self.fill}" stroke="{self.stroke}" stroke-width="1.5"/>'
        )
        texts = []
        for i, line in enumerate(self.lines):
            ty = self.y + self.pad + self.line_h * i + self.line_h * 0.72
            weight = "600" if i == 0 else "400"
            texts.append(
                f'<text x="{self.x + self.w / 2}" y="{ty}" font-family="{_FONT}" '
                f'font-size="13" font-weight="{weight}" fill="{self.text_color}" '
                f'text-anchor="middle">{_esc(line)}</text>'
            )
        return rect + "".join(texts)

    def cx(self) -> int:
        return self.x + self.w // 2

    def bottom(self) -> int:
        return self.y + self.h

    def right(self) -> int:
        return self.x + self.w


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _wrap(label: str, value_line: str, width_chars: int = 42) -> list[str]:
    lines = [label]
    lines.extend(textwrap.wrap(value_line, width=width_chars) or [value_line])
    return lines


def render_svg(counts: PrismaCounts, out_path: str | Path, review_title: str = "") -> Path:
    out_path = Path(out_path)
    main_w = 420
    side_w = 300
    main_x = 60
    side_x = main_x + main_w + 60
    y = 30
    gap = 34

    boxes: list[_Box] = []
    arrows: list[tuple[_Box, _Box]] = []
    side_links: list[tuple[_Box, _Box]] = []

    by_source = ", ".join(f"{v} {k}" for k, v in sorted(counts.identified_by_source.items()))
    b_identified = _Box(main_x, y, main_w, _wrap(
        "Identificación",
        f"Registros identificados en bases de datos (n = {counts.identified_total}) — {by_source}",
    ), fill="#F0F9F6")
    boxes.append(b_identified)
    y = b_identified.bottom() + gap

    b_dupes_removed = _Box(main_x, y, main_w, _wrap(
        "Cribado",
        f"Registros tras eliminar duplicados (n = {counts.screened}) — "
        f"{counts.duplicates_removed} duplicados eliminados",
    ), fill="#F0F9F6")
    boxes.append(b_dupes_removed)
    arrows.append((b_identified, b_dupes_removed))
    y = b_dupes_removed.bottom() + gap

    b_screened = _Box(main_x, y, main_w, _wrap(
        "",
        f"Registros cribados por título/resumen (n = {counts.screened})",
    ), fill="#F0F9F6")
    boxes.append(b_screened)
    arrows.append((b_dupes_removed, b_screened))

    exclusion_lines = [f"Excluidos (n = {counts.excluded_at_screening})"]
    if counts.unresolved_screening_conflicts:
        exclusion_lines.append(f"Conflictos sin resolver: {counts.unresolved_screening_conflicts} — puerta G2")
    b_excl_screen = _Box(side_x, b_screened.y, side_w, exclusion_lines, fill="#FDF1EC", stroke="#A6482F")
    boxes.append(b_excl_screen)
    side_links.append((b_screened, b_excl_screen))
    y = b_screened.bottom() + gap

    b_sought = _Box(main_x, y, main_w, _wrap(
        "",
        f"Informes buscados a texto completo (n = {counts.sought_for_retrieval})",
    ), fill="#F0F9F6")
    boxes.append(b_sought)
    arrows.append((b_screened, b_sought))

    if counts.not_retrieved:
        b_not_retrieved = _Box(
            side_x, b_sought.y, side_w,
            [f"No recuperados (n = {counts.not_retrieved})"],
            fill="#FDF1EC", stroke="#A6482F",
        )
        boxes.append(b_not_retrieved)
        side_links.append((b_sought, b_not_retrieved))
    y = b_sought.bottom() + gap

    b_assessed = _Box(main_x, y, main_w, _wrap(
        "",
        f"Informes evaluados para elegibilidad (n = {counts.assessed_for_eligibility})",
    ), fill="#F0F9F6")
    boxes.append(b_assessed)
    arrows.append((b_sought, b_assessed))

    excl_elig_lines = [f"Informes excluidos (n = {counts.excluded_at_eligibility_total})"]
    for reason, n in sorted(counts.excluded_at_eligibility_reasons.items(), key=lambda kv: -kv[1]):
        excl_elig_lines.append(f"· {reason}: {n}")
    if counts.unresolved_eligibility_conflicts:
        excl_elig_lines.append(f"Conflictos sin resolver: {counts.unresolved_eligibility_conflicts}")
    b_excl_elig = _Box(side_x, b_assessed.y, side_w, excl_elig_lines, fill="#FDF1EC", stroke="#A6482F")
    boxes.append(b_excl_elig)
    side_links.append((b_assessed, b_excl_elig))
    y = b_assessed.bottom() + gap

    b_included = _Box(main_x, y, main_w, _wrap(
        "Incluidos",
        f"Estudios incluidos en la revisión (n = {counts.included})",
    ), fill="#DAEBE6", stroke="#0E6E62")
    boxes.append(b_included)
    arrows.append((b_assessed, b_included))
    y = b_included.bottom() + 30

    canvas_w = side_x + side_w + 40
    canvas_h = y + 20

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {canvas_w} {canvas_h}" '
        f'width="{canvas_w}" height="{canvas_h}" font-family="{_FONT}">',
        f'<rect x="0" y="0" width="{canvas_w}" height="{canvas_h}" fill="#FFFFFF"/>',
    ]
    if review_title:
        parts.append(
            f'<text x="{main_x}" y="20" font-family="{_MONO}" font-size="12" '
            f'fill="#6C7D77">{_esc(review_title)} · diagrama de flujo PRISMA 2020</text>'
        )

    marker = (
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#1F2937"/></marker></defs>'
    )
    parts.append(marker)

    for a, b in arrows:
        x = a.cx()
        parts.append(
            f'<line x1="{x}" y1="{a.bottom()}" x2="{x}" y2="{b.y}" '
            f'stroke="#1F2937" stroke-width="1.5" marker-end="url(#arrow)"/>'
        )
    for a, b in side_links:
        y_mid = a.y + a.h / 2
        parts.append(
            f'<line x1="{a.right()}" y1="{y_mid}" x2="{b.x}" y2="{y_mid}" '
            f'stroke="#A6482F" stroke-width="1.5" marker-end="url(#arrow)"/>'
        )

    for box in boxes:
        parts.append(box.svg())

    parts.append("</svg>")
    svg = "\n".join(parts)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    return out_path


def write_counts_json(counts: PrismaCounts, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(counts.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path
