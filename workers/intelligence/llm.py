"""Minimal OpenAI chat-completions adapter (LLD section 3.8).

The model gets no tools and no network access; its reply is parsed as data only. The API
key is read from the environment at call time and never logged or returned.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
TIMEOUT = httpx.Timeout(connect=5.0, read=45.0, write=10.0, pool=5.0)
RETRYABLE = {408, 409, 429, 500, 502, 503, 504}
MAX_HTTP_ATTEMPTS = 2


class LlmError(RuntimeError):
    """Provider failure. `code` is safe to store and show; it never contains secrets or response bodies."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class LlmResult:
    data: dict
    input_tokens: int
    output_tokens: int
    model: str


class LlmClient(Protocol):
    model: str

    def complete_json(self, system: str, user: str, max_tokens: int) -> LlmResult: ...


class OpenAIClient:
    def __init__(self, api_key: str, model: str | None = None):
        self._api_key = api_key
        self.model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)

    def complete_json(self, system: str, user: str, max_tokens: int) -> LlmResult:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        last_code = "api_unavailable"
        for attempt in range(MAX_HTTP_ATTEMPTS):
            try:
                response = httpx.post(OPENAI_URL, json=payload, headers=headers, timeout=TIMEOUT)
            except httpx.HTTPError:
                last_code = "api_unreachable"
            else:
                if response.status_code == 200:
                    return self._parse(response)
                last_code = f"api_http_{response.status_code}"
                if response.status_code not in RETRYABLE:
                    break
            if attempt + 1 < MAX_HTTP_ATTEMPTS:
                time.sleep(2 * (attempt + 1))
        raise LlmError(last_code)

    def _parse(self, response: httpx.Response) -> LlmResult:
        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            data = json.loads(content)
            usage = body.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LlmError("api_bad_response") from error
        if not isinstance(data, dict):
            raise LlmError("api_bad_response")
        return LlmResult(
            data=data,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            model=str(body.get("model") or self.model),
        )


def client_from_env() -> LlmClient | None:
    """Return the configured client, or None when no key is set (never raises, never echoes the key)."""
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return OpenAIClient(key) if key else None
