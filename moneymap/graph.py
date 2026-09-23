"""Deterministic graph and observed-flow features for MoneyMap Step 2.

These are descriptions of the supplied observation window, not classifications
of clients. In particular, money is neither matched across transfers nor treated
as an account balance. No role, priority or community labels are inferred here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from time import perf_counter

import networkx as nx
import numpy as np
import pandas as pd

from moneymap.data import _exact_integer, validate_dataset


@dataclass
class AnalysisResult:
    graph: nx.DiGraph
    nodes: pd.DataFrame
    components: pd.DataFrame
    daily: pd.DataFrame
    summary: dict
    elapsed_seconds: float


def _temporal_features(nodes: pd.DataFrame, transactions: pd.DataFrame) -> None:
    """Add calendar-day observations in place, retaining duplicate transfers.

    For every incoming transaction, look for the first *strictly later* outgoing
    calendar day of its receiver. The last two observed days are censored out of
    the denominator, because their full two-day follow-up is unavailable.
    ``next_out_1_2d_share`` is a share of incoming transactions, not of money.
    ``mean_next_out_days`` is conditional on a later outgoing day being observed
    among those eligible incoming transactions; missing follow-up is not zero.
    Neither statistic establishes which funds were sent onward. Same-day order
    is deliberately ignored even if an uploaded timestamp contains a time.
    """
    nodes["active_days"] = 0
    nodes["in_active_days"] = 0
    nodes["out_active_days"] = 0
    nodes["first_date"] = pd.NaT
    nodes["last_date"] = pd.NaT
    nodes["mean_next_out_days"] = np.nan
    nodes["next_out_1_2d_share"] = np.nan
    nodes["temporal_eligible_in_tx"] = 0
    if transactions.empty:
        return

    days = transactions["date"].dt.normalize()
    incoming = pd.DataFrame({"gid": transactions["dst"], "day": days})
    outgoing = pd.DataFrame({"gid": transactions["src"], "day": days})
    activity = pd.concat([incoming, outgoing], ignore_index=True).groupby("gid")["day"]
    for column, values in (
        ("active_days", activity.nunique()),
        ("in_active_days", incoming.groupby("gid")["day"].nunique()),
        ("out_active_days", outgoing.groupby("gid")["day"].nunique()),
    ):
        nodes[column] = nodes["gid"].map(values).fillna(0).astype("int64")
    nodes["first_date"] = nodes["gid"].map(activity.min())
    nodes["last_date"] = nodes["gid"].map(activity.max())

    cutoff = days.max() - pd.Timedelta(days=2)
    eligible = incoming.loc[incoming["day"] <= cutoff]
    outgoing_days = {
        int(gid): np.unique(group["day"].to_numpy(dtype="datetime64[D]"))
        for gid, group in outgoing.groupby("gid", sort=True)
    }
    temporal: dict[int, tuple[int, float, float]] = {}
    for gid, group in eligible.groupby("gid", sort=True):
        in_days = group["day"].to_numpy(dtype="datetime64[D]")
        out_days = outgoing_days.get(int(gid), np.array([], dtype="datetime64[D]"))
        # side='right' excludes same-day transfers: timestamps only establish
        # an observation day, not a reliable within-day ordering in this case.
        positions = np.searchsorted(out_days, in_days, side="right")
        has_later = positions < len(out_days)
        lags = (out_days[positions[has_later]] - in_days[has_later]).astype("timedelta64[D]").astype("int64")
        denominator = len(in_days)
        share = float(np.count_nonzero((lags >= 1) & (lags <= 2)) / denominator)
        mean_lag = float(lags.mean()) if len(lags) else math.nan
        temporal[int(gid)] = (denominator, mean_lag, share)

    nodes["temporal_eligible_in_tx"] = nodes["gid"].map({gid: value[0] for gid, value in temporal.items()}).fillna(0).astype("int64")
    nodes["mean_next_out_days"] = nodes["gid"].map({gid: value[1] for gid, value in temporal.items()})
    nodes["next_out_1_2d_share"] = nodes["gid"].map({gid: value[2] for gid, value in temporal.items()})


def analyze_dataset(frames: dict[str, pd.DataFrame]) -> AnalysisResult:
    """Validate inputs, preserve every client, and compute observed features.

    IDs remain exact int64/Python integers, including IDs beyond JavaScript's
    safe integer limit. Consumers must serialize IDs as strings for a browser.
    Components mean weak connectivity, not detected communities. Components
    are numbered from 1 by decreasing size, then by their smallest client ID.

    Betweenness is exact, directed, unweighted and normalized. Monetary weights
    are used for PageRank only; an amount is not a shortest-path distance.
    ``observed_flow_ratio`` retains the raw out/in ratio when incoming > 0;
    ``ratio_usable`` excludes seed, depth-4 and zero-incoming clients. Even an
    unmasked ratio describes only observed flows and never a full balance.
    """
    started = perf_counter()
    validation = validate_dataset(frames)
    if not validation.valid:
        failures = [f"{issue.file or 'dataset'}: {issue.code}" for issue in validation.issues if issue.severity == "error"]
        raise ValueError("Деректер жарамсыз: " + "; ".join(failures[:3]))
    nodes = validation.frames["nodes"][["gid", "depth", "is_seed"]].sort_values("gid", kind="stable").reset_index(drop=True)
    edges = validation.frames["edges"].sort_values(["src", "dst"], kind="stable").reset_index(drop=True)
    transactions = validation.frames["transactions"].sort_values(["src", "dst", "date", "sum_kzt"], kind="stable").reset_index(drop=True)
    graph = nx.DiGraph()
    # itertuples avoids pandas iterrows' implicit conversion of mixed numeric
    # rows to float, which can silently corrupt long client identifiers.
    for gid, depth, is_seed in nodes.itertuples(index=False, name=None):
        graph.add_node(int(gid), depth=int(depth), is_seed=bool(is_seed))
    for row in edges[["src", "dst", "sum_kzt", "n_tx", "depth"]].itertuples(index=False, name=None):
        src, dst, amount, n_tx, discovery_depth = row
        graph.add_edge(int(src), int(dst), sum_kzt=float(amount), amount=float(amount), n_tx=int(n_tx), discovery_depth=int(discovery_depth))

    components = sorted(nx.weakly_connected_components(graph), key=lambda members: (-len(members), min(members)))
    component_ids = {}
    component_rows = []
    for component_id, members in enumerate(components, start=1):
        subgraph = graph.subgraph(members)
        component_ids.update({gid: component_id for gid in members})
        component_rows.append({
            "component_id": component_id,
            "n_nodes": len(members),
            "n_edges": subgraph.number_of_edges(),
            "n_seed": sum(graph.nodes[gid]["is_seed"] for gid in members),
            "sum_kzt_internal": math.fsum(data["sum_kzt"] for _, _, data in subgraph.edges(data=True)),
            "is_isolated": subgraph.number_of_edges() == 0,
        })
    component_table = pd.DataFrame(component_rows)
    nodes["component_id"] = nodes["gid"].map(component_ids).astype("int64")
    nodes["in_deg"] = nodes["gid"].map(dict(graph.in_degree())).astype("int64")
    nodes["out_deg"] = nodes["gid"].map(dict(graph.out_degree())).astype("int64")
    for column, by, value, dtype in (
        ("in_kzt", "dst", "sum_kzt", "float64"),
        ("out_kzt", "src", "sum_kzt", "float64"),
        ("in_tx", "dst", "n_tx", "int64"),
        ("out_tx", "src", "n_tx", "int64"),
    ):
        totals = edges.groupby(by, sort=True)[value].sum()
        nodes[column] = nodes["gid"].map(totals).fillna(0).astype(dtype)

    try:
        pagerank = nx.pagerank(graph, alpha=0.85, weight="sum_kzt", max_iter=1000, tol=1e-12)
    except nx.PowerIterationFailedConvergence as error:
        raise RuntimeError("PageRank жинақталмады; нәтиже жасалған жоқ.") from error
    between = nx.betweenness_centrality(graph, normalized=True, weight=None, endpoints=False)
    nodes["pagerank"] = nodes["gid"].map(pagerank).astype("float64")
    nodes["betweenness"] = nodes["gid"].map(between).astype("float64")
    nodes["observed_flow_ratio"] = nodes["out_kzt"].div(nodes["in_kzt"].where(nodes["in_kzt"].gt(0)))
    nodes["truncated_by_depth"] = nodes["depth"].eq(4)
    nodes["ratio_usable"] = nodes["in_kzt"].gt(0) & ~nodes["is_seed"] & ~nodes["truncated_by_depth"]
    nodes["is_isolated"] = nodes["in_deg"].eq(0) & nodes["out_deg"].eq(0)

    reach_count = dict.fromkeys(graph, 0)
    min_hops: dict[int, int] = {}
    seeds = [int(gid) for gid in nodes.loc[nodes["is_seed"], "gid"]]
    for seed in seeds:
        for gid, hops in nx.single_source_shortest_path_length(graph, seed).items():
            if gid != seed:
                reach_count[gid] += 1
            min_hops[gid] = min(min_hops.get(gid, hops), hops)
    nodes["reachable_seed_count"] = nodes["gid"].map(reach_count).astype("int64")
    # Construct nullable integers directly: map with missing values would
    # otherwise create floats. Hops aren't IDs, but a stable dtype helps CSV/UI.
    nodes["min_seed_hops"] = pd.array([min_hops.get(int(gid), pd.NA) for gid in nodes["gid"]], dtype="Int64")
    _temporal_features(nodes, transactions)

    if transactions.empty:
        daily = pd.DataFrame({
            "date": pd.Series(dtype="datetime64[ns]"), "sum_kzt": pd.Series(dtype="float64"),
            "n_tx": pd.Series(dtype="int64"), "n_senders": pd.Series(dtype="int64"),
            "n_receivers": pd.Series(dtype="int64"),
        })
    else:
        daily = transactions.assign(date=transactions["date"].dt.normalize()).groupby("date", sort=True).agg(
            sum_kzt=("sum_kzt", "sum"), n_tx=("src", "size"), n_senders=("src", "nunique"), n_receivers=("dst", "nunique")
        )
        dates = pd.date_range(daily.index.min(), daily.index.max(), freq="D", name="date")
        daily = daily.reindex(dates, fill_value=0).reset_index()
    summary = {
        **validation.metrics,
        "n_components": len(components),
        "components_with_edges": int(component_table["n_edges"].gt(0).sum()),
        "largest_component_nodes": len(components[0]),
        "max_in_degree": int(nodes["in_deg"].max()),
        "max_out_degree": int(nodes["out_deg"].max()),
        "temporal_cutoff_date": (transactions["date"].max().normalize() - pd.Timedelta(days=2)).strftime("%Y-%m-%d") if not transactions.empty else None,
    }
    return AnalysisResult(graph, nodes, component_table, daily, summary, perf_counter() - started)


def observed_seed_paths(result: AnalysisResult, gid: int | str, limit: int = 5) -> list[list[int]]:
    """Return at most ``limit`` reproducible directed seed-to-client paths.

    One unweighted shortest path per *other* reachable seed is chosen. Seeds
    are ordered by path length and then ID. A displayed path is connectivity
    within the observation window, not proof that the same money traversed it.
    There is no temporal ordering guarantee between its edges.
    """
    target = _exact_integer(gid)
    if target not in result.graph:
        raise KeyError(f"Белгісіз gid: {target}")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit нөлден кем емес бүтін сан болуы керек")
    if limit == 0:
        return []
    # One reverse BFS finds reachable seeds without enumerating cycles or all
    # simple paths. Stable insertion order makes shortest-path ties stable.
    backwards = nx.single_source_shortest_path(result.graph.reverse(copy=False), target)
    seeds = sorted(
        (seed for seed in backwards if seed != target and result.graph.nodes[seed]["is_seed"]),
        key=lambda seed: (len(backwards[seed]), seed),
    )
    return [list(reversed(backwards[seed])) for seed in seeds[:limit]]
