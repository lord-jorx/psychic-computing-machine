"""Thin, provider-agnostic LLM router.

This is deliberately not a framework. It resolves a *role* (screening,
extraction, judgment, ...) from config.yaml to one HTTP call, enforcing the
one rule that matters most in a clinical context: data marked `restricted`
(anything touching patient-level rows) can never be routed to a free-tier
provider, because free tiers generally train on submitted data. See
PLAN.md §3.3.

`role="judgment"` is configured as provider="interactive" by default: it is
not meant to be called from this module at all. Judgment steps (protocol
design, risk-of-bias reasoning, interpretation, discussion) are meant to
happen in the Claude Code conversation itself, where a human is directly
reading the model's output — that IS the Claude Pro usage path. Calling
call_llm() with an interactive role raises InteractiveRoleError on purpose.
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

import requests

from .config import RoleConfig

DATA_SENSITIVITY_LEVELS = ["public", "restricted"]


class ProviderError(RuntimeError):
    pass


class DataSensitivityError(ProviderError):
    """Raised when a restricted-data call would be routed to a free tier."""


class InteractiveRoleError(ProviderError):
    """Raised when code tries to programmatically call a role that is
    configured to run inside the interactive Claude Code session instead.
    """


def _enforce_data_sensitivity(role_cfg: RoleConfig, data_sensitivity: str) -> None:
    if data_sensitivity not in DATA_SENSITIVITY_LEVELS:
        raise ValueError(f"Unknown data_sensitivity '{data_sensitivity}'")
    if data_sensitivity == "restricted" and role_cfg.tier == "free":
        raise DataSensitivityError(
            f"Role '{role_cfg.role}' is configured on a free tier ({role_cfg.provider}), "
            f"which is not permitted for data_sensitivity='restricted'. Free tiers generally "
            f"train on submitted data — patient-level rows (MIMIC, SEER, local EHR extracts, "
            f"and anything under a data use agreement) must never go here. Either point this "
            f"role at a paid/no-retention provider in config.yaml, or process this data "
            f"interactively inside Claude Code instead."
        )


def _post_json(
    url: str,
    headers: dict[str, str],
    payload: dict,
    timeout: float = 60.0,
    max_retries: int = 4,
) -> dict:
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(min(2**attempt, 30))
                continue
            if resp.status_code >= 400:
                raise ProviderError(f"HTTP {resp.status_code} from {url}: {resp.text[:800]}")
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(min(2**attempt, 30))
    raise ProviderError(f"POST {url} failed after {max_retries} attempts: {last_exc}")


def _call_gemini(role_cfg: RoleConfig, system: str, user: str, json_mode: bool, temperature: float, max_tokens: int) -> str:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ProviderError("GOOGLE_API_KEY (or GEMINI_API_KEY) is not set. Get a free key at aistudio.google.com.")
    model = role_cfg.model or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    generation_config = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if json_mode:
        generation_config["responseMimeType"] = "application/json"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": generation_config,
    }
    data = _post_json(url, headers={"Content-Type": "application/json"}, payload=payload)
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise ProviderError(f"Unexpected Gemini response shape: {json.dumps(data)[:800]}") from exc


def _call_groq(role_cfg: RoleConfig, system: str, user: str, json_mode: bool, temperature: float, max_tokens: int) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ProviderError("GROQ_API_KEY is not set. Get a free key at console.groq.com.")
    model = role_cfg.model or "llama-3.3-70b-versatile"
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = _post_json(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload,
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise ProviderError(f"Unexpected Groq response shape: {json.dumps(data)[:800]}") from exc


def _call_openai_compatible(role_cfg: RoleConfig, system: str, user: str, json_mode: bool, temperature: float, max_tokens: int) -> str:
    api_key_env = role_cfg.extra.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ProviderError(f"{api_key_env} is not set.")
    base_url = role_cfg.extra.get("base_url", "https://api.openai.com/v1")
    model = role_cfg.model or "gpt-4o-mini"
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = _post_json(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload=payload,
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise ProviderError(f"Unexpected response shape from {base_url}: {json.dumps(data)[:800]}") from exc


def _call_anthropic(role_cfg: RoleConfig, system: str, user: str, json_mode: bool, temperature: float, max_tokens: int) -> str:
    # Only used if you deliberately configure a role with a paid Anthropic
    # API key. A Claude Pro subscription does NOT provide this key — see
    # PLAN.md §1.2. This exists for e.g. a metered extraction role, not for
    # replacing your interactive Claude Code usage.
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ProviderError(
            "ANTHROPIC_API_KEY is not set. Note: a Claude Pro subscription does not provide "
            "this key — it's a separate, metered API key from console.anthropic.com. If you "
            "don't have one, route this role to gemini/groq instead, or run it interactively."
        )
    model = role_cfg.model or "claude-sonnet-4-6"
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": model,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    data = _post_json(
        url,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        payload=payload,
    )
    try:
        return "".join(block.get("text", "") for block in data["content"])
    except (KeyError, TypeError) as exc:
        raise ProviderError(f"Unexpected Anthropic response shape: {json.dumps(data)[:800]}") from exc


_PROVIDERS = {
    "gemini": _call_gemini,
    "groq": _call_groq,
    "openai": _call_openai_compatible,
    "anthropic": _call_anthropic,
}


def call_llm(
    role_cfg: RoleConfig,
    system: str,
    user: str,
    *,
    data_sensitivity: str = "public",
    json_mode: bool = False,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> str:
    """The single entry point every screening/extraction call goes through."""
    _enforce_data_sensitivity(role_cfg, data_sensitivity)

    if role_cfg.provider == "interactive":
        raise InteractiveRoleError(
            f"Role '{role_cfg.role}' is configured as interactive — it is meant to be run "
            f"by you, inside Claude Code, not called from a script. See "
            f".claude/commands/ for the matching slash command."
        )
    if role_cfg.provider == "deterministic":
        raise ProviderError(
            f"Role '{role_cfg.role}' is deterministic (no LLM). If you're seeing this, "
            f"something upstream should have used plain Python/R instead of call_llm()."
        )

    fn = _PROVIDERS.get(role_cfg.provider)
    if fn is None:
        raise ValueError(f"Unknown provider '{role_cfg.provider}' for role '{role_cfg.role}'")

    return fn(role_cfg, system, user, json_mode, temperature, max_tokens)


def call_llm_json(role_cfg: RoleConfig, system: str, user: str, *, data_sensitivity: str = "public", temperature: float = 0.0, max_tokens: int = 2048) -> dict | list:
    """Like call_llm, but parses the response as JSON and retries once with
    a stricter reminder if parsing fails — models occasionally wrap JSON in
    prose or a markdown fence even when asked not to.
    """
    raw = call_llm(
        role_cfg, system, user,
        data_sensitivity=data_sensitivity, json_mode=True,
        temperature=temperature, max_tokens=max_tokens,
    )
    parsed = _try_parse_json(raw)
    if parsed is not None:
        return parsed

    retry_user = (
        user
        + "\n\nYour previous reply could not be parsed as JSON. Reply with ONLY "
          "valid JSON — no markdown fences, no commentary before or after."
    )
    raw2 = call_llm(
        role_cfg, system, retry_user,
        data_sensitivity=data_sensitivity, json_mode=True,
        temperature=temperature, max_tokens=max_tokens,
    )
    parsed2 = _try_parse_json(raw2)
    if parsed2 is not None:
        return parsed2
    raise ProviderError(f"Could not parse JSON from role '{role_cfg.role}' after retry. Raw: {raw2[:500]}")


def _try_parse_json(text: str) -> Optional[dict | list]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        return None
