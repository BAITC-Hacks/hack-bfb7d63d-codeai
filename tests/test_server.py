"""Structural simulation and local API behavior checks."""

from __future__ import annotations

import copy
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from moneygraph.server import ApplicationState, make_handler, simulate


def example_analysis():
    return {
        "nodes": [{"gid": gid, "is_seed": gid in {1, 6}} for gid in range(1, 8)],
        "edges": [
            {"src": 1, "dst": 2, "sum_kzt": 10_000},
            {"src": 2, "dst": 3, "sum_kzt": 20_000},
            {"src": 5, "dst": 2, "sum_kzt": 30_000},
            {"src": 3, "dst": 2, "sum_kzt": 40_000},
            {"src": 3, "dst": 4, "sum_kzt": 50_000},
        ],
    }


class SimulationTests(unittest.TestCase):
    def test_bridge_removal_uses_directed_reachability_and_does_not_mutate_input(self):
        analysis = example_analysis()
        original = copy.deepcopy(analysis)
        result = simulate(analysis, [2])
        self.assertEqual(result["before"], {
            "n_nodes": 7, "n_edges": 5, "components": 3,
            "largest_component": 5, "reachable_from_seeds": 5,
        })
        self.assertEqual(result["after"], {
            "n_nodes": 6, "n_edges": 1, "components": 5,
            "largest_component": 2, "reachable_from_seeds": 2,
        })
        self.assertEqual(result["lost_reachable"], 2)
        self.assertEqual(result["observed_flow_removed_kzt"], 100_000)
        self.assertEqual(analysis, original)
        self.assertTrue(result["note"].strip())

    def test_isolate_removal_does_not_count_as_lost_reachability(self):
        result = simulate(example_analysis(), [7])
        self.assertEqual(result["after"]["n_nodes"], 6)
        self.assertEqual(result["after"]["components"], 2)
        self.assertEqual(result["after"]["reachable_from_seeds"], 5)
        self.assertEqual(result["lost_reachable"], 0)
        self.assertEqual(result["observed_flow_removed_kzt"], 0)

    def test_seed_removal_excludes_removed_node_from_lost_count(self):
        result = simulate(example_analysis(), [1])
        self.assertEqual(result["after"]["reachable_from_seeds"], 1)
        self.assertEqual(result["lost_reachable"], 3)

    def test_removal_of_all_nodes_produces_finite_zero_snapshot(self):
        result = simulate(example_analysis(), list(range(1, 8)))
        self.assertEqual(result["after"], {
            "n_nodes": 0, "n_edges": 0, "components": 0,
            "largest_component": 0, "reachable_from_seeds": 0,
        })
        self.assertEqual(result["lost_reachable"], 0)
        self.assertEqual(result["observed_flow_removed_kzt"], 150_000)
        json.dumps(result, allow_nan=False)

    def test_decimal_strings_preserve_int64_gids_and_duplicates_count_once(self):
        gid = 9_007_199_254_740_995
        analysis = {
            "nodes": [{"gid": gid, "is_seed": True}, {"gid": gid + 1, "is_seed": False}],
            "edges": [{"src": gid, "dst": gid + 1, "sum_kzt": 5000}],
        }
        result = simulate(analysis, [str(gid), gid])
        # JSON string output prevents JavaScript from rounding an int64 GID.
        self.assertEqual(result["removed"], [str(gid)])
        self.assertEqual(result["lost_reachable"], 1)
        self.assertEqual(result["observed_flow_removed_kzt"], 5000)

    def test_invalid_or_unknown_gids_are_rejected(self):
        for invalid in (None, [], [999], [True], [2.5], ["2.0"], ["x"], [1] * 101):
            with self.subTest(gids=invalid):
                with self.assertRaises(ValueError):
                    simulate(example_analysis(), invalid)


class LocalApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp_root = Path(__file__).resolve().parents[1] / ".build-temp"
        temp_root.mkdir(exist_ok=True)
        cls.workspace = tempfile.TemporaryDirectory(prefix="aqsha-api-", dir=temp_root)
        cls.output = Path(cls.workspace.name)
        (cls.output / "nodes_roles.csv").write_text("gid,role\n1,peripheral\n", encoding="utf-8")
        cls.state = ApplicationState(example_analysis(), cls.output)
        handler = make_handler(cls.state)
        handler.log_message = lambda *args: None
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.server.daemon_threads = True
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=5)
        cls.workspace.cleanup()

    def request(self, method, path, payload=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = dict(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        try:
            conn.request(method, path, body=body, headers=request_headers)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_analysis_and_simulation_have_coherent_api_contract(self):
        status, headers, body = self.request("GET", "/api/analysis")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), example_analysis())
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        status, _, body = self.request("POST", "/api/simulate", {"gids": ["2"]})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["lost_reachable"], 2)

    def test_rejected_request_preserves_current_analysis(self):
        for path, payload in (("/api/simulate", {"gids": [999]}),
                              ("/api/analyze", {"files": {"nodes.parquet": ""}})):
            status, _, body = self.request("POST", path, payload)
            self.assertEqual(status, 400)
            self.assertTrue(json.loads(body)["error"])
        self.assertEqual(self.state.snapshot()[0], example_analysis())

    def test_exports_download_and_arbitrary_files_do_not(self):
        status, headers, body = self.request("GET", "/api/download/nodes_roles.csv")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(body, (self.output / "nodes_roles.csv").read_bytes())
        for path in ("/api/download/../../README.md", "/../README.md", "/data/nodes.parquet"):
            status, _, _ = self.request("GET", path)
            self.assertEqual(status, 404)

    def test_foreign_host_and_cross_origin_post_are_rejected(self):
        status, _, _ = self.request("GET", "/api/analysis", headers={"Host": "example.com"})
        self.assertEqual(status, 403)
        status, _, _ = self.request("POST", "/api/simulate", {"gids": [2]},
                                    headers={"Origin": "https://example.com"})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
