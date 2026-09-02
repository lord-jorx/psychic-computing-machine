"""freeMDlabor — deterministic core + LLM-assisted tools for systematic reviews
and evidence synthesis in medicine and surgery.

This package is intentionally NOT a multi-agent framework. Orchestration is
done by a human researcher driving Claude Code (or another chat assistant)
through the .claude/commands/ slash commands; this package supplies the
parts that must be deterministic, auditable, and cheap: search, dedup,
PRISMA counts, provenance/citation integrity checks, and a budget-aware
LLM router for the genuinely LLM-shaped steps (screening, extraction).
"""

__version__ = "0.1.0"
