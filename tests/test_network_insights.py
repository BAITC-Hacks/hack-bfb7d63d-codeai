from copy import deepcopy

import pandas as pd
import pytest

from moneymap.graph import analyze_dataset
from moneymap.network_insights import analyze_network, compare_removal_strategies
from moneymap.roles import classify_graph
from test_investigation import dataset


def case():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 2, False), (4, 4, False), (5, 0, True)], [
        (1, 2, "2026-07-01", 10), (2, 3, "2026-07-02", 20),
        (3, 2, "2026-07-03", 30), (3, 4, "2026-07-04", 40),
        (2, 2, "2026-07-04", 50),
    ])
    graph = analyze_dataset(frames)
    roles = classify_graph(graph)
    # Prescribed partition makes accounting independent of Louvain heuristics.
    roles.nodes_roles["cluster_id"] = roles.nodes_roles.gid.map({1: 1, 2: 1, 3: 2, 4: 2, 5: 3})
    return frames, graph, roles


def test_directed_cluster_flows_and_cross_cluster_accounting():
    _, graph, roles = case()
    before = roles.nodes_roles.copy(deep=True)
    result = analyze_network(graph, roles)
    assert result.flows.to_dict("records") == [
        {"src_cluster": 2, "dst_cluster": 1, "sum_kzt": 30, "n_tx": 1, "n_edges": 1},
        {"src_cluster": 1, "dst_cluster": 2, "sum_kzt": 20, "n_tx": 1, "n_edges": 1},
    ]
    assert result.summary["internal_turnover_kzt"] == 100  # includes self transfer
    assert result.summary["external_turnover_kzt"] == 50
    assert result.summary["total_turnover_kzt"] == 150
    bridges = result.bridges.set_index("gid")
    assert set(bridges.index) == {"2", "3"}
    assert bridges.loc["2", "external_in_kzt"] == 30
    assert bridges.loc["2", "external_out_kzt"] == 20
    assert bridges.loc["2", "external_neighbors"] == 1
    assert bridges.is_articulation.all()
    pd.testing.assert_frame_equal(before, roles.nodes_roles)


def test_coverage_keeps_isolates_and_never_invents_completeness():
    _, graph, roles = case()
    result = analyze_network(graph, roles)
    nodes = result.coverage.set_index("gid")
    assert len(nodes) == 5
    assert "no_observed_links" in nodes.loc["5", "specific_gaps"]
    assert "outgoing_beyond_boundary_unknown" in nodes.loc["4", "specific_gaps"]
    assert "seed_incoming_incomplete" in nodes.loc["1", "specific_gaps"]
    assert nodes.coverage_status.eq("unknown_full_coverage").all()
    assert result.summary["full_coverage"] == "unknown"
    assert result.requests.set_index("request_id").loc["isolated_clients", "gids"] == "5"
    assert result.requests.set_index("request_id").loc["boundary_outgoing", "affected_nodes"] == 1


def test_large_identifiers_remain_exact_and_empty_flows_have_headers():
    a, b = 2**63 - 2, 2**63 - 1
    graph = analyze_dataset(dataset([(a, 0, True), (b, 0, True)], []))
    result = analyze_network(graph, classify_graph(graph))
    assert set(result.coverage.gid) == {str(a), str(b)}
    assert result.flows.empty and "src_cluster" in result.flows
    assert result.bridges.empty and "gid" in result.bridges
    assert result.summary["total_turnover_kzt"] == 0


def test_strategy_comparison_uses_equal_counts_and_preserves_graph():
    _, graph, roles = case()
    before = deepcopy(graph.graph)
    comparison, meta = compare_removal_strategies(graph, roles, top_n=4)
    assert meta["compared_n"] == 2  # only two seeds, including the isolated seed
    assert comparison.removed_count.tolist() == [0, 2, 2]
    assert comparison.n_nodes.tolist() == [5, 3, 3]
    assert comparison.set_index("scenario").loc["seed_only", "removed_gids"] == "1|5"
    assert set(graph.graph) == set(before)
    assert set(graph.graph.edges) == set(before.edges)


def test_no_seed_comparison_is_explicitly_unavailable():
    graph = analyze_dataset(dataset([(1, 1, False)], []))
    comparison, meta = compare_removal_strategies(graph, classify_graph(graph))
    assert meta["compared_n"] == 0
    assert comparison.scenario.tolist() == ["before"]


@pytest.mark.parametrize("bad", [0, -1, True, 1.5])
def test_strategy_rejects_invalid_size(bad):
    _, graph, roles = case()
    with pytest.raises(ValueError):
        compare_removal_strategies(graph, roles, bad)


def test_mismatched_role_dataset_rejected():
    _, graph, roles = case()
    roles.nodes_roles = roles.nodes_roles.iloc[:-1]
    with pytest.raises(ValueError):
        analyze_network(graph, roles)
