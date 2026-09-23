"""Explainable observation signals, never fraud labels or calibrated scores.

All methods use the supplied transactions only. Calendar baselines include
zero-activity days, peer comparisons stay within depth, and unavailable or
degenerate comparisons are reported instead of manufacturing a score.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import numbers

import numpy as np
import pandas as pd

from moneymap.data import _exact_integer
from moneymap.graph import AnalysisResult


SIGNAL_LABELS = {
    "similar_amounts": "Ұқсас сомалармен қайталау",
    "daily_spike": "Күндік белсенділіктің өсуі",
    "same_day_payers": "Бір күндегі бірнеше жіберуші",
    "depth_peer_outlier": "Өз буынындағы көлем айырмасы",
}
ALERT_COLUMNS = [
    "gid", "signal", "direction", "date", "depth", "is_seed", "boundary",
    "window_edge_day", "n_tx", "sum_kzt", "n_counterparties", "observed_value",
    "baseline_value", "statistic", "threshold", "amount_min_kzt", "amount_max_kzt",
    "peer_n", "peer_median_log", "peer_mad_log", "observed_days", "explanation", "caveats",
]


@dataclass
class AnomalyAnalysis:
    alerts: pd.DataFrame
    summary: dict
    limitations: tuple[str, ...]


def _integer(value, name: str, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < minimum:
        raise ValueError(f"{name}: {minimum}-ден кем емес бүтін сан болуы керек")


def _real(value, name: str, *, minimum: float, strict: bool = False, maximum=None) -> None:
    if (isinstance(value, bool) or not isinstance(value, numbers.Real)
            or not math.isfinite(value) or (value <= minimum if strict else value < minimum)
            or (maximum is not None and value > maximum)):
        raise ValueError(f"{name}: рұқсат етілген аралықтағы шекті сан болуы керек")


def _transactions(analysis: AnalysisResult, transactions: pd.DataFrame) -> pd.DataFrame:
    """Reject partial/stale inputs and preserve exact IDs and duplicate rows."""
    required = {"src", "dst", "date", "sum_kzt"}
    if not isinstance(transactions, pd.DataFrame) or required - set(transactions.columns):
        raise ValueError("transactions: src, dst, date, sum_kzt бағандары қажет")
    frame = transactions[["src", "dst", "date", "sum_kzt"]].copy(deep=True)
    for name in ("src", "dst"):
        try:
            frame[name] = pd.Series([_exact_integer(value) for value in frame[name]], index=frame.index, dtype="int64")
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"transactions.{name}: дәл int64 идентификатор қажет") from error
    if any(isinstance(value, (bool, numbers.Number)) for value in frame["date"]):
        raise ValueError("transactions.date: сандық күннің өлшем бірлігі белгісіз")
    try:
        dates = pd.to_datetime(frame["date"], format="mixed", errors="raise")
        if dates.isna().any() or dates.dt.tz is not None:
            raise ValueError("date")
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError("transactions.date: бірдей уақыт белдеуіндегі бос емес күндер қажет") from error
    frame["date"] = dates.dt.normalize()
    if any(isinstance(value, bool) for value in frame["sum_kzt"]):
        raise ValueError("transactions.sum_kzt: логикалық мән сома бола алмайды")
    try:
        frame["sum_kzt"] = pd.to_numeric(frame["sum_kzt"], errors="raise").astype("float64")
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("transactions.sum_kzt: оң шекті сома қажет") from error
    if not np.isfinite(frame["sum_kzt"]).all() or not frame["sum_kzt"].gt(0).all():
        raise ValueError("transactions.sum_kzt: оң шекті сома қажет")

    observed = frame.groupby(["src", "dst"], sort=True)["sum_kzt"].agg(["size", "sum"])
    if set(observed.index) != set(analysis.graph.edges):
        raise ValueError("Транзакциялар мен графтың байланыстары сәйкес емес")
    for src, dst, count, total in observed.reset_index().itertuples(index=False, name=None):
        edge = analysis.graph.edges[int(src), int(dst)]
        if count != edge["n_tx"] or not math.isfinite(total) or not math.isclose(total, edge["sum_kzt"], rel_tol=0, abs_tol=0.01):
            raise ValueError("Транзакциялар толық емес немесе граф сомаларына сәйкес емес")
    if not frame.empty:
        for name, value in (("min_date", frame["date"].min()), ("max_date", frame["date"].max())):
            expected = analysis.summary.get(name)
            if expected is not None and value.strftime("%Y-%m-%d") != expected:
                raise ValueError("Транзакциялар кезеңі графтың бақылау кезеңіне сәйкес емес")
    return frame.sort_values(["src", "dst", "date", "sum_kzt"], kind="stable").reset_index(drop=True)


def _similar_band(group: pd.DataFrame, tolerance: float, reference: float | None) -> pd.DataFrame:
    """Densest bounded band; no transitive chaining of near amounts.

    Without a reference, max <= min * (1+tolerance). Equal-count ties pick the
    smallest lower amount. With a reference, both endpoints are inclusive.
    """
    ordered = group.sort_values(["sum_kzt", "dst"], kind="stable").reset_index(drop=True)
    amounts = ordered["sum_kzt"].to_numpy()
    if reference is not None:
        return ordered.loc[ordered["sum_kzt"].between(reference * (1 - tolerance), reference * (1 + tolerance))]
    left, best_left, best_right = 0, 0, 0
    for right, value in enumerate(amounts):
        while left < right and (value - amounts[left]) / amounts[left] > tolerance + 1e-12:
            left += 1
        if right + 1 - left > best_right - best_left:
            best_left, best_right = left, right + 1
    return ordered.iloc[best_left:best_right]


def analyze_anomalies(
    analysis: AnalysisResult, transactions: pd.DataFrame, *,
    reference_amount: float | None = None, amount_tolerance: float = 0.05,
    repeat_min_tx: int = 3, spike_min_tx: int = 5, spike_ratio: float = 3.0,
    min_observation_days: int = 7, sync_min_payers: int = 3,
    peer_min_size: int = 10, peer_z_threshold: float = 3.5, max_alerts: int = 1000,
) -> AnomalyAnalysis:
    """Return four deterministic signals with numeric evidence and parameters.

    Repeats concern one sender on one date. Daily spikes compare a node's
    incoming/outgoing transaction count with its mean on *all other calendar
    days*, including zero days; a zero baseline has no invented ratio. Multi-
    payer signals require distinct senders on a date, not simultaneous times.

    Peer volumes are external in/out totals, compared only within node depth
    using (log1p(volume)-median)/(1.4826*MAD). Zero/near-zero scale and small
    groups are skipped. Seed incoming and depth-4 outgoing peer comparisons
    are excluded because their coverage is censored. Self transfers enter none
    of the four signals, but remain in the original graph and its accounting.

    max_alerts caps display/export rows only. Every candidate is evaluated and
    counts describe all detected signals. Output is in stable rule order, not
    a cross-rule severity ranking. The inputs are never modified.
    """
    if reference_amount is not None:
        _real(reference_amount, "reference_amount", minimum=0, strict=True)
    _real(amount_tolerance, "amount_tolerance", minimum=0, maximum=1)
    _real(spike_ratio, "spike_ratio", minimum=1, strict=True)
    _real(peer_z_threshold, "peer_z_threshold", minimum=0, strict=True)
    for name, value, minimum in (
        ("repeat_min_tx", repeat_min_tx, 2), ("spike_min_tx", spike_min_tx, 2),
        ("min_observation_days", min_observation_days, 3), ("sync_min_payers", sync_min_payers, 2),
        ("peer_min_size", peer_min_size, 5), ("max_alerts", max_alerts, 0),
    ):
        _integer(value, name, minimum)
    if reference_amount is not None and not math.isfinite(float(reference_amount) * (1 + float(amount_tolerance))):
        raise ValueError("reference_amount: сома аралығы сандық шектен аспауы керек")
    params = {
        "reference_amount": float(reference_amount) if reference_amount is not None else None,
        "amount_tolerance": float(amount_tolerance), "repeat_min_tx": int(repeat_min_tx),
        "spike_min_tx": int(spike_min_tx), "spike_ratio": float(spike_ratio),
        "min_observation_days": int(min_observation_days), "sync_min_payers": int(sync_min_payers),
        "peer_min_size": int(peer_min_size), "peer_z_threshold": float(peer_z_threshold), "max_alerts": int(max_alerts),
    }
    frame = _transactions(analysis, transactions)
    external = frame.loc[frame["src"].ne(frame["dst"])].copy()
    records = {int(row["gid"]): row for row in analysis.nodes.to_dict("records")}
    if len(records) != len(analysis.nodes) or set(records) != set(analysis.graph):
        raise ValueError("Клиент көрсеткіштері мен граф сәйкес емес")
    first, last = (frame["date"].min(), frame["date"].max()) if not frame.empty else (None, None)
    days = (last.date() - first.date()).days + 1 if first is not None else 0
    counts = dict.fromkeys(SIGNAL_LABELS, 0)
    rows = []

    def emit(gid, signal, direction, date=None, **facts):
        counts[signal] += 1
        if len(rows) >= max_alerts:
            return
        node = records[int(gid)]
        edge_day = date is not None and date in (first, last)
        caveats = ["Тек көрінетін операциялар; белгі кінәлілік ықтималдығы емес."]
        if bool(node["is_seed"]):
            caveats.append("Seed кірістері толық емес.")
        if int(node["depth"]) == 4:
            caveats.append("4-буыннан кейінгі шығыс қамтылмауы мүмкін.")
        if edge_day:
            caveats.append("Кезеңнің шеткі күні: тәуліктің толық қамтылғаны расталмаған.")
        row = dict.fromkeys(ALERT_COLUMNS)
        row.update({
            "gid": str(int(gid)), "signal": signal, "direction": direction,
            "date": date.strftime("%Y-%m-%d") if date is not None else "",
            "depth": int(node["depth"]), "is_seed": bool(node["is_seed"]),
            "boundary": int(node["depth"]) == 4, "window_edge_day": bool(edge_day),
            "observed_days": days, "caveats": " ".join(caveats), **facts,
        })
        rows.append(row)

    # The same-day sender band is a repeat pattern, not proof of structuring.
    for (gid, date), group in external.groupby(["src", "date"], sort=True):
        if len(group) < repeat_min_tx:
            continue
        band = _similar_band(group, float(amount_tolerance), params["reference_amount"])
        if len(band) >= repeat_min_tx:
            low, high = float(band["sum_kzt"].min()), float(band["sum_kzt"].max())
            emit(gid, "similar_amounts", "outgoing", date,
                 n_tx=len(band), sum_kzt=float(band["sum_kzt"].sum()), n_counterparties=int(band["dst"].nunique()),
                 observed_value=len(band), statistic=len(band), threshold=repeat_min_tx,
                 amount_min_kzt=low, amount_max_kzt=high,
                 explanation=f"Бір жіберушінің бір күнде {low:.2f}–{high:.2f} ₸ аралығындағы {len(band)} аударымы бар; минимум {repeat_min_tx}. Бұл бөлшектеуге ұқсас үлгі болуы мүмкін; мақсаты анықталмаған.")

    zero_baseline_days = 0
    if days >= min_observation_days:
        for direction, by, other in (("outgoing", "src", "dst"), ("incoming", "dst", "src")):
            totals = external.groupby(by, sort=True).size()
            for (gid, date), group in external.groupby([by, "date"], sort=True):
                count = len(group)
                if count < spike_min_tx:
                    continue
                baseline = (int(totals.loc[gid]) - count) / (days - 1)
                if baseline <= 0:
                    zero_baseline_days += 1
                    continue
                ratio = count / baseline
                if ratio >= spike_ratio:
                    emit(gid, "daily_spike", direction, date,
                         n_tx=count, sum_kzt=float(group["sum_kzt"].sum()), n_counterparties=int(group[other].nunique()),
                         observed_value=count, baseline_value=baseline, statistic=ratio, threshold=spike_ratio,
                         explanation=f"Осы күні {count} операция; қалған {days - 1} күннің орташа саны {baseline:.4f} (бос күндер де кіреді). Өсу {ratio:.2f} есе, шарт ≥{spike_ratio:g}; күндік минимум {spike_min_tx}.")

    for (gid, date), group in external.groupby(["dst", "date"], sort=True):
        payers = int(group["src"].nunique())
        if payers >= sync_min_payers:
            emit(gid, "same_day_payers", "incoming", date,
                 n_tx=len(group), sum_kzt=float(group["sum_kzt"].sum()), n_counterparties=payers,
                 observed_value=payers, statistic=payers, threshold=sync_min_payers,
                 explanation=f"Бір күнде {payers} әртүрлі жіберушіден {len(group)} кіріс операциясы; шарт ≥{sync_min_payers} жіберуші. Бір мезетте жасалғаны немесе ортақ жоспар болғаны анықталмайды.")

    peer_groups = []
    for direction, by, other in (("incoming", "dst", "src"), ("outgoing", "src", "dst")):
        totals = external.groupby(by, sort=True)["sum_kzt"].sum()
        tx_counts = external.groupby(by, sort=True).size()
        counterparties = external.groupby(by, sort=True)[other].nunique()
        for depth in sorted({int(row["depth"]) for row in records.values()}):
            candidates = sorted(gid for gid, node in records.items() if int(node["depth"]) == depth
                                and not (direction == "incoming" and bool(node["is_seed"]))
                                and not (direction == "outgoing" and depth == 4))
            group_info = {"depth": depth, "direction": direction, "n_peers": len(candidates)}
            if len(candidates) < peer_min_size:
                peer_groups.append({**group_info, "status": "coverage_excluded" if not candidates else "small_group"})
                continue
            values = np.asarray([float(totals.get(gid, 0.0)) for gid in candidates], dtype="float64")
            if not np.isfinite(values).all():
                raise ValueError("Клиент айналымы сандық шектен асты")
            logged = np.log1p(values)
            median = float(np.median(logged))
            mad = float(np.median(np.abs(logged - median)))
            scale = 1.4826 * mad
            group_info.update({"median_log": median, "mad_log": mad, "scale_log": scale})
            if scale <= 1e-12:
                peer_groups.append({**group_info, "status": "zero_robust_scale"})
                continue
            peer_groups.append({**group_info, "status": "evaluated"})
            for gid, value, log_value in zip(candidates, values, logged):
                z = float((log_value - median) / scale)
                if z >= peer_z_threshold:
                    emit(gid, "depth_peer_outlier", direction,
                         n_tx=int(tx_counts.get(gid, 0)), sum_kzt=float(value), n_counterparties=int(counterparties.get(gid, 0)),
                         observed_value=float(value), baseline_value=math.expm1(median), statistic=z, threshold=peer_z_threshold,
                         peer_n=len(candidates), peer_median_log=median, peer_mad_log=mad,
                         explanation=f"{depth}-буындағы {len(candidates)} клиентпен көлем салыстырылды. z=(log1p({value:.2f})−{median:.6f})/(1.4826×{mad:.6f})={z:.2f}; шарт ≥{peer_z_threshold:g}. Бір буын клиенттің кәсібі бірдей дегенді білдірмейді.")

    detected = sum(counts.values())
    return AnomalyAnalysis(
        pd.DataFrame(rows, columns=ALERT_COLUMNS),
        {
            "parameters": params, "n_nodes": len(records), "n_transactions": len(frame),
            "excluded_self_transfers": len(frame) - len(external),
            "observed_below_case_sampling_floor": int(frame["sum_kzt"].lt(5000).sum()),
            "observation_period": {"first_date": first.strftime("%Y-%m-%d") if first is not None else None,
                                   "last_date": last.strftime("%Y-%m-%d") if last is not None else None,
                                   "calendar_days": days, "endpoint_days_may_be_censored": True},
            "alerts_detected": detected, "alerts_returned": len(rows), "alerts_truncated": detected > len(rows),
            "signal_counts": counts, "spikes_evaluated": days >= min_observation_days,
            "spike_zero_baseline_node_days_skipped": zero_baseline_days, "peer_groups": peer_groups,
            "order": "rule, direction, exact client identifier, date; not severity",
            "peer_formula": "(log1p(external_volume)-median_log)/(1.4826*MAD_log); scale <=1e-12 is excluded",
        },
        (
            "Барлық нәтижелер — бақыланған үлгілер. Статистика кінәлілік ықтималдығы емес; әр ереженің бірлігі бөлек, олар бір ортақ ұпайға қосылмайды.",
            "Соманың үлгі мәні мен төзімі — талдаушы параметрлері, заңдық немесе банктік бақылау шектері емес. Ұқсас аударымдар қалыпты төлемдер болуы мүмкін.",
            "Кейстегі 5 000 ₸ іріктеу шегі төмен сомалы операцияларды өткізіп жіберуі мүмкін. Ереже тек файлдағы жолдарды көреді; басқа банктер мен бақылау мерзімінен тыс қозғалыс қалпына келтірілмейді.",
            "Бақылау аралығы файлдағы ең ерте және ең кеш күннен алынады; аралықтағы бос күндер орташаға кіреді. Шеткі тәуліктердің толық қамтылуы белгісіз; салыстыру болашақты болжау емес.",
            "Өзіне аударымдар бұл белгілерге кірмейді. Қайталанған бастапқы жолдар операция ретінде сақталады; дерек көзіндегі ықтимал техникалық көшірмелерді жеке тексеру керек.",
            "Seed кірісі мен 4-буын шығысы толық емес. Олар тиісті көлем салыстыруынан алынады; өзге бақыланған белгілерде шектеу көрсетіледі. Бір күндегі бірнеше жіберуші уақыт бойынша синхрондылықты дәлелдемейді.",
            "Буын бойынша салыстыру тек құрылымдық ұқсастықты қолданады. Клиенттің кәсібі, әдеттегі табысы және расталған белгілер берілмеген; дәлдік немесе жалған белгілер үлесі бағаланған жоқ.",
        ),
    )
