import copy
import json
import os
import unittest
from unittest.mock import patch

from moneygraph.local_llm import _base_url, answer_with_model, evidence_pack, model_status, LocalModelUnavailable
from moneygraph.recovery import recovery_scenario


def example():
    return {"nodes": [{"gid": 1, "is_seed": True, "priority_score": .1},
                      {"gid": 2, "is_seed": False, "priority_score": .9},
                      {"gid": 3, "is_seed": False, "priority_score": .2}],
            "edges": [{"src": 1, "dst": 2, "sum_kzt": 10000}, {"src": 2, "dst": 3, "sum_kzt": 5000}]}


class RecoveryTests(unittest.TestCase):
    def test_zero_and_full_recovery_are_explicit_not_observed_edges(self):
        analysis = example()
        before = copy.deepcopy(analysis)
        zero = recovery_scenario(analysis, {"top_n": 1, "replacement_fraction": 0})
        full = recovery_scenario(analysis, {"top_n": 1, "replacement_fraction": 1})
        self.assertEqual(zero["scenario"], zero["post_removal"])
        self.assertEqual(full["scenario"], full["baseline"])
        self.assertEqual(full["observed_survivors_reconnected"], 1)
        self.assertTrue(all(e["synthetic"] for e in full["assumed_edges"]))
        self.assertEqual(analysis, before)

    def test_partial_recovery_has_no_false_complete_path(self):
        result = recovery_scenario(example(), {"gids": [2], "replacement_fraction": .5})
        self.assertEqual(len(result["assumed_edges"]), 1)
        self.assertEqual(result["observed_survivors_reconnected"], 0)
        self.assertEqual(result["reference_turnover_kzt"], 10000)

    def test_bad_fraction_rejected(self):
        for value in (True, -1, 2, "1", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                recovery_scenario(example(), {"replacement_fraction": value})

    def test_full_recovery_replaces_isolated_seed(self):
        analysis = example()
        analysis["nodes"].append({"gid": 4, "is_seed": True})
        result = recovery_scenario(analysis, {"gids": [4], "replacement_fraction": 1})
        self.assertEqual(result["scenario"], result["baseline"])
        self.assertEqual(len(result["hypothetical_nodes"]), 1)


class LocalModelTests(unittest.TestCase):
    def test_missing_identity_is_answered_without_model_inference(self):
        with patch("moneygraph.local_llm._request") as inference:
            result = answer_with_model(example(), "Нақты ұйымдастырушының аты-жөні кім?")
        inference.assert_not_called()
        self.assertTrue(result["guarded"])
        self.assertEqual(result["mode"], "local_rules_guard")
        self.assertEqual(result["citations"], [])

    def test_malformed_status_returns_unavailable(self):
        for response in ([], {"data": [None]}, {"data": [{}]}, {"data": "bad"}):
            with patch("moneygraph.local_llm._request", return_value=response):
                self.assertFalse(model_status()["available"])

    def test_remote_endpoints_credentials_and_redirect_targets_not_allowed(self):
        for address in ("https://example.com", "http://1.2.3.4:8766", "http://127.0.0.1:8766/path", "http://x@localhost:8766"):
            with self.subTest(address=address), patch.dict(os.environ, {"AQSHA_LLM_URL": address}), self.assertRaises(ValueError):
                _base_url()

    def test_evidence_has_only_exact_known_ids_and_explicit_limits(self):
        analysis = example()
        pack, refs = evidence_pack(analysis, "Compare GID 1 and GID 2")
        self.assertEqual({r["gid"] for r in refs.values()}, {1, 2})
        self.assertIn("hypotheses", pack["limits"])
        with self.assertRaises(ValueError):
            evidence_pack(analysis, "GID 999")

    def test_generation_returns_only_known_citations_and_labels_model_mode(self):
        fake = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"answer": "Review [N1]", "refs": ["N1"]})}}]}
        with patch("moneygraph.local_llm._request", return_value=fake):
            result = answer_with_model(example(), "Explain GID 2")
        self.assertEqual(result["mode"], "local_llm")
        self.assertEqual(result["citations"][0]["gid"], 2)

    def test_bad_generated_references_and_truncation_are_rejected(self):
        for answer, refs, finish in (("[N9]", ["N9"], "stop"), ("999999999999999", ["N1"], "stop"),
                                     ("text", [], "length"), (123, [], "stop"), ("x" * 501, [], "stop")):
            fake = {"choices": [{"finish_reason": finish, "message": {"content": json.dumps({"answer": answer, "refs": refs})}}]}
            with patch("moneygraph.local_llm._request", return_value=fake), self.assertRaises(LocalModelUnavailable):
                answer_with_model(example(), "Explain GID 2")

    def test_invented_numeric_claim_falls_back_to_explicit_rules(self):
        fake = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(
            {"answer": "[N1] received an unseen 3987.23 KZT transfer.", "refs": ["N1"]})}}]}
        with patch("moneygraph.local_llm._request", return_value=fake), \
             patch("moneygraph.assistant.answer_question", return_value={"answer": "Known evidence only", "citations": [], "suggestions": []}):
            result = answer_with_model(example(), "Explain GID 2")
        self.assertEqual(result["mode"], "local_rules_guard")
        self.assertEqual(result["answer"], "Known evidence only")


if __name__ == "__main__":
    unittest.main()
