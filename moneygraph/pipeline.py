"""Deterministic, evidence-based hypotheses for a censored transaction network.

Only the supplied account identifiers, extraction depths, seed indicators and
observed transfers are used. Roles and scores are rules, not allegations or
calibrated probabilities. See docs/METHODOLOGY.md for the complete definitions.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import time
from typing import Any
import uuid

import networkx as nx
import numpy as np
import pandas as pd


MAX_DEPTH = 4
RANDOM_SEED = 1729
TOP_N = 20
SCHEMAS = {
    "nodes": ("gid", "depth", "is_seed"),
    "edges": ("src", "dst", "sum_kzt", "n_tx", "depth"),
    "transactions": ("src", "dst", "date", "sum_kzt"),
}
CSV_SCHEMAS = {
    "nodes_roles": ("gid", "role", "role_score", "cluster_id", "priority_score", "evidence"),
    "clusters": ("cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"),
    "top_nodes": ("rank", "gid", "role", "priority_score", "why"),
}
ROLES = ("consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral")
PRIORITY_WEIGHTS = {
    "betweenness": 0.25,
    "observed_volume": 0.20,
    "fan_in": 0.15,
    "fan_out": 0.10,
    "pagerank": 0.10,
    "community_bridging": 0.10,
    "temporal_association": 0.10,
}
FEATURE_LABELS = {
    "betweenness": "жоларалық орталықтық",
    "observed_volume": "бақыланған айналым",
    "fan_in": "кіріс контрагенттері",
    "fan_out": "шығыс контрагенттері",
    "pagerank": "кіріс ағынындағы орын",
    "community_bridging": "кластерлер арасындағы байланыс",
    "temporal_association": "күндік уақыт сәйкестігі",
}


def _validate_integer(frame: pd.DataFrame, column: str, source: str, *, minimum: int | None = None,
                      maximum: int | None = None) -> None:
    values = frame[column]
    if values.isna().any():
        raise ValueError(f"{source}.{column}: missing values are not allowed")
    # A float that happens to equal an integer is not a declared integer ID.
    for row, value in enumerate(values):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise ValueError(f"{source}.{column}: row {row + 1} must be an integer, got {value!r}")
        integer = int(value)
        if not -(2**63) <= integer < 2**63:
            raise ValueError(f"{source}.{column}: row {row + 1} is outside int64 range")
        if minimum is not None and integer < minimum:
            raise ValueError(f"{source}.{column}: row {row + 1} must be >= {minimum}")
        if maximum is not None and integer > maximum:
            raise ValueError(f"{source}.{column}: row {row + 1} must be <= {maximum}")
    frame[column] = values.astype("int64")


def _validate_amount(frame: pd.DataFrame, source: str) -> None:
    for row, value in enumerate(frame["sum_kzt"]):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError(f"{source}.sum_kzt: row {row + 1} must be numeric")
        if not math.isfinite(float(value)) or float(value) <= 0:
            raise ValueError(f"{source}.sum_kzt: row {row + 1} must be positive and finite")
    frame["sum_kzt"] = frame["sum_kzt"].astype("float64")
    if not math.isfinite(float(frame["sum_kzt"].sum())):
        raise ValueError(f"{source}.sum_kzt: total exceeds the supported finite numeric range")


def _load_inputs(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    frames: dict[str, pd.DataFrame] = {}
    for name, columns in SCHEMAS.items():
        path = data_dir / f"{name}.parquet"
        if not path.is_file():
            raise ValueError(f"Required input file is missing: {path.name}")
        try:
            frame = pd.read_parquet(path, engine="pyarrow")
        except Exception as exc:
            raise ValueError(f"Cannot read {path.name} as Parquet: {exc}") from exc
        missing = set(columns) - set(frame.columns)
        extra = set(frame.columns) - set(columns)
        if missing or extra or frame.columns.duplicated().any():
            raise ValueError(f"{path.name}: expected exactly {', '.join(columns)}; "
                             f"missing={sorted(missing)}, unexpected={sorted(extra)}")
        frames[name] = frame.loc[:, columns].copy()
    nodes, edges, transactions = (frames[name] for name in SCHEMAS)
    _validate_integer(nodes, "gid", "nodes")
    _validate_integer(nodes, "depth", "nodes", minimum=0, maximum=MAX_DEPTH)
    if nodes["gid"].duplicated().any():
        duplicate = int(nodes.loc[nodes["gid"].duplicated(), "gid"].iloc[0])
        raise ValueError(f"nodes.gid: duplicate account identifier {duplicate}")
    for row, value in enumerate(nodes["is_seed"]):
        if not isinstance(value, (bool, np.bool_)):
            raise ValueError(f"nodes.is_seed: row {row + 1} must be boolean")
    nodes["is_seed"] = nodes["is_seed"].astype(bool)
    inconsistent = nodes["is_seed"] != nodes["depth"].eq(0)
    if inconsistent.any():
        raise ValueError("nodes: is_seed must be true exactly for depth=0 accounts")
    ids = set(nodes["gid"].tolist())
    for name, frame in (("edges", edges), ("transactions", transactions)):
        for column in ("src", "dst"):
            _validate_integer(frame, column, name)
            unknown = sorted(set(frame[column].tolist()) - ids)
            if unknown:
                raise ValueError(f"{name}.{column}: endpoint {unknown[0]} is absent from nodes")
        _validate_amount(frame, name)
    _validate_integer(edges, "n_tx", "edges", minimum=1)
    # Official depth is discovery hop 1–4. Also accept 0 for compatible
    # exporters using source depth; node.depth determines boundary censoring.
    _validate_integer(edges, "depth", "edges", minimum=0, maximum=MAX_DEPTH)
    if edges.duplicated(["src", "dst"]).any():
        raise ValueError("edges: each directed (src, dst) pair must appear once; aggregate duplicate pairs")
    for row, value in enumerate(transactions["date"]):
        if not isinstance(value, (str, date, datetime, pd.Timestamp, np.datetime64)):
            raise ValueError(f"transactions.date: row {row + 1} must be a date or date string")
    try:
        transactions["date"] = pd.to_datetime(transactions["date"], utc=True, errors="raise", format="mixed")
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"transactions.date: invalid date: {exc}") from exc
    if transactions["date"].isna().any():
        raise ValueError("transactions.date: missing/NaT dates are not allowed")
    transactions["date"] = transactions["date"].dt.normalize()
    grouped = transactions.groupby(["src", "dst"], sort=True)["sum_kzt"].agg(["sum", "size"])
    edge_indexed = edges.set_index(["src", "dst"]).sort_index()
    if set(grouped.index.tolist()) != set(edge_indexed.index.tolist()):
        raise ValueError("edges and transactions: directed endpoint pairs must match exactly")
    if len(grouped):
        actual = edge_indexed.reindex(grouped.index)
        counts_match = np.array_equal(actual["n_tx"].to_numpy(), grouped["size"].to_numpy())
        sums_match = np.isclose(actual["sum_kzt"].to_numpy(), grouped["sum"].to_numpy(), rtol=1e-9, atol=0.01).all()
        if not counts_match or not sums_match:
            raise ValueError("edges and transactions: aggregate sum_kzt or n_tx mismatch "
                             "(amount tolerance: 0.01 KZT + 1e-9 relative)")
    warnings: list[str] = []
    if len(transactions) and (transactions["sum_kzt"] < 5000).any():
        warnings.append("Кейбір аударымдар 5 000 ₸ шегінен төмен; олар жасырын сүзілмей, талдауға енгізілді.")
    if len(transactions):
        if not ((transactions["date"].dt.year == 2026) & (transactions["date"].dt.month == 7)).all():
            warnings.append("Деректерде 2026 жылғы шілдеден тыс күндер бар; нақты берілген кезең талданды.")
    if any(abs(int(gid)) > 2**53 - 1 for gid in ids):
        warnings.append("Кейбір gid JavaScript қауіпсіз бүтін сан шегінен үлкен; экспорттағы int64 ID сақталған.")
    if not len(nodes):
        warnings.append("Түйіндер кестесі бос.")
    elif not nodes["is_seed"].any():
        warnings.append("Бастапқы шоттар белгіленбеген; бастапқы шоттан қолжетімділік анықталмайды.")
    if not len(transactions):
        warnings.append("Бақыланған аударымдар жоқ; құрылымдық рөлдер анықталмайды.")
    return (nodes.sort_values("gid").reset_index(drop=True),
            edges.sort_values(["src", "dst"]).reset_index(drop=True),
            transactions.sort_values(["date", "src", "dst", "sum_kzt"]).reset_index(drop=True), warnings)


def _positive_percentiles(values: dict[int, float]) -> dict[int, float]:
    """Empirical CDF among positive observations; zero remains zero, ties agree."""
    positive = sorted(value for value in values.values() if value > 0)
    if not positive:
        return {gid: 0.0 for gid in values}
    return {gid: float(np.searchsorted(positive, value, side="right") / len(positive)) if value > 0 else 0.0
            for gid, value in values.items()}


def _weighted_pagerank(graph: nx.DiGraph, *, alpha: float = 0.85) -> dict[int, float]:
    """Weighted PageRank without NetworkX's optional SciPy dependency."""
    ids = list(graph.nodes)
    count = len(ids)
    if count == 0:
        return {}
    index = {gid: position for position, gid in enumerate(ids)}
    arcs = list(graph.edges(data=True))
    source = np.array([index[a] for a, _, _ in arcs], dtype=np.int64)
    target = np.array([index[b] for _, b, _ in arcs], dtype=np.int64)
    weights = np.array([data["weight"] for _, _, data in arcs], dtype=np.float64)
    totals = np.bincount(source, weights=weights, minlength=count)
    fractions = weights / totals[source] if len(weights) else weights
    dangling = totals == 0
    ranks = np.full(count, 1.0 / count, dtype=np.float64)
    for _ in range(1000):
        incoming = np.bincount(target, weights=ranks[source] * fractions, minlength=count)
        updated = alpha * (incoming + ranks[dangling].sum() / count) + (1 - alpha) / count
        if np.abs(updated - ranks).sum() < 1e-12:
            ranks = updated
            break
        ranks = updated
    ranks /= ranks.sum()
    return {gid: float(ranks[index[gid]]) for gid in ids}


def _communities(graph: nx.DiGraph) -> tuple[dict[int, int], list[list[int]]]:
    support = nx.Graph()
    support.add_nodes_from(graph.nodes)
    for source, target, attrs in graph.edges(data=True):
        previous = support.get_edge_data(source, target, {}).get("weight", 0.0)
        support.add_edge(source, target, weight=previous + attrs["weight"])
    groups: list[list[int]] = []
    for component in sorted(nx.connected_components(support), key=lambda group: min(group)):
        ordered = sorted(component)
        if len(ordered) == 1:
            groups.append(ordered)
            continue
        subgraph = support.subgraph(ordered).copy()
        found = nx.community.louvain_communities(subgraph, weight="weight", resolution=1, seed=RANDOM_SEED)
        groups.extend(sorted(group) for group in found)
    groups.sort(key=lambda group: (group[0], tuple(group)))
    membership = {gid: cluster_id for cluster_id, group in enumerate(groups) for gid in group}
    return membership, groups


def _temporal_features(transactions: pd.DataFrame, ids: list[int]) -> dict[int, dict[str, Any]]:
    daily_in: dict[int, dict[pd.Timestamp, float]] = defaultdict(dict)
    daily_out: dict[int, dict[pd.Timestamp, float]] = defaultdict(dict)
    payer_max: dict[int, int] = {}
    if len(transactions):
        for (gid, day), value in transactions.groupby(["dst", "date"], sort=True)["sum_kzt"].sum().items():
            daily_in[int(gid)][day] = float(value)
        for (gid, day), value in transactions.groupby(["src", "date"], sort=True)["sum_kzt"].sum().items():
            daily_out[int(gid)][day] = float(value)
        payer_counts = transactions.groupby(["dst", "date"], sort=True)["src"].nunique().groupby(level=0).max()
        payer_max = {int(gid): int(value) for gid, value in payer_counts.items()}
    result = {}
    for gid in ids:
        inbound, outbound = daily_in[gid], daily_out[gid]
        days = sorted(set(inbound) | set(outbound))
        available: deque[list[Any]] = deque()
        matched = 0.0
        for day in days:
            # Same-day order is unknown. This is only an overlap of daily flows.
            while available and (day - available[0][0]).days > 1:
                available.popleft()
            if inbound.get(day, 0) > 0:
                available.append([day, inbound[day]])
            remaining = outbound.get(day, 0.0)
            while remaining > 0 and available:
                consumed = min(remaining, available[0][1])
                remaining -= consumed
                available[0][1] -= consumed
                matched += consumed
                if available[0][1] <= 0:
                    available.popleft()
        incoming_total = sum(inbound.values())
        result[gid] = {
            "active_days": len(days),
            "incoming_active_days": len(inbound),
            "outgoing_active_days": len(outbound),
            "fast_forward_ratio": min(1.0, matched / incoming_total) if incoming_total else None,
            "synchronized_payers": payer_max.get(gid, 0),
            "first_observed": days[0].date().isoformat() if days else None,
            "last_observed": days[-1].date().isoformat() if days else None,
            "last_incoming": max(inbound).date().isoformat() if inbound else None,
        }
    return result


def _role(node: dict[str, Any], between_percentile: float, period_end: str | None) -> tuple[str, float]:
    """Ordered formal rules; an unmatched or censored pattern stays peripheral."""
    incoming, outgoing = node["in_degree"], node["out_degree"]
    ratio = node["pass_through"]
    temporal = node["temporal"]
    if incoming >= 3 and outgoing >= 3 and min(incoming, outgoing) / max(incoming, outgoing) >= 0.5 \
            and node["betweenness"] > 0 and between_percentile >= 0.75:
        return "coordinator", min(0.95, 0.65 + 0.20 * between_percentile + 0.10 * min(1, min(incoming, outgoing) / 6))
    if incoming >= 3 and incoming >= 2 * max(outgoing, 1):
        return "consolidator", min(0.95, 0.55 + 0.20 * min(incoming / 10, 1) + 0.20 * (1 - outgoing / incoming))
    if outgoing >= 3 and outgoing >= 2 * max(incoming, 1):
        return "distributor", min(0.95, 0.55 + 0.20 * min(outgoing / 10, 1) + 0.20 * (1 - incoming / outgoing))
    if not node["is_seed"] and ratio is not None and incoming >= 1 and outgoing >= 1 \
            and max(incoming, outgoing) <= 3 and 0.80 <= ratio <= 1:
        association = temporal["fast_forward_ratio"] or 0
        return "transit", min(0.95, 0.55 + 0.25 * ratio + 0.15 * association)
    # Low *positive* outward flow supplies evidence beyond a missing edge.
    # A zero-outflow node is never made terminal by this conservative rule.
    if not node["is_seed"] and node["depth"] < MAX_DEPTH and incoming >= 2 \
            and ratio is not None and 0 < ratio <= 0.15 and temporal["incoming_active_days"] >= 3 \
            and period_end is not None and temporal["last_incoming"] is not None:
        followup_days = (date.fromisoformat(period_end) - date.fromisoformat(temporal["last_incoming"])).days
        if followup_days >= 2:
            return "terminal", min(0.80, 0.50 + 0.20 * (1 - ratio) + 0.10 * min(temporal["incoming_active_days"] / 7, 1))
    # This low score expresses weak support for any functional role.
    return "peripheral", 0.0 if node["in_degree"] + node["out_degree"] == 0 else 0.25


def _money(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} млн ₸"
    return f"{value:,.0f} ₸".replace(",", " ")


def _next_request(node: dict[str, Any]) -> str:
    flags = node["flags"]
    if "isolated" in flags:
        return "Осы gid үшін толық кіріс/шығыс тізілімін, 5 000 ₸-ден төмен аударымдарды және көршілес кезеңді сұрату."
    if "boundary_censored" in flags:
        return "Төртінші қадамдағы осы gid-дің барлық шығысын, келесі контрагенттерін және кейінгі 7 күнді сұрату."
    if "seed_inflow_incomplete" in flags:
        return "Бастапқы шоттың толық кірісін, кезең алдындағы 30 күнді және бастапқы қалдықты сұрату."
    if "outflow_exceeds_observed_inflow" in flags:
        return "Кезең алдындағы қалдықты, бұрынғы кірістерді және сүзгіден тыс кіріс аударымдарын сұрату."
    if "no_observed_outflow" in flags or node["role"] == "terminal":
        return "Толық шығыс тізілімін, төмен сомалы аударымдарды және келесі 7–30 күнді сұрату; соңғы алушыны нақтылау."
    if node["role"] == "coordinator":
        return "Кіріс/шығыс операцияларының нақты уақытын және шоттардың заңды иесін растайтын рұқсат етілген деректерді сұрату."
    return "Таңдалған жол бойынша нақты уақыт белгісі бар толық операцияларды және көршілес кезеңді сұрату."


def _evidence(node: dict[str, Any]) -> str:
    role = node["role"]
    incoming, outgoing = node["in_degree"], node["out_degree"]
    ratio = node["pass_through"]
    if role == "coordinator":
        text = f"{incoming} кіріс, {outgoing} шығыс контрагенті; жоларалық орталықтық жоғары. Үйлестіруші — тек құрылымдық гипотеза."
    elif role == "consolidator":
        text = f"{incoming} контрагенттен {_money(node['in_kzt'])}; {outgoing} шығыс контрагенті. Кіріс ағындары осы жерде тоғысады."
    elif role == "distributor":
        text = f"{outgoing} контрагентке {_money(node['out_kzt'])}; {incoming} көрінетін кіріс контрагенті. Тарату үлгісі байқалады."
    elif role == "transit":
        text = f"Кіріс {_money(node['in_kzt'])}, шығыс {_money(node['out_kzt'])}; қатынасы {ratio:.0%}. Бір ақшаның қайта жіберілгенін дәлелдемейді."
    elif role == "terminal":
        text = f"{incoming} төлеуші, {node['temporal']['incoming_active_days']} кіріс күні; оң шығыс/кіріс {ratio:.0%}. Соңғы алушы рөлі қосымша тексеріледі."
    elif "isolated" in node["flags"]:
        text = "0 кіріс / 0 шығыс контрагенті: үзіндіде байланыс жоқ. Бұл шоттың нақты белсенді емес екенін білдірмейді."
    elif "boundary_censored" in node["flags"]:
        text = "4-қадам шекарасы: кейінгі аударымдар үзіндіден тыс қалуы мүмкін. Соңғы алушы рөлі тағайындалмады."
    else:
        text = f"{incoming} кіріс, {outgoing} шығыс контрагенті. Берілген үзінді функционалдық рөлді сенімді ажыратуға жеткіліксіз."
    if "seed_inflow_incomplete" in node["flags"] and len(text) < 145:
        text += " Бастапқы шоттың кірісі толық емес."
    return text[:200]


def _json_safe_ids(analysis: dict[str, Any]) -> dict[str, Any]:
    """Keep int64 identity lossless for JavaScript without changing CSV types."""
    def safe(value: int) -> int | str:
        return str(value) if abs(value) > 2**53 - 1 else value

    result = dict(analysis)
    result["nodes"] = [{**node, "gid": safe(node["gid"])} for node in analysis["nodes"]]
    result["edges"] = [{**edge, "src": safe(edge["src"]), "dst": safe(edge["dst"])} for edge in analysis["edges"]]
    result["top_nodes"] = [{**node, "gid": safe(node["gid"])} for node in analysis["top_nodes"]]
    result["clusters"] = [{**cluster, "top_gids": [safe(gid) for gid in cluster["top_gids"]]}
                          for cluster in analysis["clusters"]]
    result["quality"] = {**analysis["quality"],
                         "requests": [{**request, "gid": safe(request["gid"])}
                                      for request in analysis["quality"]["requests"]]}
    return result


def _write_outputs(output_dir: Path, analysis: dict[str, Any], wire_analysis: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "nodes_roles": analysis["nodes"],
        "clusters": [{**cluster, "top_gids": json.dumps(cluster["top_gids"], separators=(",", ":"))}
                     for cluster in analysis["clusters"]],
        "top_nodes": analysis["top_nodes"],
    }
    temporary_paths: list[Path] = []
    try:
        for name, columns in CSV_SCHEMAS.items():
            temporary = output_dir / f".{name}.{uuid.uuid4().hex}.tmp"
            temporary_paths.append(temporary)
            pd.DataFrame(tables[name], columns=columns).to_csv(temporary, index=False, encoding="utf-8-sig", float_format="%.8f")
        json_temp = output_dir / f".analysis.{uuid.uuid4().hex}.tmp"
        temporary_paths.append(json_temp)
        json_temp.write_text(json.dumps(wire_analysis, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        for temporary, filename in zip(temporary_paths, [f"{name}.csv" for name in tables] + ["analysis.json"]):
            os.replace(temporary, output_dir / filename)
    finally:
        for path in temporary_paths:
            if path.exists():
                path.unlink()


def analyze(data_dir: str | Path, output_dir: str | Path, *, demo: bool = False) -> dict[str, Any]:
    """Validate three Parquet tables, infer hypotheses, and export four artifacts.

    Input files are never modified. Invalid input raises ``ValueError`` before
    outputs are replaced. Output ordering and all analytical values are stable
    for the same data; generation time and elapsed runtime are metadata only.
    """
    started = time.perf_counter()
    nodes, edges, transactions, warnings = _load_inputs(Path(data_dir))
    graph = nx.DiGraph()
    graph.add_nodes_from(int(gid) for gid in nodes["gid"])
    for edge in edges.itertuples(index=False):
        graph.add_edge(int(edge.src), int(edge.dst), weight=float(edge.sum_kzt), n_tx=int(edge.n_tx))
    ids = list(graph.nodes)
    membership, groups = _communities(graph)
    # Sampling is explicitly reported for larger data and always seeded.
    sample = min(256, len(ids)) if len(ids) > 1000 else None
    between = nx.betweenness_centrality(graph, k=sample, normalized=True, weight=None, seed=RANDOM_SEED) if ids else {}
    between_percentiles = _positive_percentiles(between)
    pagerank = _weighted_pagerank(graph)
    temporal = _temporal_features(transactions, ids)
    period_start = transactions["date"].min().date().isoformat() if len(transactions) else None
    period_end = transactions["date"].max().date().isoformat() if len(transactions) else None
    if sample is not None:
        warnings.append(f"Жоларалық орталықтық {sample} тірек түйінмен бағаланды; тұрақты seed={RANDOM_SEED}.")
    warnings.append("Іріктеу төрт қадаммен және дерек кезеңімен шектеледі; көрінбейтін аударым жоқ деген қорытынды жасалмайды.")
    warnings.append("Рөлдер мен балдар — таңбаланбаған дерекке арналған ережелік гипотезалар; кінәні немесе ықтималдықты білдірмейді.")
    node_results: list[dict[str, Any]] = []
    for row in nodes.itertuples(index=False):
        gid = int(row.gid)
        incoming_ids = set(graph.predecessors(gid)) - {gid}
        outgoing_ids = set(graph.successors(gid)) - {gid}
        incoming = math.fsum(float(graph[a][gid]["weight"]) for a in graph.predecessors(gid))
        outgoing = math.fsum(float(graph[gid][b]["weight"]) for b in graph.successors(gid))
        incoming_count = sum(int(graph[a][gid]["n_tx"]) for a in graph.predecessors(gid))
        outgoing_count = sum(int(graph[gid][b]["n_tx"]) for b in graph.successors(gid))
        flags = []
        if row.depth == MAX_DEPTH:
            flags.append("boundary_censored")
        if row.is_seed:
            flags.append("seed_inflow_incomplete")
        excess = outgoing > incoming + max(0.01, incoming * 1e-9)
        if excess:
            flags.append("outflow_exceeds_observed_inflow")
        if graph.degree(gid) == 0:
            flags.append("isolated")
        if outgoing == 0:
            flags.append("no_observed_outflow")
        if graph.has_edge(gid, gid):
            flags.append("self_transfer")
        ratio = min(1.0, outgoing / incoming) if not row.is_seed and incoming > 0 and not excess else None
        if ratio is None:
            temporal[gid]["fast_forward_ratio"] = None
        neighbors = incoming_ids | outgoing_ids
        outside = {membership[other] for other in neighbors if membership[other] != membership[gid]}
        counts = Counter(membership[other] for other in neighbors)
        participation = 1.0 - sum((count / len(neighbors)) ** 2 for count in counts.values()) if neighbors else 0.0
        result = {
            "gid": gid, "depth": int(row.depth), "is_seed": bool(row.is_seed),
            "role": "peripheral", "role_score": 0.0, "cluster_id": membership[gid],
            "priority_score": 0.0, "evidence": "", "in_degree": len(incoming_ids), "out_degree": len(outgoing_ids),
            "in_kzt": incoming, "out_kzt": outgoing, "in_tx": incoming_count, "out_tx": outgoing_count,
            "pass_through": ratio,
            "betweenness": float(between[gid]), "pagerank": pagerank[gid],
            "flags": flags, "temporal": temporal[gid], "next_request": "",
            "external_communities": len(outside), "community_participation": max(0.0, participation),
        }
        result["role"], strength = _role(result, between_percentiles[gid], period_end)
        # Censoring lowers the strength of a pattern without hiding the node.
        if "boundary_censored" in flags:
            strength = min(strength, 0.55)
        elif row.is_seed and result["role"] != "peripheral":
            strength = min(strength, 0.70)
        if excess:
            strength = min(strength, 0.65)
        result["role_score"] = round(strength, 8)
        result["evidence"] = _evidence(result)
        result["next_request"] = _next_request(result)
        node_results.append(result)
    feature_values = {
        "betweenness": {n["gid"]: n["betweenness"] for n in node_results},
        "observed_volume": {n["gid"]: n["in_kzt"] + n["out_kzt"] for n in node_results},
        "fan_in": {n["gid"]: float(n["in_degree"]) for n in node_results},
        "fan_out": {n["gid"]: float(n["out_degree"]) for n in node_results},
        "pagerank": {n["gid"]: n["pagerank"] if n["in_degree"] + n["out_degree"] else 0.0 for n in node_results},
        "community_bridging": {n["gid"]: n["community_participation"] for n in node_results},
    }
    features = {name: _positive_percentiles(values) for name, values in feature_values.items()}
    synchronization = _positive_percentiles({n["gid"]: max(0, n["temporal"]["synchronized_payers"] - 1) for n in node_results})
    features["temporal_association"] = {
        n["gid"]: 0.5 * (n["temporal"]["fast_forward_ratio"] or 0.0) + 0.5 * synchronization[n["gid"]]
        for n in node_results
    }
    for node in node_results:
        gid = node["gid"]
        node["priority_features"] = {name: round(features[name][gid], 8) for name in PRIORITY_WEIGHTS}
        node["priority_contributions"] = {name: round(PRIORITY_WEIGHTS[name] * features[name][gid], 8) for name in PRIORITY_WEIGHTS}
        node["priority_score"] = round(min(1.0, sum(node["priority_contributions"].values())), 8)
    ranked = sorted(node_results, key=lambda node: (-node["priority_score"], node["gid"]))
    top_nodes = []
    for rank, node in enumerate(ranked[:TOP_N], 1):
        contributions = sorted(node["priority_contributions"].items(), key=lambda item: (-item[1], item[0]))
        reasons = [f"{FEATURE_LABELS[name]} +{amount:.2f}" for name, amount in contributions[:2] if amount > 0]
        why = "; ".join(reasons) + (". " if reasons else "") + node["evidence"]
        top_nodes.append({"rank": rank, "gid": node["gid"], "role": node["role"],
                          "priority_score": node["priority_score"], "why": why[:200]})
    by_id = {node["gid"]: node for node in node_results}
    cluster_internal: dict[int, list[float]] = defaultdict(list)
    for edge in edges.itertuples(index=False):
        if membership[int(edge.src)] == membership[int(edge.dst)]:
            cluster_internal[membership[int(edge.src)]].append(float(edge.sum_kzt))
    cluster_results = []
    for cluster_id, members in enumerate(groups):
        role_counts = Counter(by_id[gid]["role"] for gid in members)
        seeds = sum(by_id[gid]["is_seed"] for gid in members)
        if len(members) == 1 and "isolated" in by_id[members[0]]["flags"]:
            hypothesis = "Оқшау шот; үзіндіде байланыс жоқ. Бөлек ұйым деген қорытынды жасалмайды."
        elif role_counts["consolidator"] and role_counts["distributor"]:
            hypothesis = "Жинау және тарату үлгілері бар ағын қауымдастығы; ортақ бақылауды тексеру қажет."
        elif role_counts["coordinator"]:
            hypothesis = "Құрылымдық орталығы бар ағын қауымдастығы; үйлестіру қатынасы дәлелденбеген."
        elif role_counts["consolidator"]:
            hypothesis = "Кіріс ағындары тоғысатын қауымдастық; заңды төлем қызметі де осындай үлгі бере алады."
        elif role_counts["distributor"]:
            hypothesis = "Бірнеше бағытқа таралатын ағындар; ортақ заңсыз мақсат туралы қорытынды жоқ."
        else:
            hypothesis = "Өзара байланысқан ағындар қауымдастығы; рөл мен ортақ бақылауға қосымша дерек қажет."
        ordered = sorted(members, key=lambda gid: (-by_id[gid]["priority_score"], gid))
        cluster_results.append({"cluster_id": cluster_id, "n_nodes": len(members), "n_seed": int(seeds),
                                "sum_kzt_internal": math.fsum(cluster_internal[cluster_id]), "top_gids": ordered[:5],
                                "hypothesis": hypothesis})
    timeline = [{"date": day.date().isoformat(), "sum_kzt": float(group["sum_kzt"].sum()), "n_tx": len(group)}
                for day, group in transactions.groupby("date", sort=True)]
    requests = [{"gid": node["gid"], "reason": ", ".join(node["flags"]) or f"role={node['role']}",
                 "request": node["next_request"]} for node in ranked
                if node["flags"] or node["role"] in {"coordinator", "terminal"}]
    seed_ids = [n["gid"] for n in node_results if n["is_seed"]]
    if seed_ids:
        calculated = nx.multi_source_dijkstra_path_length(graph, seed_ids, cutoff=MAX_DEPTH, weight=None)
        mismatch = sum(calculated.get(n["gid"]) != n["depth"] for n in node_results if "isolated" not in n["flags"])
        if mismatch:
            warnings.append(f"{mismatch} түйіннің берілген depth мәні көрінетін графтағы ең қысқа жолға сәйкес емес; бастапқы depth сақталды.")
    analysis = {
        "meta": {"demo": bool(demo), "generated_at": datetime.now(timezone.utc).isoformat(),
                 "runtime_seconds": round(time.perf_counter() - started, 6),
                 "period_start": period_start, "period_end": period_end,
                 "n_nodes": len(nodes), "n_edges": len(edges), "n_transactions": len(transactions),
                 "n_seeds": len(seed_ids), "n_clusters": len(groups),
                 "total_kzt": float(transactions["sum_kzt"].sum()), "max_depth": MAX_DEPTH, "warnings": warnings,
                 "priority_weights": PRIORITY_WEIGHTS, "method_version": "1.0.0",
                 "betweenness_sample_size": sample, "temporal_resolution": "UTC calendar day",
                 "source_amount_threshold_kzt": 5000, "score_type": "heuristic_not_probability"},
        "nodes": node_results,
        "edges": [{"src": int(edge.src), "dst": int(edge.dst), "sum_kzt": float(edge.sum_kzt),
                   "n_tx": int(edge.n_tx), "depth": int(edge.depth)} for edge in edges.itertuples(index=False)],
        "clusters": cluster_results, "top_nodes": top_nodes, "timeline": timeline,
        "role_counts": {role: sum(n["role"] == role for n in node_results) for role in ROLES},
        "quality": {"boundary_nodes": sum("boundary_censored" in n["flags"] for n in node_results),
                    "isolated_seeds": sum(n["is_seed"] and "isolated" in n["flags"] for n in node_results),
                    "seeds_without_outgoing": sum(n["is_seed"] and n["out_kzt"] == 0 for n in node_results),
                    "outflow_exceeds_inflow": sum("outflow_exceeds_observed_inflow" in n["flags"] for n in node_results),
                    "weak_components": nx.number_weakly_connected_components(graph), "requests": requests},
    }
    wire_analysis = _json_safe_ids(analysis)
    _write_outputs(Path(output_dir), analysis, wire_analysis)
    return wire_analysis
