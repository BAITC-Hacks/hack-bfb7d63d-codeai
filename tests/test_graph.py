"""Observed-graph contracts with hand-checkable synthetic networks."""

import math

import networkx as nx
import pandas as pd
import pytest

from moneymap.graph import analyze_dataset, observed_seed_paths


def dataset(nodes, transfers):
    node_table = pd.DataFrame(nodes, columns=["gid", "depth", "is_seed"])
    transactions = pd.DataFrame(transfers, columns=["src", "dst", "date", "sum_kzt"])
    transactions["date"] = pd.to_datetime(transactions["date"])
    edges = transactions.groupby(["src", "dst"], sort=True, as_index=False).agg(
        sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size")
    )
    # Discovery depth is an edge property, independent of node depth.
    edges["depth"] = 1
    return {"nodes": node_table, "edges": edges, "transactions": transactions}


@pytest.fixture
def network():
    return dataset(
        [(1, 0, True), (2, 0, True), (3, 1, False), (4, 2, False),
         (5, 4, False), (6, 0, True), (7, 1, False), (8, 2, False)],
        [(1, 3, "2026-07-01", 10_000), (1, 3, "2026-07-02", 20_000),
         (2, 3, "2026-07-01", 30_000), (3, 4, "2026-07-03", 40_000),
         (4, 5, "2026-07-05", 30_000), (3, 1, "2026-07-04", 5_000),
         (4, 3, "2026-07-06", 5_000), (7, 8, "2026-07-07", 10_000)],
    )


def test_all_nodes_edges_and_money_conservation(network):
    original = {name: table.copy(deep=True) for name, table in network.items()}
    result = analyze_dataset(network)
    nodes = result.nodes.set_index("gid")
    assert list(result.graph) == list(range(1, 9))
    assert result.graph.number_of_edges() == 7
    assert nodes.loc[6, "is_isolated"]
    assert nodes.loc[6, "in_deg"] == nodes.loc[6, "out_deg"] == 0
    assert nodes.loc[3, "in_deg"] == 3
    assert nodes.loc[3, "out_deg"] == 2
    assert nodes.loc[3, "in_tx"] == 4
    assert nodes.loc[3, "in_kzt"] == 65_000
    assert nodes.loc[3, "out_kzt"] == 45_000
    assert nodes["in_kzt"].sum() == nodes["out_kzt"].sum() == 150_000
    assert nodes["in_tx"].sum() == nodes["out_tx"].sum() == 8
    assert result.daily["sum_kzt"].sum() == result.summary["turnover_kzt"] == 150_000
    assert result.daily["n_tx"].sum() == 8
    assert result.graph.edges[1, 3] == {"sum_kzt": 30_000.0, "amount": 30_000.0, "n_tx": 2, "discovery_depth": 1}
    assert math.isclose(nodes["pagerank"].sum(), 1, abs_tol=1e-10)
    assert nodes["pagerank"].ge(0).all()
    for name in network:
        pd.testing.assert_frame_equal(original[name], network[name])


def test_components_are_weak_connectivity_not_communities(network):
    result = analyze_dataset(network)
    assert result.summary["n_components"] == 3
    assert result.summary["components_with_edges"] == 2
    assert result.summary["largest_component_nodes"] == 5
    assert result.components["n_nodes"].tolist() == [5, 2, 1]
    assert result.components["n_edges"].tolist() == [6, 1, 0]
    assert result.components["n_seed"].tolist() == [2, 0, 1]
    assert result.components["sum_kzt_internal"].sum() == 150_000
    assert result.nodes.set_index("gid").loc[6, "component_id"] == 3
    assert result.components.iloc[2]["is_isolated"]


def test_reachable_seed_counts_exclude_self_even_through_cycles(network):
    result = analyze_dataset(network)
    nodes = result.nodes.set_index("gid")
    assert nodes.loc[[3, 4, 5], "reachable_seed_count"].tolist() == [2, 2, 2]
    assert nodes.loc[1, "reachable_seed_count"] == 1  # seed 2 reaches seed 1
    assert nodes.loc[2, "reachable_seed_count"] == 0
    assert nodes.loc[6, "reachable_seed_count"] == 0
    assert nodes.loc[[1, 2, 6], "min_seed_hops"].tolist() == [0, 0, 0]
    assert nodes.loc[5, "min_seed_hops"] == 3
    assert pd.isna(nodes.loc[7, "min_seed_hops"])
    assert pd.isna(nodes.loc[8, "min_seed_hops"])
    assert observed_seed_paths(result, 5) == [[1, 3, 4, 5], [2, 3, 4, 5]]
    assert observed_seed_paths(result, 5, limit=1) == [[1, 3, 4, 5]]
    assert observed_seed_paths(result, 1) == [[2, 3, 1]]
    assert observed_seed_paths(result, 6) == []
    assert observed_seed_paths(result, 8) == []
    assert observed_seed_paths(result, 5, limit=0) == []
    with pytest.raises(KeyError):
        observed_seed_paths(result, 999)
    with pytest.raises(ValueError):
        observed_seed_paths(result, 5, limit=-1)


def test_ratios_flag_incomplete_observation_without_inventing_balance(network):
    nodes = analyze_dataset(network).nodes.set_index("gid")
    assert nodes.loc[1, "observed_flow_ratio"] == 6
    assert not nodes.loc[1, "ratio_usable"]  # seed's visible incoming is incomplete
    assert nodes.loc[3, "ratio_usable"]
    assert nodes.loc[3, "observed_flow_ratio"] == pytest.approx(45_000 / 65_000)
    assert nodes.loc[5, "truncated_by_depth"]
    assert nodes.loc[5, "observed_flow_ratio"] == 0
    assert not nodes.loc[5, "ratio_usable"]
    assert pd.isna(nodes.loc[6, "observed_flow_ratio"])
    assert not nodes.loc[6, "ratio_usable"]
    assert "role" not in nodes and "priority_score" not in nodes


def test_exact_directed_betweenness_uses_hops_not_amount():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 2, False)], [
        (1, 2, "2026-07-01", 10_000), (2, 3, "2026-07-02", 999_000),
    ])
    result = analyze_dataset(frames)
    nodes = result.nodes.set_index("gid")
    # Directed normalization is 1 / ((n-1)(n-2)) = 1/2 for one ordered pair.
    assert nodes.loc[2, "betweenness"] == 0.5
    assert nodes.loc[[1, 3], "betweenness"].tolist() == [0, 0]
    assert nodes.loc[3, "pagerank"] > nodes.loc[2, "pagerank"] > nodes.loc[1, "pagerank"]


def test_pagerank_weights_transfers_by_observed_amount():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 1, False)], [
        (1, 2, "2026-07-01", 10_000), (1, 3, "2026-07-01", 90_000),
        (2, 1, "2026-07-02", 50_000), (3, 1, "2026-07-02", 50_000),
    ])
    nodes = analyze_dataset(frames).nodes.set_index("gid")
    assert nodes.loc[3, "pagerank"] > nodes.loc[2, "pagerank"]
    # Both endpoints have the same connectivity; only monetary weights differ.
    assert nodes.loc[3, "betweenness"] == nodes.loc[2, "betweenness"]


def test_temporal_pattern_has_strict_direction_censoring_and_duplicate_denominator():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 2, False)], [
        (1, 2, "2026-07-01 01:00", 10_000),
        (1, 2, "2026-07-01 01:00", 10_000),  # preserved as a second transaction
        (2, 3, "2026-07-01 23:00", 5_000),   # same day is not matched
        (1, 2, "2026-07-02 12:00", 10_000),
        (2, 3, "2026-07-03 12:00", 15_000),
        (1, 2, "2026-07-04 12:00", 10_000),  # next exit is 3 days later
        (1, 2, "2026-07-07 12:00", 10_000),  # eligible, no later exit
        (2, 3, "2026-07-07 13:00", 5_000),
        (1, 2, "2026-07-08 12:00", 10_000),  # eligible at the cutoff, no later exit
        (1, 2, "2026-07-10 12:00", 10_000),  # last day, censored
    ])
    nodes = analyze_dataset(frames).nodes.set_index("gid")
    assert nodes.loc[2, "in_tx"] == 7
    assert nodes.loc[2, "temporal_eligible_in_tx"] == 6  # cutoff July 8 inclusive
    assert nodes.loc[2, "next_out_1_2d_share"] == pytest.approx(3 / 6)
    assert nodes.loc[2, "mean_next_out_days"] == 2  # conditional lags [2,2,1,3]
    assert nodes.loc[2, "active_days"] == 7
    assert nodes.loc[2, "in_active_days"] == 6
    assert nodes.loc[2, "out_active_days"] == 3
    assert nodes.loc[2, "first_date"] == pd.Timestamp("2026-07-01")
    assert nodes.loc[2, "last_date"] == pd.Timestamp("2026-07-10")
    assert pd.isna(nodes.loc[1, "next_out_1_2d_share"])
    assert nodes.loc[3, "next_out_1_2d_share"] == 0
    assert pd.isna(nodes.loc[3, "mean_next_out_days"])


def test_same_day_exit_is_not_a_temporal_success_and_last_two_days_excluded():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 2, False)], [
        (1, 2, "2026-07-01", 10_000), (2, 3, "2026-07-01", 10_000),
        (1, 2, "2026-07-03", 10_000), (1, 3, "2026-07-04", 10_000),
    ])
    nodes = analyze_dataset(frames).nodes.set_index("gid")
    assert nodes.loc[2, "temporal_eligible_in_tx"] == 1
    assert nodes.loc[2, "next_out_1_2d_share"] == 0
    assert pd.isna(nodes.loc[2, "mean_next_out_days"])


def test_temporal_contradiction_requires_strict_calendar_day_order_and_both_directions():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 1, False), (4, 1, False), (5, 2, False), (6, 0, True)], [
        (2, 5, "2026-07-01 23:00", 100), (1, 2, "2026-07-03 01:00", 100),
        (3, 5, "2026-07-02 01:00", 100), (1, 3, "2026-07-02 23:00", 100),
        (1, 4, "2026-07-01 01:00", 100), (4, 5, "2026-07-08 01:00", 100),
    ])
    result = analyze_dataset(frames)
    nodes = result.nodes.set_index("gid")
    assert nodes.loc[2, "temporal_contradiction"]
    assert nodes.loc[2, "temporal_order_status"] == "all_out_before_in"
    assert nodes.loc[2, "first_in_date"] == pd.Timestamp("2026-07-03")
    assert nodes.loc[2, "last_out_date"] == pd.Timestamp("2026-07-01")
    assert nodes.loc[3, "temporal_order_status"] == "same_day_order_unknown"
    assert not nodes.loc[3, "temporal_contradiction"]  # ignore within-day timestamps
    assert nodes.loc[4, "temporal_order_status"] == "later_out_observed"
    assert nodes.loc[[1, 5, 6], "temporal_order_status"].eq("insufficient_data").all()
    assert not nodes.loc[[1, 5, 6], "temporal_contradiction"].any()
    assert pd.isna(nodes.loc[6, "first_in_date"])
    assert result.summary["n_temporal_contradictions"] == 1


def test_daily_table_counts_operations_not_edges_and_includes_inactive_dates():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 1, False)], [
        (1, 2, "2026-07-01", 5_000), (1, 2, "2026-07-01", 5_000),
        (1, 3, "2026-07-03", 10_000),
    ])
    daily = analyze_dataset(frames).daily
    assert len(daily) == 3
    assert daily["n_tx"].tolist() == [2, 0, 1]
    assert daily["n_senders"].tolist() == [1, 0, 1]
    assert daily["n_receivers"].tolist() == [1, 0, 1]
    assert daily["sum_kzt"].tolist() == [10_000, 0, 10_000]


def test_reordering_inputs_does_not_change_results_or_paths(network):
    result = analyze_dataset(network)
    shuffled = analyze_dataset({name: frame.sample(frac=1, random_state=53).reset_index(drop=True) for name, frame in network.items()})
    pd.testing.assert_frame_equal(result.nodes, shuffled.nodes)
    pd.testing.assert_frame_equal(result.components, shuffled.components)
    pd.testing.assert_frame_equal(result.daily, shuffled.daily)
    assert result.summary == shuffled.summary
    assert list(result.graph.edges(data=True)) == list(shuffled.graph.edges(data=True))
    assert observed_seed_paths(result, 5) == observed_seed_paths(shuffled, 5)


def test_large_identifiers_are_never_rounded(network):
    mapping = {gid: 2**63 - 10 + gid for gid in network["nodes"]["gid"]}
    network["nodes"]["gid"] = network["nodes"]["gid"].map(mapping)
    for name in ("edges", "transactions"):
        for column in ("src", "dst"):
            network[name][column] = network[name][column].map(mapping)
    result = analyze_dataset(network)
    assert str(result.nodes["gid"].dtype) == "int64"
    assert set(result.graph) == set(mapping.values())
    assert len(result.graph) == 8
    assert nx.has_path(result.graph, mapping[1], mapping[5])
    assert observed_seed_paths(result, str(mapping[5])) == [
        [mapping[1], mapping[3], mapping[4], mapping[5]],
        [mapping[2], mapping[3], mapping[4], mapping[5]],
    ]


def test_invalid_input_is_rejected_before_analysis(network):
    network["edges"].loc[0, "n_tx"] += 1
    with pytest.raises(ValueError, match="count_mismatch"):
        analyze_dataset(network)


def test_empty_transfer_tables_preserve_all_nodes_and_nullable_observations():
    frames = dataset([(8, 0, True), (9, 1, False)], [])
    result = analyze_dataset(frames)
    assert result.summary["n_components"] == 2
    assert result.summary["components_with_edges"] == 0
    assert result.summary["turnover_kzt"] == 0
    assert result.summary["temporal_cutoff_date"] is None
    assert result.nodes["is_isolated"].all()
    assert result.nodes["pagerank"].tolist() == [0.5, 0.5]
    assert result.nodes["betweenness"].eq(0).all()
    assert result.nodes["next_out_1_2d_share"].isna().all()
    assert result.nodes["observed_flow_ratio"].isna().all()
    assert result.daily.empty
    assert observed_seed_paths(result, 9) == []
