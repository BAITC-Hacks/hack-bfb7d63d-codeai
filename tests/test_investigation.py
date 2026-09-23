"""Hand-checkable observation limits, temporal motifs and node removal scenarios."""

import networkx as nx
import pandas as pd
import pytest

from moneymap.graph import AnalysisResult, analyze_dataset
from moneymap.investigation import (
    COMPARISON_COLUMNS, CYCLE_COLUMNS, RECIPROCAL_COLUMNS, ROUTE_COLUMNS,
    analyze_routes, node_briefing, resilience_analysis,
)
from moneymap.roles import classify_graph


def dataset(nodes, transfers):
    node_table = pd.DataFrame(nodes, columns=["gid", "depth", "is_seed"])
    transactions = pd.DataFrame(transfers, columns=["src", "dst", "date", "sum_kzt"])
    transactions["date"] = pd.to_datetime(transactions["date"], format="mixed")
    edges = transactions.groupby(["src", "dst"], sort=True, as_index=False).agg(
        sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"),
    )
    edges["depth"] = 1
    return {"nodes": node_table, "edges": edges, "transactions": transactions}


def test_cycles_are_directed_canonical_and_self_transfers_are_excluded():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 2, False), (4, 1, False)], [
        (1, 2, "2026-01-01", 10), (2, 1, "2026-01-01", 20),
        (2, 3, "2026-01-02", 30), (3, 1, "2026-01-03", 40),
        (1, 1, "2026-01-01", 50),
    ])
    result = analyze_routes(analyze_dataset(frames), frames["transactions"])
    assert result.cycles["path"].tolist() == ["1 → 2 → 1", "1 → 2 → 3 → 1"]
    assert result.cycles["n_edges"].tolist() == [2, 3]
    assert result.cycles["observed_edge_turnover_kzt"].tolist() == [30, 80]
    assert result.reciprocal.to_dict(orient="records") == [{
        "src": "1", "dst": "2", "forward_kzt": 10, "reverse_kzt": 20,
        "forward_tx": 1, "reverse_tx": 1,
    }]
    assert not result.summary["cycles_truncated"]
    assert result.routes.empty  # topology is not a repeated temporal motif
    assert any("бір ақшаның" in value for value in result.limitations)
    assert any("бірегей қаражат" in value for value in result.limitations)


def test_cycle_search_has_explicit_length_count_and_work_limits():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 2, False)], [
        (1, 2, "2026-01-01", 10), (2, 1, "2026-01-02", 20),
        (2, 3, "2026-01-03", 30), (3, 1, "2026-01-04", 40),
    ])
    graph = analyze_dataset(frames)
    length_limited = analyze_routes(graph, frames["transactions"], max_cycle_length=2)
    assert length_limited.cycles["path"].tolist() == ["1 → 2 → 1"]
    assert not length_limited.summary["cycles_truncated"]
    count_limited = analyze_routes(graph, frames["transactions"], max_cycles=1)
    assert len(count_limited.cycles) == 1
    assert count_limited.summary["cycles_truncated"]
    work_limited = analyze_routes(graph, frames["transactions"], max_cycle_steps=1)
    assert work_limited.summary["cycle_steps"] == 1
    assert work_limited.summary["cycles_truncated"]
    zero_limited = analyze_routes(graph, frames["transactions"], max_cycle_steps=0)
    assert zero_limited.cycles.empty
    assert zero_limited.summary["cycles_truncated"]
    exact_limit = analyze_routes(graph, frames["transactions"], max_cycle_length=2, max_cycles=1)
    assert not exact_limit.summary["cycles_truncated"]  # no extra cycle was found


@pytest.fixture
def temporal_frames():
    return dataset([
        (1, 0, True), (2, 1, False), (3, 2, False),
        (4, 2, False), (5, 1, False), (6, 2, False),
    ], [
        (1, 2, "2026-01-01 01:00", 10),
        (1, 2, "2026-01-01 02:00", 10),  # duplicates count as operations, not days
        (1, 2, "2026-01-02 01:00", 20),
        (1, 2, "2026-01-04 01:00", 30),  # no later transfer to client 3
        (1, 2, "2026-01-05 01:00", 40),  # censored, even though client 4 gets paid later
        (2, 3, "2026-01-03 01:00", 50),  # one day supports two separate incoming days
        (2, 4, "2026-01-01 23:00", 60),  # same day never supports Jan 1 incoming
        (2, 4, "2026-01-02 23:00", 70),  # only Jan 1 is supported within full followup
        (2, 4, "2026-01-06 01:00", 80),  # supports Jan 4 too, producing another motif
        (5, 6, "2026-01-06 01:00", 90),
    ])


def test_two_hop_repeats_use_distinct_days_strict_order_and_complete_followup(temporal_frames):
    result = analyze_routes(analyze_dataset(temporal_frames), temporal_frames["transactions"])
    routes = result.routes.set_index("path")
    route = routes.loc["1 → 2 → 3"]
    assert route["eligible_in_days"] == 3
    assert route["matched_in_days"] == 2
    assert route["matched_in_tx"] == 3
    assert route["first_in_date"] == "2026-01-01"
    assert route["last_in_date"] == "2026-01-02"
    assert route["min_lag_days"] == 1
    assert route["max_lag_days"] == 2
    second = routes.loc["1 → 2 → 4"]
    assert second["matched_in_days"] == 2  # Jan 1 and Jan 4, excludes same-day Jan 2 and censored Jan 5
    assert second["last_in_date"] == "2026-01-04"
    assert result.summary["temporal_cutoff_date"] == "2026-01-04"
    assert result.summary["n_repeated_routes"] == 2


def test_two_hop_search_and_output_limits_are_separate(temporal_frames):
    analysis = analyze_dataset(temporal_frames)
    search_limited = analyze_routes(analysis, temporal_frames["transactions"], max_route_candidates=1)
    assert search_limited.summary["route_candidates"] == 1
    assert search_limited.summary["route_search_truncated"]
    assert not search_limited.summary["routes_truncated"]
    assert search_limited.routes["path"].tolist() == ["1 → 2 → 3"]
    output_limited = analyze_routes(analysis, temporal_frames["transactions"], max_routes=1)
    assert not output_limited.summary["route_search_truncated"]
    assert output_limited.summary["routes_truncated"]
    assert output_limited.summary["n_repeated_routes_detected"] == 2
    zero_limited = analyze_routes(analysis, temporal_frames["transactions"], max_route_candidates=0)
    assert zero_limited.routes.empty
    assert zero_limited.summary["route_search_truncated"]


def test_duplicate_incoming_transactions_on_one_day_do_not_create_repeated_route():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 2, False)], [
        (1, 2, "2026-01-01", 10), (1, 2, "2026-01-01", 10),
        (2, 3, "2026-01-02", 10), (2, 3, "2026-01-05", 10),
    ])
    assert analyze_routes(analyze_dataset(frames), frames["transactions"]).routes.empty


def test_same_day_order_and_censored_days_never_count_as_temporal_repeats():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 2, False)], [
        (1, 2, "2026-01-01 01:00", 10), (2, 3, "2026-01-01 23:00", 10),
        (1, 2, "2026-01-05 01:00", 10), (2, 3, "2026-01-05 23:00", 10),
        (1, 2, "2026-01-07 01:00", 10), (2, 3, "2026-01-08 01:00", 10),
    ])
    assert analyze_routes(analyze_dataset(frames), frames["transactions"]).routes.empty


@pytest.fixture
def removal_analysis():
    return analyze_dataset(dataset([
        (1, 0, True), (2, 1, False), (3, 2, False), (4, 2, False), (5, 0, True),
    ], [
        (1, 2, "2026-01-01", 10), (2, 3, "2026-01-02", 20),
        (2, 4, "2026-01-03", 30), (4, 3, "2026-01-04", 40),
    ]))


def test_removal_preserves_nonremoved_clients_including_newly_isolated(removal_analysis):
    result = resilience_analysis(removal_analysis, [2], top_n=1)
    comparison = result.comparison.set_index("scenario")
    assert result.removed_gids == ("2",)
    assert result.remaining_gids == ("1", "3", "4", "5")
    assert comparison.loc["before", "n_nodes"] == 5
    assert comparison.loc["before", "weak_components"] == 2
    assert comparison.loc["before", "largest_component_share"] == 4 / 5
    assert comparison.loc["after", "n_nodes"] == 4
    assert comparison.loc["after", "n_edges"] == 1
    assert comparison.loc["after", "weak_components"] == 3
    assert comparison.loc["after", "largest_component_share"] == 2 / 4
    assert comparison.loc["after", "observed_edge_turnover_kzt"] == 40
    assert comparison.loc["after", "retained_turnover_share"] == 0.4
    assert removal_analysis.graph.number_of_nodes() == 5
    assert removal_analysis.graph.number_of_edges() == 4


def test_removal_all_none_duplicates_and_unknown_nodes(removal_analysis):
    untouched = resilience_analysis(removal_analysis, [1, 2], top_n=0)
    assert untouched.removed_gids == ()
    assert untouched.comparison.iloc[0].drop("scenario").equals(untouched.comparison.iloc[1].drop("scenario"))
    deduplicated = resilience_analysis(removal_analysis, ["2", 2, 1, 3], top_n=2)
    assert deduplicated.removed_gids == ("2", "1")
    removed_all = resilience_analysis(removal_analysis, list(removal_analysis.graph), top_n=99)
    after = removed_all.comparison.set_index("scenario").loc["after"]
    assert removed_all.remaining_gids == ()
    assert after["n_nodes"] == after["weak_components"] == after["largest_component_nodes"] == 0
    assert after["largest_component_share"] == after["retained_turnover_share"] == 0
    with pytest.raises(KeyError):
        resilience_analysis(removal_analysis, [999], top_n=1)
    with pytest.raises(ValueError):
        resilience_analysis(removal_analysis, [1], top_n=-1)


def test_empty_graph_and_isolated_clients_have_stable_schemas_and_undefined_retention():
    frames = dataset([(1, 0, True), (2, 4, False)], [])
    analysis = analyze_dataset(frames)
    routes = analyze_routes(analysis, frames["transactions"])
    assert list(routes.cycles) == CYCLE_COLUMNS
    assert list(routes.reciprocal) == RECIPROCAL_COLUMNS
    assert list(routes.routes) == ROUTE_COLUMNS
    assert routes.cycles.empty and routes.reciprocal.empty and routes.routes.empty
    assert routes.summary["temporal_cutoff_date"] is None
    assert not routes.summary["cycles_truncated"]
    resilience = resilience_analysis(analysis, [1], top_n=1)
    assert resilience.remaining_gids == ("2",)
    assert resilience.comparison["retained_turnover_share"].isna().all()
    assert resilience.comparison["weak_components"].tolist() == [2, 1]
    empty = AnalysisResult(nx.DiGraph(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}, 0)
    empty_routes = analyze_routes(empty, frames["transactions"])
    assert empty_routes.summary["cycle_steps"] == empty_routes.summary["route_candidates"] == 0
    empty_resilience = resilience_analysis(empty, [], top_n=5)
    assert list(empty_resilience.comparison) == COMPARISON_COLUMNS
    assert empty_resilience.comparison["n_nodes"].eq(0).all()
    assert empty_resilience.comparison["largest_component_share"].eq(0).all()
    assert empty_resilience.comparison["retained_turnover_share"].isna().all()


def test_long_identifiers_survive_routes_resilience_and_briefing(temporal_frames):
    mapping = {gid: 2**63 - 20 + gid for gid in temporal_frames["nodes"]["gid"]}
    temporal_frames["nodes"]["gid"] = temporal_frames["nodes"]["gid"].map(mapping)
    for name in ("edges", "transactions"):
        for column in ("src", "dst"):
            temporal_frames[name][column] = temporal_frames[name][column].map(mapping)
    analysis = analyze_dataset(temporal_frames)
    routes = analyze_routes(analysis, temporal_frames["transactions"])
    assert routes.routes.iloc[0]["src"] == str(mapping[1])
    assert routes.routes.iloc[0]["via"] == str(mapping[2])
    assert routes.routes.iloc[0]["dst"] == str(mapping[3])
    resilience = resilience_analysis(analysis, [str(mapping[2])], top_n=1)
    assert resilience.removed_gids == (str(mapping[2]),)
    briefing = node_briefing(analysis, str(mapping[2]), roles=classify_graph(analysis))
    assert briefing.gid == str(mapping[2])
    assert f"gid {mapping[2]}:" in briefing.text
    with pytest.raises(ValueError):
        node_briefing(analysis, float(mapping[2]))


def test_briefing_uses_observations_and_conditional_evidence_limits():
    frames = dataset([(1, 0, True), (2, 4, False), (3, 0, True)], [
        (1, 2, "2026-01-01", 10_000), (1, 2, "2026-01-04", 20_000),
    ])
    analysis = analyze_dataset(frames)
    seed = node_briefing(analysis, 1)
    assert "30 000.00 ₸ (2 операция)" in seed.text
    assert "2026-01-01–2026-01-04" in seed.text
    assert any("Seed-клиенттің кірістері толық емес" in item for item in seed.limitations)
    assert any("толық кіріс операцияларын" in item for item in seed.next_requests)
    boundary = node_briefing(analysis, 2)
    assert "1 басқа seed-клиенттен" in boundary.text
    assert any("depth=4" in item for item in boundary.limitations)
    assert any("1 кіріс операциясы" in item for item in boundary.limitations)
    assert any("Depth=4" in item for item in boundary.next_requests)
    assert not any("Seed-клиенттің" in item for item in boundary.limitations)
    isolated = node_briefing(analysis, 3)
    assert "Бақыланған операция күні жоқ" in isolated.text
    assert any("үзіндіде байланысы жоқ" in item for item in isolated.limitations)
    assert any("идентификатор сәйкестігін" in item for item in isolated.next_requests)
    assert all(any("5 000" in item for item in item_set) for item_set in [seed.limitations, seed.next_requests])
    with pytest.raises(KeyError):
        node_briefing(analysis, "999")


def test_briefing_keeps_self_transfer_totals_separate_and_cites_actual_role_evidence():
    frames = dataset([(1, 0, True)], [(1, 1, "2026-01-01", 15_000)])
    analysis = analyze_dataset(frames)
    roles = classify_graph(analysis)
    role = roles.nodes_roles.to_dict(orient="records")[0]
    briefing = node_briefing(analysis, 1, roles=roles)
    assert "бақыланған кіріс 15 000.00 ₸ (1 операция)" in briefing.text
    assert "Өзге жіберуші: 0; өзге алушы: 0" in briefing.text
    assert f"ережеге сәйкестік ұпайы {role['role_score']:.3f}" in briefing.text
    assert f"кластер {role['cluster_id']}" in briefing.text
    assert role["evidence"] in briefing.text
    assert any("өзіне аударымдарды да қамтиды" in item for item in briefing.limitations)
    assert not any("үзіндіде байланысы жоқ" in item for item in briefing.limitations)


def test_output_is_reproducible_and_does_not_mutate_inputs(temporal_frames):
    original = {name: frame.copy(deep=True) for name, frame in temporal_frames.items()}
    first_analysis = analyze_dataset(temporal_frames)
    shuffled = {name: frame.sample(frac=1, random_state=47).reset_index(drop=True) for name, frame in temporal_frames.items()}
    second_analysis = analyze_dataset(shuffled)
    first = analyze_routes(first_analysis, temporal_frames["transactions"])
    second = analyze_routes(second_analysis, shuffled["transactions"])
    for table in ("cycles", "reciprocal", "routes"):
        pd.testing.assert_frame_equal(getattr(first, table), getattr(second, table))
    assert first.summary == second.summary
    assert node_briefing(first_analysis, 2) == node_briefing(second_analysis, 2)
    for name, frame in original.items():
        pd.testing.assert_frame_equal(temporal_frames[name], frame)


@pytest.mark.parametrize("options", [
    {"window_days": 0}, {"window_days": True}, {"max_cycle_length": 1},
    {"max_cycles": -1}, {"max_cycle_steps": -1}, {"max_route_candidates": -1},
    {"max_routes": -1},
])
def test_invalid_limits_fail_explicitly(temporal_frames, options):
    with pytest.raises(ValueError):
        analyze_routes(analyze_dataset(temporal_frames), temporal_frames["transactions"], **options)


def test_transaction_pairs_must_belong_to_same_graph(temporal_frames):
    analysis = analyze_dataset(temporal_frames)
    wrong = temporal_frames["transactions"].copy()
    wrong.loc[0, "src"] = 999
    with pytest.raises(ValueError, match="графта жоқ байланыс"):
        analyze_routes(analysis, wrong)
