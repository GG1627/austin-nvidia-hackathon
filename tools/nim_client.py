"""Minimal NVIDIA NIM chat-completions client.

Uses only the Python standard library (urllib) so the project runs with zero
pip installs. NIM exposes an OpenAI-compatible REST API, so this also works
against any compatible endpoint by overriding `base_url` / `model`.

If no NVIDIA_API_KEY is configured the client reports `available == False`
and Agent 3 falls back to its deterministic recommendation engine, so the
demo never dies on stage because of a missing key or flaky wifi.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "meta/llama-3.1-70b-instruct"


class NIMError(RuntimeError):
    """Raised when the NIM API call fails or returns an unusable response."""


def load_env(path: str = ".env") -> None:
    """Tiny .env loader (KEY=VALUE lines) so python-dotenv is optional.

    Does not override variables already set in the environment.
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


class NIMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY", "")
        self.model = os.environ.get("NIM_MODEL", model)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.4,
        max_tokens: int = 2000,
    ) -> str:
        """Single-turn chat completion. Returns the assistant message text."""
        if not self.available:
            raise NIMError("No NVIDIA_API_KEY configured")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise NIMError(f"NIM API HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise NIMError(f"NIM API request failed: {exc}") from exc

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise NIMError(f"Unexpected NIM response shape: {body}") from exc
