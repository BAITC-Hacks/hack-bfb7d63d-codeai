"""Read and validate case inputs without losing nodes or altering raw files.

This module deliberately does not infer roles, identify crimes, or repair bad
rows. Normalized DataFrame copies are returned alongside explicit diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from io import BytesIO
import math
import numbers
import re
from typing import Literal

import pandas as pd


REQUIRED_COLUMNS = {
    "nodes": ("gid", "depth", "is_seed"),
    "edges": ("src", "dst", "sum_kzt", "n_tx", "depth"),
    "transactions": ("src", "dst", "date", "sum_kzt"),
}
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
FLOAT_SAFE_INTEGER_MAX = 2**53 - 1


@dataclass(frozen=True)
class Issue:
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    file: str | None = None


@dataclass
class ValidationResult:
    valid: bool
    issues: list[Issue] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)


def _exact_integer(value: object) -> int:
    """Never route integer identifiers through a lossy floating-point cast."""
    if isinstance(value, (bool,)) or type(value).__name__ == "bool_":
        raise ValueError("boolean is not an integer identifier")
    if isinstance(value, numbers.Integral):
        result = int(value)
    elif isinstance(value, numbers.Real):
        if not math.isfinite(value) or value != math.trunc(value):
            raise ValueError("not finite/integral")
        if abs(value) > FLOAT_SAFE_INTEGER_MAX:
            raise ValueError("float may already have lost identifier precision")
        result = int(value)
    elif isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        result = int(value.strip())
    elif isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        result = int(value)
    else:
        raise ValueError("not an integer")
    if not INT64_MIN <= result <= INT64_MAX:
        raise ValueError("outside signed int64")
    return result


def _seed_boolean(value: object) -> bool:
    if isinstance(value, bool) or type(value).__name__ == "bool_":
        return bool(value)
    if isinstance(value, numbers.Integral) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "false", "0", "1"):
        return value.strip().lower() in ("true", "1")
    raise ValueError("expected boolean or integer 0/1")


def validate_dataset(frames: dict[str, pd.DataFrame]) -> ValidationResult:
    """Validate the three input tables and return independent normalized copies.

    Sizes are observed, never fixed to the competition's published row counts.
    Warnings represent incomplete observation, not suspected illegal activity.
    """
    issues: list[Issue] = []
    normalized: dict[str, pd.DataFrame] = {}
    good: set[tuple[str, str]] = set()

    def report(severity: str, code: str, message: str, name: str | None = None) -> None:
        issues.append(Issue(severity, code, message, f"{name}.parquet" if name else None))

    for name, required in REQUIRED_COLUMNS.items():
        frame = frames.get(name)
        if frame is None:
            report("error", "missing_file", "Міндетті файл жүктелмеген.", name)
            continue
        if not isinstance(frame, pd.DataFrame):
            report("error", "invalid_table", "Файл кесте ретінде оқылмады.", name)
            continue
        frame = frame.copy(deep=True)
        normalized[name] = frame
        if frame.columns.duplicated().any():
            report("error", "duplicate_columns", "Баған атаулары қайталанады; әр атау бірегей болуы керек.", name)
            continue
        missing = [column for column in required if column not in frame]
        if missing:
            report("error", "missing_columns", f"Міндетті бағандар жоқ: {', '.join(missing)}.", name)
        if frame.empty:
            report("error" if name == "nodes" else "warning", "empty_table", "Кестеде бірде-бір жол жоқ.", name)
        for column in required:
            if column not in frame:
                continue
            series = frame[column]
            missing_count = int(series.isna().sum())
            if missing_count:
                report("error", "null_values", f"{column}: {missing_count} жолда міндетті мән толтырылмаған.", name)
                continue
            try:
                if column in ("gid", "src", "dst", "depth", "n_tx"):
                    values = [_exact_integer(value) for value in series]
                    frame[column] = pd.Series(values, index=frame.index, dtype="int64")
                    if column == "depth" and not frame[column].between(0, 4).all():
                        report("error", "invalid_depth", "depth: тереңдік 0–4 аралығындағы бүтін сан болуы керек.", name)
                        continue
                    if column == "n_tx" and not frame[column].gt(0).all():
                        report("error", "invalid_count", "n_tx: операция саны нөлден үлкен бүтін сан болуы керек.", name)
                        continue
                elif column == "is_seed":
                    frame[column] = pd.Series([_seed_boolean(value) for value in series], index=frame.index, dtype=bool)
                elif column == "sum_kzt":
                    if any(isinstance(value, bool) or type(value).__name__ == "bool_" for value in series):
                        raise ValueError("boolean money")
                    converted = pd.to_numeric(series, errors="coerce")
                    if not converted.map(lambda value: math.isfinite(value) and value > 0).all():
                        report("error", "invalid_amount", "sum_kzt: әр сома нөлден үлкен, шекті сан болуы керек (NaN/inf жарамсыз).", name)
                        continue
                    # Monetary calculations use floats to avoid silent int64
                    # wraparound during groupby/sum. Overflow is checked below.
                    frame[column] = converted.astype("float64")
                elif column == "date":
                    if any(isinstance(value, numbers.Number) for value in series):
                        raise ValueError("numeric date has no declared epoch unit")
                    dates = pd.to_datetime(series, format="mixed", errors="coerce", utc=True)
                    if dates.isna().any():
                        report("error", "invalid_date", "date: кейбір күндер танылмады; мысалы, 2026-07-01 пішімін қолданыңыз.", name)
                        continue
                    frame[column] = dates.dt.tz_localize(None)
                good.add((name, column))
            except (ValueError, TypeError, OverflowError):
                if column == "is_seed":
                    message = "is_seed: true/false немесе бүтін 0/1 мәндері қажет."
                elif column == "date":
                    message = "date: жарамды күн қажет; белгісіз бірліктегі сандық уақыт қабылданбайды."
                elif column == "sum_kzt":
                    message = "sum_kzt: жарамды оң сан қажет; логикалық мән сома бола алмайды."
                else:
                    message = f"{column}: дәл int64 бүтін саны қажет; бөлшек, inf, логикалық мән немесе дәлдігін жоғалтқан үлкен float жарамсыз."
                report("error", f"invalid_{column}", message, name)

    def ready(name: str, *columns: str) -> bool:
        return all((name, column) in good for column in columns)

    if ready("nodes", "depth", "is_seed"):
        nodes = normalized["nodes"]
        inconsistent = nodes["is_seed"] != nodes["depth"].eq(0)
        if inconsistent.any():
            report("error", "inconsistent_seed_depth", f"{int(inconsistent.sum())} клиентте is_seed және depth сәйкес емес: бастапқы клиенттің тереңдігі 0, қалғандарынікі 1–4 болуы керек.", "nodes")

    if ready("nodes", "gid"):
        nodes = normalized["nodes"]
        duplicate_count = int(nodes["gid"].duplicated().sum())
        if duplicate_count:
            report("error", "duplicate_gid", f"gid: {duplicate_count} қайталанған жол бар; клиент идентификаторы бірегей болуы керек.", "nodes")
        known = set(nodes["gid"])
        for name in ("edges", "transactions"):
            for column in ("src", "dst"):
                if ready(name, column):
                    unknown = set(normalized[name][column]) - known
                    if unknown:
                        examples = ", ".join(map(str, sorted(unknown)[:5]))
                        report("error", "unknown_endpoint", f"{column}: nodes ішінде жоқ {len(unknown)} клиент табылды. Мысалы: {examples}.", name)

    if ready("edges", "src", "dst"):
        duplicates = int(normalized["edges"].duplicated(["src", "dst"]).sum())
        if duplicates:
            report("error", "duplicate_edge", f"{duplicates} қайталанған src → dst жұбы бар; edges әр жұпты бір рет қамтуы керек.", "edges")

    if ready("edges", "src", "dst", "sum_kzt", "n_tx") and ready("transactions", "src", "dst", "sum_kzt"):
        edges = normalized["edges"]
        transactions = normalized["transactions"]
        aggregated = transactions.groupby(["src", "dst"], sort=True).agg(
            transaction_sum=("sum_kzt", "sum"), transaction_count=("sum_kzt", "size")
        ).reset_index()
        if not aggregated["transaction_sum"].map(math.isfinite).all():
            report("error", "aggregate_overflow", "Кейбір жұптардың жиынтық сомасы шекті сан емес; мәндер сандық шектен асып кетті.", "transactions")
        compared = edges[["src", "dst", "sum_kzt", "n_tx"]].merge(
            aggregated, on=["src", "dst"], how="outer", indicator=True
        )
        # Merge uses int64 IDs on both sides; avoid iterrows, which can silently
        # convert large identifiers into float when money columns are present.
        absent_edges = int((compared["_merge"] == "right_only").sum())
        absent_transactions = int((compared["_merge"] == "left_only").sum())
        if absent_edges or absent_transactions:
            report("error", "pair_mismatch", f"Жұптар сәйкес емес: edges ішінде жоқ — {absent_edges}; transactions ішінде жоқ — {absent_transactions}.")
        shared = compared.loc[compared["_merge"] == "both"]
        count_mismatch = int((shared["n_tx"] != shared["transaction_count"]).sum())
        if count_mismatch:
            report("error", "count_mismatch", f"{count_mismatch} жұпта n_tx нақты транзакциялар санына сәйкес емес.", "edges")
        sum_mismatch = sum(
            not math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=0.01)
            for left, right in zip(shared["sum_kzt"], shared["transaction_sum"])
        )
        if sum_mismatch:
            report("error", "amount_mismatch", f"{sum_mismatch} жұпта edges сомасы транзакциялар қосындысына сәйкес емес (абсолюттік төзім: 0,01 ₸).", "edges")

    metrics = {
        "nodes": len(normalized.get("nodes", [])),
        "edges": len(normalized.get("edges", [])),
        "transactions": len(normalized.get("transactions", [])),
        "seeds": None,
        "boundary_nodes": None,
        "isolated_nodes": None,
        "turnover_kzt": None,
        "min_date": None,
        "max_date": None,
    }
    if ready("nodes", "is_seed"):
        metrics["seeds"] = int(normalized["nodes"]["is_seed"].sum())
        if metrics["seeds"]:
            report("warning", "seed_incoming_incomplete", "Бастапқы клиенттердің (seed) кірістері толық емес: шығыс/кіріс қатынасы толық балансты білдірмейді.", "nodes")
    if ready("nodes", "depth"):
        metrics["boundary_nodes"] = int(normalized["nodes"]["depth"].eq(4).sum())
        if metrics["boundary_nodes"]:
            report("warning", "boundary_truncation", f"{metrics['boundary_nodes']} клиент 4-буында: кейінгі аударымдар бақыланбауы мүмкін; оларды автоматты түрде соңғы алушы деуге болмайды.", "nodes")
    if ready("nodes", "gid") and ready("edges", "src", "dst"):
        nodes, edges = normalized["nodes"], normalized["edges"]
        connected = set(edges["src"]) | set(edges["dst"])
        isolated = ~nodes["gid"].isin(connected)
        metrics["isolated_nodes"] = int(isolated.sum())
        if ready("nodes", "is_seed"):
            isolated_seeds = int((isolated & nodes["is_seed"]).sum())
            if isolated_seeds:
                report("warning", "isolated_seeds", f"{isolated_seeds} seed клиенттің бақыланған байланысы жоқ. Олар кестеде толық сақталды.", "nodes")
        if ready("edges", "sum_kzt"):
            outgoing = edges.groupby("src")["sum_kzt"].sum()
            incoming = edges.groupby("dst")["sum_kzt"].sum()
            if not outgoing.map(math.isfinite).all() or not incoming.map(math.isfinite).all():
                report("error", "aggregate_overflow", "Клиенттердің жиынтық кіріс немесе шығыс сомасы сандық шектен асты.", "edges")
            balances = pd.concat([outgoing.rename("out"), incoming.rename("in")], axis=1).fillna(0)
            count = int((balances["out"] > balances["in"] + 0.01).sum())
            if count:
                report("warning", "outgoing_exceeds_incoming", f"{count} клиенттің бақыланған шығысы кірісінен артық. Бұл толық емес үзінді; өздігінен заңсыздық белгісі емес.")
    for name in ("edges", "transactions"):
        if not ready(name, "sum_kzt"):
            continue
        try:
            total = math.fsum(normalized[name]["sum_kzt"])
        except OverflowError:
            total = math.inf
        if not math.isfinite(total):
            report("error", "total_overflow", "Сомалардың жиынтығы сандық шектен асты.", name)
        elif name == "transactions":
            metrics["turnover_kzt"] = total
    if ready("transactions", "sum_kzt"):
        below_threshold = int(normalized["transactions"]["sum_kzt"].lt(5000).sum())
        if below_threshold:
            report("warning", "below_threshold", f"{below_threshold} аударым 5 000 ₸ шегінен төмен; бұл кейстегі іріктеу шартынан өзгеше.", "transactions")
    if ready("transactions", "date") and not normalized["transactions"].empty:
        dates = normalized["transactions"]["date"]
        metrics["min_date"] = dates.min().strftime("%Y-%m-%d")
        metrics["max_date"] = dates.max().strftime("%Y-%m-%d")
        out_of_period = ~((dates >= pd.Timestamp("2026-07-01")) & (dates < pd.Timestamp("2026-08-01")))
        if out_of_period.any():
            report("warning", "out_of_period", f"{int(out_of_period.sum())} операция 2026 жылғы шілдеден тыс; кезеңді дерек көзімен тексеріңіз.", "transactions")
    report("info", "observation_limits", "Деректер — банк ішіндегі шектеулі кезеңнің үзіндісі. Айналым бір ақша бірнеше буыннан өткенде қайта есептелуі мүмкін.")
    return ValidationResult(not any(issue.severity == "error" for issue in issues), issues, metrics, normalized)


def load_parquet_files(files: dict[str, bytes]) -> ValidationResult:
    """Decode named uploads, returning diagnostics instead of parser tracebacks."""
    frames: dict[str, pd.DataFrame] = {}
    read_issues: list[Issue] = []
    expected = {f"{name}.parquet" for name in REQUIRED_COLUMNS}
    for filename in files:
        if filename not in expected:
            read_issues.append(Issue("warning", "unexpected_file", "Қосымша файл өңделмеді. Тек nodes.parquet, edges.parquet және transactions.parquet қолданылады.", str(filename)))
    for name in REQUIRED_COLUMNS:
        filename = f"{name}.parquet"
        if filename not in files:
            continue
        try:
            payload = files[filename]
            if not isinstance(payload, (bytes, bytearray, memoryview)):
                raise TypeError("upload must be bytes")
            frames[name] = pd.read_parquet(BytesIO(payload), engine="pyarrow")
        except Exception:
            # Input is untrusted; return a fixed message without local paths,
            # binary data or engine-specific exception details in the UI.
            read_issues.append(Issue("error", "unreadable_parquet", "Файл Parquet ретінде оқылмады. Файлдың пішімін және бүтіндігін тексеріңіз.", filename))
    result = validate_dataset(frames)
    failed_files = {issue.file for issue in read_issues if issue.severity == "error"}
    result.issues = read_issues + [
        issue for issue in result.issues
        if not (issue.code == "missing_file" and issue.file in failed_files)
    ]
    result.valid = not any(issue.severity == "error" for issue in result.issues)
    return result
