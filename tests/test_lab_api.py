"""End-to-end local HTTP contracts for the investigation workspace."""
import copy
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from moneygraph.demo import generate_demo
from moneygraph.pipeline import analyze
from moneygraph.server import ApplicationState, make_handler


class LabApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path(__file__).resolve().parents[1] / ".build-temp"
        scratch.mkdir(exist_ok=True)
        cls.workspace = tempfile.TemporaryDirectory(dir=scratch)
        cls.root = Path(cls.workspace.name)
        generate_demo(cls.root / "input")
        cls.analysis = analyze(cls.root / "input", cls.root / "output", demo=True)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.storage = tempfile.TemporaryDirectory(dir=self.root)
        self.state = ApplicationState(copy.deepcopy(self.analysis), self.root / "output", self.storage.name)
        handler = make_handler(self.state)
        handler.log_message = lambda *args: None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)
        self.storage.cleanup()

    def request(self, method, path, payload=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            connection.request(method, path, body=json.dumps(payload) if payload is not None else None,
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if "application/json" in response.getheader("Content-Type", "") else raw
        finally:
            connection.close()

    def test_review_roundtrip_and_stale_write_preserves_saved_labels(self):
        status, empty = self.request("GET", "/api/reviews")
        self.assertEqual(status, 200)
        self.assertIsNone(empty["evaluation"]["accuracy"])
        node = self.analysis["nodes"][0]
        payload = {"action": "import_labels", "expected_revision": 0, "labels": [
            {"gid": str(node["gid"]), "verified_role": node["role"],
             "reviewer": "Synthetic test reviewer", "source_reference": "synthetic-test-only"}]}
        status, saved = self.request("POST", "/api/reviews", payload)
        self.assertEqual(status, 200)
        self.assertEqual(saved["evaluation"]["evaluated_count"], 1)
        self.assertEqual(saved["evaluation"]["accuracy"], 1)
        self.assertEqual(self.request("POST", "/api/reviews", payload)[0], 400)
        reopened = ApplicationState(self.analysis, self.root / "output", self.storage.name)
        self.assertEqual(reopened.reviews()["labels"], saved["labels"])
        self.assertEqual(reopened.reviews()["revision"], 1)
        self.assertEqual(self.request("GET", "/api/reviews/export.json")[1]["labels"], saved["labels"])

    def test_casebook_is_scoped_to_input_fingerprint(self):
        node = self.analysis["nodes"][0]
        self.state.reviews({"gid": str(node["gid"]), "status": "in_review", "reviewer": "test"})
        other = copy.deepcopy(self.analysis)
        other["meta"]["dataset_fingerprint"] = "a" * 64
        self.assertEqual(ApplicationState(other, self.root / "output", self.storage.name).reviews()["revision"], 0)

    def test_stale_browser_cannot_write_review_or_overlay_to_changed_dataset(self):
        old_fingerprint = self.analysis["meta"]["dataset_fingerprint"]
        self.state.analysis["meta"]["dataset_fingerprint"] = "b" * 64
        status, _ = self.request("POST", "/api/reviews", {"gid": str(self.analysis["nodes"][0]["gid"]),
            "status": "in_review", "reviewer": "test", "expected_dataset_fingerprint": old_fingerprint})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/expand", {"incremental_disjoint": True, "transactions": [],
            "expected_dataset_fingerprint": old_fingerprint})
        self.assertEqual(status, 400)
        self.assertEqual(list(Path(self.storage.name).iterdir()), [])

    def test_csv_template_contains_exact_ids_and_no_manufactured_labels(self):
        status, raw = self.request("GET", "/api/reviews/template.csv")
        self.assertEqual(status, 200)
        from moneygraph.review import parse_labels_csv
        self.assertEqual(parse_labels_csv(self.analysis, raw.decode("utf-8-sig")), [])
        self.assertIn(str(self.analysis["nodes"][0]["gid"]), raw.decode("utf-8-sig"))

    def test_supplementary_upload_persists_deduplicates_and_supports_new_path(self):
        start = str(self.analysis["nodes"][0]["gid"])
        new_gid = "9223372036854775000"
        payload = {"incremental_disjoint": True, "transactions": [{"src": start, "dst": new_gid,
            "date": "2026-08-01", "sum_kzt": 1000, "source_reference": "synthetic-test-only", "transaction_id": "T1"}]}
        self.assertEqual(self.request("GET", "/api/expansion")[1], {"available": False})
        status, result = self.request("POST", "/api/expand", payload)
        self.assertEqual(status, 200, result)
        count = result["graph"]["meta"]["n_transactions"]
        status, repeated = self.request("POST", "/api/expand", payload)
        self.assertEqual(status, 200, repeated)
        self.assertEqual(repeated["graph"]["meta"]["n_transactions"], count)
        status, path = self.request("POST", "/api/explore", {"scope": "expanded", "kind": "shortest",
                                                          "start_gid": start, "end_gid": new_gid})
        self.assertEqual(status, 200, path)
        self.assertTrue(path["complete_within_scope"])
        self.assertIn(new_gid, json.dumps(path))
        reopened = ApplicationState(self.analysis, self.root / "output", self.storage.name)
        self.assertEqual(reopened.expansion()["graph"], repeated["graph"])
        self.assertEqual(self.state.snapshot()[0], self.analysis)

    def test_invalid_upload_does_not_create_overlay(self):
        status, _ = self.request("POST", "/api/expand", {"incremental_disjoint": False, "transactions": []})
        self.assertEqual(status, 400)
        self.assertEqual(self.request("GET", "/api/expansion")[1], {"available": False})
        self.assertEqual(self.request("POST", "/api/explore", {"scope": "expanded", "start_gid": "1"})[0], 400)

    def test_model_status_unavailable_and_data_limit_guard(self):
        with patch("moneygraph.local_llm.model_status", return_value={"available": False, "mode": "local_llm"}):
            self.assertFalse(self.request("GET", "/api/assistant/status")[1]["available"])
        from moneygraph.local_llm import LocalModelUnavailable
        with patch("moneygraph.local_llm.answer_with_model", side_effect=LocalModelUnavailable("offline")):
            self.assertEqual(self.request("POST", "/api/assistant", {"mode": "local_llm", "question": "Explain"})[0], 503)
        status, answer = self.request("POST", "/api/assistant", {"mode": "local_llm", "question": "Нақты ұйымдастырушының аты-жөні кім?"})
        self.assertEqual(status, 200)
        self.assertEqual(answer["mode"], "local_rules_guard")

    def test_recovery_http_is_an_assumption_and_preserves_analysis(self):
        status, result = self.request("POST", "/api/recovery", {"top_n": 5, "replacement_fraction": 1})
        self.assertEqual(status, 200)
        self.assertEqual(result["mode"], "assumption_scenario")
        self.assertEqual(result["scenario"], result["baseline"])
        self.assertEqual(self.state.snapshot()[0], self.analysis)


if __name__ == "__main__":
    unittest.main()
