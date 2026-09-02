"""Loads config.yaml: per-role model routing plus the data-sensitivity gate.

The whole point of this file is to make the Claude-Pro-is-not-an-API and
free-tiers-train-on-your-data lessons from PLAN.md structural instead of
a rule someone has to remember. See providers.py for how roles are
resolved into an actual client call.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

DEFAULT_CONFIG_PATH = "config.yaml"


class ConfigError(RuntimeError):
    pass


@dataclass
class RoleConfig:
    role: str
    provider: str                 # gemini | groq | anthropic | openai | interactive | deterministic
    model: Optional[str] = None
    tier: str = "free"            # free | paid | interactive | none
    max_data_sensitivity: str = "public"   # public | restricted — the ceiling this role may touch
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewConfig:
    roles: dict[str, RoleConfig]
    dedup_title_threshold: float = 92.0
    contact_email: Optional[str] = None
    screening_batch_size: int = 20
    screening_kappa_threshold: float = 0.6

    def role(self, name: str) -> RoleConfig:
        try:
            return self.roles[name]
        except KeyError:
            raise ConfigError(
                f"No role '{name}' in config.yaml. Configured roles: {sorted(self.roles)}"
            )


_DEFAULTS: dict[str, Any] = {
    "roles": {
        "screening": {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "tier": "free",
            "max_data_sensitivity": "public",
        },
        "extraction": {
            "provider": "gemini",
            "model": "gemini-2.5-pro",
            "tier": "free",
            "max_data_sensitivity": "public",
        },
        "judgment": {
            "provider": "interactive",
            "model": None,
            "tier": "interactive",
            "max_data_sensitivity": "restricted",
        },
        "deterministic": {
            "provider": "deterministic",
            "model": None,
            "tier": "none",
            "max_data_sensitivity": "restricted",
        },
    },
    "dedup_title_threshold": 92.0,
    "screening_batch_size": 20,
    "screening_kappa_threshold": 0.6,
}


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> ReviewConfig:
    path = Path(path)
    data: dict[str, Any] = dict(_DEFAULTS)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            user_data = yaml.safe_load(f) or {}
        # shallow-merge roles, deep-merge each role dict
        merged_roles = dict(_DEFAULTS["roles"])
        for role_name, role_data in (user_data.get("roles") or {}).items():
            merged_roles[role_name] = {**_DEFAULTS["roles"].get(role_name, {}), **role_data}
        data = {**_DEFAULTS, **user_data, "roles": merged_roles}

    roles = {
        name: RoleConfig(
            role=name,
            provider=cfg.get("provider", "interactive"),
            model=cfg.get("model"),
            tier=cfg.get("tier", "free"),
            max_data_sensitivity=cfg.get("max_data_sensitivity", "public"),
            extra={k: v for k, v in cfg.items() if k not in {"provider", "model", "tier", "max_data_sensitivity"}},
        )
        for name, cfg in data["roles"].items()
    }

    return ReviewConfig(
        roles=roles,
        dedup_title_threshold=float(data.get("dedup_title_threshold", 92.0)),
        contact_email=data.get("contact_email") or os.environ.get("NCBI_CONTACT_EMAIL"),
        screening_batch_size=int(data.get("screening_batch_size", 20)),
        screening_kappa_threshold=float(data.get("screening_kappa_threshold", 0.6)),
    )
