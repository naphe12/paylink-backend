import json
import logging
from dataclasses import dataclass

import httpx

from app.config import settings


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IntentResolution:
    intent: str
    source: str
    confidence: float | None = None


def _normalized_mode() -> str:
    return str(getattr(settings, "ASSISTANT_INTENT_PARSER_MODE", "heuristic") or "heuristic").strip().lower()


def _normalized_provider() -> str:
    return str(getattr(settings, "ASSISTANT_INTENT_PARSER_PROVIDER", "disabled") or "disabled").strip().lower()


def _llm_is_configured() -> bool:
    provider = _normalized_provider()
    model = str(getattr(settings, "ASSISTANT_INTENT_PARSER_MODEL", "") or "").strip()
    base_url = str(getattr(settings, "ASSISTANT_INTENT_PARSER_BASE_URL", "") or "").strip()
    return provider in {"ollama", "openai_compatible"} and bool(model and base_url)


def _build_prompt(domain: str, message: str, intents: dict[str, str]) -> str:
    intent_lines = "\n".join(f'- "{intent}": {description}' for intent, description in intents.items())
    return (
        "You are an intent classifier for a fintech assistant.\n"
        f"Domain: {domain}\n"
        "Return only JSON with this shape:\n"
        '{"intent":"<allowed_intent>","confidence":0.0,"reason":"short"}\n'
        "Rules:\n"
        "- Use exactly one allowed intent.\n"
        '- If the request is ambiguous or unsupported, return "unknown".\n'
        "- Confidence must be between 0 and 1.\n"
        "- Do not include markdown.\n"
        "Allowed intents:\n"
        f"{intent_lines}\n"
        f"User message: {message}"
    )


def _extract_json_object(raw_text: str) -> dict | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_confidence(value: object) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence < 0:
        return 0.0
    if confidence > 1:
        return 1.0
    return confidence


def _call_ollama(prompt: str) -> dict | None:
    response = httpx.post(
        f"{str(settings.ASSISTANT_INTENT_PARSER_BASE_URL or '').rstrip('/')}/api/generate",
        json={
            "model": settings.ASSISTANT_INTENT_PARSER_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        },
        timeout=settings.ASSISTANT_INTENT_PARSER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return _extract_json_object(payload.get("response"))


def _call_openai_compatible(prompt: str) -> dict | None:
    headers = {"Content-Type": "application/json"}
    api_key = str(getattr(settings, "ASSISTANT_INTENT_PARSER_API_KEY", "") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = httpx.post(
        f"{str(settings.ASSISTANT_INTENT_PARSER_BASE_URL or '').rstrip('/')}/chat/completions",
        headers=headers,
        json={
            "model": settings.ASSISTANT_INTENT_PARSER_MODEL,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "You classify assistant intents and must return JSON only."},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=settings.ASSISTANT_INTENT_PARSER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        return None
    message = choices[0].get("message") or {}
    return _extract_json_object(message.get("content"))


def classify_intent_with_llm(domain: str, message: str, intents: dict[str, str]) -> IntentResolution | None:
    if not _llm_is_configured():
        return None

    provider = _normalized_provider()
    prompt = _build_prompt(domain=domain, message=message, intents=intents)
    try:
        payload = _call_ollama(prompt) if provider == "ollama" else _call_openai_compatible(prompt)
    except Exception as exc:
        logger.warning("Assistant intent parser LLM call failed provider=%s domain=%s error=%s", provider, domain, exc)
        return None

    if not payload:
        return None

    intent = str(payload.get("intent") or "").strip()
    confidence = _parse_confidence(payload.get("confidence"))
    min_confidence = float(getattr(settings, "ASSISTANT_INTENT_PARSER_MIN_CONFIDENCE", 0.55) or 0.55)

    if intent not in intents:
        logger.warning("Assistant intent parser returned invalid intent provider=%s domain=%s intent=%s", provider, domain, intent)
        return None
    if confidence is not None and confidence < min_confidence:
        return None

    return IntentResolution(intent=intent, source=f"llm:{provider}", confidence=confidence)


def resolve_intent(domain: str, message: str, intents: dict[str, str], heuristic_intent: str) -> IntentResolution:
    mode = _normalized_mode()
    llm_result = classify_intent_with_llm(domain=domain, message=message, intents=intents) if mode in {"hybrid", "llm"} else None

    if llm_result is not None:
        return llm_result
    if mode == "llm":
        return IntentResolution(intent="unknown", source="llm_unavailable")
    return IntentResolution(intent=heuristic_intent, source="heuristic")
