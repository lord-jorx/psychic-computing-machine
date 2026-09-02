"""Single entry point: python -m freemdlabor <command> ...

This is the whole "orchestrator" for Vía A (see PLAN.md §4) — there is no
agent loop here. A human, driving Claude Code, calls these subcommands
directly or through the matching .claude/commands/*.md slash command, and
Claude Code supplies the judgment steps in between as ordinary conversation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import dedup as dedup_mod
from . import extraction as extraction_mod
from . import gates as gates_mod
from . import integrity as integrity_mod
from . import prisma as prisma_mod
from . import screening as screening_mod
from .config import load_config
from .db import connect, export_bias_csv, init_db, insert_bias_assessment, insert_records, insert_search_run
from .search import SOURCES


def _db_path(workspace: str) -> Path:
    return Path(workspace) / "review.sqlite"


def _config_path(workspace: str) -> Path:
    p = Path(workspace) / "config.yaml"
    return p if p.exists() else Path("config.yaml")


def _read_protocol(workspace: str, protocol_path: str | None) -> str:
    path = Path(protocol_path) if protocol_path else Path(workspace) / "protocol.md"
    if not path.exists():
        raise SystemExit(f"Protocol file not found: {path}. Run 'freemdlabor init' first, or pass --protocol.")
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------- init ----

def cmd_init(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    init_db(_db_path(workspace))

    protocol_path = workspace / "protocol.md"
    if not protocol_path.exists():
        protocol_path.write_text(_PROTOCOL_TEMPLATE, encoding="utf-8")

    for sub in ("search", "screening", "extraction", "analysis", "manuscript", "gates"):
        (workspace / sub).mkdir(exist_ok=True)

    schema_path = workspace / "extraction" / "schema.json"
    if not schema_path.exists():
        schema_path.write_text(json.dumps(_SCHEMA_TEMPLATE, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Workspace initialized at {workspace}")
    print(f"  Next: edit {protocol_path} (PICO, criteria, search strategy), then run gate G1.")
    return 0


_PROTOCOL_TEMPLATE = """# Protocolo de revisión — [título provisional]

## Pregunta (PICO / PICOTS)
- Población:
- Intervención:
- Comparación:
- Desenlaces (primario / secundarios):
- Diseño de estudio elegible:
- (Si aplica) Horizonte temporal / entorno:

## Criterios de inclusión
-

## Criterios de exclusión
-

## Estrategia de búsqueda
- Bases de datos: PubMed, Europe PMC, ClinicalTrials.gov, OpenAlex (+ Embase/CENTRAL manual si hay acceso)
- Cadena de búsqueda (PubMed):
- Límites de fecha / idioma:

## Plan de análisis
- Medida de efecto:
- Modelo (efectos aleatorios / fijos):
- Análisis de subgrupos previstos:
- Análisis de sensibilidad previstos:
- Umbral de heterogeneidad (I²) que motivaría no combinar:

## Registro
- PROSPERO ID:
"""

_SCHEMA_TEMPLATE = [
    {"name": "design", "type": "string", "description": "Study design (RCT, cohort, case-control, ...)"},
    {"name": "country", "type": "string", "description": "Country/countries where the study was conducted"},
    {"name": "n_intervention", "type": "integer", "description": "Sample size, intervention/exposed arm"},
    {"name": "n_control", "type": "integer", "description": "Sample size, control/comparison arm"},
    {"name": "primary_outcome_definition", "type": "string", "description": "Exact definition of the primary outcome as stated"},
]


# ------------------------------------------------------------- search ----

def cmd_search(args: argparse.Namespace) -> int:
    if args.source not in SOURCES:
        raise SystemExit(f"Unknown source '{args.source}'. Options: {sorted(SOURCES)}")
    fn = SOURCES[args.source]
    print(f"Searching {args.source} for: {args.query!r} (max {args.max_results})")
    records = fn(args.query, max_results=args.max_results)
    print(f"  {len(records)} records returned")

    with connect(_db_path(args.workspace)) as conn:
        run_id = insert_search_run(conn, args.source, args.query)
        n = insert_records(conn, run_id, records)
        conn.commit()
    print(f"  Inserted {n} records into review.sqlite (search_run_id={run_id})")
    return 0


# -------------------------------------------------------------- dedup ----

def cmd_dedup(args: argparse.Namespace) -> int:
    config = load_config(_config_path(args.workspace))
    threshold = args.threshold if args.threshold is not None else config.dedup_title_threshold
    with connect(_db_path(args.workspace)) as conn:
        stats = dedup_mod.deduplicate(conn, title_threshold=threshold)
    print(f"Total records:              {stats.total_records}")
    print(f"  Duplicates by DOI:        {stats.duplicates_by_doi}")
    print(f"  Duplicates by PMID:       {stats.duplicates_by_pmid}")
    print(f"  Duplicates by fuzzy title (>= {threshold}): {stats.duplicates_by_fuzzy_title}")
    print(f"Canonical records remaining: {stats.canonical_remaining}")
    return 0


# -------------------------------------------------------------- prisma ---

def cmd_prisma(args: argparse.Namespace) -> int:
    with connect(_db_path(args.workspace)) as conn:
        counts = prisma_mod.compute_counts(conn)
    out_dir = Path(args.workspace) / "prisma"
    json_path = prisma_mod.write_counts_json(counts, out_dir / "counts.json")
    svg_path = prisma_mod.render_svg(counts, out_dir / "flow_diagram.svg", review_title=args.title or "")
    print(json.dumps(counts.to_dict(), indent=2, ensure_ascii=False))
    print(f"\nWrote {json_path}")
    print(f"Wrote {svg_path}")
    return 0


# ------------------------------------------------------------ screen -----

def cmd_screen_title_abstract(args: argparse.Namespace) -> int:
    config = load_config(_config_path(args.workspace))
    role_cfg = config.role(args.role)
    protocol = _read_protocol(args.workspace, args.protocol)
    with connect(_db_path(args.workspace)) as conn:
        n = screening_mod.run_title_abstract_pass(
            conn, role_cfg, protocol, args.pass_label,
            batch_size=args.batch_size or config.screening_batch_size,
        )
    print(f"Decided {n} records for pass '{args.pass_label}' using role '{args.role}' ({role_cfg.provider}/{role_cfg.model}).")
    return 0


def cmd_screen_full_text(args: argparse.Namespace) -> int:
    config = load_config(_config_path(args.workspace))
    role_cfg = config.role(args.role)
    protocol = _read_protocol(args.workspace, args.protocol)
    full_text = Path(args.full_text_file).read_text(encoding="utf-8")
    with connect(_db_path(args.workspace)) as conn:
        result = screening_mod.run_full_text_pass(
            conn, role_cfg, protocol, args.record_id, full_text, pass_label=args.pass_label
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_screen_kappa(args: argparse.Namespace) -> int:
    with connect(_db_path(args.workspace)) as conn:
        result = screening_mod.compute_screening_kappa(conn, stage=args.stage)
    print(f"n compared:          {result.n_compared}")
    print(f"observed agreement:  {result.observed_agreement:.3f}")
    print(f"expected agreement:  {result.expected_agreement:.3f}")
    print(f"Cohen's kappa:       {result.kappa:.3f}")
    config = load_config(_config_path(args.workspace))
    if result.kappa < config.screening_kappa_threshold:
        print(
            f"\nWARNING: kappa {result.kappa:.3f} is below the configured threshold "
            f"({config.screening_kappa_threshold}). Do not trust automated screening at scale "
            f"until this is investigated — see PLAN.md F2 (calibration against 100 manual records)."
        )
    return 0


def cmd_screen_conflicts(args: argparse.Namespace) -> int:
    out_path = Path(args.workspace) / "screening" / f"conflicts_{args.stage}.csv"
    with connect(_db_path(args.workspace)) as conn:
        n = screening_mod.export_conflicts(conn, out_path, stage=args.stage)
    print(f"Wrote {n} conflicts to {out_path}")
    return 0


def cmd_screen_resolve(args: argparse.Namespace) -> int:
    with connect(_db_path(args.workspace)) as conn:
        screening_mod.resolve_conflict(
            conn, args.record_id, args.decision, args.by, reason=args.reason, stage=args.stage
        )
    print(f"Recorded human resolution for record {args.record_id}: {args.decision} (by {args.by})")
    return 0


# ---------------------------------------------------------- extraction ---

def cmd_extract_run(args: argparse.Namespace) -> int:
    config = load_config(_config_path(args.workspace))
    role_cfg = config.role(args.role)
    schema = extraction_mod.load_schema(args.schema)
    full_text = Path(args.full_text_file).read_text(encoding="utf-8")
    with connect(_db_path(args.workspace)) as conn:
        result = extraction_mod.extract_study(conn, role_cfg, schema, args.record_id, full_text)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_extract_export(args: argparse.Namespace) -> int:
    schema = extraction_mod.load_schema(args.schema)
    out_path = Path(args.workspace) / "extraction" / "studies.csv"
    with connect(_db_path(args.workspace)) as conn:
        n = extraction_mod.export_studies_csv(conn, schema, out_path)
    print(f"Wrote {n} studies to {out_path}")
    return 0


def cmd_extract_verify(args: argparse.Namespace) -> int:
    with connect(_db_path(args.workspace)) as conn:
        extraction_mod.verify_field(conn, args.record_id, args.field, args.by)
    print(f"Marked {args.field} for record {args.record_id} as verified by {args.by}")
    return 0


# ---------------------------------------------------------------- bias ---

def cmd_bias_add(args: argparse.Namespace) -> int:
    with connect(_db_path(args.workspace)) as conn:
        row_id = insert_bias_assessment(
            conn, args.record_id, args.tool, args.domain, args.judgment,
            args.justification, quote=args.quote, model=args.by,
        )
    print(f"Recorded bias assessment #{row_id} for record {args.record_id} ({args.tool} / {args.domain})")
    return 0


def cmd_bias_export(args: argparse.Namespace) -> int:
    out_path = Path(args.workspace) / "extraction" / "bias_assessments.csv"
    with connect(_db_path(args.workspace)) as conn:
        n = export_bias_csv(conn, out_path)
    print(f"Wrote {n} bias assessments to {out_path}")
    return 0


# --------------------------------------------------------------- gates ---

def cmd_gate_approve(args: argparse.Namespace) -> int:
    with connect(_db_path(args.workspace)) as conn:
        record = gates_mod.approve_gate(
            conn, args.gate, args.artifact, args.by, args.workspace,
            notes=args.notes, status="rejected" if args.reject else "approved",
        )
    print(f"Gate {record.gate_id}: {record.status} by {record.approved_by} at {record.decided_at}")
    print(f"  artifact: {record.artifact_path} (sha256={record.artifact_sha256[:12]}...)")
    return 0


def cmd_gate_status(args: argparse.Namespace) -> int:
    with connect(_db_path(args.workspace)) as conn:
        statuses = gates_mod.all_gates_status(conn)
    for gate_id, record in statuses.items():
        desc = gates_mod.GATE_DESCRIPTIONS[gate_id]
        if record is None:
            print(f"{gate_id}  [ PENDING ]  {desc}")
        else:
            print(f"{gate_id}  [{record.status.upper():>9}]  {desc}  (by {record.approved_by} at {record.decided_at})")
    return 0


# ----------------------------------------------------------- integrity ---

def cmd_resolve_citations(args: argparse.Namespace) -> int:
    try:
        results = integrity_mod.check_citations_or_fail(args.bib)
    except integrity_mod.IntegrityError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"All {len(results)} citations in {args.bib} resolve cleanly against Crossref.")
    return 0


def cmd_check_provenance(args: argparse.Namespace) -> int:
    with connect(_db_path(args.workspace)) as conn:
        try:
            report = integrity_mod.check_provenance_or_fail(conn, args.manuscript)
        except integrity_mod.IntegrityError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    print(f"Provenance OK: {len(report.referenced)} tagged claims all resolve.")
    if report.unprovenanced_numeric_claims:
        print(f"\n{len(report.unprovenanced_numeric_claims)} numeric-looking lines have no \\provenance{{}} tag nearby (heuristic, review by hand):")
        for lineno, snippet in report.unprovenanced_numeric_claims[:50]:
            print(f"  line {lineno}: {snippet}")
    return 0


def cmd_add_provenance(args: argparse.Namespace) -> int:
    with connect(_db_path(args.workspace)) as conn:
        integrity_mod.add_provenance(
            conn, args.claim_id, args.value, args.source_table, args.source_ref, note=args.note
        )
    print(f"Recorded provenance for claim_id='{args.claim_id}'")
    return 0


# ---------------------------------------------------------------- main ---

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="freemdlabor", description="Deterministic core for medical/surgical evidence synthesis (Vía A).")
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a new review workspace")
    p_init.add_argument("workspace")
    p_init.set_defaults(func=cmd_init)

    p_search = sub.add_parser("search", help="Query a bibliographic source and store results")
    p_search.add_argument("--workspace", required=True)
    p_search.add_argument("--source", required=True, choices=sorted(SOURCES))
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--max-results", type=int, default=500, dest="max_results")
    p_search.set_defaults(func=cmd_search)

    p_dedup = sub.add_parser("dedup", help="Deduplicate records (DOI/PMID exact, then fuzzy title)")
    p_dedup.add_argument("--workspace", required=True)
    p_dedup.add_argument("--threshold", type=float, default=None)
    p_dedup.set_defaults(func=cmd_dedup)

    p_prisma = sub.add_parser("prisma", help="Compute PRISMA 2020 counts + flow diagram from review.sqlite")
    p_prisma.add_argument("--workspace", required=True)
    p_prisma.add_argument("--title", default=None)
    p_prisma.set_defaults(func=cmd_prisma)

    p_screen = sub.add_parser("screen", help="Screening commands")
    screen_sub = p_screen.add_subparsers(dest="screen_command", required=True)

    p_ta = screen_sub.add_parser("title-abstract", help="Run one screening pass over all un-decided canonical records")
    p_ta.add_argument("--workspace", required=True)
    p_ta.add_argument("--pass", dest="pass_label", required=True, choices=["pass_a", "pass_b"])
    p_ta.add_argument("--role", default="screening")
    p_ta.add_argument("--protocol", default=None)
    p_ta.add_argument("--batch-size", type=int, default=None, dest="batch_size")
    p_ta.set_defaults(func=cmd_screen_title_abstract)

    p_ft = screen_sub.add_parser("full-text", help="Run full-text eligibility screening for one record")
    p_ft.add_argument("--workspace", required=True)
    p_ft.add_argument("--record-id", type=int, required=True, dest="record_id")
    p_ft.add_argument("--full-text-file", required=True, dest="full_text_file")
    p_ft.add_argument("--pass", dest="pass_label", default="pass_a", choices=["pass_a", "pass_b"])
    p_ft.add_argument("--role", default="extraction")
    p_ft.add_argument("--protocol", default=None)
    p_ft.set_defaults(func=cmd_screen_full_text)

    p_kappa = screen_sub.add_parser("kappa", help="Cohen's kappa between pass_a and pass_b")
    p_kappa.add_argument("--workspace", required=True)
    p_kappa.add_argument("--stage", default="title_abstract", choices=["title_abstract", "full_text"])
    p_kappa.set_defaults(func=cmd_screen_kappa)

    p_conflicts = screen_sub.add_parser("conflicts", help="Export pass_a/pass_b disagreements for gate G2")
    p_conflicts.add_argument("--workspace", required=True)
    p_conflicts.add_argument("--stage", default="title_abstract", choices=["title_abstract", "full_text"])
    p_conflicts.set_defaults(func=cmd_screen_conflicts)

    p_resolve = screen_sub.add_parser("resolve", help="Record a human resolution for a screening conflict")
    p_resolve.add_argument("--workspace", required=True)
    p_resolve.add_argument("--record-id", type=int, required=True, dest="record_id")
    p_resolve.add_argument("--decision", required=True, choices=["include", "exclude"])
    p_resolve.add_argument("--by", required=True)
    p_resolve.add_argument("--reason", default=None)
    p_resolve.add_argument("--stage", default="title_abstract", choices=["title_abstract", "full_text"])
    p_resolve.set_defaults(func=cmd_screen_resolve)

    p_extract = sub.add_parser("extract", help="Extraction commands")
    extract_sub = p_extract.add_subparsers(dest="extract_command", required=True)

    p_erun = extract_sub.add_parser("run", help="Extract one study's fields per extraction/schema.json")
    p_erun.add_argument("--workspace", required=True)
    p_erun.add_argument("--record-id", type=int, required=True, dest="record_id")
    p_erun.add_argument("--full-text-file", required=True, dest="full_text_file")
    p_erun.add_argument("--schema", default=None)
    p_erun.add_argument("--role", default="extraction")
    p_erun.set_defaults(func=cmd_extract_run)

    p_eexport = extract_sub.add_parser("export", help="Export extraction/studies.csv from the DB")
    p_eexport.add_argument("--workspace", required=True)
    p_eexport.add_argument("--schema", default=None)
    p_eexport.set_defaults(func=cmd_extract_export)

    p_everify = extract_sub.add_parser("verify", help="Mark one extracted cell as spot-checked (gate G3)")
    p_everify.add_argument("--workspace", required=True)
    p_everify.add_argument("--record-id", type=int, required=True, dest="record_id")
    p_everify.add_argument("--field", required=True)
    p_everify.add_argument("--by", required=True)
    p_everify.set_defaults(func=cmd_extract_verify)

    p_bias = sub.add_parser("bias", help="Risk-of-bias assessment commands")
    bias_sub = p_bias.add_subparsers(dest="bias_command", required=True)

    p_badd = bias_sub.add_parser("add", help="Record one domain judgment for one study")
    p_badd.add_argument("--workspace", required=True)
    p_badd.add_argument("--record-id", type=int, required=True, dest="record_id")
    p_badd.add_argument("--tool", required=True, choices=["RoB2", "ROBINS-I", "QUADAS-2", "NOS"])
    p_badd.add_argument("--domain", required=True)
    p_badd.add_argument("--judgment", required=True)
    p_badd.add_argument("--justification", required=True)
    p_badd.add_argument("--quote", default=None)
    p_badd.add_argument("--by", required=True, help="e.g. 'human:your_name' or 'claude-code'")
    p_badd.set_defaults(func=cmd_bias_add)

    p_bexport = bias_sub.add_parser("export", help="Export all bias assessments to CSV")
    p_bexport.add_argument("--workspace", required=True)
    p_bexport.set_defaults(func=cmd_bias_export)

    p_gate = sub.add_parser("gate", help="Human gate commands")
    gate_sub = p_gate.add_subparsers(dest="gate_command", required=True)

    p_gapprove = gate_sub.add_parser("approve", help="Approve (or --reject) a gate")
    p_gapprove.add_argument("--workspace", required=True)
    p_gapprove.add_argument("gate", choices=gates_mod.GATE_IDS)
    p_gapprove.add_argument("artifact")
    p_gapprove.add_argument("--by", required=True)
    p_gapprove.add_argument("--notes", default=None)
    p_gapprove.add_argument("--reject", action="store_true")
    p_gapprove.set_defaults(func=cmd_gate_approve)

    p_gstatus = gate_sub.add_parser("status", help="Show status of all gates")
    p_gstatus.add_argument("--workspace", required=True)
    p_gstatus.set_defaults(func=cmd_gate_status)

    p_integrity = sub.add_parser("integrity", help="Anti-fabrication checks")
    integrity_sub = p_integrity.add_subparsers(dest="integrity_command", required=True)

    p_cites = integrity_sub.add_parser("resolve-citations", help="Hard-fail unless every .bib entry resolves live against Crossref")
    p_cites.add_argument("--bib", required=True)
    p_cites.set_defaults(func=cmd_resolve_citations)

    p_prov = integrity_sub.add_parser("check-provenance", help="Hard-fail unless every \\provenance{} tag resolves")
    p_prov.add_argument("--workspace", required=True)
    p_prov.add_argument("--manuscript", required=True)
    p_prov.set_defaults(func=cmd_check_provenance)

    p_addprov = integrity_sub.add_parser("add-provenance", help="Record where one manuscript number comes from")
    p_addprov.add_argument("--workspace", required=True)
    p_addprov.add_argument("--claim-id", required=True, dest="claim_id")
    p_addprov.add_argument("--value", required=True)
    p_addprov.add_argument("--source-table", required=True, dest="source_table", choices=["extractions", "bias_assessments", "analysis"])
    p_addprov.add_argument("--source-ref", required=True, dest="source_ref")
    p_addprov.add_argument("--note", default=None)
    p_addprov.set_defaults(func=cmd_add_provenance)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "schema") and args.schema is None and hasattr(args, "workspace"):
        args.schema = str(Path(args.workspace) / "extraction" / "schema.json")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
