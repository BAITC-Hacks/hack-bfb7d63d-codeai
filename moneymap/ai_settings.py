"""Explicit local AI configuration; secrets never appear in repr or errors."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import re
from typing import Mapping


OPENAI_MODEL = "gpt-4.1-mini-2025-04-14"
NVIDIA_MODEL = "meta/llama-3.3-70b-instruct"
SUPPORTED_MODELS = {"openai": OPENAI_MODEL, "nvidia": NVIDIA_MODEL}
DEFAULT_ROOT = Path(__file__).resolve().parents[1]


class AIConfigError(ValueError):
    """A configuration failure with a predefined, secret-free explanation."""


def _integer(value, minimum, maximum) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


@dataclass(frozen=True)
class AISettings:
    provider: str
    model: str
    api_key: str = field(repr=False)
    enabled: bool = False
    max_output_tokens: int = 1200
    timeout_seconds: int = 45
    budget_usd: float = 1.0
    max_requests: int = 20
    max_total_tokens: int = 200_000

    def __post_init__(self):
        if self.provider not in SUPPORTED_MODELS:
            raise AIConfigError("AI провайдері қолдау таппайды.")
        if self.model != SUPPORTED_MODELS[self.provider]:
            raise AIConfigError("Бұл модель қолдау таппайды; тек тексерілген модельді таңдаңыз.")
        if not isinstance(self.enabled, bool):
            raise AIConfigError("AI қосқышы true немесе false болуы керек.")
        if not isinstance(self.api_key, str) or any(ord(char) < 33 or ord(char) > 126 for char in self.api_key):
            raise AIConfigError("API кілтінің пішімі жарамсыз; бос орын мен басқару таңбаларын алып тастаңыз.")
        if not _integer(self.max_output_tokens, 1, 8192):
            raise AIConfigError("AI жауап көлемі 1–8192 токен аралығында болуы керек.")
        if not _integer(self.timeout_seconds, 1, 120):
            raise AIConfigError("AI күту уақыты 1–120 секунд аралығында болуы керек.")
        if isinstance(self.budget_usd, bool) or not isinstance(self.budget_usd, (int, float)) or not math.isfinite(self.budget_usd) or not 0 < self.budget_usd <= 50:
            raise AIConfigError("Жергілікті AI бюджеті 0-ден үлкен және 50 USD-ден аспауы керек.")
        if not _integer(self.max_requests, 1, 10_000):
            raise AIConfigError("AI сұрау шегі 1–10000 аралығындағы бүтін сан болуы керек.")
        if not _integer(self.max_total_tokens, 1, 10_000_000):
            raise AIConfigError("AI токен шегі 1–10000000 аралығындағы бүтін сан болуы керек.")

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.api_key)


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read a small KEY=value subset without interpolation or shell execution."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(262_145)
    except FileNotFoundError:
        return {}
    except OSError:
        raise AIConfigError(".env файлын оқу мүмкін болмады.") from None
    if len(raw) > 262_144:
        raise AIConfigError(".env файлы тым үлкен.")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AIConfigError(".env файлын UTF-8 пішімінде сақтаңыз.") from None
    values = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise AIConfigError(".env жолы KEY=value пішімінде болуы керек.")
        key, value = (part.strip() for part in line.split("=", 1))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise AIConfigError(".env параметр атауы жарамсыз.")
        if value.startswith(("'", '"')):
            quote = value[0]
            closing = value.find(quote, 1)
            if closing == -1 or (value[closing + 1:].strip() and not value[closing + 1:].strip().startswith("#")):
                raise AIConfigError(".env тырнақшалары жабылмаған немесе мән пішімі жарамсыз.")
            value = value[1:closing]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
        values[key] = value
    return values


def load_settings(provider: str, root: Path | None = None, environ: Mapping | None = None) -> AISettings:
    """Environment values override .env, including explicitly empty values.

    Loading never enables AI implicitly and does not perform network calls.
    Model aliases/custom endpoints are intentionally unsupported so pricing
    assumptions cannot silently switch under the local budget guard.
    """
    if provider not in SUPPORTED_MODELS:
        raise AIConfigError("AI провайдері қолдау таппайды.")
    values = _read_dotenv((Path(root) if root is not None else DEFAULT_ROOT) / ".env")
    environment = os.environ if environ is None else environ

    def value(key: str, default: str) -> str:
        found = environment[key] if key in environment else values.get(key, default)
        if not isinstance(found, str):
            raise AIConfigError("AI орта параметрі мәтін болуы керек.")
        return found.strip()

    enabled = value("MONEYMAP_AI_ENABLED", "false").lower()
    if enabled not in {"true", "false"}:
        raise AIConfigError("MONEYMAP_AI_ENABLED мәні true немесе false болуы керек.")
    try:
        output = int(value("MONEYMAP_AI_MAX_OUTPUT_TOKENS", "1200"))
        timeout = int(value("MONEYMAP_AI_TIMEOUT_SECONDS", "45"))
        budget = float(value("MONEYMAP_AI_BUDGET_USD", "1"))
        requests = int(value("MONEYMAP_AI_MAX_REQUESTS", "20"))
        tokens = int(value("MONEYMAP_AI_MAX_TOTAL_TOKENS", "200000"))
    except (ValueError, OverflowError):
        raise AIConfigError("AI бюджеті, сұрау саны немесе токен шегі сан түрінде берілуі керек.") from None
    prefix = provider.upper()
    return AISettings(
        provider=provider, model=value(f"{prefix}_MODEL", SUPPORTED_MODELS[provider]),
        api_key=value(f"{prefix}_API_KEY", ""), enabled=enabled == "true",
        max_output_tokens=output, timeout_seconds=timeout, budget_usd=budget,
        max_requests=requests, max_total_tokens=tokens,
    )
