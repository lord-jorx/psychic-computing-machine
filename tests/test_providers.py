import pytest

from freemdlabor.config import RoleConfig
from freemdlabor.providers import DataSensitivityError, InteractiveRoleError, call_llm


def test_restricted_data_on_free_tier_is_blocked():
    role = RoleConfig(role="screening", provider="gemini", model="gemini-2.5-flash", tier="free")
    with pytest.raises(DataSensitivityError):
        call_llm(role, "system", "user", data_sensitivity="restricted")


def test_public_data_on_free_tier_is_allowed_to_proceed_past_the_gate(monkeypatch):
    # We only assert the sensitivity gate doesn't block this — the fake
    # provider call raises a distinct error, proving we got past the gate.
    from freemdlabor import providers as providers_mod

    def fake_gemini(role_cfg, system, user, json_mode, temperature, max_tokens):
        raise RuntimeError("fake provider called")

    monkeypatch.setitem(providers_mod._PROVIDERS, "gemini", fake_gemini)
    role = RoleConfig(role="screening", provider="gemini", model="gemini-2.5-flash", tier="free")
    with pytest.raises(RuntimeError, match="fake provider called"):
        call_llm(role, "system", "user", data_sensitivity="public")


def test_interactive_role_cannot_be_called_programmatically():
    role = RoleConfig(role="judgment", provider="interactive", tier="interactive", max_data_sensitivity="restricted")
    with pytest.raises(InteractiveRoleError):
        call_llm(role, "system", "user", data_sensitivity="public")
