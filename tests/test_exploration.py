"""Exact directed exploration, page continuation and honest finite scope."""

import copy
import unittest
from unittest.mock import patch

from moneygraph.exploration import explore_paths


def graph(arcs, offset=0):
    ids = sorted({gid for arc in arcs for gid in arc})
    return {"nodes": [{"gid": offset + gid, "is_seed": gid == ids[0]} for gid in ids],
            "edges": [{"src": offset + src, "dst": offset + dst, "sum_kzt": 5000, "n_tx": 1}
                      for src, dst in arcs]}


BRANCHES = [(1, 2), (1, 3), (2, 4), (3, 4), (4, 1)]


class ExplorationTests(unittest.TestCase):
    def test_returns_actual_directed_paths_and_gross_observed_edge_volume(self):
        data = graph(BRANCHES)
        result = explore_paths(data, {"start_gid": 1, "end_gid": 4, "max_hops": 3})
        self.assertEqual([item["gids"] for item in result["routes"]], [[1, 2, 4], [1, 3, 4]])
        self.assertTrue(result["complete_within_scope"])
        self.assertIsNone(result["next_cursor"])
        self.assertTrue(all(item["observed_volume_kzt"] == 10_000 for item in result["routes"]))
        self.assertTrue(all(not item["temporal_order_verified"] for item in result["routes"]))

    def test_cycles_close_at_requested_start_including_a_seed_and_self_cycle(self):
        result = explore_paths(graph(BRANCHES), {"start_gid": 1, "end_gid": 1, "kind": "cycles", "max_hops": 3})
        self.assertEqual([item["gids"] for item in result["routes"]], [[1, 2, 4, 1], [1, 3, 4, 1]])
        self_cycle = explore_paths(graph([(1, 1)]), {"start_gid": 1, "kind": "cycles", "max_hops": 1})
        self.assertEqual(self_cycle["routes"][0]["gids"], [1, 1])
        with self.assertRaises(ValueError):
            explore_paths(graph(BRANCHES), {"start_gid": 1, "end_gid": 4, "kind": "cycles"})

    def test_budgeted_pages_resume_without_missing_or_duplicate_paths(self):
        data = graph(BRANCHES)
        scope = {"start_gid": 1, "max_hops": 4}
        complete = explore_paths(data, {**scope, "max_results": 100, "budget": 1000})
        cursor, gathered, last = None, [], None
        for _ in range(100):
            result = explore_paths(data, {**scope, "max_results": 1, "budget": 1, **({"cursor": cursor} if cursor else {})})
            self.assertLessEqual(result["limits"]["budget_used"], 1)
            self.assertLessEqual(len(result["routes"]), 1)
            gathered.extend(result["routes"])
            last = result
            if result["complete_within_scope"]:
                break
            cursor = result["next_cursor"]
            self.assertTrue(cursor)
        else:
            self.fail("Finite search did not complete after bounded resumptions")
        self.assertEqual(gathered, complete["routes"])
        self.assertEqual(len({row["id"] for row in gathered}), len(gathered))
        self.assertEqual(last["limits"]["cumulative_work"], complete["limits"]["budget_used"])

    def test_cycle_pagination_and_changed_page_budget_preserve_scope(self):
        data = graph(BRANCHES)
        scope = {"start_gid": 1, "kind": "cycles", "max_hops": 3}
        first = explore_paths(data, {**scope, "budget": 1})
        self.assertFalse(first["complete_within_scope"])
        second = explore_paths(data, {**scope, "budget": 100, "max_results": 100, "cursor": first["cursor"]})
        self.assertEqual(len(second["routes"]), 2)
        self.assertTrue(second["complete_within_scope"])

    def test_cursor_rejects_tampering_scope_changes_graph_changes_and_restart(self):
        data = graph(BRANCHES)
        payload = {"start_gid": 1, "kind": "paths", "max_hops": 3, "budget": 1}
        cursor = explore_paths(data, payload)["next_cursor"]
        with self.assertRaises(ValueError):
            explore_paths(data, {**payload, "cursor": ("A" if cursor[0] != "A" else "B") + cursor[1:]})
        with self.assertRaises(ValueError):
            explore_paths(data, {**payload, "max_hops": 4, "cursor": cursor})
        altered = copy.deepcopy(data)
        altered["edges"][0]["sum_kzt"] = 7000
        with self.assertRaises(ValueError):
            explore_paths(altered, {**payload, "cursor": cursor})
        with patch("moneygraph.exploration._CURSOR_SECRET", b"replacement-process-secret"):
            with self.assertRaises(ValueError):
                explore_paths(data, {**payload, "cursor": cursor})

    def test_exact_shortest_path_is_not_limited_to_twelve_hops(self):
        data = graph([(gid, gid + 1) for gid in range(1, 22)])
        result = explore_paths(data, {"start_gid": 1, "end_gid": 22, "kind": "shortest", "max_hops": 4})
        self.assertEqual(result["shortest_path"]["length"], 21)
        self.assertIsNone(result["scope"]["max_hops"])
        self.assertFalse(result["limits"]["budget_applies"])
        self.assertTrue(result["complete_within_scope"])
        scoped = explore_paths(data, {"start_gid": 1, "end_gid": 22, "max_hops": 12})
        self.assertEqual(scoped["routes"], [])
        self.assertTrue(scoped["complete_within_scope"])

    def test_shortest_paths_are_deterministic_and_disconnected_direction_is_respected(self):
        data = graph(BRANCHES)
        reversed_data = {"nodes": list(reversed(data["nodes"])), "edges": list(reversed(data["edges"]))}
        payload = {"start_gid": 1, "end_gid": 4, "kind": "shortest"}
        self.assertEqual(explore_paths(data, payload), explore_paths(reversed_data, payload))
        disconnected = explore_paths(graph([(1, 2), (3, 4)]), {"start_gid": 1, "end_gid": 4, "kind": "shortest"})
        self.assertIsNone(disconnected["shortest_path"])
        identity = explore_paths(data, {"start_gid": 1, "end_gid": 1, "kind": "shortest"})
        self.assertEqual(identity["shortest_path"]["length"], 0)

    def test_large_ids_are_lossless_and_graph_not_mutated(self):
        offset = 9_007_199_254_740_992
        data = graph(BRANCHES, offset)
        before = copy.deepcopy(data)
        result = explore_paths(data, {"start_gid": str(offset + 1), "end_gid": str(offset + 4)})
        self.assertEqual(result["routes"][0]["gids"], [str(offset + 1), str(offset + 2), str(offset + 4)])
        self.assertTrue(all(isinstance(edge["src"], str) and isinstance(edge["dst"], str)
                            for row in result["routes"] for edge in row["edges"]))
        self.assertEqual(data, before)

    def test_invalid_parameters_and_unknown_nodes_are_rejected(self):
        for changes in ({"start_gid": True}, {"start_gid": 1.5}, {"start_gid": "1e18"}, {"start_gid": 999},
                        {"max_hops": 13}, {"max_hops": 0}, {"max_results": 101}, {"budget": 100_001},
                        {"budget": 0}, {"kind": "all"}, {"end_gid": 999}, {"kind": "shortest"},
                        {"unexpected": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                explore_paths(graph(BRANCHES), {"start_gid": 1, **changes})


if __name__ == "__main__":
    unittest.main()
