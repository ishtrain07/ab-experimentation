import json
import os
from urllib import request
from urllib.error import URLError

NANO_MODEL = "nvidia/nemotron-3-nano-30b-a3b"
SUPER_MODEL = "nvidia/nemotron-3-super-120b-a12b"
DEFAULT_BASE = "https://api.tokenfactory.us-central1.nebius.com/v1/"

_EXTRACT_SCHEMA = {
    "supplier": "string",
    "date": "YYYY-MM-DD",
    "grade": "string",
    "size": "string",
    "quantity": "number",
    "unit": "string",
    "unit_price": "number",
    "currency": "string",
    "reason": "string",
}


def token_factory_configured() -> bool:
    return bool(os.environ.get("NEBIUS_API_KEY"))


def extract_with_nano(text: str) -> dict[str, str] | None:
    if not token_factory_configured():
        return None
    prompt = (
        "Extract one commercial document as JSON with exactly these keys: "
        f"{json.dumps(_EXTRACT_SCHEMA)}. Use an empty string when a value is absent. "
        "Do not invent prices. Document:\n"
        f"{text}"
    )
    raw = _complete(NANO_MODEL, prompt)
    if raw is None:
        return None
    return _json_object(raw)


def write_with_super(calculated_note: str, question: str) -> str | None:
    if not token_factory_configured():
        return None
    prompt = (
        "You are writing for a buying desk. Use only the figures in the audit note. "
        "Do not introduce a new percentage, price, or cause. "
        f"Audit note:\n{calculated_note}\n\nQuestion:\n{question}"
    )
    return _complete(SUPER_MODEL, prompt)


def _complete(model: str, prompt: str) -> str | None:
    base = os.environ.get("TOKEN_FACTORY_BASE_URL", DEFAULT_BASE).rstrip("/")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    req = request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['NEBIUS_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            body = json.loads(response.read().decode())
    except (URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return None
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None


def _json_object(raw: str) -> dict[str, str] | None:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return {str(key): "" if value is None else str(value) for key, value in parsed.items()}
