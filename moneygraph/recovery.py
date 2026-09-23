"""Explicit what-if rewiring assumptions, never a forecast of criminal behaviour."""
import math
import networkx as nx


def recovery_scenario(analysis, payload):
    from .server import simulate_request
    fraction = payload.get("replacement_fraction", .5)
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("replacement_fraction must be a finite number between 0 and 1")
    removal_args = {key: payload[key] for key in ("top_n", "gids") if key in payload}
    if not removal_args:
        removal_args = {"top_n": 5}
    removal = simulate_request(analysis, removal_args)
    removed = {str(value) for value in removal["removed"]}
    seeds = {str(n["gid"]) for n in analysis["nodes"] if n["is_seed"]}
    survivors = {str(n["gid"]) for n in analysis["nodes"]} - removed
    graph = nx.DiGraph()
    graph.add_nodes_from(survivors)
    incident = []
    for edge in analysis["edges"]:
        src, dst = str(edge["src"]), str(edge["dst"])
        if src in removed or dst in removed:
            incident.append(edge)
        else:
            graph.add_edge(src, dst)
    incident.sort(key=lambda e: (-float(e["sum_kzt"]), int(e["src"]), int(e["dst"])))

    def reachable(g, starts):
        seen = set(starts) & set(g)
        pending = list(seen)
        while pending:
            for other in g.successors(pending.pop()):
                if other not in seen:
                    seen.add(other)
                    pending.append(other)
        return seen

    reachable_after_removal = reachable(graph, seeds - removed)
    replace = {gid: f"hypothetical-{i}" for i, gid in enumerate(sorted(removed, key=int), 1)}
    # Rounding downward is deliberate: 0% restores no edges, 100% restores all.
    selected = incident[:int(math.floor(len(incident) * fraction))]
    hypothetical = {}
    assumed_edges = []
    if fraction == 1:
        # Full replacement also retains removed isolates, including isolated seeds.
        for original, replacement in replace.items():
            hypothetical[replacement] = {"id": replacement, "replaces_gid": original,
                                         "is_seed": original in seeds, "synthetic": True}
            graph.add_node(replacement)
    for edge in selected:
        original_src, original_dst = str(edge["src"]), str(edge["dst"])
        src, dst = replace.get(original_src, original_src), replace.get(original_dst, original_dst)
        for original in (original_src, original_dst):
            if original in replace:
                hypothetical[replace[original]] = {"id": replace[original], "replaces_gid": original,
                                                  "is_seed": original in seeds, "synthetic": True}
        graph.add_edge(src, dst)
        assumed_edges.append({"src": src, "dst": dst, "reference_src": original_src,
                              "reference_dst": original_dst, "prior_observed_kzt": float(edge["sum_kzt"]),
                              "synthetic": True})
    hypothetical_seeds = {item["id"] for item in hypothetical.values() if item["is_seed"]}
    reachable_after_recovery = reachable(graph, (seeds - removed) | hypothetical_seeds)
    components = list(nx.weakly_connected_components(graph))
    scenario = {"n_nodes": graph.number_of_nodes(), "n_edges": graph.number_of_edges(),
                "components": len(components), "largest_component": max(map(len, components), default=0),
                "reachable_from_seeds": len(reachable_after_recovery)}
    restored = survivors & (reachable_after_recovery - reachable_after_removal)
    return {"mode": "assumption_scenario", "baseline": removal["before"], "post_removal": removal["after"],
            "scenario": scenario, "removed": removal["removed"], "replacement_fraction": fraction,
            "restored_edge_fraction": len(selected) / len(incident) if incident else 0,
            "hypothetical_nodes": list(hypothetical.values()), "assumed_edges": assumed_edges,
            "observed_survivors_reconnected": len(restored),
            "reference_turnover_kzt": round(math.fsum(float(edge["sum_kzt"]) for edge in selected), 2),
            "assumptions": ["Алынған шоттардың орнына тек осы сценарийге арналған жасанды алмастырушы түйіндер қосылады.",
                            "Бұрынғы байланыстардың таңдалған үлесі көлемі үлкенінен бастап қайта құрылады; уақыт пен жаңа сома болжанбайды.",
                            "Алынған seed орнына қосылған жасанды түйін seed қызметін жалғастырады деген жорамал қолданылды.",
                            "Көрсетілген сомалар бұрын бақыланған байланыстарға сілтеме ғана; болашақ ақша көлемі емес."],
            "note": "Бұл — берілген жорамал кезіндегі сценарий. Желі шынымен осылай қайта құрылады деген болжам немесе дәлел емес."}
