"""Observable-pattern positives, counterexamples, caps, replay and identity."""

import copy
import json
import unittest

import pandas as pd

from moneygraph.insights import derive_insights, enrich_analysis


def frame(rows):
    return pd.DataFrame(rows, columns=["src", "dst", "date", "sum_kzt"])


def nodes_for(transactions, overrides=None):
    ids = sorted(set(transactions.src) | set(transactions.dst))
    result = [{"gid": int(gid), "depth": 1, "is_seed": False, "role": "peripheral",
               "role_score": 0.25, "priority_score": 0.1} for gid in ids]
    for node in result:
        node.update((overrides or {}).get(node["gid"], {}))
    return result


def positive_fixture(offset=0):
    rows = [(1, 10, "2026-07-01", 10_000), (1, 10, "2026-07-31", 10_000)]
    rows += [(payer, 10, "2026-07-02", 50_000) for payer in range(1, 5)]
    rows += [(10, 20, "2026-07-04", 200_000)]
    rows += [(99, 98, "2026-07-10", 10_000)] * 4
    for start in (1, 8, 15):
        for hop, (src, dst) in enumerate(((30, 31), (31, 32), (32, 33))):
            rows.append((src, dst, f"2026-07-{start + hop:02d}", 10_000))
        for hop, (src, dst) in enumerate(((40, 41), (41, 42), (42, 40))):
            rows.append((src, dst, f"2026-07-{start + hop:02d}", 10_000))
    return frame([(src + offset, dst + offset, day, amount) for src, dst, day, amount in rows])


class InsightTests(unittest.TestCase):
    def test_observed_spike_synchronization_fast_forward_and_splitting(self):
        tx = positive_fixture()
        insights, replay, references = derive_insights(nodes_for(tx), tx)
        kinds = {item["kind"] for item in insights["events"]}
        self.assertTrue({"activity_spike", "synchronized_payers", "fast_forward", "payment_splitting"} <= kinds)
        spikes = [item for item in insights["events"] if item["kind"] == "activity_spike" and item["gids"] == [10]]
        self.assertEqual(len(spikes), 1)
        self.assertEqual(spikes[0]["metrics"]["baseline_days"], 30)
        self.assertAlmostEqual(spikes[0]["metrics"]["baseline_daily_kzt"], 20_000 / 30, places=2)
        forwarding = next(item for item in insights["events"] if item["kind"] == "fast_forward" and item["gids"] == [10])
        self.assertEqual(forwarding["metrics"]["window_days"], 2)
        self.assertEqual(forwarding["metrics"]["matched_kzt"], 200_000)
        splitting = next(item for item in insights["events"] if item["kind"] == "payment_splitting" and item["gids"] == [99, 98])
        self.assertEqual(splitting["metrics"]["n_tx"], 4)
        self.assertIn("есептілік шегін", splitting["evidence"])
        self.assertTrue(references[10])

    def test_routine_single_payer_activity_does_not_trigger_patterns(self):
        tx = frame([(1, 2, f"2026-07-{day:02d}", 5000) for day in range(1, 32)])
        insights, _, _ = derive_insights(nodes_for(tx), tx)
        self.assertEqual(insights["events"], [])
        self.assertEqual(insights["cycles"], [])
        self.assertEqual(insights["routes"], [])

    def test_peer_outlier_uses_same_depth_and_candidate_keeps_existing_role(self):
        tx = frame([(100, gid, "2026-07-01", 500_000 if gid == 12 else 5000) for gid in range(1, 13)])
        overrides = {gid: {"depth": 2} for gid in range(1, 13)}
        overrides[100] = {"depth": 0, "is_seed": True}
        overrides[12].update({"role": "coordinator", "in_degree": 3, "out_degree": 3,
                              "external_communities": 2, "betweenness": 0.2, "role_score": 0.7})
        nodes = nodes_for(tx, overrides)
        original = copy.deepcopy(nodes)
        insights, _, _ = derive_insights(nodes, tx)
        peers = [item for item in insights["events"] if item["kind"] == "peer_outlier"]
        self.assertEqual([item["gids"] for item in peers], [[12]])
        self.assertEqual(peers[0]["metrics"]["cohort_size"], 12)
        candidate = next(item for item in insights["events"] if item["kind"] == "organizer_candidate")
        self.assertEqual(candidate["gids"], [12])
        self.assertEqual(candidate["metrics"]["existing_role_score"], 0.7)
        self.assertEqual(nodes, original)

    def test_repeated_two_and_three_edge_routes_and_rotation_deduplicated_cycle(self):
        tx = positive_fixture()
        insights, _, _ = derive_insights(nodes_for(tx), tx)
        route = next(item for item in insights["routes"] if item["gids"] == [30, 31, 32, 33])
        self.assertEqual(route["n_occurrences"], 3)
        self.assertEqual(route["occurrences"][0]["dates"], ["2026-07-01", "2026-07-02", "2026-07-03"])
        self.assertFalse(route["same_day_order_unknown"])
        self.assertTrue(any(item["gids"] == [30, 31, 32] for item in insights["routes"]))
        cycles = [item for item in insights["cycles"] if set(item["gids"]) == {40, 41, 42}]
        self.assertEqual(len(cycles), 1)
        self.assertEqual(len(cycles[0]["edges"]), 3)
        self.assertFalse(cycles[0]["temporal_order_verified"])

    def test_same_day_routes_are_explicitly_unordered(self):
        tx = frame([(src, dst, f"2026-07-{day:02d}", 5000)
                    for day in (1, 8) for src, dst in ((1, 2), (2, 3))])
        insights, _, _ = derive_insights(nodes_for(tx), tx)
        self.assertEqual(len(insights["routes"]), 1)
        self.assertTrue(insights["routes"][0]["same_day_order_unknown"])

    def test_wrong_dates_and_reused_edge_days_do_not_create_repeated_routes(self):
        for rows in (
            [(1, 2, "2026-07-05", 5000), (1, 2, "2026-07-12", 5000),
             (2, 3, "2026-07-01", 5000), (2, 3, "2026-07-08", 5000)],
            [(1, 2, "2026-07-01", 5000), (1, 2, "2026-07-02", 5000),
             (2, 3, "2026-07-02", 5000), (2, 3, "2026-07-10", 5000)],
        ):
            tx = frame(rows)
            with self.subTest(rows=rows):
                insights, _, _ = derive_insights(nodes_for(tx), tx)
                self.assertEqual(insights["routes"], [])

    def test_daily_replay_reconciles_exact_counts_and_amounts_including_zero_days(self):
        tx = positive_fixture()
        _, replay, _ = derive_insights(nodes_for(tx), tx)
        self.assertEqual(len(replay["days"]), 31)
        self.assertIn("2026-07-30", replay["days"])
        actual = {(edge["src"], edge["dst"], day["date"]): (day["sum_kzt"], day["n_tx"])
                  for edge in replay["edges"] for day in edge["days"]}
        grouped = tx.groupby(["src", "dst", "date"]).sum_kzt.agg(["sum", "size"])
        self.assertEqual(set(actual), set(grouped.index))
        for key, row in grouped.iterrows():
            self.assertAlmostEqual(actual[key][0], row["sum"])
            self.assertEqual(actual[key][1], row["size"])
        self.assertEqual(sum(value[1] for value in actual.values()), len(tx))

    def test_output_and_search_caps_are_deterministic_and_report_truncation(self):
        tx = frame([(src, dst, f"2026-07-{day:02d}", 5000)
                    for day in (1, 8) for src in range(1, 9) for dst in range(1, 9) if src != dst])
        caps = {"max_events": 3, "max_cycles": 2, "max_routes": 2,
                "max_cycle_candidates": 25, "max_route_candidates": 30}
        nodes = nodes_for(tx)
        first = derive_insights(nodes, tx, caps=caps)
        second = derive_insights(nodes, tx.iloc[::-1], caps=caps)
        self.assertEqual(first, second)
        insights = first[0]
        self.assertLessEqual(len(insights["events"]), 3)
        self.assertLessEqual(len(insights["cycles"]), 2)
        self.assertLessEqual(len(insights["routes"]), 2)
        self.assertTrue(insights["limits"]["events_truncated"])
        self.assertTrue(insights["limits"]["cycle_search_truncated"])
        self.assertTrue(insights["limits"]["route_search_truncated"])
        self.assertEqual(insights["limits"]["cycle_candidates_scanned"], 25)
        self.assertEqual(insights["limits"]["route_candidates_scanned"], 30)

    def test_all_nested_gids_preserve_large_int64_identity(self):
        offset = 9_007_199_254_740_992
        tx = positive_fixture(offset)
        nodes = nodes_for(tx)
        expected = {str(node["gid"]) for node in nodes}
        insights, replay, refs = derive_insights(nodes, tx)

        def check(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"src", "dst", "gid"}:
                        self.assertIsInstance(child, str)
                        self.assertIn(child, expected)
                    elif key == "gids":
                        self.assertTrue(all(isinstance(gid, str) and gid in expected for gid in child))
                    else:
                        check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        check({"insights": insights, "replay": replay})
        catalog = {item["id"]: item for key in ("events", "cycles", "routes") for item in insights[key]}
        for gid, identifiers in refs.items():
            self.assertEqual(len(identifiers), len(set(identifiers)))
            for identifier in identifiers:
                self.assertIn(str(gid), catalog[identifier]["gids"])
        json.dumps({"insights": insights, "replay": replay}, allow_nan=False)

    def test_empty_and_long_period_data_have_bounded_calendar(self):
        empty = frame([])
        insights, replay, refs = derive_insights([], empty)
        self.assertEqual(replay, {"days": [], "edges": []})
        self.assertEqual(insights["events"], [])
        self.assertEqual(refs, {})
        tx = frame([(1, 2, "1900-01-01", 5000), (1, 2, "2100-01-01", 5000)])
        insights, replay, _ = derive_insights(nodes_for(tx), tx, caps={"max_replay_calendar_days": 5})
        self.assertTrue(insights["limits"]["replay_calendar_truncated"])
        self.assertLessEqual(len(replay["days"]), 5)

    def test_enrichment_is_additive_and_does_not_mutate_source_transactions(self):
        tx = positive_fixture()
        original = tx.copy(deep=True)
        nodes = nodes_for(tx)
        analysis = {"nodes": copy.deepcopy(nodes), "other": {"kept": True}}
        enrich_analysis(analysis, tx)
        self.assertEqual([{k: v for k, v in node.items() if k != "insight_ids"} for node in analysis["nodes"]], nodes)
        self.assertEqual(analysis["other"], {"kept": True})
        self.assertIn("insights", analysis)
        self.assertIn("replay", analysis)
        pd.testing.assert_frame_equal(tx, original)


if __name__ == "__main__":
    unittest.main()
