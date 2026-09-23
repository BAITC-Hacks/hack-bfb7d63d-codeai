"""Provider wire-contract tests are fully mocked: no key and no live API call."""

from dataclasses import replace
import json

import pytest
import requests

from moneymap.ai_provider import AIProviderError, MAX_RESPONSE_BYTES, call_provider
from moneymap.ai_settings import AISettings, NVIDIA_MODEL, OPENAI_MODEL


SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"], "additionalProperties": False}


class FakeResponse:
    def __init__(self, body=None, status=200, headers=None, chunks=None):
        self.status_code, self.headers = status, headers or {}
        self.chunks = chunks if chunks is not None else [json.dumps(body or {}, ensure_ascii=False).encode()]
        self.closed = False
        self.read = False

    def iter_content(self, chunk_size):
        self.read = True
        yield from self.chunks

    def close(self):
        self.closed = True


def settings(provider="openai"):
    return AISettings(provider, OPENAI_MODEL if provider == "openai" else NVIDIA_MODEL, "fake-test-secret", enabled=True)


def openai_body(usage=True):
    body = {"status": "completed", "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": '{"summary":"Тексеру гипотезасы"}'}]}]}
    if usage:
        body["usage"] = {"input_tokens": 150, "output_tokens": 30}
    return body


def mock_post(monkeypatch, response):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return response

    monkeypatch.setattr("moneymap.ai_provider.requests.post", post)
    return calls


def test_openai_exact_wire_shape_usage_and_closure(monkeypatch):
    response = FakeResponse(openai_body())
    calls = mock_post(monkeypatch, response)
    result = call_provider(settings(), "Use only given facts.", {"gid": "100000008686313100"}, SCHEMA)
    assert result.input_tokens == 150 and result.output_tokens == 30
    assert json.loads(result.text)["summary"] == "Тексеру гипотезасы"
    url, request = calls[0]
    assert url == "https://api.openai.com/v1/responses"
    assert len(calls) == 1 and request["allow_redirects"] is False and request["stream"] is True
    assert request["timeout"] == (5, 45)
    body = request["json"]
    assert body["model"] == OPENAI_MODEL and body["store"] is False and body["max_output_tokens"] == 1200
    assert body["text"]["format"] == {"type": "json_schema", "name": "money_map", "strict": True, "schema": SCHEMA}
    assert json.loads(body["input"][1]["content"])["gid"] == "100000008686313100"
    assert "fake-test-secret" not in json.dumps(body) and response.closed


def test_nvidia_fixed_endpoint_json_instruction_and_nullable_usage(monkeypatch):
    response = FakeResponse({"choices": [{"finish_reason": "stop", "message": {"content": '{"summary":"test"}'}}]})
    calls = mock_post(monkeypatch, response)
    result = call_provider(settings("nvidia"), "Facts only.", {"gid": "100000008686313100"}, SCHEMA)
    url, request = calls[0]
    assert url == "https://integrate.api.nvidia.com/v1/chat/completions"
    body = request["json"]
    assert body["model"] == NVIDIA_MODEL and body["max_tokens"] == 1200 and body["stream"] is False
    assert "JSON Schema" in body["messages"][0]["content"] and "response_format" not in body
    assert result.input_tokens is None and result.output_tokens is None and response.closed


@pytest.mark.parametrize("status,code", [(301, "redirect"), (307, "redirect"), (401, "authentication"), (403, "authentication"), (429, "rate_limit"), (500, "http_error")])
def test_http_errors_never_read_or_expose_body_or_retry(monkeypatch, status, code):
    response = FakeResponse({"error": "fake-test-secret confidential-body"}, status=status)
    calls = mock_post(monkeypatch, response)
    with pytest.raises(AIProviderError) as caught:
        call_provider(settings(), "Facts", {}, SCHEMA)
    assert caught.value.code == code and "fake-test-secret" not in str(caught.value)
    assert "confidential-body" not in str(caught.value)
    assert len(calls) == 1 and not response.read and response.closed


@pytest.mark.parametrize("error,code", [(requests.Timeout("fake-test-secret"), "timeout"), (requests.ConnectionError("fake-test-secret"), "network")])
def test_network_exceptions_are_redacted_no_retry(monkeypatch, error, code):
    calls = []

    def post(*args, **kwargs):
        calls.append(True)
        raise error

    monkeypatch.setattr("moneymap.ai_provider.requests.post", post)
    with pytest.raises(AIProviderError) as caught:
        call_provider(settings(), "Facts", {}, SCHEMA)
    assert caught.value.code == code and "fake-test-secret" not in str(caught.value) and len(calls) == 1


@pytest.mark.parametrize("reason", ["incomplete", "failed", "queued", None])
def test_openai_noncompleted_rejected_with_usage_retained(monkeypatch, reason):
    body = openai_body()
    body["status"] = reason
    response = FakeResponse(body)
    mock_post(monkeypatch, response)
    with pytest.raises(AIProviderError) as caught:
        call_provider(settings(), "Facts", {}, SCHEMA)
    assert caught.value.code == "incomplete" and caught.value.input_tokens == 150 and response.closed


def test_refusal_does_not_expose_provider_refusal_text(monkeypatch):
    body = openai_body()
    body["output"][0]["content"] = [{"type": "refusal", "refusal": "fake-test-secret confidential"}]
    response = FakeResponse(body)
    mock_post(monkeypatch, response)
    with pytest.raises(AIProviderError) as caught:
        call_provider(settings(), "Facts", {}, SCHEMA)
    assert caught.value.code == "refused" and caught.value.output_tokens == 30
    assert "fake-test-secret" not in str(caught.value)


@pytest.mark.parametrize("usage,expected", [(None, (None, None)), ({"input_tokens": True, "output_tokens": -5}, (None, None)), ({"input_tokens": 20}, (20, None))])
def test_usage_missing_or_invalid_never_becomes_zero(monkeypatch, usage, expected):
    body = openai_body(False)
    body["usage"] = usage
    mock_post(monkeypatch, FakeResponse(body))
    result = call_provider(settings(), "Facts", {}, SCHEMA)
    assert (result.input_tokens, result.output_tokens) == expected


@pytest.mark.parametrize("announced", [False, True])
def test_oversized_response_closes_and_fails(monkeypatch, announced):
    response = FakeResponse(headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)} if announced else {}, chunks=[b"x" * (MAX_RESPONSE_BYTES + 1)])
    mock_post(monkeypatch, response)
    with pytest.raises(AIProviderError) as caught:
        call_provider(settings(), "Facts", {}, SCHEMA)
    assert caught.value.code == "response_too_large" and response.closed


@pytest.mark.parametrize("body", [b"not-json fake-test-secret", b"[]", b"\xff"])
def test_invalid_outer_json_never_exposes_body(monkeypatch, body):
    response = FakeResponse(chunks=[body])
    mock_post(monkeypatch, response)
    with pytest.raises(AIProviderError) as caught:
        call_provider(settings(), "Facts", {}, SCHEMA)
    assert caught.value.code == "invalid_response" and "fake-test-secret" not in str(caught.value) and response.closed


def test_disabled_never_calls_network(monkeypatch):
    calls = mock_post(monkeypatch, FakeResponse(openai_body()))
    with pytest.raises(AIProviderError) as caught:
        call_provider(replace(settings(), enabled=False), "Facts", {}, SCHEMA)
    assert caught.value.code == "not_ready" and not calls


def test_nvidia_truncated_response_rejected_and_usage_preserved(monkeypatch):
    response = FakeResponse({"choices": [{"finish_reason": "length", "message": {"content": "partial"}}], "usage": {"prompt_tokens": 33, "completion_tokens": 1200}})
    mock_post(monkeypatch, response)
    with pytest.raises(AIProviderError) as caught:
        call_provider(settings("nvidia"), "Facts", {}, SCHEMA)
    assert caught.value.code == "incomplete" and caught.value.input_tokens == 33 and caught.value.output_tokens == 1200
