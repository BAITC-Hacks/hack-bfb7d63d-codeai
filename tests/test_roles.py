"""Stage-3 rules, explainability and reproducibility on controlled networks."""

import json
import math

import pandas as pd
import pytest

from moneymap.demo import create_demo_frames
from moneymap.graph import analyze_dataset
from moneymap.roles import CLUSTER_COLUMNS, NODE_ROLE_COLUMNS, ROLE_ORDER, TOP_COLUMNS, classify_graph, load_config


def dataset(nodes, transfers):
    node_table = pd.DataFrame(nodes, columns=["gid", "depth", "is_seed"])
    transactions = pd.DataFrame(transfers, columns=["src", "dst", "sum_kzt"])
    transactions["date"] = pd.to_datetime("2026-07-01")
    if transactions.empty:
        transactions = transactions.astype({"src": "int64", "dst": "int64", "sum_kzt": "float64"})
    edges = transactions.groupby(["src", "dst"], sort=True, as_index=False).agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"))
    edges["depth"] = 1
    return {"nodes": node_table, "edges": edges, "transactions": transactions}


@pytest.fixture
def six_roles():
    # Three source seeds -> central coordinator -> separate observed branches.
    nodes = [(1, 0, True), (2, 0, True), (3, 0, True), (700, 0, True)]
    ordinary = [100, 200, 300, 400, 500, 600, *range(10, 15), *range(510, 521)]
    nodes += [(gid, 4 if gid == 600 else 1, False) for gid in ordinary]
    transfers = [(seed, 100, 1000) for seed in (1, 2, 3)]
    transfers += [(100, 200, 100), (100, 300, 100), (100, 400, 100), (200, 400, 100)]
    transfers += [(payer, 300, 100) for payer in range(10, 15)]
    transfers += [(payer, 600, 100) for payer in range(10, 15)]
    transfers += [(100, 500, 1100)] + [(500, receiver, 100) for receiver in range(510, 521)]
    return dataset(nodes, transfers)


def test_six_role_gates_and_precedence_on_structural_graph(six_roles):
    result = classify_graph(analyze_dataset(six_roles))
    nodes = result.details.set_index("gid")
    assert nodes.loc[100, "role"] == "coordinator"
    assert nodes.loc[500, "role"] == "distributor"
    assert nodes.loc[300, "role"] == "consolidator"
    assert nodes.loc[200, "role"] == "transit"
    assert nodes.loc[400, "role"] == "terminal"
    assert nodes.loc[700, "role"] == "peripheral"
    assert nodes.loc[500, "matched_roles"] == "distributor|transit"
    assert nodes.loc[300, "matched_roles"] == "consolidator|terminal"
    assert nodes.loc[600, "role"] == "peripheral"
    assert nodes.loc[600, "matched_roles"] == "peripheral"
    assert nodes.loc[600, "priority_consolidation"] == 0
    assert nodes.loc[600, "priority_score"] > 0  # boundary is not innocence
    assert nodes.loc[700, "priority_score"] == 0
    assert f"{nodes.loc[100, 'betweenness']:.6f}" in nodes.loc[100, "evidence"]


def test_seed_ratio_is_never_a_role_gate_and_seed_score_is_capped():
    nodes = [(1, 0, True)] + [(gid, 1, False) for gid in range(2, 23)]
    transfers = [(gid, 1, 100) for gid in range(2, 12)] + [(1, gid, 100) for gid in range(12, 23)]
    result = classify_graph(analyze_dataset(dataset(nodes, transfers)))
    row = result.details.set_index("gid").loc[1]
    assert row["role"] == "distributor"
    assert row["observed_flow_ratio"] == 1.1
    assert row["matched_roles"] == "distributor"
    assert row["role_score"] <= 0.7
    assert row["priority_consolidation"] == 0
    assert "Seed кірісі толық емес" in row["evidence"]


def test_no_positive_centrality_never_qualifies_as_coordinator():
    # Complete directed graph: every shortest path is a direct edge.
    nodes = [(gid, 0 if gid <= 2 else 1, gid <= 2) for gid in range(1, 5)]
    result = classify_graph(analyze_dataset(dataset(nodes, [(src, dst, 100) for src in range(1, 5) for dst in range(1, 5) if src != dst])))
    assert result.details["betweenness"].eq(0).all()
    assert result.summary["thresholds"]["coordinator_betweenness_cutoff"] is None
    assert not result.details["role"].eq("coordinator").any()


@pytest.mark.parametrize("external_senders,expected_role", [(4, "terminal"), (5, "consolidator")])
def test_self_transfer_does_not_reach_consolidator_sender_threshold(external_senders, expected_role):
    nodes = [(gid, 0, True) for gid in range(1, external_senders + 1)] + [(100, 1, False)]
    transfers = [(gid, 100, 10_000) for gid in range(1, external_senders + 1)] + [(100, 100, 5_000)]
    row = classify_graph(analyze_dataset(dataset(nodes, transfers))).details.set_index("gid").loc[100]
    assert row["in_deg"] == external_senders
    assert row["out_deg"] == 0
    assert row["role"] == expected_role
    assert row["out_kzt"] == 5_000  # Self transfer remains observed money.
    if expected_role == "terminal":
        assert row["matched_roles"] == "terminal"
        assert "Өзге клиентке шығыс байқалмады" in row["evidence"]


@pytest.mark.parametrize("external_receivers,expected_role", [(9, "peripheral"), (10, "distributor")])
def test_self_transfer_does_not_reach_distributor_recipient_threshold(external_receivers, expected_role):
    nodes = [(1, 0, True)] + [(gid, 1, False) for gid in range(2, external_receivers + 2)]
    transfers = [(1, gid, 10_000) for gid in range(2, external_receivers + 2)] + [(1, 1, 5_000)]
    row = classify_graph(analyze_dataset(dataset(nodes, transfers))).details.set_index("gid").loc[1]
    assert row["out_deg"] == external_receivers
    assert row["in_deg"] == 0
    assert row["role"] == expected_role
    assert row["in_kzt"] == 5_000


def test_independent_priority_components_sum_and_hand_calculation(six_roles):
    analysis = analyze_dataset(six_roles)
    result = classify_graph(analysis)
    nodes = result.details.set_index("gid")
    weighted = [f"priority_{name}" for name in result.config["priority"]["weights"]]
    for row in result.details.to_dict("records"):
        assert row["priority_score"] == pytest.approx(sum(row[column] for column in weighted))
    assert nodes.loc[300, "consolidation_signal"] == 1
    assert nodes.loc[300, "priority_consolidation"] == 0.25
    expected = min(math.log1p(nodes.loc[300, "in_kzt"]) / math.log1p(result.summary["normalizers"]["in_kzt"]), 1) * 0.15
    assert nodes.loc[300, "priority_in_kzt"] == pytest.approx(expected)
    assert nodes.loc[700, weighted].eq(0).all()
    # Changing only role gates/caps cannot affect independently scored priority.
    other = classify_graph(analysis, {"rules": {"distributor_min_out_deg": 50}, "scores": {"general_cap": 0.6}})
    pd.testing.assert_series_equal(result.details["priority_score"], other.details["priority_score"])
    assert other.details.set_index("gid").loc[500, "role"] == "transit"


def test_cluster_membership_and_original_directed_internal_amounts(six_roles):
    analysis = analyze_dataset(six_roles)
    result = classify_graph(analysis)
    membership = result.details.set_index("gid")["cluster_id"].to_dict()
    assert result.clusters["n_nodes"].sum() == len(analysis.nodes)
    assert result.clusters["n_seed"].sum() == int(analysis.nodes["is_seed"].sum())
    for row in result.clusters.itertuples(index=False):
        amounts = [data["sum_kzt"] for src, dst, data in analysis.graph.edges(data=True) if membership[src] == membership[dst] == row.cluster_id]
        assert row.sum_kzt_internal == pytest.approx(math.fsum(amounts))
        top_gids = json.loads(row.top_gids)
        assert 1 <= len(top_gids) <= 5
        assert all(isinstance(gid, str) and membership[int(gid)] == row.cluster_id for gid in top_gids)
    assert result.summary["internal_turnover_kzt"] <= analysis.summary["turnover_kzt"]
    for gid in analysis.graph:
        neighbors = set(analysis.graph.predecessors(gid)) | set(analysis.graph.successors(gid))
        expected = len({membership[neighbor] for neighbor in neighbors} - {membership[gid]})
        assert result.details.set_index("gid").loc[gid, "neighbor_cluster_count"] == expected


def test_reciprocal_projection_and_self_loop_accounting():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 1, False), (4, 0, True)], [(1, 2, 10), (2, 1, 20), (2, 2, 7), (3, 3, 11)])
    analysis = analyze_dataset(frames)
    result = classify_graph(analysis)
    nodes = result.details.set_index("gid")
    assert nodes.loc[1, "cluster_id"] == nodes.loc[2, "cluster_id"]
    assert nodes.loc[3, "cluster_id"] != nodes.loc[4, "cluster_id"]
    assert nodes.loc[3, "self_loop_only"]
    assert not nodes.loc[3, "is_isolated"]
    assert nodes.loc[3, "in_deg"] == nodes.loc[3, "out_deg"] == 0
    assert nodes.loc[3, "role"] == "peripheral"
    assert nodes.loc[3, "role_score"] == 0.2
    assert nodes.loc[3, "matched_roles"] == "peripheral"
    assert not nodes.loc[2, "self_loop_only"]
    assert "өзге клиентпен байланыс жоқ" in nodes.loc[3, "evidence"]
    assert result.summary["n_self_loop_only"] == 1
    # Clustering omits self loops, internal exports still retain them.
    assert sorted(result.clusters["sum_kzt_internal"].tolist()) == [0, 11, 37]
    assert analysis.graph.has_edge(2, 2)
    self_loop_cluster = result.clusters.set_index("cluster_id").loc[nodes.loc[3, "cluster_id"]]
    assert "өзіне аударым" in self_loop_cluster["hypothesis"]
    assert "Байланыс байқалмаған" not in self_loop_cluster["hypothesis"]


def test_zero_custom_weight_signals_do_not_falsely_imply_no_links():
    frames = dataset([(1, 0, True), (2, 1, False)], [(1, 2, 100)])
    weights = {key: 0 for key in load_config()["priority"]["weights"]}
    weights["betweenness"] = 1
    result = classify_graph(analyze_dataset(frames), {"priority": {"weights": weights}})
    assert result.top_nodes["priority_score"].eq(0).all()
    assert result.top_nodes["why"].str.contains("Салмақталған белгілер=0", regex=False).all()
    assert not result.top_nodes["why"].str.contains("Байланыс жоқ", regex=False).any()


def test_no_edges_all_nodes_preserved_and_priority_zero():
    frames = dataset([(gid, 0, True) for gid in range(1, 5)], [])
    result = classify_graph(analyze_dataset(frames))
    assert result.summary["n_clusters"] == 4
    assert result.summary["modularity"] is None
    assert result.nodes_roles["role"].eq("peripheral").all()
    assert result.nodes_roles["priority_score"].eq(0).all()
    assert result.clusters["sum_kzt_internal"].eq(0).all()
    assert result.top_nodes["gid"].tolist() == [1, 2, 3, 4]


def test_shuffled_inputs_and_long_identifiers_are_reproducible(six_roles):
    # All IDs exceed JavaScript's exact integer range; odd digits must survive.
    for column in ("gid",):
        six_roles["nodes"][column] += 100_000_000_000_000_001
    for name in ("edges", "transactions"):
        for column in ("src", "dst"):
            six_roles[name][column] += 100_000_000_000_000_001
    first = classify_graph(analyze_dataset(six_roles))
    shuffled = {name: frame.sample(frac=1, random_state=13).reset_index(drop=True) for name, frame in six_roles.items()}
    second = classify_graph(analyze_dataset(shuffled))
    for key in ("nodes_roles", "clusters", "top_nodes", "details"):
        pd.testing.assert_frame_equal(getattr(first, key), getattr(second, key))
    assert first.summary == second.summary
    assert str(first.nodes_roles["gid"].dtype) == "int64"
    assert str(first.top_nodes["gid"].dtype) == "int64"
    assert set(first.nodes_roles["gid"]) == set(six_roles["nodes"]["gid"])
    assert any("100000000000000101" in value for value in first.clusters["top_gids"])


def test_exports_contract_bounds_evidence_and_rank_order(six_roles):
    analysis = analyze_dataset(six_roles)
    original = analysis.nodes.copy(deep=True)
    result = classify_graph(analysis, top_n=20)
    assert list(result.nodes_roles) == NODE_ROLE_COLUMNS
    assert list(result.clusters) == CLUSTER_COLUMNS
    assert list(result.top_nodes) == TOP_COLUMNS
    assert len(result.top_nodes) == 20
    assert result.top_nodes["rank"].tolist() == list(range(1, 21))
    assert set(result.nodes_roles["role"]).issubset(ROLE_ORDER)
    assert result.nodes_roles["role_score"].between(0, 0.9).all()
    assert result.nodes_roles["priority_score"].between(0, 1).all()
    assert result.nodes_roles["evidence"].str.len().between(1, 200).all()
    assert result.nodes_roles["evidence"].str.contains(r"\d").all()
    assert result.details.loc[result.details["depth"].eq(4), "role_score"].le(0.25).all()
    assert result.details.loc[result.details["is_seed"], "role_score"].le(0.7).all()
    assert result.details.loc[result.details["role"].eq("terminal"), "role_score"].le(0.55).all()
    assert result.nodes_roles["gid"].is_unique and result.summary["full_coverage"]
    assert sum(result.summary["role_counts"].values()) == len(analysis.nodes)
    expected = result.details.sort_values(["priority_score", "in_kzt", "gid"], ascending=[False, False, True]).head(20)["gid"].tolist()
    assert result.top_nodes["gid"].tolist() == expected
    pd.testing.assert_frame_equal(original, analysis.nodes)
    json.dumps(result.summary, allow_nan=False)
    json.dumps(result.config, allow_nan=False)


@pytest.mark.parametrize("bad", [
    {"unknown": 1}, {"rules": {"bogus": 1}}, {"clustering": {"seed": -1}},
    {"clustering": {"seed": 42.5}}, {"clustering": {"resolution": 0}},
    {"rules": {"distributor_min_out_deg": True}}, {"rules": {"consolidator_min_in_deg": 0}},
    {"rules": {"coordinator_betweenness_quantile": 1.1}},
    {"rules": {"transit_min_ratio": 1.1}}, {"rules": {"transit_max_ratio": 0.9}},
    {"priority": {"weights": {"pagerank": 0.9}}},
    {"priority": {"normalizer_quantile": 0}}, {"scores": {"seed_cap": 0.8}},
    {"scores": {"terminal_cap": float("nan")}}, {"clustering": {"resolution": float("inf")}},
    {"rules": []}, {"version": 2},
])
def test_bad_configuration_rejected(bad, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_configuration_defaults_can_be_overridden_without_shared_mutation(tmp_path):
    config = load_config()
    path = tmp_path / "overrides.json"
    path.write_text('{"clustering": {"resolution": 1.5}}', encoding="utf-8")
    override = load_config(path)
    assert override["clustering"]["resolution"] == 1.5
    assert override["clustering"]["seed"] == 42
    override["rules"]["distributor_min_out_deg"] = 15
    assert config == load_config()
    assert config["rules"]["distributor_min_out_deg"] == 10


@pytest.mark.parametrize("top_n", [0, 19, True, 20.5, "30"])
def test_top_minimum_validation(top_n):
    with pytest.raises(ValueError, match="top_n"):
        classify_graph(analyze_dataset(create_demo_frames()), top_n=top_n)


def test_small_demo_keeps_every_client_in_top_list():
    result = classify_graph(analyze_dataset(create_demo_frames()), top_n=30)
    assert len(result.top_nodes) == len(result.nodes_roles) == 16
