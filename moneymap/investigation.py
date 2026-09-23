"""Bounded, deterministic investigation aids for the supplied observation window.

These functions describe observable topology and dates. They neither trace the
same funds across transfers nor infer wrongdoing. No external service is used.
All identifiers in returned tables and briefings are strings for browser safety.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

import networkx as nx
import numpy as np
import pandas as pd

from moneymap.data import _exact_integer
from moneymap.graph import AnalysisResult
from moneymap.roles import ROLE_LABELS, RoleAnalysis


CYCLE_COLUMNS = ["path", "n_edges", "observed_edge_turnover_kzt"]
RECIPROCAL_COLUMNS = ["src", "dst", "forward_kzt", "reverse_kzt", "forward_tx", "reverse_tx"]
ROUTE_COLUMNS = [
    "src", "via", "dst", "path", "eligible_in_days", "matched_in_days", "matched_in_tx",
    "first_in_date", "last_in_date", "min_lag_days", "max_lag_days",
]
COMPARISON_COLUMNS = [
    "scenario", "n_nodes", "n_edges", "weak_components", "largest_component_nodes",
    "largest_component_share", "observed_edge_turnover_kzt", "retained_turnover_share",
]


@dataclass
class RouteAnalysis:
    cycles: pd.DataFrame
    reciprocal: pd.DataFrame
    routes: pd.DataFrame
    summary: dict
    limitations: tuple[str, ...]


@dataclass
class ResilienceAnalysis:
    comparison: pd.DataFrame
    removed_gids: tuple[str, ...]
    remaining_gids: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class NodeBriefing:
    gid: str
    text: str
    limitations: tuple[str, ...]
    next_requests: tuple[str, ...]


def _nonnegative_integer(value: int, name: str, *, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name}: {minimum}-ден кем емес бүтін сан болуы керек")


def _bounded_cycles(
    graph: nx.DiGraph, max_length: int, max_cycles: int, max_steps: int,
) -> tuple[list[dict], int, bool]:
    """Visit at most max_steps successor entries; emit each orientation once.

    A cycle starts at its smallest exact integer identifier. Self transfers are
    excluded, because they do not establish a route between distinct clients.
    An extra discovered cycle proves truncation; merely reaching the row limit
    does not. Exhausting the visit budget is conservatively marked incomplete.
    """
    neighbors = {gid: tuple(sorted(graph.successors(gid))) for gid in graph}
    rows: list[dict] = []
    steps = 0
    for start in sorted(graph):
        path = [start]
        members = {start}
        stack = [iter(neighbors[start])]
        while stack:
            target = next(stack[-1], None)
            if target is None:
                stack.pop()
                members.remove(path.pop())
                continue
            if steps >= max_steps:
                return rows, steps, True
            steps += 1
            if target == start and len(path) >= 2:
                if len(rows) >= max_cycles:
                    return rows, steps, True
                closed = [*path, start]
                rows.append({
                    "path": " → ".join(map(str, closed)),
                    "n_edges": len(path),
                    "observed_edge_turnover_kzt": math.fsum(
                        graph.edges[src, dst]["sum_kzt"] for src, dst in zip(closed, closed[1:])
                    ),
                })
            elif target > start and target not in members and len(path) < max_length:
                path.append(target)
                members.add(target)
                stack.append(iter(neighbors[target]))
    return rows, steps, False


def _daily_pairs(graph: nx.DiGraph, transactions: pd.DataFrame) -> tuple[dict, np.datetime64 | None]:
    """Read validated transactions without converting integer IDs through float."""
    missing = {"src", "dst", "date"} - set(transactions.columns)
    if missing:
        raise ValueError("transactions: бағандар жоқ: " + ", ".join(sorted(missing)))
    if transactions.empty:
        return {}, None
    dates = pd.to_datetime(transactions["date"], errors="raise")
    if dates.isna().any():
        raise ValueError("transactions.date: бос күндер болмауы керек")
    if dates.dt.tz is not None:
        raise ValueError("transactions.date: талдауға бір уақыт белдеуіндегі жергілікті күндер қажет")
    days = dates.dt.normalize().to_numpy(dtype="datetime64[D]")
    pair_days: dict[tuple[int, int], list[np.datetime64]] = {}
    for (src, dst), day in zip(transactions[["src", "dst"]].itertuples(index=False, name=None), days):
        pair = (_exact_integer(src), _exact_integer(dst))
        if not graph.has_edge(*pair):
            raise ValueError(f"transactions: графта жоқ байланыс {pair[0]} → {pair[1]}")
        pair_days.setdefault(pair, []).append(day)
    daily = {}
    for pair, values in pair_days.items():
        unique, counts = np.unique(np.asarray(values, dtype="datetime64[D]"), return_counts=True)
        daily[pair] = (unique, counts)
    return daily, days.max()


def analyze_routes(
    analysis: AnalysisResult,
    transactions: pd.DataFrame,
    *,
    window_days: int = 2,
    max_cycle_length: int = 5,
    max_cycles: int = 100,
    max_cycle_steps: int = 50_000,
    max_route_candidates: int = 20_000,
    max_routes: int = 100,
) -> RouteAnalysis:
    """Find structural cycles, reciprocal pairs, and repeated dated two-hop motifs.

    ``transactions`` must be from the same validated dataset as ``analysis``.
    A two-hop motif A→B→C requires at least two distinct incoming calendar days
    on A→B. For each such day, the first strictly later observed B→C day must
    occur within ``window_days``. Incoming days without a complete observation
    window are excluded. Duplicate transfers count in ``matched_in_tx``, but
    never create repeated days. One outgoing day may support several incoming
    days: these are temporal co-occurrences, not independently matched paths.
    ``first_in_date`` and ``last_in_date`` refer to matched incoming days.

    Cycles are bounded by length, visited successor entries, and result count.
    Two-hop search is bounded by candidate count. Returned motifs are ranked
    only among evaluated candidates; truncation and limits are explicit.
    Reciprocal pairs are enumerated once in O(E), without a temporal claim.
    """
    _nonnegative_integer(window_days, "window_days", minimum=1)
    _nonnegative_integer(max_cycle_length, "max_cycle_length", minimum=2)
    for name, value in (
        ("max_cycles", max_cycles), ("max_cycle_steps", max_cycle_steps),
        ("max_route_candidates", max_route_candidates), ("max_routes", max_routes),
    ):
        _nonnegative_integer(value, name)
    graph = analysis.graph
    daily, last_day = _daily_pairs(graph, transactions)
    cycle_rows, cycle_steps, cycles_truncated = _bounded_cycles(
        graph, max_cycle_length, max_cycles, max_cycle_steps,
    )
    reciprocal_rows = []
    for src, dst, data in sorted(graph.edges(data=True), key=lambda edge: (edge[0], edge[1])):
        if src < dst and graph.has_edge(dst, src):
            reverse = graph.edges[dst, src]
            reciprocal_rows.append({
                "src": str(src), "dst": str(dst),
                "forward_kzt": float(data["sum_kzt"]), "reverse_kzt": float(reverse["sum_kzt"]),
                "forward_tx": int(data["n_tx"]), "reverse_tx": int(reverse["n_tx"]),
            })

    cutoff = last_day - np.timedelta64(window_days, "D") if last_day is not None else None
    candidates = 0
    search_truncated = False
    route_rows = []
    if cutoff is not None:
        for via in sorted(graph):
            for src in sorted(graph.predecessors(via)):
                if src == via or (src, via) not in daily:
                    continue
                incoming_days, incoming_counts = daily[src, via]
                eligible = incoming_days <= cutoff
                incoming_days, incoming_counts = incoming_days[eligible], incoming_counts[eligible]
                for dst in sorted(graph.successors(via)):
                    if dst == via or (via, dst) not in daily:
                        continue
                    if candidates >= max_route_candidates:
                        search_truncated = True
                        break
                    candidates += 1
                    if len(incoming_days) < 2:
                        continue
                    outgoing_days = daily[via, dst][0]
                    positions = np.searchsorted(outgoing_days, incoming_days, side="right")
                    valid = positions < len(outgoing_days)
                    selected_days, selected_counts = incoming_days[valid], incoming_counts[valid]
                    lags = (outgoing_days[positions[valid]] - selected_days).astype("timedelta64[D]").astype("int64")
                    matched = lags <= window_days
                    if int(matched.sum()) < 2:
                        continue
                    selected_days, selected_counts, lags = selected_days[matched], selected_counts[matched], lags[matched]
                    route_rows.append({
                        "src": src, "via": via, "dst": dst,
                        "path": f"{src} → {via} → {dst}",
                        "eligible_in_days": len(incoming_days), "matched_in_days": len(selected_days),
                        "matched_in_tx": int(selected_counts.sum()),
                        "first_in_date": str(selected_days.min()), "last_in_date": str(selected_days.max()),
                        "min_lag_days": int(lags.min()), "max_lag_days": int(lags.max()),
                    })
                if search_truncated:
                    break
            if search_truncated:
                break
    route_rows.sort(key=lambda row: (-row["matched_in_days"], -row["matched_in_tx"], row["src"], row["via"], row["dst"]))
    n_detected = len(route_rows)
    route_rows = route_rows[:max_routes]
    for row in route_rows:
        for column in ("src", "via", "dst"):
            row[column] = str(row[column])
    summary = {
        "n_cycles": len(cycle_rows), "n_reciprocal_pairs": len(reciprocal_rows),
        "n_repeated_routes": len(route_rows), "n_repeated_routes_detected": n_detected,
        "cycles_truncated": cycles_truncated, "route_search_truncated": search_truncated,
        "routes_truncated": n_detected > max_routes,
        "cycle_steps": cycle_steps, "route_candidates": candidates,
        "window_days": window_days, "max_cycle_length": max_cycle_length,
        "max_cycles": max_cycles, "max_cycle_steps": max_cycle_steps,
        "max_route_candidates": max_route_candidates, "max_routes": max_routes,
        "temporal_cutoff_date": str(cutoff) if cutoff is not None else None,
    }
    limitations = (
        "Циклдер мен екіжақты байланыстар — бағытталған құрылым; бір ақшаның қайтып келгенін дәлелдемейді.",
        f"Екі қадамдық үлгі кемінде екі бөлек кіріс күнінде қайталанады: шығыс келесі 1–{window_days} күн ішінде байқалуы керек. Бір күн ішіндегі реттілік қолданылмайды.",
        f"Соңғы {window_days} күннің кірістері толық бақылау аралығы болмағандықтан салыстырудан алынады. Бір шығыс күні бірнеше кіріс күнімен сәйкес келуі мүмкін.",
        f"Цикл ұзындығы 2–{max_cycle_length} байланыспен шектелген. Іздеу немесе жол саны шегіне жеткен нәтиже барлық маршрутты қамтымайды; бос нәтиже олардың жоқтығын дәлелдемейді.",
        "Цикл сомасы — оның қабырғаларындағы бақыланған айналымның қосындысы; бұл айналып өткен бірегей қаражат көлемі емес.",
    )
    return RouteAnalysis(
        pd.DataFrame(cycle_rows, columns=CYCLE_COLUMNS),
        pd.DataFrame(reciprocal_rows, columns=RECIPROCAL_COLUMNS),
        pd.DataFrame(route_rows, columns=ROUTE_COLUMNS), summary, limitations,
    )


def resilience_analysis(
    analysis: AnalysisResult, ranked_gids: Sequence[int | str], *, top_n: int = 5,
) -> ResilienceAnalysis:
    """Remove the first N distinct ranked clients in a copied observed graph.

    All nonremoved nodes remain, including clients isolated by the removal.
    Largest-component share uses the current remaining-node denominator;
    retained turnover uses the original observed edge-turnover denominator.
    If original turnover is zero, retention is undefined (NaN), not zero.
    Unknown identifiers are rejected, duplicates retain their first position.
    The caller supplies an explicit ranking; roles and priorities do not change.
    """
    _nonnegative_integer(top_n, "top_n")
    graph = analysis.graph
    ranking = list(dict.fromkeys(_exact_integer(gid) for gid in ranked_gids))
    unknown = [gid for gid in ranking if gid not in graph]
    if unknown:
        raise KeyError(f"Белгісіз gid: {unknown[0]}")
    removed = ranking[:top_n]
    remaining = sorted(set(graph) - set(removed))
    after = graph.subgraph(remaining).copy()
    baseline = math.fsum(float(data["sum_kzt"]) for _, _, data in graph.edges(data=True))

    def metrics(current: nx.DiGraph, scenario: str) -> dict:
        sizes = [len(members) for members in nx.weakly_connected_components(current)]
        largest = max(sizes, default=0)
        turnover = math.fsum(float(data["sum_kzt"]) for _, _, data in current.edges(data=True))
        return {
            "scenario": scenario, "n_nodes": len(current), "n_edges": current.number_of_edges(),
            "weak_components": len(sizes), "largest_component_nodes": largest,
            "largest_component_share": largest / len(current) if len(current) else 0.0,
            "observed_edge_turnover_kzt": turnover,
            "retained_turnover_share": turnover / baseline if baseline else math.nan,
        }

    return ResilienceAnalysis(
        pd.DataFrame([metrics(graph, "before"), metrics(after, "after")], columns=COMPARISON_COLUMNS),
        tuple(map(str, removed)), tuple(map(str, remaining)),
        (
            "Бұл — таңдалған клиенттер мен оларға тиесілі байланыстарды алып тастайтын құрылымдық сценарий. Қалған барлық клиент, соның ішінде оқшауланғандары сақталады.",
            "Үлкен компонент үлесі сол сценарийдегі қалған клиенттер санынан, сақталған айналым үлесі бастапқы граф айналымынан есептеледі. Бастапқы айналым нөл болса, оның үлесі анықталмайды.",
            "Нәтиже желінің қайта құрылуын немесе болашақ аударымдарды болжамайды. Құрамдағы өзгеріс нақты операцияны тоқтату әсеріне тең емес.",
        ),
    )


def node_briefing(
    analysis: AnalysisResult, gid: int | str, *, roles: RoleAnalysis | None = None,
) -> NodeBriefing:
    """Build a short reproducible Kazakh briefing from actual node observations.

    This is a local template, not generated evidence or an AI confidence score.
    Data requests are conditional on seed, boundary, isolation, and temporal
    coverage. The case's 5,000 KZT sampling rule is a documented possible blind
    spot, not a claim that the uploaded data has no smaller transactions.
    """
    target = _exact_integer(gid)
    if target not in analysis.graph:
        raise KeyError(f"Белгісіз gid: {target}")
    records = analysis.nodes.loc[analysis.nodes["gid"].eq(target)].to_dict(orient="records")
    if len(records) != 1:
        raise ValueError("Клиент көрсеткіштері графқа сәйкес емес")
    row = records[0]

    def amount(value: float) -> str:
        return f"{float(value):,.2f}".replace(",", " ")

    text = (
        f"gid {target}: бақыланған кіріс {amount(row['in_kzt'])} ₸ "
        f"({int(row['in_tx'])} операция), шығыс {amount(row['out_kzt'])} ₸ "
        f"({int(row['out_tx'])} операция). Өзге жіберуші: {int(row['in_deg'])}; "
        f"өзге алушы: {int(row['out_deg'])}. "
        f"{int(row['reachable_seed_count'])} басқа seed-клиенттен бағытталған жол бар. "
    )
    if int(row["active_days"]):
        text += (
            f"Белсенділігі {int(row['active_days'])} күн: "
            f"{pd.Timestamp(row['first_date']).date()}–{pd.Timestamp(row['last_date']).date()}. "
        )
    else:
        text += "Бақыланған операция күні жоқ. "
    if roles is not None:
        role_rows = roles.nodes_roles.loc[roles.nodes_roles["gid"].eq(target)].to_dict(orient="records")
        if len(role_rows) != 1:
            raise ValueError("Рөлдер кестесінде клиенттің бірегей жазбасы жоқ")
        role = role_rows[0]
        text += (
            f"Рөл болжамы: {ROLE_LABELS.get(role['role'], role['role'])}; "
            f"ережеге сәйкестік ұпайы {float(role['role_score']):.3f}, "
            f"кластер {int(role['cluster_id'])}, тексеру басымдығы {float(role['priority_score']):.3f}. "
            f"Негізі: {role['evidence']} "
        )
    text += "Бұл — бақыланған дерекке негізделген анықтама; рөл мен ұпай кінәлілік ықтималдығы емес."

    limitations = [
        "Бақылау мерзімінен тыс аударымдар мен шоттың толық балансы берілмеген; сомалар тек көрінетін айналымды сипаттайды.",
        "Кейстегі 5 000 ₸ іріктеу шегі төмен сомалы аударымдарды өткізіп жіберуі мүмкін; нақты файлдың қамту шартын тексеру қажет.",
    ]
    requests = [
        "Бақылау мерзімін және іріктеу ережесін растау; қажет болса, 5 000 ₸-ден төмен аударымдар мен кеңірек мерзімдегі толық операциялар үзіндісін сұрату.",
    ]
    if analysis.graph.has_edge(target, target):
        limitations.append("Кіріс пен шығыс сомалары өзіне аударымдарды да қамтиды; өзге жіберуші мен алушы санына клиенттің өзі кірмейді.")
    if bool(row["is_seed"]):
        limitations.append("Seed-клиенттің кірістері толық емес; шығыс/кіріс қатынасы рөл дәлелі ретінде қолданылмайды.")
        requests.append("Seed-клиенттің толық кіріс операцияларын және бастапқы жіберушілерін сұрату.")
    if int(row["depth"]) == 4:
        limitations.append("Клиент depth=4 шекарасында: кейінгі шығыстар көрінбеуі мүмкін; соңғы алушы екені анықталмаған.")
        requests.append("Depth=4 шекарасынан кейінгі шығыс операциялары мен келесі алушылардың деректерін сұрату.")
    if bool(row["is_isolated"]):
        limitations.append("Клиенттің осы үзіндіде байланысы жоқ; бұл оның басқа операциялары жоқ дегенді білдірмейді.")
        requests.append("Клиенттің қамтуын және идентификатор сәйкестігін тексеріп, осы кезеңдегі толық операциялар үзіндісін сұрату.")
    elif float(row["in_kzt"]) == 0:
        limitations.append("Бақыланған кіріс нөл: шығыс/кіріс қатынасы анықталмайды, қаражат көзі белгісіз.")
        requests.append("Бақыланған шығыстарға дейінгі кірістерді және қаражат көзін растайтын деректерді сұрату.")
    if int(row["temporal_eligible_in_tx"]) == 0:
        limitations.append("Екі күндік толық бақылауы бар кіріс операциясы жоқ; кейінгі шығыс үлгісін бағалауға дәлел жеткіліксіз.")
        requests.append("Кірістерден кейін кемінде екі толық күнді қамтитын бақылау аралығын кеңейту.")
    else:
        limitations.append(
            f"Кейінгі шығыс көрсеткішіне {int(row['temporal_eligible_in_tx'])} кіріс операциясы жарайды; "
            "күндік сәйкестік дәл сол қаражаттың әрі қарай кеткенін дәлелдемейді."
        )
    return NodeBriefing(str(target), text, tuple(limitations), tuple(requests))
