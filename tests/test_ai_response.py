import json
from types import SimpleNamespace

import pytest

from moneymap.ai_response import AIResponseError, render_report, validate_response


@pytest.fixture
def bundle():
    return SimpleNamespace(
        title="Клиент туралы анықтама",
        aliases={"C001": "100000008686313100"},
        facts=[{"id": "F001", "label": "C001 · кіріс", "value": 1912716.0, "unit": "₸", "source": "in_kzt"}],
        warnings=["Рөл — тексеру гипотезасы."],
    )


def valid_reply():
    return {"summary": "C001 клиентінің бақыланған байланыстарын тексеру қажет.",
            "findings": [{"fact_ids": ["F001"], "interpretation": "Бақыланған кірісті бастапқы операциялармен салыстыруға болады."}],
            "next_steps": ["review_transfers"]}


def test_exact_numbers_and_gid_are_inserted_only_from_local_evidence(bundle):
    data = validate_response(json.dumps(valid_reply()), bundle)
    report = render_report(data, bundle, provider="openai", model="test")
    assert "100000008686313100" in report
    assert "1912716.0 ₸" in report
    assert "Рөл — тексеру гипотезасы." in report


@pytest.mark.parametrize("sentence", [
    "Кіріс 999999 теңге.", "Үлесі ９９ пайыз.", "gid 100000008686313100.",
    "C999 клиентін тексеру керек.", "Мынау F001 дәлелі.", "https://example.com ашыңыз.",
    "[Сурет](https://example.com)", "<script>bad()</script>", "Клиент кінәлі.", "Клиент алаяқ.",
    "C001 қауіпсіз клиент.", "C001 кінәсіз.", "C001 шотын бұғаттау керек.",
    "Клиент невиновен.", "C001 is safe.",
    "C001 sends funds to foreign accounts.", "C001 шетелдік шоттарға ақша жібереді.",
    "C001 қаражатты офшор арқылы өткізеді.", "C001 қолма-қол ақша шығарады.",
])
def test_untrusted_narrative_is_rejected_without_echoing_it(bundle, sentence):
    reply = valid_reply()
    reply["summary"] = sentence
    with pytest.raises(AIResponseError) as error:
        validate_response(json.dumps(reply), bundle)
    assert sentence not in str(error.value)


@pytest.mark.parametrize("change", ["unknown_fact", "extra_property", "no_evidence", "duplicate_fact", "unknown_action", "empty_summary"])
def test_invalid_contract_never_reaches_report(bundle, change):
    reply = valid_reply()
    if change == "unknown_fact":
        reply["findings"][0]["fact_ids"] = ["F999"]
    elif change == "extra_property":
        reply["secret"] = "sk-do-not-echo"
    elif change == "no_evidence":
        reply["findings"][0]["fact_ids"] = []
    elif change == "duplicate_fact":
        reply["findings"][0]["fact_ids"] = ["F001", "F001"]
    elif change == "unknown_action":
        reply["next_steps"] = ["freeze_account"]
    else:
        reply["summary"] = "   "
    with pytest.raises(AIResponseError):
        validate_response(json.dumps(reply), bundle)


def test_duplicate_json_keys_and_truncated_output_are_rejected(bundle):
    for text in ('{"summary":"ok","summary":"bad"}', '{"summary":', '```json\n{}\n```'):
        with pytest.raises(AIResponseError):
            validate_response(text, bundle)
