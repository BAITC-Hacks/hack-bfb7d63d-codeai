"""One bounded, nonretrying request to an explicitly selected hosted provider.

No user-configurable URL, redirect, provider fallback, tool call, or raw provider
error is accepted. The caller reserves its budget before invoking this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from time import monotonic

import requests

from moneymap.ai_settings import AISettings


ENDPOINTS = {
    "openai": "https://api.openai.com/v1/responses",
    "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
}
MAX_RESPONSE_BYTES = 1_048_576


@dataclass(frozen=True)
class ProviderResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    provider: str
    model: str


class AIProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, input_tokens=None, output_tokens=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


def _token_count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100_000_000 else None


def _usage(data: dict, provider: str) -> tuple[int | None, int | None]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None, None
    names = ("input_tokens", "output_tokens") if provider == "openai" else ("prompt_tokens", "completion_tokens")
    return _token_count(usage.get(names[0])), _token_count(usage.get(names[1]))


def _parse_result(data: dict, settings: AISettings) -> ProviderResult:
    incoming, outgoing = _usage(data, settings.provider)

    def fail(code, message):
        raise AIProviderError(code, message, input_tokens=incoming, output_tokens=outgoing)

    if data.get("error"):
        fail("provider_error", "AI провайдері жауапты аяқтамады; автоматты қайталау жасалмады.")
    if settings.provider == "openai":
        if data.get("status") != "completed":
            fail("incomplete", "AI жауабы толық аяқталмаған; ол көрсетілмейді.")
        output = data.get("output")
        if not isinstance(output, list):
            fail("invalid_response", "AI жауап пішімі күтілгендей емес.")
        pieces = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            if item.get("status", "completed") != "completed":
                fail("incomplete", "AI хабарламасы толық аяқталмаған; ол көрсетілмейді.")
            content = item.get("content")
            if not isinstance(content, list):
                fail("invalid_response", "AI жауап пішімі күтілгендей емес.")
            for part in content:
                if not isinstance(part, dict):
                    fail("invalid_response", "AI жауап пішімі күтілгендей емес.")
                if part.get("type") == "refusal":
                    fail("refused", "AI провайдері бұл сұрауға жауап бермеді.")
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    pieces.append(part["text"])
        text = "".join(pieces)
    else:
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            fail("invalid_response", "AI жауап пішімі күтілгендей емес.")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            fail("invalid_response", "AI жауап пішімі күтілгендей емес.")
        if message.get("refusal") or choice.get("finish_reason") == "content_filter":
            fail("refused", "AI провайдері бұл сұрауға жауап бермеді.")
        if choice.get("finish_reason") != "stop":
            fail("incomplete", "AI жауабы толық аяқталмаған; ол көрсетілмейді.")
        if message.get("tool_calls"):
            fail("invalid_response", "AI мәтіннің орнына қолдау таппайтын әрекет ұсынды.")
        text = message.get("content")
    if not isinstance(text, str) or not text.strip():
        fail("invalid_response", "AI бос немесе жарамсыз жауап берді.")
    return ProviderResult(text, incoming, outgoing, settings.provider, settings.model)


def call_provider(settings: AISettings, system_prompt: str, user_payload: dict, response_schema: dict) -> ProviderResult:
    """Dispatch once; response content is capped at 1 MiB before JSON parsing.

    The read timeout applies to each socket read; an additional elapsed-time
    check bounds incremental streaming. No retry is attempted on any failure.
    NVIDIA JSON adherence is checked by the caller, not assumed from its prompt.
    """
    if not settings.ready:
        raise AIProviderError("not_ready", "AI өшірулі немесе API кілті енгізілмеген.")
    if not isinstance(system_prompt, str) or not system_prompt.strip() or not isinstance(user_payload, dict) or not isinstance(response_schema, dict):
        raise AIProviderError("invalid_request", "AI сұрауының жергілікті пішімі жарамсыз.")
    try:
        payload_text = json.dumps(user_payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        schema_text = json.dumps(response_schema, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError, OverflowError):
        raise AIProviderError("invalid_request", "AI сұрауын JSON пішіміне айналдыру мүмкін болмады.") from None
    if settings.provider == "openai":
        body = {
            "model": settings.model, "store": False, "temperature": 0.2,
            "max_output_tokens": settings.max_output_tokens,
            "input": [{"role": "system", "content": system_prompt}, {"role": "user", "content": payload_text}],
            "text": {"format": {"type": "json_schema", "name": "money_map", "strict": True, "schema": response_schema}},
        }
    else:
        body = {
            "model": settings.model, "temperature": 0.2, "max_tokens": settings.max_output_tokens,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt + "\nReturn only one JSON object, without Markdown, matching this JSON Schema:\n" + schema_text},
                {"role": "user", "content": payload_text},
            ],
        }
    response = None
    started = monotonic()
    try:
        response = requests.post(
            ENDPOINTS[settings.provider], json=body,
            headers={"Authorization": "Bearer " + settings.api_key, "Accept": "application/json", "Content-Type": "application/json"},
            timeout=(5, settings.timeout_seconds), allow_redirects=False, stream=True,
        )
        status = response.status_code
        if 300 <= status < 400:
            raise AIProviderError("redirect", "AI қызметінің қайта бағыттауы қабылданбады.")
        if status in (401, 403):
            raise AIProviderError("authentication", "API кілтін және осы модельге қолжетімділікті тексеріңіз.")
        if status == 429:
            raise AIProviderError("rate_limit", "Провайдердің сұрау немесе кредит шегі жетті; автоматты қайталау жасалмады.")
        if status < 200 or status >= 300:
            raise AIProviderError("http_error", "AI қызметі сұрауды орындамады; автоматты қайталау жасалмады.")
        announced_size = response.headers.get("Content-Length")
        if announced_size is not None:
            try:
                oversized = int(announced_size) > MAX_RESPONSE_BYTES
            except (ValueError, TypeError):
                oversized = False
            if oversized:
                raise AIProviderError("response_too_large", "AI жауабы рұқсат етілген көлемнен асты.")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if monotonic() - started > settings.timeout_seconds + 5:
                raise AIProviderError("timeout", "AI жауап беру уақытынан асты; автоматты қайталау жасалмады.")
            if chunk:
                content.extend(chunk)
            if len(content) > MAX_RESPONSE_BYTES:
                raise AIProviderError("response_too_large", "AI жауабы рұқсат етілген көлемнен асты.")
        try:
            data = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise AIProviderError("invalid_response", "AI жауабы жарамды JSON пішімінде емес.") from None
        if not isinstance(data, dict):
            raise AIProviderError("invalid_response", "AI жауап пішімі күтілгендей емес.")
        return _parse_result(data, settings)
    except requests.Timeout:
        raise AIProviderError("timeout", "AI жауап беру уақытынан асты; автоматты қайталау жасалмады.") from None
    except requests.RequestException:
        raise AIProviderError("network", "AI қызметіне қосылу мүмкін болмады; автоматты қайталау жасалмады.") from None
    finally:
        if response is not None:
            response.close()
