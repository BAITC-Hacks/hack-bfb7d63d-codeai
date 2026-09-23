"""Persistent local request/token guards and estimated OpenAI cost accounting.

Reservations commit atomically before dispatch. Unknown usage keeps the full
reservation across restarts; failed requests still consume the attempt limit.
This is an application guard, not a provider-side billing cap or credit balance.
No request text, client identifier, response text or API key is stored here.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
import sqlite3
from uuid import uuid4

from moneymap.ai_settings import AISettings, OPENAI_MODEL


# GPT-4.1 mini 2025-04-14: $0.40 input / $1.60 output per million tokens.
# Integer nano-USD avoids floating-point races at a spending threshold.
OPENAI_PRICE_NANOS = {OPENAI_MODEL: (400, 1600)}
SETTLEMENT_STATUSES = {"success", "completed", "error", "failed", "invalid_response", "refused", "incomplete", "timeout", "provider_error", "rejected"}


class AIBudgetError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _tokens(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100_000_000


def _cost(provider: str, model: str, incoming: int, outgoing: int) -> int | None:
    if provider == "nvidia":
        return None
    prices = OPENAI_PRICE_NANOS.get(model)
    if provider != "openai" or prices is None:
        raise AIBudgetError("unknown_price", "Бұл модель үшін тексерілген баға жоқ; сұрау жіберілмейді.")
    return incoming * prices[0] + outgoing * prices[1]


class BudgetLedger:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS reservations (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    input_reserved INTEGER NOT NULL,
                    output_reserved INTEGER NOT NULL,
                    accounted_input INTEGER NOT NULL,
                    accounted_output INTEGER NOT NULL,
                    cost_nanos INTEGER,
                    status TEXT NOT NULL DEFAULT 'reserved',
                    usage_known INTEGER NOT NULL DEFAULT 0,
                    settled INTEGER NOT NULL DEFAULT 0
                )""")
        except (OSError, sqlite3.Error):
            raise AIBudgetError("storage", "AI бюджет журналын ашу мүмкін болмады; сұрау жіберілмейді.") from None

    @contextmanager
    def _connection(self):
        connection = None
        try:
            connection = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
            connection.row_factory = sqlite3.Row
            yield connection
        except sqlite3.Error:
            raise AIBudgetError("storage", "AI бюджет журналын жаңарту мүмкін болмады; жаңа сұрау жіберілмейді.") from None
        finally:
            if connection is not None:
                connection.close()

    def reserve(self, settings: AISettings, input_upper_bound: int) -> str:
        if not settings.ready:
            raise AIBudgetError("not_ready", "AI өшірулі немесе API кілті енгізілмеген.")
        if not _tokens(input_upper_bound) or input_upper_bound == 0:
            raise AIBudgetError("invalid_reservation", "Кіріс токендерінің жоғарғы бағасы оң бүтін сан болуы керек.")
        incoming, outgoing = input_upper_bound, settings.max_output_tokens
        cost = _cost(settings.provider, settings.model, incoming, outgoing)
        budget_nanos = int(Decimal(str(settings.budget_usd)) * 1_000_000_000)
        reservation_id = str(uuid4())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            totals = connection.execute("SELECT COUNT(*) AS attempts, COALESCE(SUM(accounted_input+accounted_output),0) AS tokens, COALESCE(SUM(cost_nanos),0) AS cost FROM reservations").fetchone()
            if totals["attempts"] >= settings.max_requests:
                raise AIBudgetError("request_limit", "Жергілікті AI сұрау шегі жетті.")
            if totals["tokens"] + incoming + outgoing > settings.max_total_tokens:
                raise AIBudgetError("token_limit", "Жергілікті AI токен шегі жаңа сұрауға жеткіліксіз.")
            if cost is not None and totals["cost"] + cost > budget_nanos:
                raise AIBudgetError("budget_limit", "Жергілікті OpenAI бюджеті жаңа сұрауға жеткіліксіз.")
            connection.execute("INSERT INTO reservations (id,provider,model,input_reserved,output_reserved,accounted_input,accounted_output,cost_nanos) VALUES (?,?,?,?,?,?,?,?)", (reservation_id, settings.provider, settings.model, incoming, outgoing, incoming, outgoing, cost))
            connection.execute("COMMIT")
        return reservation_id

    def settle(self, reservation_id: str, input_tokens: int | None, output_tokens: int | None, status: str) -> None:
        """Settle once. Missing/invalid usage retains both original reservations.

        Valid usage is recorded even if it exceeds the reservation, so future
        requests see the real overrun. A repeat settlement cannot reduce it.
        """
        if status not in SETTLEMENT_STATUSES:
            raise AIBudgetError("invalid_status", "AI журнал күйі қолдау таппайды.")
        if not isinstance(reservation_id, str):
            raise AIBudgetError("unknown_reservation", "AI сұрауының бюджет жазбасы табылмады.")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM reservations WHERE id=?", (reservation_id,)).fetchone()
            if row is None:
                raise AIBudgetError("unknown_reservation", "AI сұрауының бюджет жазбасы табылмады.")
            if row["settled"]:
                connection.execute("COMMIT")
                return
            known = _tokens(input_tokens) and _tokens(output_tokens)
            incoming = input_tokens if known else row["input_reserved"]
            outgoing = output_tokens if known else row["output_reserved"]
            cost = _cost(row["provider"], row["model"], incoming, outgoing)
            connection.execute("UPDATE reservations SET accounted_input=?,accounted_output=?,cost_nanos=?,status=?,usage_known=?,settled=1 WHERE id=?", (incoming, outgoing, cost, status, int(known), reservation_id))
            connection.execute("COMMIT")

    def stats(self) -> dict:
        with self._connection() as connection:
            rows = connection.execute("SELECT provider,accounted_input,accounted_output,cost_nanos,status,usage_known,settled FROM reservations").fetchall()
        by_provider = {}
        for provider in ("openai", "nvidia"):
            selected = [row for row in rows if row["provider"] == provider]
            by_provider[provider] = {
                "requests": len(selected),
                "total_tokens": sum(row["accounted_input"] + row["accounted_output"] for row in selected),
                "estimated_usd": sum(row["cost_nanos"] or 0 for row in selected) / 1_000_000_000 if provider == "openai" else None,
            }
        return {
            "attempts": len(rows),
            "pending_requests": sum(not row["settled"] for row in rows),
            "settled_requests": sum(bool(row["settled"]) for row in rows),
            "unknown_usage_requests": sum(bool(row["settled"]) and not row["usage_known"] for row in rows),
            "conservative_requests": sum(not row["usage_known"] for row in rows),
            "total_tokens": sum(row["accounted_input"] + row["accounted_output"] for row in rows),
            "openai_estimated_usd": by_provider["openai"]["estimated_usd"],
            "nvidia_estimated_usd": None,
            "nvidia_requests": by_provider["nvidia"]["requests"],
            "by_provider": by_provider,
        }
