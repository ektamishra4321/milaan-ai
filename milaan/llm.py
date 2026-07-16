"""Dual-provider LLM layer (Anthropic / Gemini) — ported patterns from SahaayakAI:
- provider switch via LLM_PROVIDER env var
- Gemini model-name self-healing via ListModels (avoids 404s)
- thinking tokens disabled, with automatic retry if thinkingConfig unsupported
- minimum output-token budget enforced (no truncated JSON)
- parse_json_block() strips markdown fences
- every call logged to logs/telemetry.jsonl
"""

import json
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

TELEMETRY_PATH = Path("logs/telemetry.jsonl")
MIN_OUTPUT_TOKENS = 1200


class LLMError(Exception):
    pass


def _log(record: dict) -> None:
    TELEMETRY_PATH.parent.mkdir(exist_ok=True)
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with TELEMETRY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_json_block(text: str):
    """Extract the first JSON object/array from text, tolerating ``` fences."""
    if text is None:
        raise LLMError("Empty LLM response")
    cleaned = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    # Fast path
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fallback: first {...} or [...] span
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"Could not parse JSON from response: {cleaned[:300]}")


# ---------------------------------------------------------------- Anthropic
def _anthropic_complete(prompt: str, system: str, max_tokens: int) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMError("ANTHROPIC_API_KEY not set")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    body = {
        "model": model,
        "max_tokens": max(max_tokens, MIN_OUTPUT_TOKENS),
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=120,
    )
    if resp.status_code != 200:
        raise LLMError(f"Anthropic {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return "".join(b.get("text", "") for b in data.get("content", []))


# ------------------------------------------------------------------- Gemini
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_resolved_gemini_model = None

_FALLBACK_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite-001",
    "gemini-2.0-flash",
    "gemini-flash-lite-latest",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
]


def _gemini_list_models(api_key: str) -> list:
    resp = requests.get(f"{_GEMINI_BASE}/models",
                        headers={"x-goog-api-key": api_key}, timeout=60)
    if resp.status_code != 200:
        raise LLMError(f"Gemini ListModels {resp.status_code}: {resp.text[:300]}")
    models = resp.json().get("models", [])
    return [
        m["name"].split("/")[-1]
        for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]


def _gemini_call(api_key: str, model: str, prompt: str, system: str,
                 max_tokens: int):
    gen_cfg = {"maxOutputTokens": max(max_tokens, MIN_OUTPUT_TOKENS)}
    if "2.5" in model:
        gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
    if system and "gemma" in model.lower():
        # Gemma has no systemInstruction support: fold into the prompt
        prompt = system + "\n\n" + prompt
        system = ""
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": gen_cfg,
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return requests.post(
        f"{_GEMINI_BASE}/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key},
        json=body,
        timeout=120,
    )


def _gemini_complete(prompt: str, system: str, max_tokens: int) -> str:
    global _resolved_gemini_model
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise LLMError("GEMINI_API_KEY not set")

    preferred = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    candidates = [_resolved_gemini_model] if _resolved_gemini_model else []
    for m in [preferred] + _FALLBACK_MODELS:
        if m not in candidates:
            candidates.append(m)

    errors = []
    for model in candidates:
        resp = _gemini_call(api_key, model, prompt, system, max_tokens)
        if resp.status_code == 429:
            errors.append(f"{model}: 429 quota")
            print(f"  [llm] {model} quota exhausted, rotating to next model...")
            continue
        if resp.status_code == 404:
            errors.append(f"{model}: 404")
            continue
        if resp.status_code == 400 and "thinking" in resp.text.lower():
            resp = _gemini_call(api_key, model, prompt, system, max_tokens)
        if resp.status_code != 200:
            raise LLMError(f"Gemini {model} {resp.status_code}: {resp.text[:500]}")
        if model != _resolved_gemini_model:
            print(f"  [llm] using model: {model}")
        _resolved_gemini_model = model
        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError):
            raise LLMError(f"Unexpected Gemini response: {json.dumps(data)[:300]}")
    raise LLMError("All Gemini models quota-exhausted: " + "; ".join(errors))


# -------------------------------------------------------------------- Public
def complete(prompt: str, system: str = "", max_tokens: int = 2000,
             agent: str = "unknown") -> str:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    t0 = time.time()
    try:
        if provider == "gemini":
            text = _gemini_complete(prompt, system, max_tokens)
        else:
            text = _anthropic_complete(prompt, system, max_tokens)
        _log({"agent": agent, "provider": provider, "ok": True,
              "latency_s": round(time.time() - t0, 2),
              "prompt_chars": len(prompt), "response_chars": len(text)})
        return text
    except Exception as e:
        _log({"agent": agent, "provider": provider, "ok": False, "error": str(e)})
        raise


def complete_json(prompt: str, system: str = "", max_tokens: int = 2000,
                  agent: str = "unknown"):
    return parse_json_block(complete(prompt, system, max_tokens, agent))
