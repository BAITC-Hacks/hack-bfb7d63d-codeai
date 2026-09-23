"""Cross-feature contracts: real analysis -> API -> grounded answer/PDF/simulation."""
import copy
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from moneygraph.demo import generate_demo
from moneygraph.pipeline import analyze
from moneygraph.server import ApplicationState, make_handler, simulate_request


class RemovalCurveTests(unittest.TestCase):
    def setUp(self):
        self.analysis = {
            "nodes": [{"gid": g, "is_seed": g == 1, "priority_score": p}
                      for g, p in ((1, .1), (2, .9), (3, .9), (4, .2))],
            "edges": [{"src": a, "dst": b, "sum_kzt": 5000}
                      for a, b in ((1, 2), (2, 3), (3, 4))],
        }

    def test_curve_ranks_ties_by_exact_gid_and_counts_each_edge_once(self):
        original = copy.deepcopy(self.analysis)
        result = simulate_request(self.analysis, {"top_n": 2, "curve": True})
        self.assertEqual(result["removed"], [2, 3])
        self.assertEqual([p["n"] for p in result["curve"]], [0, 1, 2])
        self.assertEqual(result["curve"][1]["lost_reachable"], 2)
        self.assertEqual(result["curve"][2]["lost_reachable"], 1)
        self.assertEqual(result["observed_flow_removed_kzt"], 15000)
        self.assertEqual(self.analysis, original)

    def test_actual_count_is_explicit_for_small_graph(self):
        result = simulate_request(self.analysis, {"top_n": 20})
        self.assertEqual(result["requested_n"], 20)
        self.assertEqual(result["actual_n"], 4)
        self.assertEqual(result["after"]["n_nodes"], 0)

    def test_invalid_parameters_and_empty_graph_rejected(self):
        for body in ({"top_n": True}, {"top_n": 1.2}, {"top_n": 0},
                     {"top_n": 101}, {"top_n": 2, "gids": [1]},
                     {"gids": [1], "curve": "yes"}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                simulate_request(self.analysis, body)
        with self.assertRaises(ValueError):
            simulate_request({"nodes": [], "edges": []}, {"top_n": 1})


class InvestigationWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1] / ".build-temp"
        root.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix="workflow-", dir=root)
        path = Path(cls.temp.name)
        generate_demo(path / "data")
        cls.analysis = analyze(path / "data", path / "output", demo=True)
        cls.state = ApplicationState(cls.analysis, path / "output")
        handler = make_handler(cls.state)
        handler.log_message = lambda *args: None
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=5)
        cls.temp.cleanup()

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=30)
        try:
            conn.request(method, path, json.dumps(body) if body is not None else None,
                         {"Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_assistant_citations_resolve_to_current_analysis(self):
        gid = self.analysis["top_nodes"][0]["gid"]
        status, _, data = self.request("POST", "/api/assistant", {"question": "Неге бұл шот маңызды?", "gid": gid})
        self.assertEqual(status, 200, data)
        answer = json.loads(data)
        self.assertEqual(answer["mode"], "local_rules")
        self.assertTrue(answer["answer"])
        self.assertIn(str(gid), {str(c["gid"]) for c in answer["citations"]})
        self.assertEqual(self.request("POST", "/api/assistant", {"question": "Неге?", "gid": "999999999999999999"})[0], 400)

    def test_pdf_route_serves_real_document_and_rejects_unknown_id(self):
        gid = self.analysis["top_nodes"][0]["gid"]
        for path in ("/api/report.pdf", f"/api/report.pdf?gid={gid}"):
            status, headers, data = self.request("GET", path)
            self.assertEqual(status, 200, data[:300])
            self.assertEqual(headers["Content-Type"], "application/pdf")
            self.assertTrue(data.startswith(b"%PDF-"))
            self.assertGreater(len(data), 10000)
        for query in ("gid=999999999999999999", "gid=1&gid=2", "path=../../README.md"):
            self.assertEqual(self.request("GET", "/api/report.pdf?" + query)[0], 400)

    def test_top_n_api_and_replay_conservation(self):
        status, _, data = self.request("POST", "/api/simulate", {"top_n": 5, "curve": True})
        self.assertEqual(status, 200, data)
        result = json.loads(data)
        self.assertEqual(result["actual_n"], 5)
        self.assertEqual(len(result["curve"]), 6)
        self.assertEqual(result["curve"][-1]["after"], result["after"])
        replay = self.analysis["replay"]
        self.assertEqual(sum(d["n_tx"] for e in replay["edges"] for d in e["days"]), self.analysis["meta"]["n_transactions"])
        self.assertAlmostEqual(sum(d["sum_kzt"] for e in replay["edges"] for d in e["days"]), self.analysis["meta"]["total_kzt"], places=2)


if __name__ == "__main__":
    unittest.main()
