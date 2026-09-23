"""Display selections must preserve source edges, IDs and global evidence."""

from copy import deepcopy
import json

import networkx as nx
import pandas as pd
import pytest

from moneymap.graph import analyze_dataset
from moneymap.graph_view import build_graph_view, client_neighbors, client_transactions, cluster_color
from moneymap.roles import classify_graph


def dataset(offset=0):
    nodes = pd.DataFrame([
        (gid + offset, 0 if gid in (1, 2, 6) else 4 if gid == 5 else 1, gid in (1, 2, 6))
        for gid in range(1, 9)
    ], columns=["gid", "depth", "is_seed"])
    tx = pd.DataFrame([
        (1, 3, 100), (1, 3, 100), (2, 3, 200), (3, 4, 300),
        (4, 5, 400), (3, 1, 50), (4, 3, 60), (8, 2, 70), (7, 7, 80),
    ], columns=["src", "dst", "sum_kzt"])
    tx[["src", "dst"]] += offset
    tx["date"] = pd.to_datetime("2026-07-01")
    edges = tx.groupby(["src", "dst"], sort=True, as_index=False).agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"))
    edges["depth"] = 1
    return {"nodes": nodes, "edges": edges, "transactions": tx}


@pytest.fixture
def network():
    frames = dataset()
    analysis = analyze_dataset(frames)
    return frames, analysis, classify_graph(analysis)


def ids(view):
    return {int(node["id"]) for node in view["nodes"]}


@pytest.mark.parametrize(("direction", "hops", "expected"), [
    ("incoming", 1, {1, 2, 3, 4}), ("outgoing", 1, {1, 3, 4}),
    ("both", 1, {1, 2, 3, 4}), ("incoming", 2, {1, 2, 3, 4, 8}),
    ("outgoing", 2, {1, 3, 4, 5}), ("both", 2, {1, 2, 3, 4, 5, 8}),
])
def test_direction_and_hops_follow_original_graph_before_filters(network, direction, hops, expected):
    _, analysis, roles = network
    view = build_graph_view(analysis, roles, focus_gid=3, direction=direction, hops=hops)
    assert ids(view) == expected
    expected_edges = {(str(src), str(dst)) for src, dst in analysis.graph.edges if src in expected and dst in expected}
    assert {(edge["from"], edge["to"]) for edge in view["edges"]} == expected_edges


def test_filters_retain_focus_and_expose_scope_and_exclusion_counts(network):
    _, analysis, roles = network
    view = build_graph_view(analysis, roles, focus_gid=3, role_filter=[], hops=2)
    assert ids(view) == {3}
    summary = view["summary"]
    assert summary["focus_outside_filter"] is True
    assert summary["eligible_nodes"] == 6
    assert summary["excluded_nodes"] == 5
    assert summary["outside_scope_nodes"] == 2
    assert summary["visible_edges"] == 0
    assert summary["eligible_edges"] == summary["excluded_edges"] == 7
    assert view["nodes"][0]["outside_filter"] is True
    assert summary["total_edges"] == 8


def test_full_view_and_edge_amount_filter_preserve_isolates_and_all_nodes(network):
    _, analysis, roles = network
    view = build_graph_view(analysis, roles, mode="full", focus_gid=3)
    assert ids(view) == set(range(1, 9))
    assert len(view["edges"]) == 8
    assert view["summary"]["outside_scope_nodes"] == 0
    filtered = build_graph_view(analysis, roles, mode="full", min_amount=1000)
    assert ids(filtered) == ids(view)
    assert filtered["edges"] == []
    assert filtered["summary"]["excluded_nodes"] == 0
    assert filtered["summary"]["excluded_edges"] == 8
    isolate = build_graph_view(analysis, roles, focus_gid=6)
    assert ids(isolate) == {6}
    assert isolate["edges"] == []
    assert isolate["nodes"][0]["shape"] == "diamond"


def test_cluster_selection_retains_focus_outside_cluster_and_does_not_invent_links(network):
    _, analysis, roles = network
    cluster = int(roles.nodes_roles.set_index("gid").loc[6, "cluster_id"])
    view = build_graph_view(analysis, roles, mode="cluster", cluster_filter=cluster, focus_gid=3)
    assert ids(view) == {3, 6}
    assert view["edges"] == []
    assert view["summary"]["focus_outside_filter"] is True
    assert view["summary"]["eligible_nodes"] == 2
    filtered = build_graph_view(analysis, roles, mode="full", role_filter="peripheral", cluster_filter=[cluster], focus_gid=6)
    assert ids(filtered) == {6}
    assert filtered["summary"]["focus_outside_filter"] is False


def test_global_metrics_role_tables_and_input_frames_are_never_mutated(network):
    frames, analysis, roles = network
    originals = {name: frame.copy(deep=True) for name, frame in frames.items()}
    old_analysis, old_roles = deepcopy(analysis), deepcopy(roles)
    full = build_graph_view(analysis, roles, mode="full", focus_gid=3)
    filtered = build_graph_view(analysis, roles, focus_gid=3, role_filter=[], min_amount=1e6)
    before = next(node for node in full["nodes"] if node["id"] == "3")
    after = filtered["nodes"][0]
    for field in ("role", "priority_score", "in_kzt", "out_kzt", "in_deg", "out_deg", "cluster_id", "evidence", "size"):
        assert before[field] == after[field]
    client_neighbors(analysis, roles, 3)
    client_transactions(frames, 3)
    assert nx.utils.graphs_equal(analysis.graph, old_analysis.graph)
    pd.testing.assert_frame_equal(analysis.nodes, old_analysis.nodes)
    pd.testing.assert_frame_equal(roles.nodes_roles, old_roles.nodes_roles)
    pd.testing.assert_frame_equal(roles.details, old_roles.details)
    for name in frames:
        pd.testing.assert_frame_equal(frames[name], originals[name])


def test_tables_keep_all_transactions_duplicates_bidirectional_neighbors_and_self_loop(network):
    frames, analysis, roles = network
    transactions = client_transactions(frames, "3")
    assert len(transactions) == 6
    assert transactions.duplicated().sum() == 1
    assert transactions["direction_label"].value_counts().to_dict() == {"Кіріс": 4, "Шығыс": 2}
    neighbors = client_neighbors(analysis, roles, 3)
    assert len(neighbors) == 5
    assert list(neighbors.loc[neighbors["counterparty_gid"].eq(1), "direction_label"]) == ["Кіріс", "Шығыс"]
    assert neighbors["n_tx"].sum() == 6
    assert neighbors.loc[neighbors["src"].eq(1), "n_tx"].item() == 2
    own_tx = client_transactions(frames, 7)
    own_neighbors = client_neighbors(analysis, roles, 7)
    assert len(own_tx) == len(own_neighbors) == 1
    assert own_tx["direction_label"].item() == own_neighbors["direction_label"].item() == "Өзіне"
    assert client_neighbors(analysis, roles, 6).empty
    assert client_transactions(frames, 6).empty
    view = build_graph_view(analysis, roles, focus_gid=7)
    assert len(view["edges"]) == 1
    assert view["edges"][0]["from"] == view["edges"][0]["to"] == "7"


def test_large_int64_ids_are_exact_in_payload_and_tables():
    offset = 234_567_890_123_456_700
    frames = dataset(offset)
    analysis = analyze_dataset(frames)
    roles = classify_graph(analysis)
    view = build_graph_view(analysis, roles, mode="full", focus_gid=str(offset + 3))
    assert view["selected_gid"] == str(offset + 3)
    assert {node["id"] for node in view["nodes"]} == {str(offset + gid) for gid in range(1, 9)}
    assert all(isinstance(node["id"], str) for node in view["nodes"])
    assert all(isinstance(edge["from"], str) and isinstance(edge["to"], str) for edge in view["edges"])
    assert json.loads(json.dumps(view, ensure_ascii=False, allow_nan=False)) == view
    neighbors = client_neighbors(analysis, roles, str(offset + 3))
    assert str(neighbors["src"].dtype) == str(neighbors["counterparty_gid"].dtype) == "int64"
    assert neighbors["src"].min() == offset + 1
    transactions = client_transactions(frames, str(offset + 3))
    assert transactions["src"].min() == offset + 1
    with pytest.raises(ValueError, match="int64"):
        build_graph_view(analysis, roles, focus_gid=float(offset + 3))


def test_default_focus_and_output_order_are_deterministic(network):
    _, analysis, roles = network
    view = build_graph_view(analysis, roles)
    assert view["selected_gid"] == str(int(roles.top_nodes.iloc[0]["gid"]))
    shuffled = deepcopy(roles)
    shuffled.nodes_roles = shuffled.nodes_roles.sample(frac=1, random_state=7)
    assert build_graph_view(analysis, shuffled) == view
    assert ids(view) == set(sorted(ids(view)))
    assert [int(node["id"]) for node in view["nodes"]] == sorted(ids(view))


@pytest.mark.parametrize("kwargs", [
    {"focus_gid": 999}, {"focus_gid": True}, {"focus_gid": "1.1"},
    {"hops": 0}, {"hops": 3}, {"hops": True}, {"hops": 1.0},
    {"mode": "invalid"}, {"mode": "cluster"}, {"mode": "cluster", "cluster_filter": []},
    {"direction": "back"}, {"role_filter": "unknown"}, {"role_filter": 1},
    {"cluster_filter": 999}, {"cluster_filter": 1.5},
    {"min_amount": -1}, {"min_amount": float("nan")}, {"min_amount": float("inf")},
    {"min_amount": True}, {"color_by": "risk"},
])
def test_invalid_arguments_fail_explicitly(network, kwargs):
    _, analysis, roles = network
    with pytest.raises(ValueError):
        build_graph_view(analysis, roles, **kwargs)


def test_unknown_client_table_requests_fail_explicitly(network):
    frames, analysis, roles = network
    with pytest.raises(ValueError, match="табылмады"):
        client_transactions(frames, 999)
    with pytest.raises(ValueError, match="табылмады"):
        client_neighbors(analysis, roles, 999)


def test_color_modes_include_legends_and_keep_labels_and_boundary_flags(network):
    _, analysis, roles = network
    for mode, legend_key in (("role", "roles"), ("cluster", "clusters"), ("depth", "depths")):
        view = build_graph_view(analysis, roles, mode="full", color_by=mode)
        colors = {item["key"]: item["color"] for item in view["legend"][legend_key]}
        field = {"role": "role", "cluster": "cluster_id", "depth": "depth"}[mode]
        for node in view["nodes"]:
            assert node["color"] == colors[node[field]]
            assert node["role_label"]
        assert next(node for node in view["nodes"] if node["id"] == "5")["boundary"] is True


def test_cluster_colors_do_not_cycle_and_stay_stable_when_filters_change(network):
    # The actual supplied case contains 91 communities, beyond a small palette.
    assert len({cluster_color(cluster) for cluster in range(1, 92)}) == 91
    _, analysis, roles = network
    full = build_graph_view(analysis, roles, mode="full", color_by="cluster", focus_gid=3)
    filtered = build_graph_view(analysis, roles, color_by="cluster", focus_gid=3, role_filter=[])
    full_focus = next(node for node in full["nodes"] if node["id"] == "3")
    assert full_focus["color"] == filtered["nodes"][0]["color"]
    assert full["legend"]["clusters"] == filtered["legend"]["clusters"]
