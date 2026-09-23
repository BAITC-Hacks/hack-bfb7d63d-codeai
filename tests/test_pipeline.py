"""Data-contract and analytical-limit checks runnable with stdlib unittest."""

from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest

import pandas as pd

from moneygraph.demo import generate_demo
from moneygraph.pipeline import analyze


INPUT_FILES = ("nodes.parquet", "edges.parquet", "transactions.parquet")
ROLES = {"consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"}


class PipelineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp_root = Path(__file__).resolve().parents[1] / ".build-temp"
        temp_root.mkdir(exist_ok=True)
        cls.workspace = tempfile.TemporaryDirectory(prefix="aqsha-contract-", dir=temp_root)
        cls.root = Path(cls.workspace.name)
        cls.source = cls.root / "source"
        generate_demo(cls.source)
        cls.fingerprints_before = cls._fingerprints(cls.source)
        cls.result = analyze(cls.source, cls.root / "output", demo=True)
        cls.nodes = pd.read_parquet(cls.source / "nodes.parquet")
        cls.edges = pd.read_parquet(cls.source / "edges.parquet")
        cls.transactions = pd.read_parquet(cls.source / "transactions.parquet")

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    @staticmethod
    def _fingerprints(directory):
        return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                for name in INPUT_FILES}

    def _copy_source(self, suffix):
        target = self.root / suffix
        shutil.copytree(self.source, target)
        return target

    def test_demo_is_reproducible_and_contains_no_extra_attributes(self):
        other = self.root / "second_demo"
        generate_demo(other)
        columns = {
            "nodes.parquet": ["gid", "depth", "is_seed"],
            "edges.parquet": ["src", "dst", "sum_kzt", "n_tx", "depth"],
            "transactions.parquet": ["src", "dst", "date", "sum_kzt"],
        }
        for name in INPUT_FILES:
            with self.subTest(file=name):
                original = pd.read_parquet(self.source / name)
                pd.testing.assert_frame_equal(original, pd.read_parquet(other / name))
                self.assertEqual(list(original.columns), columns[name])
        self.assertGreaterEqual(len(self.nodes), 180)
        self.assertLessEqual(len(self.nodes), 300)

    def test_demo_depths_aggregates_and_filter_threshold_match_extract(self):
        tx = self.transactions
        self.assertTrue((tx.sum_kzt >= 5000).all())
        dates = pd.to_datetime(tx.date)
        self.assertTrue((dates.dt.year == 2026).all())
        self.assertTrue((dates.dt.month == 7).all())
        aggregated = tx.groupby(["src", "dst"], as_index=False).agg(
            sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"))
        actual = self.edges.drop(columns="depth").sort_values(["src", "dst"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(aggregated, actual)
        adjacency = defaultdict(set)
        for edge in self.edges.itertuples():
            adjacency[edge.src].add(edge.dst)
        distances = {int(row.gid): 0 for row in self.nodes.itertuples() if row.is_seed}
        queue = deque(sorted(distances))
        while queue:
            src = queue.popleft()
            for dst in adjacency[src]:
                if dst not in distances:
                    distances[dst] = distances[src] + 1
                    queue.append(dst)
        for node in self.nodes.itertuples():
            if node.gid in distances:
                self.assertEqual(node.depth, distances[node.gid])
            if node.depth == 4:
                self.assertFalse(adjacency[node.gid])

    def test_every_input_node_has_one_explainable_finite_role(self):
        output = pd.read_csv(self.root / "output" / "nodes_roles.csv")
        self.assertEqual(list(output.columns), ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"])
        self.assertEqual(len(output), len(self.nodes))
        self.assertTrue(output.gid.is_unique)
        self.assertEqual(set(output.gid), set(self.nodes.gid))
        self.assertFalse(output.isna().any().any())
        self.assertTrue(set(output.role).issubset(ROLES))
        self.assertEqual(set(output.role), ROLES, "Synthetic motifs should demonstrate all six roles")
        for field in ("role_score", "priority_score"):
            self.assertTrue(output[field].between(0, 1).all())
            self.assertTrue(output[field].map(math.isfinite).all())
        self.assertTrue(output.evidence.str.len().between(1, 200).all())
        self.assertTrue(output.evidence.str.contains(r"\d", regex=True).all())
        # Disallow NaN/Infinity anywhere, including extra JSON metrics.
        json.dumps(self.result, allow_nan=False)
        saved = json.loads((self.root / "output" / "analysis.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, self.result)

    def test_node_transfer_counts_reconcile_with_transactions(self):
        incoming = self.transactions.groupby("dst").size().to_dict()
        outgoing = self.transactions.groupby("src").size().to_dict()
        for node in self.result["nodes"]:
            gid = int(node["gid"])
            self.assertEqual(node["in_tx"], incoming.get(gid, 0))
            self.assertEqual(node["out_tx"], outgoing.get(gid, 0))
        self.assertEqual(sum(n["in_tx"] for n in self.result["nodes"]), len(self.transactions))
        self.assertEqual(sum(n["out_tx"] for n in self.result["nodes"]), len(self.transactions))

    def test_censored_boundary_and_unreliable_ratios_are_explicit(self):
        boundary = [node for node in self.result["nodes"]
                    if node["depth"] == 4 and node["out_degree"] == 0]
        self.assertGreater(len(boundary), 0)
        for node in boundary:
            self.assertNotEqual(node["role"], "terminal")
            self.assertIn("boundary_censored", node["flags"])
        for node in self.result["nodes"]:
            if node["is_seed"]:
                self.assertIsNone(node["pass_through"])
                self.assertIn("seed_inflow_incomplete", node["flags"])
            if node["in_kzt"] == 0 or node["out_kzt"] > node["in_kzt"]:
                self.assertIsNone(node["pass_through"])
            if node["out_kzt"] > node["in_kzt"]:
                self.assertIn("outflow_exceeds_observed_inflow", node["flags"])
        isolates = [node for node in self.result["nodes"]
                    if node["in_degree"] == node["out_degree"] == 0]
        self.assertGreaterEqual(len([node for node in isolates if node["is_seed"]]), 4)
        self.assertTrue(all("isolated" in node["flags"] for node in isolates))

    def test_clusters_match_membership_and_observed_internal_turnover(self):
        nodes = self.result["nodes"]
        clusters = self.result["clusters"]
        membership = {node["gid"]: node["cluster_id"] for node in nodes}
        cluster_ids = {cluster["cluster_id"] for cluster in clusters}
        self.assertEqual(len(cluster_ids), len(clusters))
        self.assertEqual(cluster_ids, set(membership.values()))
        self.assertEqual(sum(cluster["n_nodes"] for cluster in clusters), len(nodes))
        for cluster in clusters:
            cid = cluster["cluster_id"]
            members = [node for node in nodes if node["cluster_id"] == cid]
            self.assertEqual(cluster["n_nodes"], len(members))
            self.assertEqual(cluster["n_seed"], sum(node["is_seed"] for node in members))
            observed = sum(float(row.sum_kzt) for row in self.edges.itertuples()
                           if membership[row.src] == cid and membership[row.dst] == cid)
            self.assertAlmostEqual(cluster["sum_kzt_internal"], observed, places=5)
            self.assertTrue(set(cluster["top_gids"]).issubset({node["gid"] for node in members}))
            self.assertTrue(cluster["hypothesis"].strip())
        csv = pd.read_csv(self.root / "output" / "clusters.csv")
        self.assertEqual(list(csv.columns), ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"])
        self.assertEqual(set(csv.cluster_id), cluster_ids)

    def test_ranking_is_unique_ordered_and_grounded_in_node_results(self):
        ranked = pd.read_csv(self.root / "output" / "top_nodes.csv")
        self.assertEqual(list(ranked.columns), ["rank", "gid", "role", "priority_score", "why"])
        self.assertGreaterEqual(len(ranked), 20)
        self.assertTrue(ranked.gid.is_unique)
        self.assertEqual(ranked["rank"].tolist(), list(range(1, len(ranked) + 1)))
        self.assertTrue(ranked.priority_score.is_monotonic_decreasing)
        by_id = {node["gid"]: node for node in self.result["nodes"]}
        for row in ranked.itertuples(index=False):
            self.assertIn(row.gid, by_id)
            self.assertEqual(row.role, by_id[row.gid]["role"])
            self.assertAlmostEqual(row.priority_score, by_id[row.gid]["priority_score"], places=6)
            self.assertTrue(str(row.why).strip())

    def test_repeat_analysis_is_deterministic_and_never_rewrites_inputs(self):
        other = analyze(self.source, self.root / "repeat", demo=True)
        for name in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv"):
            self.assertEqual((self.root / "output" / name).read_bytes(),
                             (self.root / "repeat" / name).read_bytes())
        for key in ("nodes", "edges", "clusters", "top_nodes", "timeline", "role_counts", "quality"):
            self.assertEqual(self.result[key], other[key])
        self.assertEqual(self.fingerprints_before, self._fingerprints(self.source))

    def test_unknown_edge_endpoint_is_rejected(self):
        source = self._copy_source("orphan_edge")
        edges = pd.read_parquet(source / "edges.parquet")
        edges.loc[0, "src"] = 999_999_999
        edges.to_parquet(source / "edges.parquet", index=False)
        with self.assertRaises(ValueError):
            analyze(source, self.root / "orphan_edge_output")

    def test_unknown_transaction_endpoint_is_rejected(self):
        source = self._copy_source("orphan_transaction")
        tx = pd.read_parquet(source / "transactions.parquet")
        tx.loc[0, "dst"] = 999_999_999
        tx.to_parquet(source / "transactions.parquet", index=False)
        with self.assertRaises(ValueError):
            analyze(source, self.root / "orphan_transaction_output")

    def test_invalid_amounts_dates_and_duplicate_ids_are_rejected(self):
        mutations = {
            "nan_amount": ("transactions.parquet", "sum_kzt", float("nan")),
            "negative_amount": ("transactions.parquet", "sum_kzt", -5000),
            "infinite_amount": ("transactions.parquet", "sum_kzt", float("inf")),
            "invalid_date": ("transactions.parquet", "date", "not-a-date"),
            "fractional_gid": ("nodes.parquet", "gid", 100001.5),
        }
        for label, (name, column, value) in mutations.items():
            with self.subTest(case=label):
                source = self._copy_source(label)
                frame = pd.read_parquet(source / name)
                if label == "invalid_date":
                    frame[column] = frame[column].astype(str)
                elif label in {"nan_amount", "infinite_amount", "fractional_gid"}:
                    frame[column] = frame[column].astype(float)
                frame.loc[0, column] = value
                frame.to_parquet(source / name, index=False)
                with self.assertRaises(ValueError):
                    analyze(source, self.root / (label + "_output"))
        source = self._copy_source("duplicate_id")
        frame = pd.read_parquet(source / "nodes.parquet")
        frame.loc[0, "gid"] = frame.loc[1, "gid"]
        frame.to_parquet(source / "nodes.parquet", index=False)
        with self.assertRaises(ValueError):
            analyze(source, self.root / "duplicate_output")

    def test_edge_transaction_disagreement_is_rejected(self):
        source = self._copy_source("aggregate_mismatch")
        edges = pd.read_parquet(source / "edges.parquet")
        edges.loc[0, "sum_kzt"] += 5000
        edges.to_parquet(source / "edges.parquet", index=False)
        with self.assertRaises(ValueError):
            analyze(source, self.root / "aggregate_mismatch_output")

    def test_int64_gids_remain_exact_in_csv_and_browser_safe_json(self):
        source = self._copy_source("large_gids")
        offset = 9_007_199_254_740_992
        for name in INPUT_FILES:
            frame = pd.read_parquet(source / name)
            for column in ("gid", "src", "dst"):
                if column in frame:
                    frame[column] = frame[column] + offset
            frame.to_parquet(source / name, index=False)
        output = self.root / "large_gids_output"
        result = analyze(source, output, demo=True)
        expected = {int(gid) + offset for gid in self.nodes.gid}
        roles = pd.read_csv(output / "nodes_roles.csv", dtype={"gid": "int64"})
        self.assertEqual(set(roles.gid), expected)
        self.assertEqual({int(node["gid"]) for node in result["nodes"]}, expected)
        self.assertTrue(all(isinstance(node["gid"], str) for node in result["nodes"]))
        for edge in result["edges"]:
            self.assertIsInstance(edge["src"], str)
            self.assertIsInstance(edge["dst"], str)
            self.assertIn(int(edge["src"]), expected)
            self.assertIn(int(edge["dst"]), expected)
        for node in result["top_nodes"]:
            self.assertIsInstance(node["gid"], str)
            self.assertIn(int(node["gid"]), expected)
        for cluster in result["clusters"]:
            self.assertTrue(all(isinstance(gid, str) for gid in cluster["top_gids"]))
        for request in result["quality"]["requests"]:
            self.assertIsInstance(request["gid"], str)


if __name__ == "__main__":
    unittest.main()
