"""Incremental overlay provenance, arithmetic, identity and conflict checks."""

import copy
import json
import unittest

from moneygraph.expansion import expand_analysis


def base_graph(offset=0):
    nodes = [{"gid": offset + gid, "depth": gid - 1, "is_seed": gid == 1,
              "role": "peripheral", "role_score": 0.25, "priority_score": 0.1,
              "cluster_id": 0, "evidence": "Original hypothesis", "flags": []}
             for gid in range(1, 6)]
    edges = [{"src": offset + gid, "dst": offset + gid + 1, "sum_kzt": 10_000, "n_tx": 1}
             for gid in range(1, 5)]
    replay = {"days": [f"2026-07-{day:02d}" for day in range(1, 5)],
              "edges": [{**edge, "days": [{"date": f"2026-07-{day:02d}", "sum_kzt": 10_000, "n_tx": 1}]}
                        for day, edge in enumerate(edges, 1)]}
    return {"nodes": nodes, "edges": edges, "replay": replay,
            "meta": {"demo": True, "n_seeds": 1, "dataset_fingerprint": "test-exact-dataset-fingerprint"}}


def record(src=5, dst=6, amount=8000, day="2026-08-01", source="Bank export A", txid="supp-001"):
    return {"src": src, "dst": dst, "date": day, "sum_kzt": amount,
            "source_reference": source, "transaction_id": txid}


def request(*records):
    return {"incremental_disjoint": True, "transactions": list(records)}


class ExpansionTests(unittest.TestCase):
    def test_requires_explicit_disjoint_assertion(self):
        for declaration in (None, False, "true", 1):
            with self.subTest(declaration=declaration), self.assertRaises(ValueError):
                expand_analysis(base_graph(), {"transactions": [record()], "incremental_disjoint": declaration})

    def test_adds_only_provided_flows_and_neutral_new_nodes_beyond_four_hops(self):
        result = expand_analysis(base_graph(), request(record(), record(6, 7, 7000, "2026-08-02", txid="supp-002")))
        graph = result["graph"]
        self.assertEqual(result["base_comparison"]["new_nodes"], 2)
        self.assertEqual(result["base_comparison"]["new_edges"], 2)
        self.assertEqual(result["base_comparison"]["added_kzt"], 15_000)
        self.assertEqual(graph["meta"]["n_transactions"], 6)
        self.assertEqual(graph["meta"]["total_kzt"], 55_000)
        nodes = {node["gid"]: node for node in graph["nodes"]}
        self.assertEqual(nodes[6]["depth"], 5)
        self.assertEqual(nodes[7]["depth"], 6)
        self.assertEqual(nodes[7]["role"], "unclassified")
        self.assertFalse(nodes[7]["role_assigned"])
        self.assertIsNone(nodes[7]["priority_score"])
        self.assertEqual(nodes[5]["role_scope"], "base_snapshot")
        self.assertEqual(nodes[5]["evidence"], "Original hypothesis")
        self.assertEqual(nodes[5]["out_kzt"], 8000)
        self.assertEqual(nodes[5]["base_metrics"]["role"], "peripheral")
        self.assertEqual(graph["meta"]["max_observed_depth"], 6)
        self.assertFalse(graph["meta"]["roles_recomputed"])

    def test_disconnected_new_nodes_have_unknown_seed_distance(self):
        result = expand_analysis(base_graph(), request(record(10, 11)))
        new = [node for node in result["graph"]["nodes"] if node["gid"] in {10, 11}]
        self.assertTrue(all(node["depth"] is None and node["observed_depth"] is None for node in new))
        self.assertTrue(all(not node["is_seed"] for node in new))

    def test_duplicate_ids_deduplicate_within_batch_and_after_json_persistence(self):
        result = expand_analysis(base_graph(), request(record(), record()))
        self.assertEqual(result["provenance"]["accepted_transactions"], 1)
        self.assertEqual(result["provenance"]["duplicate_transactions"], 1)
        persisted = json.loads(json.dumps(result["graph"]))
        repeated = expand_analysis(persisted, request(record()))
        self.assertEqual(repeated["provenance"]["accepted_transactions"], 0)
        self.assertEqual(repeated["provenance"]["duplicate_transactions"], 1)
        self.assertEqual(repeated["base_comparison"]["added_kzt"], 0)
        self.assertEqual(repeated["graph"]["edges"], result["graph"]["edges"])
        self.assertEqual(repeated["provenance"]["base_summary"]["n_transactions"], 4)
        self.assertEqual(repeated["provenance"]["base_fingerprint"], "test-exact-dataset-fingerprint")

    def test_id_conflicts_rejected_but_different_sources_are_separate_id_namespaces(self):
        with self.assertRaises(ValueError):
            expand_analysis(base_graph(), request(record(), record(amount=9000)))
        first = expand_analysis(base_graph(), request(record()))
        with self.assertRaises(ValueError):
            expand_analysis(first["graph"], request(record(day="2026-08-01T01:00:00Z")))
        other = expand_analysis(first, request(record(source="Bank export B")))
        self.assertEqual(other["provenance"]["accepted_transactions"], 1)
        self.assertEqual(other["provenance"]["total_supplementary_transactions"], 2)

    def test_possible_base_overlap_is_disclosed_not_claimed_verified(self):
        result = expand_analysis(base_graph(), request(record(1, 2, 6000, "2026-07-01")))
        self.assertEqual(result["provenance"]["same_pair_day_records"], 1)
        self.assertFalse(result["provenance"]["disjointness_verified"])
        self.assertEqual(result["graph"]["edges"][0]["sum_kzt"], 16_000)
        self.assertGreaterEqual(len(result["provenance"]["warnings"]), 3)

    def test_daily_replay_and_timeline_reconcile_and_normalize_utc(self):
        result = expand_analysis(base_graph(), request(record(day="2026-08-01T01:00:00+05:00")))
        graph = result["graph"]
        self.assertEqual(graph["meta"]["period_end"], "2026-07-31")
        self.assertEqual(sum(day["n_tx"] for edge in graph["replay"]["edges"] for day in edge["days"]), 5)
        self.assertEqual(sum(day["sum_kzt"] for edge in graph["replay"]["edges"] for day in edge["days"]), 48_000)
        self.assertEqual(sum(row["sum_kzt"] for row in graph["timeline"]), 48_000)

    def test_invalid_records_dates_overflow_and_missing_base_replay_rejected(self):
        for changes in ({"src": 1.5}, {"src": True}, {"src": "1e18"}, {"src": 2**63},
                        {"date": "07/01/2026"}, {"date": "2026-07-32"}, {"date": "NaT"},
                        {"sum_kzt": float("inf")}, {"sum_kzt": -1}, {"sum_kzt": 10**1000},
                        {"transaction_id": ""}, {"source_reference": "\n"}, {"unexpected": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                expand_analysis(base_graph(), request({**record(), **changes}))
        with self.assertRaises(ValueError):
            expand_analysis(base_graph(), request(record(amount=1e308), record(amount=1e308, txid="second")))
        graph = base_graph()
        graph.pop("replay")
        with self.assertRaises(ValueError):
            expand_analysis(graph, request(record()))
        graph = base_graph()
        graph["replay"]["edges"][0]["days"][0]["sum_kzt"] = 1
        with self.assertRaises(ValueError):
            expand_analysis(graph, request(record()))

    def test_large_ids_are_exact_and_input_immutable(self):
        offset = 9_007_199_254_740_992
        graph = base_graph(offset)
        payload = request(record(str(offset + 5), str(offset + 6)))
        original, original_payload = copy.deepcopy(graph), copy.deepcopy(payload)
        result = expand_analysis(graph, payload)
        self.assertEqual({node["gid"] for node in result["graph"]["nodes"]}, {str(offset + gid) for gid in range(1, 7)})
        self.assertTrue(all(isinstance(edge["src"], str) and isinstance(edge["dst"], str) for edge in result["graph"]["edges"]))
        self.assertEqual(result["graph"]["expansion"]["records"][0]["dst"], str(offset + 6))
        self.assertEqual(graph, original)
        self.assertEqual(payload, original_payload)
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
