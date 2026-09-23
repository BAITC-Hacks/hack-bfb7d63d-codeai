"""Observed inter-community flows, data gaps and comparable removal scenarios.

No structural measure establishes control, ownership, guilt or missing money.
Every client is preserved; UI identifiers are exact decimal strings.
"""

from dataclasses import dataclass
import math

import networkx as nx
import pandas as pd

from moneymap.investigation import resilience_analysis


@dataclass
class NetworkInsights:
    flows: pd.DataFrame
    bridges: pd.DataFrame
    coverage: pd.DataFrame
    requests: pd.DataFrame
    summary: dict
    limitations: tuple[str, ...]


def analyze_network(analysis, roles):
    graph = analysis.graph
    records = roles.nodes_roles.to_dict("records")
    if len(records) != len(graph) or {int(r["gid"]) for r in records} != set(graph):
        raise ValueError("Рөлдер мен граф клиенттері сәйкес емес")
    membership = {int(r["gid"]): int(r["cluster_id"]) for r in records}
    predictions = {int(r["gid"]): r for r in records}
    node_info = {int(r["gid"]): r for r in analysis.nodes.to_dict("records")}
    flow_groups = {}
    external = {gid: {"incoming": [], "outgoing": [], "neighbors": set(), "clusters": set()} for gid in graph}
    internal = []
    for src, dst, edge in sorted(graph.edges(data=True)):
        amount = float(edge["sum_kzt"])
        a, b = membership[src], membership[dst]
        if a == b:
            internal.append(amount)
            continue
        group = flow_groups.setdefault((a, b), {"amounts": [], "n_tx": 0, "n_edges": 0})
        group["amounts"].append(amount)
        group["n_tx"] += int(edge["n_tx"])
        group["n_edges"] += 1
        for gid, neighbor, direction in ((src, dst, "outgoing"), (dst, src, "incoming")):
            external[gid][direction].append(amount)
            external[gid]["neighbors"].add(neighbor)
            external[gid]["clusters"].add(membership[neighbor])
    flow_rows = [
        {"src_cluster": a, "dst_cluster": b, "sum_kzt": math.fsum(value["amounts"]),
         "n_tx": value["n_tx"], "n_edges": value["n_edges"]}
        for (a, b), value in flow_groups.items()
    ]
    flow_rows.sort(key=lambda row: (-row["sum_kzt"], row["src_cluster"], row["dst_cluster"]))
    articulation = set(nx.articulation_points(graph.to_undirected()))
    bridge_rows = []
    for gid in sorted(graph):
        item = external[gid]
        if not item["neighbors"]:
            continue
        incoming, outgoing = math.fsum(item["incoming"]), math.fsum(item["outgoing"])
        bridge_rows.append({
            "gid": str(gid), "cluster_id": membership[gid],
            "neighbor_clusters": len(item["clusters"]), "external_neighbors": len(item["neighbors"]),
            "external_in_kzt": incoming, "external_out_kzt": outgoing,
            "external_turnover_kzt": incoming + outgoing,
            "betweenness": float(node_info[gid]["betweenness"]),
            "is_articulation": gid in articulation,
            "role": predictions[gid]["role"], "priority_score": predictions[gid]["priority_score"],
            "evidence": f"Өзге кластер={len(item['clusters'])}; өзге кластердегі клиент={len(item['neighbors'])}; кіріс={incoming:.2f} ₸; шығыс={outgoing:.2f} ₸.",
        })
    # Lexicographic ranking is explicit, not a trained score or organizer label.
    bridge_rows.sort(key=lambda r: (-r["neighbor_clusters"], -r["betweenness"], -r["external_turnover_kzt"], int(r["gid"])))
    for rank, row in enumerate(bridge_rows, 1):
        row["rank"] = rank
    coverage = []
    for gid in sorted(graph):
        row = node_info[gid]
        flags = []
        if row["is_seed"]:
            flags.append("seed_incoming_incomplete")
        if int(row["depth"]) == 4:
            flags.append("outgoing_beyond_boundary_unknown")
        if row["is_isolated"]:
            flags.append("no_observed_links")
        if row["out_kzt"] > row["in_kzt"]:
            flags.append("outgoing_exceeds_observed_incoming")
        coverage.append({
            "gid": str(gid), "depth": int(row["depth"]), "is_seed": bool(row["is_seed"]),
            "in_kzt": float(row["in_kzt"]), "out_kzt": float(row["out_kzt"]),
            "role": predictions[gid]["role"],
            "min_observed_seed_hops": int(row["min_seed_hops"]) if pd.notna(row["min_seed_hops"]) else None,
            "specific_gaps": "|".join(flags) or "no_additional_node_specific_flag",
            "coverage_status": "unknown_full_coverage",
        })
    requests = []
    for code, gids, reason, request in (
        ("boundary_outgoing", [g for g in graph if node_info[g]["depth"] == 4],
         "Төртінші қадамнан кейінгі шығыс бақыланбаған.", "Осы анонимді gid үшін кейінгі шығыс аударымдарын сұрату."),
        ("seed_incoming", [g for g in graph if node_info[g]["is_seed"]],
         "Бастапқы клиенттердің барлық кірісі қамтылмаған.", "Осы анонимді gid үшін сол кезеңдегі толық кіріс аударымдарын сұрату."),
        ("isolated_clients", [g for g in graph if node_info[g]["is_isolated"]],
         "Клиент кестеде бар, бақыланған байланыс жоқ.", "Осы gid үшін толық үзіндіні және іріктеу шарттарын нақтылау."),
        ("sampling_scope", list(graph), "Банк, кезең және 5 000 ₸ іріктеу шегі толық ақша жолын көрсетпейді.",
         "Рұқсат етілген анонимді кеңейтілген үзінді: сомалық шексіз, кеңірек кезең және жетіспейтін банк бағыттары."),
        ("expert_review", list(graph), "Бастапқы транзакция файлдарында сарапшы бағасы жоқ; бөлек сақталған бағалар бұл бастапқы дерек есебіне кірмейді.",
         "Сарапшы бағасы бөлімінде тексерілген белгілер мен қамтылуды қарап, қалған клиенттерді бағалау; расталмағанын белгісіз күйде қалдыру."),
    ):
        if gids:
            requests.append({"request_id": code, "affected_nodes": len(gids),
                             "gids": "|".join(map(str, sorted(gids))), "reason": reason, "request": request})
    external_total = math.fsum(r["sum_kzt"] for r in flow_rows)
    return NetworkInsights(
        pd.DataFrame(flow_rows, columns=["src_cluster", "dst_cluster", "sum_kzt", "n_tx", "n_edges"]),
        pd.DataFrame(bridge_rows, columns=["rank", "gid", "cluster_id", "neighbor_clusters", "external_neighbors", "external_in_kzt", "external_out_kzt", "external_turnover_kzt", "betweenness", "is_articulation", "role", "priority_score", "evidence"]),
        pd.DataFrame(coverage), pd.DataFrame(requests),
        {"intercluster_pairs": len(flow_rows), "bridge_candidates": len(bridge_rows),
         "internal_turnover_kzt": math.fsum(internal), "external_turnover_kzt": external_total,
         "total_turnover_kzt": math.fsum(internal) + external_total,
         "bridge_ranking": "other-cluster count descending, directed betweenness descending, external turnover descending, gid ascending",
         "full_coverage": "unknown"},
        ("Кластер мен бағытталған ағын басқару иерархиясын немесе ортақ қылмыстық ниетті дәлелдемейді.",
         "Байланыстырушы клиенттер өзге кластер саны, аралық орталықтық, сыртқы айналым ретімен көрсетіледі. Бұл ұйымдастырушы рейтингі емес.",
         "Бөлуші түйін белгісі бағытты уақытша ескермейтін графқа қатысты. Оны алу байланысқан бөліктер санын арттырады.",
         "Ең қысқа seed жолының қадам саны — бақыланған байланыс қашықтығы; басқару деңгейі немесе бір ақшаның жолы емес.",
         "Толықтық пайызы белгісіз: көрінбейтін аударымдардың жалпы саны берілмеген. Жоқ дерек жасанды толтырылмайды."),
    )


def compare_removal_strategies(analysis, roles, top_n=5):
    """Compare priority and seed-only removal with the same candidate count."""
    ranked = roles.details.sort_values(["priority_score", "in_kzt", "gid"], ascending=[False, False, True], kind="stable")
    seed_ranking = ranked.loc[ranked["is_seed"], "gid"].tolist()
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n: оң бүтін сан болуы керек")
    matched_n = min(top_n, len(seed_ranking), len(ranked))
    baseline = resilience_analysis(analysis, [], top_n=0).comparison.iloc[0].to_dict()
    baseline.update(scenario="before", removed_count=0, removed_gids="")
    rows = [baseline]
    if matched_n:
        for label, ranking in (("priority", ranked.gid.tolist()), ("seed_only", seed_ranking)):
            result = resilience_analysis(analysis, ranking, top_n=matched_n)
            row = result.comparison.iloc[1].to_dict()
            row.update(scenario=label, removed_count=matched_n, removed_gids="|".join(result.removed_gids))
            rows.append(row)
    return pd.DataFrame(rows), {
        "requested_n": top_n, "compared_n": matched_n, "available_seeds": len(seed_ranking),
        "note": "Екі стратегия бірдей клиент санымен салыстырылады; seed жеткіліксіз болса сан азаяды. Seed — бастапқы тізім, расталған төменгі деңгей емес. Нақты араласу мен желінің қайта құрылуы болжанбайды.",
    }
