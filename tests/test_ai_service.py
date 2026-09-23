import json
from types import SimpleNamespace

import pytest

from moneymap.ai_facts import build_evidence
from moneymap.ai_provider import AIProviderError
from moneymap.ai_response import AIResponseError
from moneymap.ai_service import request_analysis
from moneymap.demo import create_demo_frames
from moneymap.graph import analyze_dataset
from moneymap.roles import classify_graph


class LedgerStub:
    def __init__(self):
        self.reservations = []
        self.settlements = []

    def reserve(self, settings, tokens):
        self.reservations.append(tokens)
        return str(len(self.reservations))

    def settle(self, reservation, input_tokens, output_tokens, status):
        self.settlements.append((reservation, input_tokens, output_tokens, status))


@pytest.fixture
def bundle():
    analysis = analyze_dataset(create_demo_frames())
    return build_evidence(analysis, classify_graph(analysis), "explain_client", gid="1004")


def settings(ready=True):
    return SimpleNamespace(ready=ready, provider="openai", model="test", max_output_tokens=1200)


def reply(bundle):
    return SimpleNamespace(text=json.dumps({
        "summary": "Бақылау шектеулі, қосымша дерек қажет.",
        "findings": [{"fact_ids": [bundle.facts[0]["id"]], "interpretation": "Бастапқы бақылау шектеулерін ескеру керек."}],
        "next_steps": ["check_observation_limits"],
    }), input_tokens=100, output_tokens=80)


def test_disabled_never_reserves_or_dispatches(monkeypatch, bundle):
    ledger = LedgerStub()
    monkeypatch.setattr("moneymap.ai_service.call_provider", lambda *args: pytest.fail("Network dispatch was not authorized"))
    with pytest.raises(AIProviderError):
        request_analysis(settings(False), bundle, cache={}, ledger=ledger)
    assert not ledger.reservations


def test_verified_cache_is_free_and_does_not_share_mutable_output(monkeypatch, bundle):
    ledger, cache, calls = LedgerStub(), {}, []

    def provider(config, prompt, payload, schema):
        assert len(ledger.reservations) == 1  # Reservation precedes dispatch.
        assert "aliases" not in payload
        assert "1004" not in json.dumps(payload)
        calls.append(payload)
        return reply(bundle)

    monkeypatch.setattr("moneymap.ai_service.call_provider", provider)
    one = request_analysis(settings(), bundle, cache=cache, ledger=ledger)
    one["data"]["summary"] = "mutated"
    two = request_analysis(settings(), bundle, cache=cache, ledger=ledger)
    assert two["from_cache"] and two["data"]["summary"] != "mutated"
    assert len(calls) == len(ledger.reservations) == len(ledger.settlements) == 1
    assert ledger.settlements[0][1:] == (100, 80, "success")


def test_invalid_answer_is_charged_once_and_never_cached_or_retried(monkeypatch, bundle):
    ledger, cache, calls = LedgerStub(), {}, []

    def provider(*args):
        calls.append(1)
        return SimpleNamespace(text='{"summary":"999999"}', input_tokens=123, output_tokens=45)

    monkeypatch.setattr("moneymap.ai_service.call_provider", provider)
    with pytest.raises(AIResponseError):
        request_analysis(settings(), bundle, cache=cache, ledger=ledger)
    assert len(calls) == 1 and not cache
    assert ledger.settlements[0][1:] == (123, 45, "invalid_response")


def test_timeout_keeps_unknown_usage_and_does_not_switch_provider(monkeypatch, bundle):
    ledger, calls = LedgerStub(), []

    def provider(*args):
        calls.append(1)
        raise AIProviderError("timeout", "Уақыт шегі аяқталды.")

    monkeypatch.setattr("moneymap.ai_service.call_provider", provider)
    with pytest.raises(AIProviderError):
        request_analysis(settings(), bundle, cache={}, ledger=ledger)
    assert len(calls) == 1
    assert ledger.settlements[0][1:] == (None, None, "error")
