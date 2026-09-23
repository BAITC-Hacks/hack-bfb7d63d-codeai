"""Display-only graph selections and complete client tables for Stage 4.

Filtering never recomputes global metrics, roles, priority, or communities.
Browser identifiers are strings; tabular identifiers remain exact int64.
"""

from __future__ import annotations

import colorsys
import math
import numbers

import pandas as pd

from moneymap.data import _exact_integer
from moneymap.graph import AnalysisResult
from moneymap.roles import ROLE_LABELS, ROLE_ORDER, RoleAnalysis


ROLE_COLORS = {
    "coordinator": "#695AC7", "distributor": "#C48B32",
    "consolidator": "#167D77", "transit": "#438DC1",
    "terminal": "#788BA3", "peripheral": "#A6B1BF",
}
DEPTH_COLORS = ("#243B66", "#4477AA", "#137B71", "#C26912", "#8856A7")
NEIGHBOR_COLUMNS = ["src", "dst", "sum_kzt", "n_tx", "counterparty_gid", "direction_label", "role", "cluster_id"]


def cluster_color(cluster_id: int) -> str:
    """Stable colors without repeating a short palette for larger datasets.

    The golden-angle hue progression is independent of which clusters are
    visible. Cluster numbers remain the identity, since dozens of colors are
    not reliably distinguishable by color alone.
    """
    index = int(cluster_id) - 1
    hue = (0.58 + index * 0.618033988749895) % 1
    saturation = (0.60, 0.66, 0.54)[index % 3]
    lightness = (0.43, 0.49, 0.38)[index % 3]
    rgb = colorsys.hls_to_rgb(hue, lightness, saturation)
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in rgb)


def _known_gid(gid: object, available) -> int:
    try:
        parsed = _exact_integer(gid)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("gid дәл int64 бүтін саны болуы керек") from exc
    if parsed not in available:
        raise ValueError(f"Клиент табылмады: {parsed}")
    return parsed


def _filters(value, *, kind: str, available: set) -> set | None:
    if value is None:
        return None
    if isinstance(value, (str, numbers.Number)):
        values = [value]
    else:
        try:
            values = list(value)
        except TypeError as exc:
            raise ValueError(f"{kind}: мән немесе мәндер тізімі болуы керек") from exc
    if kind == "role_filter":
        if any(not isinstance(item, str) or item not in available for item in values):
            raise ValueError("role_filter: белгісіз рөл")
        return set(values)
    try:
        parsed = {_exact_integer(item) for item in values}
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("cluster_filter: кластердің бүтін нөмірі болуы керек") from exc
    if not parsed <= available:
        raise ValueError("cluster_filter: белгісіз кластер")
    return parsed


def _records(analysis: AnalysisResult, roles: RoleAnalysis) -> dict[int, dict]:
    """Join without mixed-number row coercion that would round long gids."""
    metrics = {int(row["gid"]): row for row in analysis.nodes.to_dict("records")}
    role_rows = {int(row["gid"]): row for row in roles.nodes_roles.to_dict("records")}
    if set(metrics) != set(analysis.graph) or set(role_rows) != set(metrics):
        raise ValueError("Граф пен рөлдер бір деректер жиынына тиесілі болуы керек")
    return {gid: {**metrics[gid], **role_rows[gid]} for gid in sorted(metrics)}


def build_graph_view(
    analysis: AnalysisResult,
    roles: RoleAnalysis,
    *,
    focus_gid=None,
    mode="ego",
    hops=1,
    direction="both",
    role_filter=None,
    cluster_filter=None,
    min_amount=0.0,
    color_by="role",
) -> dict:
    """Build a deterministic JSON-safe graph; never truncate the full network.

    Ego traversal first finds clients at <= 1/2 directed or undirected hops,
    then display filters apply. All original directed edges induced by visible
    clients remain eligible, irrespective of traversal direction. Minimum
    amount filters edges only, so isolated clients remain visible.

    The selected client is retained even outside the scope or node filters.
    ``eligible_nodes/edges`` count the chosen scope PLUS that retained focus,
    before role/cluster/amount display filters; ``excluded_*`` are differences
    within that scope. ``outside_scope_*`` describes the rest of the network.
    """
    if mode not in ("ego", "full", "cluster"):
        raise ValueError("mode: ego, full немесе cluster болуы керек")
    if isinstance(hops, bool) or not isinstance(hops, numbers.Integral) or hops not in (1, 2):
        raise ValueError("hops: тек 1 немесе 2")
    if direction not in ("both", "incoming", "outgoing"):
        raise ValueError("direction: both, incoming немесе outgoing болуы керек")
    if color_by not in ("role", "cluster", "depth"):
        raise ValueError("color_by: role, cluster немесе depth болуы керек")
    if isinstance(min_amount, bool) or not isinstance(min_amount, numbers.Real) or not math.isfinite(min_amount) or min_amount < 0:
        raise ValueError("min_amount: нөлден кем емес шекті сан болуы керек")

    rows = _records(analysis, roles)
    if not rows:
        raise ValueError("Граф бос")
    clusters = {int(row["cluster_id"]) for row in rows.values()}
    selected_roles = _filters(role_filter, kind="role_filter", available=set(ROLE_ORDER))
    selected_clusters = _filters(cluster_filter, kind="cluster_filter", available=clusters)
    if mode == "cluster" and not selected_clusters:
        raise ValueError("Кластер режимінде кемінде бір кластер таңдалуы керек")
    if focus_gid is None:
        focus = min(rows, key=lambda gid: (-float(rows[gid]["priority_score"]), -float(rows[gid]["in_kzt"]), gid))
    else:
        focus = _known_gid(focus_gid, rows)

    graph = analysis.graph
    if mode == "full":
        scope = set(rows)
    elif mode == "cluster":
        scope = {gid for gid, row in rows.items() if int(row["cluster_id"]) in selected_clusters}
    else:
        scope, frontier = {focus}, {focus}
        for _ in range(int(hops)):
            neighbors = set()
            for gid in frontier:
                if direction in ("both", "incoming"):
                    neighbors.update(graph.predecessors(gid))
                if direction in ("both", "outgoing"):
                    neighbors.update(graph.successors(gid))
            frontier = neighbors - scope
            scope.update(frontier)
    eligible = scope | {focus}
    visible = {
        gid for gid in scope
        if (selected_roles is None or rows[gid]["role"] in selected_roles)
        and (selected_clusters is None or int(rows[gid]["cluster_id"]) in selected_clusters)
    }
    focus_outside_filter = focus not in visible
    visible.add(focus)

    # Global scaling keeps sizes/widths comparable when display filters change.
    max_amount = max((float(data["sum_kzt"]) for _, _, data in graph.edges(data=True)), default=0.0)
    log_max = math.log1p(max_amount)
    eligible_edges = 0
    edges = []
    for src, dst, data in sorted(graph.edges(data=True), key=lambda edge: (edge[0], edge[1])):
        if src not in eligible or dst not in eligible:
            continue
        eligible_edges += 1
        amount = float(data["sum_kzt"])
        if src not in visible or dst not in visible or amount < float(min_amount):
            continue
        edges.append({
            "id": f"{src}->{dst}", "from": str(src), "to": str(dst),
            "sum_kzt": amount, "n_tx": int(data["n_tx"]),
            "width": round(1 + 4 * math.log1p(amount) / log_max, 4) if log_max else 1.0,
        })

    nodes = []
    for gid in sorted(visible):
        row = rows[gid]
        role, cluster, depth = row["role"], int(row["cluster_id"]), int(row["depth"])
        color = ROLE_COLORS[role] if color_by == "role" else cluster_color(cluster) if color_by == "cluster" else DEPTH_COLORS[depth]
        priority = float(row["priority_score"])
        nodes.append({
            "id": str(gid), "label": str(gid), "role": role, "role_label": ROLE_LABELS[role],
            "cluster_id": cluster, "depth": depth, "is_seed": bool(row["is_seed"]),
            "priority_score": priority, "in_kzt": float(row["in_kzt"]), "out_kzt": float(row["out_kzt"]),
            "in_deg": int(row["in_deg"]), "out_deg": int(row["out_deg"]),
            "evidence": str(row["evidence"]), "color": color, "size": round(12 + 24 * priority, 4),
            "shape": "diamond" if row["is_seed"] else "dot", "boundary": depth == 4,
            "is_focus": gid == focus, "outside_filter": gid == focus and focus_outside_filter,
        })
    total_edges = graph.number_of_edges()
    return {
        "nodes": nodes, "edges": edges, "selected_gid": str(focus),
        "summary": {
            "eligible_nodes": len(eligible), "eligible_edges": eligible_edges,
            "visible_nodes": len(nodes), "visible_edges": len(edges),
            "excluded_nodes": len(eligible) - len(nodes), "excluded_edges": eligible_edges - len(edges),
            "outside_scope_nodes": len(rows) - len(eligible), "outside_scope_edges": total_edges - eligible_edges,
            "total_nodes": len(rows), "total_edges": total_edges,
            "focus_outside_filter": focus_outside_filter,
            "mode": mode, "hops": int(hops), "direction": direction, "min_amount": float(min_amount),
            "color_by": color_by,
        },
        "legend": {
            "roles": [{"key": role, "label": ROLE_LABELS[role], "color": ROLE_COLORS[role]} for role in ROLE_ORDER],
            "clusters": [{"key": cluster, "label": f"Кластер {cluster}", "color": cluster_color(cluster)} for cluster in sorted(clusters)],
            "depths": [{"key": depth, "label": f"{depth}-буын", "color": color} for depth, color in enumerate(DEPTH_COLORS)],
        },
    }


def client_transactions(frames: dict[str, pd.DataFrame], gid: object) -> pd.DataFrame:
    """Return every original matching transaction, including duplicate rows."""
    focus = _known_gid(gid, set(frames["nodes"]["gid"]))
    original = frames["transactions"]
    selected = original.loc[original["src"].eq(focus) | original["dst"].eq(focus)].copy()
    selected["direction_label"] = [
        "Өзіне" if src == dst == focus else "Шығыс" if src == focus else "Кіріс"
        for src, dst in selected[["src", "dst"]].itertuples(index=False, name=None)
    ]
    return selected.sort_values(["date", "src", "dst"], kind="stable").reset_index(drop=True)


def client_neighbors(analysis: AnalysisResult, roles: RoleAnalysis, gid: object) -> pd.DataFrame:
    """One row per original incident directed edge, self transfers counted once."""
    rows = _records(analysis, roles)
    focus = _known_gid(gid, rows)
    result = []
    incident = set(analysis.graph.in_edges(focus)) | set(analysis.graph.out_edges(focus))
    for src, dst in sorted(incident):
        data = analysis.graph.edges[src, dst]
        counterparty = dst if src == focus else src
        result.append({
            "src": src, "dst": dst, "sum_kzt": float(data["sum_kzt"]), "n_tx": int(data["n_tx"]),
            "counterparty_gid": counterparty,
            "direction_label": "Өзіне" if src == dst else "Шығыс" if src == focus else "Кіріс",
            "role": str(rows[counterparty]["role"]), "cluster_id": int(rows[counterparty]["cluster_id"]),
        })
    return pd.DataFrame(result, columns=NEIGHBOR_COLUMNS).astype({
        "src": "int64", "dst": "int64", "counterparty_gid": "int64", "sum_kzt": "float64", "n_tx": "int64", "cluster_id": "int64",
    })
