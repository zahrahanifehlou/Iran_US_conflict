"""Minimal stdlib-only Ollama client (POST /api/chat)."""

from __future__ import annotations

import json
import urllib.request
import urllib.error

import config


class OllamaError(RuntimeError):
    pass


def chat(
    model: str,
    messages: list[dict],
    *,
    temperature: float = 0.7,
    num_predict: int = 512,
    json_mode: bool = False,
    timeout: int | None = None,
) -> str:
    """Send a chat request to Ollama and return the assistant content."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    if json_mode:
        payload["format"] = "json"

    req = urllib.request.Request(
        f"{config.OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or config.REQUEST_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OllamaError(f"Ollama call failed ({model}): {exc}") from exc

    return body.get("message", {}).get("content", "")


def ping() -> bool:
    try:
        with urllib.request.urlopen(f"{config.OLLAMA_HOST}/api/tags", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{config.OLLAMA_HOST}/api/tags", timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return [m["name"] for m in body.get("models", [])]
    except Exception:
        return []
