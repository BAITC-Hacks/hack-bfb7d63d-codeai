"""Hand-checkable anomaly signals and observation limits, without labels."""

from io import StringIO
import json
import math

import numpy as np
import pandas as pd
import pytest

from moneymap.anomalies import ALERT_COLUMNS, analyze_anomalies
from moneymap.graph import analyze_dataset


def dataset(nodes, transfers):
    transactions = pd.DataFrame(transfers, columns=["src", "dst", "date", "sum_kzt"])
    transactions["date"] = pd.to_datetime(transactions["date"], format="mixed")
    edges = transactions.groupby(["src", "dst"], sort=True, as_index=False).agg(
        sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"),
    )
    edges["depth"] = 1
    return {"nodes": pd.DataFrame(nodes, columns=["gid", "depth", "is_seed"]),
            "edges": edges, "transactions": transactions}


def run(frames, **kwargs):
    return analyze_anomalies(analyze_dataset(frames), frames["transactions"], **kwargs)


def test_reference_band_is_inclusive_and_self_transfers_never_support_repetition():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 1, False)], [
        (1, 2, "2026-07-01", 9500), (1, 2, "2026-07-01", 10000),
        (1, 3, "2026-07-01", 10500), (1, 3, "2026-07-01", 10501),
        (1, 1, "2026-07-01", 10000), (1, 2, "2026-07-02", 10000),
    ])
    result = run(frames, reference_amount=10000)
    row = result.alerts.loc[result.alerts.signal.eq("similar_amounts")].iloc[0]
    assert row.gid == "1" and row.n_tx == 3 and row.n_counterparties == 2
    assert row.sum_kzt == 30000 and row.amount_min_kzt == 9500 and row.amount_max_kzt == 10500
    assert row.window_edge_day and "Seed" in row.caveats
    assert result.summary["excluded_self_transfers"] == 1
    assert result.summary["parameters"]["reference_amount"] == 10000
    assert "ықтималдығы" in result.limitations[0]
    assert run(frames, reference_amount=20000).alerts.empty


def test_automatic_similarity_is_not_transitive_and_ties_are_reproducible():
    frames = dataset([(1, 0, True), (2, 1, False)], [
        (1, 2, "2026-07-01", 10000), (1, 2, "2026-07-01", 10400),
        (1, 2, "2026-07-01", 10800),  # consecutive near values must not merge
    ])
    assert run(frames).alerts.empty
    result = run(frames, repeat_min_tx=2)
    assert result.alerts.iloc[0].amount_min_kzt == 10000
    assert result.alerts.iloc[0].amount_max_kzt == 10400
    assert result.alerts.iloc[0].n_tx == 2


def test_daily_spike_uses_all_other_calendar_days_and_skips_zero_baseline():
    frames = dataset([(1, 0, True), (2, 1, False), (3, 0, True), (4, 1, False)], [
        (1, 2, "2026-07-01", 10000),
        *[(1, 2, "2026-07-07", 10000 + index * 1000) for index in range(6)],
        *[(3, 4, "2026-07-07", 10000) for _ in range(6)],
    ])
    result = run(frames)
    spike = result.alerts.loc[result.alerts.signal.eq("daily_spike") & result.alerts.gid.eq("1")].iloc[0]
    assert spike.observed_days == 7
    assert spike.observed_value == 6
    assert spike.baseline_value == pytest.approx(1 / 6)  # five zero days are retained
    assert spike.statistic == 36
    assert result.summary["spike_zero_baseline_node_days_skipped"] == 2  # src 3 and dst 4
    assert not result.alerts.loc[result.alerts.signal.eq("daily_spike")].gid.isin(["3", "4"]).any()
    assert not run(frames, min_observation_days=8).summary["spikes_evaluated"]


def test_same_day_payers_count_distinct_clients_not_transfers_or_self():
    frames = dataset([(1, 0, True), (2, 0, True), (3, 0, True), (4, 4, False)], [
        (1, 4, "2026-07-01 01:00", 5000), (1, 4, "2026-07-01 02:00", 6000),
        (2, 4, "2026-07-01 04:00", 7000), (4, 4, "2026-07-01", 8000),
        (3, 4, "2026-07-02", 9000),
    ])
    assert not run(frames).alerts.signal.eq("same_day_payers").any()
    result = run(frames, sync_min_payers=2)
    row = result.alerts.loc[result.alerts.signal.eq("same_day_payers")].iloc[0]
    assert row.gid == "4" and row.n_tx == 3 and row.n_counterparties == 2 and row.sum_kzt == 18000
    assert row.boundary and "4-буын" in row.caveats
    assert "Бір мезетте" in row.explanation


def peer_frames():
    nodes = [(1, 0, True), (50, 2, False)] + [(gid, 1, False) for gid in range(10, 20)]
    # A small variation in regular volume supplies a nonzero robust scale.
    amounts = [10000, 11000, 12000, 13000, 14000, 15000, 16000, 17000, 18000, 1000000]
    transfers = [(1, gid, "2026-07-01", amount) for gid, amount in zip(range(10, 20), amounts)]
    # Other depth has a far larger value: it must not alter depth-1 baseline.
    transfers.append((1, 50, "2026-07-07", 1000000000))
    return dataset(nodes, transfers)


def test_peer_outlier_uses_robust_log_scale_only_within_depth():
    frames = peer_frames()
    result = run(frames)
    outliers = result.alerts.loc[result.alerts.signal.eq("depth_peer_outlier")]
    assert outliers.gid.tolist() == ["19"]
    row = outliers.iloc[0]
    logged = np.log1p([10000, 11000, 12000, 13000, 14000, 15000, 16000, 17000, 18000, 1000000])
    median = np.median(logged)
    mad = np.median(np.abs(logged - median))
    assert row.peer_n == 10 and row.peer_median_log == median and row.peer_mad_log == mad
    assert row.statistic == pytest.approx((math.log1p(1000000) - median) / (1.4826 * mad))
    assert row.observed_value == 1000000
    assert run(frames, peer_min_size=11).alerts.loc[lambda table: table.signal.eq("depth_peer_outlier")].empty


def test_zero_mad_does_not_generate_infinite_score_and_coverage_is_excluded():
    nodes = [(gid, 0, True) for gid in range(1, 11)] + [(gid, 4, False) for gid in range(20, 30)]
    transfers = [(src, dst, "2026-07-01", 10000) for src, dst in zip(range(1, 11), range(20, 30))]
    result = run(dataset(nodes, transfers))
    assert not result.alerts.signal.eq("depth_peer_outlier").any()
    groups = {(row["depth"], row["direction"]): row for row in result.summary["peer_groups"]}
    assert groups[0, "incoming"]["status"] == "coverage_excluded"
    assert groups[4, "outgoing"]["status"] == "coverage_excluded"
    assert groups[4, "incoming"]["status"] == "zero_robust_scale"
    assert groups[0, "outgoing"]["status"] == "zero_robust_scale"
    json.dumps(result.summary, allow_nan=False)


def test_large_identifiers_are_exact_through_alerts_and_csv_and_inputs_unchanged():
    big = 2**63 - 7
    frames = dataset([(big, 0, True), (big + 1, 1, False)], [
        (big, big + 1, "2026-07-01", 5000),
        (big, big + 1, "2026-07-01", 5000),
        (big, big + 1, "2026-07-01", 5000),
    ])
    original = {name: table.copy(deep=True) for name, table in frames.items()}
    result = run(frames)
    assert result.alerts.gid.tolist() == [str(big)]
    assert result.alerts.iloc[0].n_tx == 3  # duplicate rows retained
    exported = pd.read_csv(StringIO(result.alerts.to_csv(index=False)), dtype={"gid": str})
    assert exported.gid.tolist() == [str(big)]
    shuffled = {name: table.sample(frac=1, random_state=18).reset_index(drop=True) for name, table in frames.items()}
    repeated = run(shuffled)
    pd.testing.assert_frame_equal(result.alerts, repeated.alerts)
    assert result.summary == repeated.summary
    for name in frames:
        pd.testing.assert_frame_equal(original[name], frames[name])


def test_output_limit_is_explicit_and_preserves_total_signal_counts():
    frames = dataset([(1, 0, True), (2, 0, True), (3, 1, False)], [
        *[(1, 3, "2026-07-01", 5000) for _ in range(3)],
        *[(2, 3, "2026-07-01", 5000) for _ in range(3)],
    ])
    full = run(frames, sync_min_payers=2)
    limited = run(frames, sync_min_payers=2, max_alerts=1)
    assert len(full.alerts) == limited.summary["alerts_detected"] == 3
    assert limited.summary["alerts_returned"] == len(limited.alerts) == 1
    assert limited.summary["alerts_truncated"]
    assert limited.summary["signal_counts"] == full.summary["signal_counts"]
    empty = run(frames, max_alerts=0)
    assert empty.alerts.empty and list(empty.alerts.columns) == ALERT_COLUMNS
    assert empty.summary["alerts_truncated"] and empty.summary["alerts_detected"] == 2


def test_isolates_and_self_only_data_never_invent_relational_patterns():
    empty = run(dataset([(1, 0, True)], []))
    assert empty.alerts.empty and empty.summary["observation_period"]["calendar_days"] == 0
    frames = dataset([(1, 0, True)], [(1, 1, "2026-07-01", 1000)] * 12)
    result = run(frames)
    assert result.alerts.empty and result.summary["excluded_self_transfers"] == 12
    assert result.summary["observed_below_case_sampling_floor"] == 12
    assert any("5 000" in item for item in result.limitations)


@pytest.mark.parametrize("params", [
    {"reference_amount": 0}, {"reference_amount": float("inf")}, {"reference_amount": True},
    {"reference_amount": 1.79e308, "amount_tolerance": 1},
    {"amount_tolerance": -0.1}, {"amount_tolerance": 1.01}, {"amount_tolerance": float("nan")},
    {"repeat_min_tx": 1}, {"repeat_min_tx": True}, {"spike_min_tx": 1}, {"spike_ratio": 1},
    {"min_observation_days": 2}, {"sync_min_payers": 1}, {"peer_min_size": 4},
    {"peer_z_threshold": 0}, {"max_alerts": -1},
])
def test_invalid_parameters_fail_instead_of_silently_changing_method(params):
    frames = dataset([(1, 0, True)], [])
    with pytest.raises(ValueError):
        run(frames, **params)


@pytest.mark.parametrize("change", ["drop", "unknown", "bad_amount", "float_id", "date", "numeric_date", "timezone"])
def test_partial_or_malformed_transactions_are_rejected(change):
    frames = peer_frames()
    graph = analyze_dataset(frames)
    bad = frames["transactions"].copy()
    if change == "drop":
        bad = bad.iloc[1:]
    elif change == "unknown":
        bad.loc[0, "src"] = 999
    elif change == "bad_amount":
        bad.loc[0, "sum_kzt"] = -1
    elif change == "float_id":
        bad["src"] = 1e18
    elif change == "date":
        bad.loc[0, "date"] = pd.NaT
    elif change == "numeric_date":
        bad["date"] = 1
    else:
        bad["date"] = bad["date"].dt.tz_localize("UTC")
    with pytest.raises(ValueError):
        analyze_anomalies(graph, bad)
