"""Deterministic structural hypotheses and review priorities for Stage 3.

No supervised labels or trained model are available. Both scores are explicit
heuristics, never a probability of wrongdoing. A role is selected by precedence,
while the independent priority is a weighted sum of observed graph features.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import Path
from time import perf_counter

import networkx as nx
import numpy as np
import pandas as pd

from moneymap.graph import AnalysisResult


DEFAULT_CONFIG = {
    "version": 1,
    "clustering": {"seed": 42, "resolution": 1.0, "threshold": 1e-7},
    "rules": {
        "coordinator_min_in_deg": 3, "coordinator_min_out_deg": 3,
        "coordinator_min_seed_reach": 2, "coordinator_betweenness_quantile": 0.9,
        "distributor_min_out_deg": 10, "consolidator_min_in_deg": 5,
        "consolidator_max_ratio": 0.3, "transit_min_ratio": 0.8,
        "transit_max_ratio": 1.2,
    },
    "priority": {
        "normalizer_quantile": 0.95,
        "weights": {"consolidation": 0.25, "in_kzt": 0.15, "in_deg": 0.15,
                    "betweenness": 0.15, "seed_reach": 0.15, "out_deg": 0.10,
                    "pagerank": 0.05},
    },
    "scores": {"general_cap": 0.9, "seed_cap": 0.7, "terminal_cap": 0.55, "boundary_cap": 0.25},
}

ROLE_ORDER = ("coordinator", "distributor", "consolidator", "transit", "terminal", "peripheral")
ROLE_LABELS = {
    "coordinator": "үйлестірушіге ұқсас құрылым", "distributor": "таратушы",
    "consolidator": "жинақтаушы", "transit": "транзит", "terminal": "бақыланған соңғы алушы",
    "peripheral": "рөлге дәлел жеткіліксіз",
}
NODE_ROLE_COLUMNS = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
CLUSTER_COLUMNS = ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]
TOP_COLUMNS = ["rank", "gid", "role", "priority_score", "why"]


@dataclass
class RoleAnalysis:
    nodes_roles: pd.DataFrame
    clusters: pd.DataFrame
    top_nodes: pd.DataFrame
    details: pd.DataFrame
    summary: dict
    config: dict
    elapsed_seconds: float


def _merge_config(base: dict, supplied: dict, path: str = "config") -> dict:
    if not isinstance(supplied, dict):
        raise ValueError(f"{path}: объект болуы керек")
    unknown = set(supplied) - set(base)
    if unknown:
        raise ValueError(f"{path}: белгісіз параметрлер: {', '.join(sorted(map(str, unknown)))}")
    result = deepcopy(base)
    for key, value in supplied.items():
        if isinstance(base[key], dict):
            result[key] = _merge_config(base[key], value, f"{path}.{key}")
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{path}.{key}: шекті сан болуы керек")
            result[key] = value
    return result


def _validated_config(supplied: dict) -> dict:
    result = _merge_config(DEFAULT_CONFIG, supplied)
    if not isinstance(result["version"], int) or result["version"] != 1:
        raise ValueError("config.version: тек 1-нұсқа қолдау табады")
    clustering, rules, priority, scores = (result[key] for key in ("clustering", "rules", "priority", "scores"))
    if not isinstance(clustering["seed"], int) or not 0 <= clustering["seed"] <= 2**32 - 1:
        raise ValueError("clustering.seed: 0..2**32-1 аралығындағы бүтін сан")
    if clustering["resolution"] <= 0 or not 0 < clustering["threshold"] <= 1:
        raise ValueError("clustering: resolution > 0 және threshold 0..1 болуы керек")
    for key in ("coordinator_min_in_deg", "coordinator_min_out_deg", "coordinator_min_seed_reach", "distributor_min_out_deg", "consolidator_min_in_deg"):
        if not isinstance(rules[key], int) or rules[key] < 1:
            raise ValueError(f"rules.{key}: оң бүтін сан болуы керек")
    for key in ("coordinator_betweenness_quantile", "consolidator_max_ratio"):
        if not 0 <= rules[key] <= 1:
            raise ValueError(f"rules.{key}: 0..1 аралығы")
    if not 0 <= rules["transit_min_ratio"] <= 1 <= rules["transit_max_ratio"] or rules["transit_min_ratio"] == rules["transit_max_ratio"]:
        raise ValueError("transit: min <= 1 <= max, min < max болуы керек")
    if not 0 < priority["normalizer_quantile"] <= 1:
        raise ValueError("priority.normalizer_quantile: 0..1 аралығы, нөлден үлкен")
    weights = priority["weights"]
    if any(not 0 <= value <= 1 for value in weights.values()) or not math.isclose(math.fsum(weights.values()), 1, abs_tol=1e-12, rel_tol=0):
        raise ValueError("priority.weights: әр салмақ 0..1, олардың қосындысы 1 болуы керек")
    for key, maximum in (("general_cap", 0.9), ("seed_cap", 0.7), ("terminal_cap", 0.55), ("boundary_cap", 0.25)):
        if not 0 < scores[key] <= maximum:
            raise ValueError(f"scores.{key}: 0..{maximum} аралығы, нөлден үлкен")
    return result


def load_config(path: str | Path | None = None) -> dict:
    """Read a reproducible configuration; partial overrides retain defaults.

    Unknown keys, nonfinite values and out-of-range thresholds fail explicitly.
    Values are freshly copied, so callers cannot mutate the defaults.
    """
    source = Path(path) if path is not None else Path(__file__).resolve().parent.parent / "config" / "roles.json"
    return _validated_config(json.loads(source.read_text(encoding="utf-8-sig")))


def _communities(graph: nx.DiGraph, config: dict) -> tuple[list[set[int]], nx.Graph, float | None]:
    projection = nx.Graph()
    projection.add_nodes_from(sorted(graph))
    pairs: dict[tuple[int, int], list[float]] = {}
    for src, dst, data in sorted(graph.edges(data=True), key=lambda edge: (edge[0], edge[1])):
        if src != dst:
            pairs.setdefault((min(src, dst), max(src, dst)), []).append(float(data["sum_kzt"]))
    for (src, dst), amounts in sorted(pairs.items()):
        projection.add_edge(src, dst, weight=math.fsum(amounts))
    if projection.number_of_edges():
        groups = nx.community.louvain_communities(projection, weight="weight", **config)
        modularity = float(nx.community.modularity(projection, groups, weight="weight", resolution=config["resolution"]))
    else:
        groups = [{gid} for gid in projection]
        modularity = None
    return sorted(groups, key=lambda group: (-len(group), min(group))), projection, modularity


def _role_strength(role: str, row: dict, rules: dict, scores: dict) -> float:
    """Match-strength formula, not confidence; formulas are exposed in summary."""
    incoming, outgoing, reach = row["in_deg"], row["out_deg"], row["reachable_seed_count"]
    ratio = row["observed_flow_ratio"]
    if row["is_isolated"]:
        score = 0.1
    elif row["self_loop_only"]:
        score = 0.2
    elif row["depth"] == 4:
        score = min(0.2, scores["boundary_cap"])
    elif role == "coordinator":
        score = 0.45 + 0.15 * min(incoming / (2 * rules["coordinator_min_in_deg"]), 1) + 0.15 * min(outgoing / (2 * rules["coordinator_min_out_deg"]), 1) + 0.15 * min(reach / (2 * rules["coordinator_min_seed_reach"]), 1)
    elif role == "distributor":
        score = 0.5 + 0.4 * min(outgoing / (2 * rules["distributor_min_out_deg"]), 1)
    elif role == "consolidator":
        score = 0.45 + 0.2 * min(incoming / (2 * rules["consolidator_min_in_deg"]), 1) + 0.25 * max(0, 1 - ratio)
    elif role == "transit":
        width = max(1 - rules["transit_min_ratio"], rules["transit_max_ratio"] - 1)
        score = 0.5 + 0.25 * max(0, 1 - abs(ratio - 1) / width) + 0.1 * min(min(incoming, outgoing) / 3, 1)
    elif role == "terminal":
        score = min(0.5, scores["terminal_cap"])
    else:
        score = 0.3
    cap = min(scores["general_cap"], scores["seed_cap"] if row["is_seed"] else 1, scores["boundary_cap"] if row["depth"] == 4 else 1)
    return float(round(min(score, cap), 6))


def _evidence(role: str, row: dict) -> str:
    if row["is_isolated"]:
        return "Кіріс көрші=0, шығыс көрші=0; операция=0. Рөлге бақылау жеткіліксіз." + (" Seed кірісі толық емес." if row["is_seed"] else "")
    if row["self_loop_only"]:
        return f"Өзіне аударым={row['in_tx']}; өзге клиентпен байланыс жоқ (0). Рөлге дәлел жеткіліксіз." + (" Seed кірісі толық емес." if row["is_seed"] else "")
    facts = f"Кіріс көрші={row['in_deg']}, шығыс көрші={row['out_deg']}; seed-жету={row['reachable_seed_count']}. "
    if row["depth"] == 4:
        return facts + "Depth=4: шығыс бақылауы шектелген, рөлге дәлел жеткіліксіз."
    if role == "peripheral" and row["temporal_contradiction"]:
        return facts + f"Соңғы шығыс={row['last_out_date']:%Y-%m-%d} < алғашқы кіріс={row['first_in_date']:%Y-%m-%d}; транзитке уақыт қайшы."
    if role == "coordinator":
        finding = f"Аралықтық={row['betweenness']:.6f}: құрылымдық үміткер, ұйымдастыру дәлелі емес."
    elif role in ("consolidator", "transit"):
        finding = f"Бақыланған шығыс/кіріс={row['observed_flow_ratio']:.2f}; {ROLE_LABELS[role]} белгісі."
    elif role == "terminal":
        finding = "Шығыс байқалмады; осы кезеңдегі соңғы алушы гипотезасы."
    elif role == "distributor":
        finding = "Көп алушыға тарату белгісі."
    else:
        finding = "Ережелерге дәлел жеткіліксіз; қауіпсіздік қорытындысы емес."
    suffix = " Бір күндегі реттілік белгісіз." if role == "transit" and row["temporal_order_status"] == "same_day_order_unknown" else ""
    if row["temporal_contradiction"]:
        suffix += " Шығыстың бәрі кірістен бұрын."
    suffix += " Seed кірісі толық емес." if row["is_seed"] else ""
    return (facts + finding + suffix)[:200]


def _cluster_flows(graph: nx.DiGraph, groups: list[set[int]], membership: dict[int, int]) -> list[dict]:
    """Describe observed directed flow without confusing turnover with balances.

    Concentration uses internal transfers between distinct clients. Self transfers
    stay in internal accounting but cannot manufacture a collection/distribution
    pattern. Each crossing edge is an exit of one group and an entry of another.
    """
    accumulators = {
        cluster_id: {"internal": [], "external_in": [], "external_out": [],
                     "receivers": {}, "senders": {}, "payers": {}, "payees": {}}
        for cluster_id in range(1, len(groups) + 1)
    }
    for src, dst, data in sorted(graph.edges(data=True), key=lambda edge: (edge[0], edge[1])):
        source_group, target_group = membership[src], membership[dst]
        amount = float(data["sum_kzt"])
        if source_group != target_group:
            accumulators[source_group]["external_out"].append(amount)
            accumulators[target_group]["external_in"].append(amount)
            continue
        bucket = accumulators[source_group]
        bucket["internal"].append(amount)
        if src != dst:
            bucket["receivers"].setdefault(dst, []).append(amount)
            bucket["senders"].setdefault(src, []).append(amount)
            bucket["payers"].setdefault(dst, set()).add(src)
            bucket["payees"].setdefault(src, set()).add(dst)
    metrics = []
    for cluster_id, group in enumerate(groups, 1):
        bucket = accumulators[cluster_id]
        incoming = {gid: math.fsum(amounts) for gid, amounts in bucket["receivers"].items()}
        outgoing = {gid: math.fsum(amounts) for gid, amounts in bucket["senders"].items()}
        receiver = min(incoming, key=lambda gid: (-incoming[gid], gid)) if incoming else None
        sender = min(outgoing, key=lambda gid: (-outgoing[gid], gid)) if outgoing else None
        distinct_turnover = math.fsum(incoming.values())
        internal = math.fsum(bucket["internal"])
        external_in, external_out = math.fsum(bucket["external_in"]), math.fsum(bucket["external_out"])
        incident = math.fsum((internal, external_in, external_out))
        receiver_share = incoming[receiver] / distinct_turnover if receiver is not None else None
        sender_share = outgoing[sender] / distinct_turnover if sender is not None else None
        receiver_payers = len(bucket["payers"].get(receiver, ()))
        sender_payees = len(bucket["payees"].get(sender, ()))
        collecting = receiver_share is not None and receiver_share >= 0.5 and receiver_payers >= 3
        distributing = sender_share is not None and sender_share >= 0.5 and sender_payees >= 3
        if incident == 0:
            pattern = "isolated"
        elif distinct_turnover == 0 and external_in == external_out == 0:
            pattern = "self_transfers_only"
        elif collecting and distributing:
            pattern = "concentration_and_distribution"
        elif collecting:
            pattern = "concentration"
        elif distributing:
            pattern = "distribution"
        elif external_in > 0 and external_out > 0 and external_in + external_out > internal:
            pattern = "intercommunity_exchange"
        else:
            pattern = "mixed_inconclusive"
        metrics.append({
            "cluster_id": cluster_id, "flow_pattern": pattern,
            "internal_kzt": internal, "external_in_kzt": external_in, "external_out_kzt": external_out,
            "internal_share_of_incident_turnover": internal / incident if incident else None,
            "internal_edge_count": len(bucket["internal"]),
            "external_in_edge_count": len(bucket["external_in"]), "external_out_edge_count": len(bucket["external_out"]),
            "distinct_client_internal_kzt": distinct_turnover,
            "top_internal_receiver_gid": str(receiver) if receiver is not None else None,
            "top_internal_receiver_share": receiver_share, "top_internal_receiver_payers": receiver_payers,
            "top_internal_sender_gid": str(sender) if sender is not None else None,
            "top_internal_sender_share": sender_share, "top_internal_sender_receivers": sender_payees,
            "boundary_count": sum(graph.nodes[gid]["depth"] == 4 for gid in group),
        })
    return metrics


def _cluster_hypothesis(flow: dict) -> str:
    pattern = flow["flow_pattern"]
    if pattern == "isolated":
        return "Байланыс байқалмаған жеке түйін: қыр=0, айналым=0 ₸; қызметі анықталмайды."
    if pattern == "self_transfers_only":
        return f"Тек өзіне аударым: {flow['internal_kzt']:.2f} ₸; өзге клиентпен қыр=0. Кластер қызметіне дәлел жеткіліксіз."
    labels = {
        "concentration": "Бір алушыға жинақтау гипотезасы",
        "distribution": "Бір орталықтан тарату гипотезасы",
        "concentration_and_distribution": "Жинақтау және тарату орталықтары бар топ гипотезасы",
        "intercommunity_exchange": "Өзге кластерлермен кіріс-шығыс алмасуы басым",
        "mixed_inconclusive": "Аралас ағын; бір орталықтың қызметі анықталмады",
    }
    facts = [f"Ішкі={flow['internal_kzt']:.2f} ₸", f"сырттан кіріс={flow['external_in_kzt']:.2f} ₸", f"сыртқа шығыс={flow['external_out_kzt']:.2f} ₸"]
    if flow["top_internal_receiver_gid"] is not None:
        facts.append(f"ішкі кірістің {flow['top_internal_receiver_share']:.1%}-ы {flow['top_internal_receiver_gid']} алушыда ({flow['top_internal_receiver_payers']} жіберуші)")
    if flow["top_internal_sender_gid"] is not None:
        facts.append(f"ішкі шығыстың {flow['top_internal_sender_share']:.1%}-ы {flow['top_internal_sender_gid']} көзінен ({flow['top_internal_sender_receivers']} алушы)")
    return f"{labels[pattern]}. " + "; ".join(facts) + f". Depth4={flow['boundary_count']}; тек көрінетін аударымдар, қылмыстық мақсат дәлелденбейді."


def classify_graph(analysis: AnalysisResult, config: dict | None = None, top_n: int = 30, *, include_sensitivity: bool = True) -> RoleAnalysis:
    """Assign six cautious structural roles, Louvain communities and priorities.

    Boundary and isolated clients always receive 'peripheral': it means evidence
    is insufficient, not low risk or innocence. Coordinator is a structural gate
    requiring positive high betweenness, never an allegation of organization.
    The input AnalysisResult is preserved. All IDs remain exact integer values.
    """
    started = perf_counter()
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 20:
        raise ValueError("top_n кемінде 20 болатын бүтін сан болуы керек")
    config = load_config() if config is None else _validated_config(config)
    details = analysis.nodes.sort_values("gid", kind="stable").reset_index(drop=True).copy(deep=True)
    groups, projection, modularity = _communities(analysis.graph, config["clustering"])
    membership = {gid: cluster_id for cluster_id, group in enumerate(groups, 1) for gid in group}
    details["cluster_id"] = details["gid"].map(membership).astype("int64")
    details["neighbor_cluster_count"] = pd.Series([
        len({membership[neighbor] for neighbor in set(analysis.graph.predecessors(int(gid))) | set(analysis.graph.successors(int(gid))) if membership[neighbor] != membership[int(gid)]})
        for gid in details["gid"]
    ], dtype="int64")
    details["self_loop_only"] = pd.Series([
        analysis.graph.has_edge(int(gid), int(gid))
        and not ((set(analysis.graph.predecessors(int(gid))) | set(analysis.graph.successors(int(gid)))) - {int(gid)})
        for gid in details["gid"]
    ], dtype="bool")

    rules = config["rules"]
    positives = details.loc[details["betweenness"].gt(0), "betweenness"]
    centrality_cutoff = float(positives.quantile(rules["coordinator_betweenness_quantile"])) if not positives.empty else None
    observed = details["depth"].lt(4) & ~details["is_isolated"] & ~details["self_loop_only"]
    coordinator = observed & details["in_deg"].ge(rules["coordinator_min_in_deg"]) & details["out_deg"].ge(rules["coordinator_min_out_deg"]) & details["reachable_seed_count"].ge(rules["coordinator_min_seed_reach"]) & details["betweenness"].gt(0)
    coordinator &= details["betweenness"].ge(centrality_cutoff) if centrality_cutoff is not None else False
    transit_without_time = observed & details["ratio_usable"] & details["in_deg"].ge(1) & details["out_deg"].ge(1) & details["observed_flow_ratio"].between(rules["transit_min_ratio"], rules["transit_max_ratio"])
    details["transit_excluded_by_time"] = transit_without_time & details["temporal_contradiction"]
    gates = {
        "coordinator": coordinator,
        "distributor": observed & details["out_deg"].ge(rules["distributor_min_out_deg"]),
        "consolidator": observed & details["ratio_usable"] & details["in_deg"].ge(rules["consolidator_min_in_deg"]) & details["observed_flow_ratio"].le(rules["consolidator_max_ratio"]),
        "transit": transit_without_time & ~details["temporal_contradiction"],
        "terminal": observed & details["ratio_usable"] & details["in_kzt"].gt(0) & details["out_deg"].eq(0),
    }
    details["role"] = "peripheral"
    # Reverse assignments implement the documented first-match precedence.
    for role in reversed(ROLE_ORDER[:-1]):
        details.loc[gates[role], "role"] = role
    details["matched_roles"] = ["|".join(role for role in ROLE_ORDER[:-1] if bool(gates[role].iat[index])) or "peripheral" for index in range(len(details))]
    detail_records = details.to_dict("records")  # preserves integer identifiers
    details["role_score"] = [_role_strength(row["role"], row, rules, config["scores"]) for row in detail_records]
    details["evidence"] = [_evidence(row["role"], row) for row in detail_records]

    priority = config["priority"]
    weights = priority["weights"]
    details["consolidation_signal"] = np.where(details["ratio_usable"], np.minimum(details["in_deg"] / rules["consolidator_min_in_deg"], 1) * np.maximum(0, 1 - np.minimum(details["observed_flow_ratio"].fillna(1), 1)), 0)
    details["priority_consolidation"] = details["consolidation_signal"] * weights["consolidation"]
    normalizers = {}
    signal_columns = {"in_kzt": "in_kzt", "in_deg": "in_deg", "betweenness": "betweenness", "seed_reach": "reachable_seed_count", "out_deg": "out_deg", "pagerank": "pagerank"}
    for name, column in signal_columns.items():
        positive = details.loc[details[column].gt(0), column]
        normalizer = float(positive.quantile(priority["normalizer_quantile"])) if len(positive) else None
        normalizers[name] = normalizer
        details[f"priority_{name}"] = np.minimum(np.log1p(details[column]) / math.log1p(normalizer), 1) * weights[name] if normalizer is not None else 0.0
    priority_columns = [f"priority_{name}" for name in weights]
    details.loc[details["is_isolated"], priority_columns] = 0.0
    details["priority_score"] = details[priority_columns].sum(axis=1).clip(0, 1)
    ranked = details.sort_values(["priority_score", "in_kzt", "gid"], ascending=[False, False, True], kind="stable")
    top = ranked.head(min(top_n, len(details))).copy()
    top["rank"] = range(1, len(top) + 1)
    part_labels = {"consolidation": "жинақталу", "in_kzt": "кіріс сома", "in_deg": "кіріс көрші", "betweenness": "орталықтық", "seed_reach": "seed-жету", "out_deg": "шығыс көрші", "pagerank": "PageRank"}
    why = []
    for row in top.to_dict("records"):
        strongest = sorted(weights, key=lambda name: (-row[f"priority_{name}"], list(weights).index(name)))[:2]
        reasons = ", ".join(f"{part_labels[name]}={row[f'priority_{name}']:.3f}" for name in strongest if row[f"priority_{name}"] > 0)
        zero_reason = "Байланыс жоқ; басымдық=0" if row["is_isolated"] else "Салмақталған белгілер=0"
        finding = f"{reasons or zero_reason}. Кіріс={row['in_kzt']:.2f} ₸; көрші={row['in_deg']}; seed-жету={row['reachable_seed_count']}."
        if row["depth"] == 4:
            finding += " Depth=4: шығыс шектеулі."
        if row["is_seed"]:
            finding += " Seed кірісі толық емес."
        if row["self_loop_only"]:
            finding += " Тек өзіне аударым."
        if row["temporal_contradiction"]:
            finding += " Шығыстың бәрі алғашқы кірістен бұрын."
        why.append(finding)
    top["why"] = why

    cluster_flows = _cluster_flows(analysis.graph, groups, membership)
    cluster_rows = []
    for flow, group in zip(cluster_flows, groups):
        cluster_id = flow["cluster_id"]
        members = ranked.loc[ranked["cluster_id"].eq(cluster_id)]
        n_seed = int(members["is_seed"].sum())
        cluster_rows.append({"cluster_id": cluster_id, "n_nodes": len(group), "n_seed": n_seed, "sum_kzt_internal": flow["internal_kzt"], "top_gids": json.dumps([str(int(gid)) for gid in members["gid"].head(5)], ensure_ascii=False), "hypothesis": _cluster_hypothesis(flow)})
    clusters = pd.DataFrame(cluster_rows, columns=CLUSTER_COLUMNS)
    summary = {
        "stage": 3, "nodes": len(details), "n_clusters": len(clusters),
        "n_top_nodes": len(top), "n_isolated": int(details["is_isolated"].sum()),
        "n_self_loop_only": int(details["self_loop_only"].sum()),
        "n_boundary": int(details["depth"].eq(4).sum()),
        "n_temporal_contradictions": int(details["temporal_contradiction"].sum()),
        "n_transit_candidates_excluded_by_time": int(details["transit_excluded_by_time"].sum()),
        "full_coverage": len(details) == analysis.graph.number_of_nodes() and details["gid"].is_unique,
        "role_counts": {role: int(details["role"].eq(role).sum()) for role in ROLE_ORDER},
        "modularity": modularity,
        "thresholds": {**rules, "coordinator_betweenness_cutoff": centrality_cutoff},
        "normalizers": normalizers, "weights": deepcopy(weights),
        "internal_turnover_kzt": math.fsum(clusters["sum_kzt_internal"]),
        "cluster_flow_metrics": cluster_flows,
        "methods": {
            "role_order": list(ROLE_ORDER),
            "clustering": "Weighted Louvain on sorted undirected projection; reciprocal amounts summed; self loops excluded only for clustering; isolates retained; canonical IDs by size then minimum gid",
            "priority": "Weighted sum independent of role and role_score; all isolated-node contributions are zero",
            "normalization": "min(log1p(x)/log1p(positive-value p95), 1); configured quantile used; zero when no positive values",
            "consolidation": "min(in_deg/consolidator_min_in_deg, 1) * max(0, 1-min(out/in, 1)); only ratio_usable",
            "transit_chronology": "Exclude transit when last outgoing calendar day is before first incoming day. Same-day order remains unknown; later outgoing does not establish matched funds or speed.",
            "cluster_hypothesis": "Directed internal/external sums; internal concentration requires a top receiver/sender share >=0.5 and at least 3 distinct counterparties. Self transfers excluded from concentration. External exchange means both boundary directions observed and their combined amount exceeds internal turnover; otherwise mixed/unknown.",
            "role_score": {
                "coordinator": "0.45 + 0.15*min(in_deg/(2*min_in),1) + 0.15*min(out_deg/(2*min_out),1) + 0.15*min(seed_reach/(2*min_reach),1)",
                "distributor": "0.5 + 0.4*min(out_deg/(2*min_out),1)",
                "consolidator": "0.45 + 0.2*min(in_deg/(2*min_in),1) + 0.25*max(0,1-ratio)",
                "transit": "0.5 + 0.25*max(0,1-abs(ratio-1)/max(1-min_ratio,max_ratio-1)) + 0.1*min(min(in_deg,out_deg)/3,1)",
                "terminal": "0.5, capped by terminal_cap",
                "peripheral": "isolated=0.1; self-loop-only=0.2; boundary=0.2; other=0.3; configured caps apply to all roles",
                "meaning": "Heuristic match strength, not calibrated confidence or wrongdoing probability",
            },
        },
        "limitations": [
            "Roles and priorities are review hypotheses, not guilt or innocence conclusions.",
            "Seed incoming and depth-4 outgoing observations are incomplete; their flow ratios are excluded from role rules.",
            "Depth-4 and isolated clients receive peripheral because evidence is insufficient; boundary structural priority can remain high.",
            "Clients with only self transfers receive peripheral because there is no observed external-counterparty structure; monetary/centrality observations remain in priority.",
            "Coordinator means structural candidate, not proof of an organizer; terminal means no observed outgoing transfer in this window.",
            "Cross-community neighbor count is supporting context, not a coordinator gate.",
            "No labeled ground truth is supplied; accuracy and calibrated probability are not claimed.",
            "Community membership depends on the supplied window, weighted projection and configured Louvain parameters.",
            "Chronological contradiction concerns observed incoming funds only; opening balances and external funding are unknown. A transit role does not assert a 1-2 day exit or matching of the same money.",
            "Cluster flow purposes are hypotheses of observed routing; mixed patterns remain inconclusive and external means another detected cluster, not another bank.",
        ],
    }
    result = RoleAnalysis(details[NODE_ROLE_COLUMNS].copy(), clusters, top[TOP_COLUMNS].reset_index(drop=True), details, summary, deepcopy(config), 0.0)
    if include_sensitivity:
        result.summary["sensitivity"] = sensitivity_analysis(analysis, result, top_n=top_n)
    result.elapsed_seconds = perf_counter() - started
    return result


def sensitivity_analysis(analysis: AnalysisResult, baseline: RoleAnalysis, *, top_n: int = 30) -> dict:
    """Four bounded counterfactual configurations; never tune to assumed labels.

    The graph/features are reused. Two neighboring consolidation thresholds and
    two Louvain resolutions test local sensitivity, not accuracy or robustness
    to missing data. Calling classifications here disables recursive analysis.
    """
    base_config = baseline.config
    threshold = base_config["rules"]["consolidator_min_in_deg"]
    resolution = base_config["clustering"]["resolution"]
    scenarios = []
    for value in (max(1, threshold - 1), threshold + 1):
        if value != threshold:
            scenarios.append(("consolidator_min_in_deg", value, {"rules": {"consolidator_min_in_deg": value}}))
    for multiplier in (0.8, 1.2):
        value = resolution * multiplier
        scenarios.append(("louvain_resolution", value, {"clustering": {"resolution": value}}))
    baseline_roles = baseline.nodes_roles.set_index("gid")["role"]
    baseline_top = set(baseline.top_nodes["gid"])
    results = []
    for parameter, value, overrides in scenarios:
        config = _merge_config(base_config, overrides)
        changed = classify_graph(analysis, config, top_n=top_n, include_sensitivity=False)
        results.append({
            "parameter": parameter, "value": value,
            "role_changes": int(changed.nodes_roles.set_index("gid")["role"].ne(baseline_roles).sum()),
            "top_overlap": len(baseline_top & set(changed.top_nodes["gid"])),
            "top_count": len(changed.top_nodes), "n_clusters": len(changed.clusters),
            "multi_seed_clusters": int(changed.clusters["n_seed"].ge(2).sum()),
            "role_counts": changed.summary["role_counts"],
        })
    return {
        "baseline": {"consolidator_min_in_deg": threshold, "louvain_resolution": resolution,
                     "top_count": len(baseline_top), "n_clusters": len(baseline.clusters)},
        "scenarios": results,
        "interpretation": "Local parameter sensitivity only, not accuracy. Consolidator threshold also normalizes the independent priority signal. Cluster labels themselves are not compared because their IDs can change.",
    }
