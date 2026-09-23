"""Offline ledger checks include real SQLite atomicity, never network calls."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3

import pytest

from moneymap.ai_budget import AIBudgetError, BudgetLedger
from moneymap.ai_settings import AISettings, NVIDIA_MODEL, OPENAI_MODEL


def settings(provider="openai", **overrides):
    return replace(AISettings(provider, OPENAI_MODEL if provider == "openai" else NVIDIA_MODEL, "invented-ledger-secret", enabled=True), **overrides)


def test_reservation_persists_before_dispatch_and_actual_usage_releases_difference(tmp_path):
    path = tmp_path / "budget.sqlite"
    ledger = BudgetLedger(path)
    reservation = ledger.reserve(settings(), 2000)
    restarted = BudgetLedger(path)
    stats = restarted.stats()
    assert stats["attempts"] == stats["pending_requests"] == 1 and stats["total_tokens"] == 3200
    assert stats["openai_estimated_usd"] == pytest.approx((2000 * .4 + 1200 * 1.6) / 1_000_000)
    restarted.settle(reservation, 100, 20, "success")
    stats = ledger.stats()
    assert stats["total_tokens"] == 120 and stats["settled_requests"] == 1 and stats["pending_requests"] == 0
    assert stats["openai_estimated_usd"] == pytest.approx(.000072)
    assert "invented-ledger-secret" not in path.read_bytes().decode("latin1")


@pytest.mark.parametrize("incoming,outgoing", [(None, None), (10, None), (-1, 2), (True, 2), (1.5, 2)])
def test_unknown_or_invalid_usage_retains_entire_reservation(tmp_path, incoming, outgoing):
    ledger = BudgetLedger(tmp_path / "budget.sqlite")
    reservation = ledger.reserve(settings(), 1000)
    before = ledger.stats()
    ledger.settle(reservation, incoming, outgoing, "error")
    after = ledger.stats()
    assert after["total_tokens"] == before["total_tokens"] == 2200
    assert after["openai_estimated_usd"] == before["openai_estimated_usd"]
    assert after["unknown_usage_requests"] == 1 and after["attempts"] == 1


def test_settlement_is_idempotent_and_actual_overrun_not_hidden(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite")
    reservation = ledger.reserve(settings(max_total_tokens=2500), 100)
    ledger.settle(reservation, 4000, 1500, "success")
    first = ledger.stats()
    ledger.settle(reservation, 0, 0, "success")
    assert ledger.stats() == first and first["total_tokens"] == 5500
    with pytest.raises(AIBudgetError) as caught:
        ledger.reserve(settings(max_total_tokens=2500), 100)
    assert caught.value.code == "token_limit" and ledger.stats()["attempts"] == 1


def test_attempt_limit_includes_failed_requests(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite")
    config = settings(max_requests=1)
    reservation = ledger.reserve(config, 100)
    ledger.settle(reservation, None, None, "timeout")
    with pytest.raises(AIBudgetError) as caught:
        ledger.reserve(config, 100)
    assert caught.value.code == "request_limit" and ledger.stats()["attempts"] == 1


def test_estimated_usd_guard_uses_known_snapshot_price_before_dispatch(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite")
    with pytest.raises(AIBudgetError) as caught:
        ledger.reserve(settings(budget_usd=.001), 100)
    assert caught.value.code == "budget_limit" and ledger.stats()["attempts"] == 0


def test_both_providers_share_token_and_attempt_limits_nvidia_cost_unknown(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite")
    first = ledger.reserve(settings(), 500)
    ledger.settle(first, 10, 10, "success")
    nvidia = ledger.reserve(settings("nvidia", max_requests=2), 300)
    ledger.settle(nvidia, 200, 50, "completed")
    stats = ledger.stats()
    assert stats["total_tokens"] == 270 and stats["nvidia_requests"] == 1
    assert stats["by_provider"]["nvidia"]["estimated_usd"] is None and stats["nvidia_estimated_usd"] is None
    assert stats["openai_estimated_usd"] == pytest.approx(.00002)
    with pytest.raises(AIBudgetError) as caught:
        ledger.reserve(settings("nvidia", max_requests=2), 50)
    assert caught.value.code == "request_limit"


def test_concurrent_reservations_do_not_oversubscribe(tmp_path):
    path = tmp_path / "budget.sqlite"
    BudgetLedger(path)
    config = settings(max_requests=3, max_total_tokens=3900)

    def reserve(_):
        ledger = BudgetLedger(path)
        try:
            return ledger.reserve(config, 100)
        except AIBudgetError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(16)))
    assert len([result for result in results if result != "request_limit"]) == 3
    assert BudgetLedger(path).stats()["attempts"] == 3
    assert BudgetLedger(path).stats()["total_tokens"] == 3900


def test_concurrent_settlements_are_first_wins_not_double_counted(tmp_path):
    path = tmp_path / "budget.sqlite"
    ledger = BudgetLedger(path)
    reservation = ledger.reserve(settings(), 1000)
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda _: BudgetLedger(path).settle(reservation, 100, 50, "success"), range(10)))
    assert ledger.stats()["attempts"] == 1 and ledger.stats()["total_tokens"] == 150


def test_journal_contains_only_accounting_fields_and_unknown_id_safe(tmp_path):
    path = tmp_path / "budget.sqlite"
    ledger = BudgetLedger(path)
    ledger.reserve(settings(), 42)
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(reservations)")}
    assert not columns & {"api_key", "prompt", "payload", "gid", "response", "text"}
    with pytest.raises(AIBudgetError) as caught:
        ledger.settle("invented-ledger-secret", None, None, "failed")
    assert "invented-ledger-secret" not in str(caught.value)


def test_disabled_reservation_creates_no_attempt(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite")
    with pytest.raises(AIBudgetError):
        ledger.reserve(settings(enabled=False), 100)
    assert ledger.stats()["attempts"] == 0
