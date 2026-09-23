"""Analyst assertions, label provenance, and honest evaluation contracts."""

from copy import deepcopy
import csv
from io import StringIO
import json
import unittest

from moneygraph.review import (
    LABEL_FIELDS, ROLES, dataset_fingerprint, empty_casebook, evaluate_labels,
    export_casebook, labels_csv_template, parse_labels_csv, update_review,
)


IDS = ("-9223372036854775808", "9007199254740993", "9007199254740995",
       "9007199254740997", "9223372036854775807")


def analysis_fixture():
    roles = ("consolidator", "consolidator", "consolidator", "transit", "terminal")
    return {"nodes": [{"gid": gid, "role": role, "depth": index,
                       "is_seed": index == 0, "temporal": {"active_days": 2}}
                      for index, (gid, role) in enumerate(zip(IDS, roles))],
            "edges": [{"src": IDS[0], "dst": IDS[1], "sum_kzt": 15000.0, "n_tx": 2, "depth": 1}],
            "timeline": [{"date": "2026-07-01", "sum_kzt": 15000.0, "n_tx": 2}],
            "meta": {"period_start": "2026-07-01", "period_end": "2026-07-31", "runtime_seconds": 1}}


def label(gid=IDS[1], role="consolidator"):
    return {"gid": gid, "verified_role": role, "source_reference": "CASE-17 / reviewed record 1",
            "reviewer": "Analyst A"}


def supported(gid=IDS[1]):
    return {**label(gid), "status": "supported", "notes": "Reviewed the supplied document",
            "evidence": [{"kind": "ownership", "source_reference": "CASE-17 / document 2",
                          "summary": "Analyst assertion, not independently verified", "related_gids": [IDS[0]]}]}


class ReviewEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.analysis = analysis_fixture()

    def test_empty_labels_never_manufacture_accuracy_or_ground_truth(self):
        book = empty_casebook(self.analysis)
        metrics = book["evaluation"]
        self.assertEqual(book["labels"], [])
        self.assertEqual(book["reviews"], [])
        self.assertEqual(metrics["evaluated_count"], 0)
        self.assertEqual(metrics["coverage"], 0)
        self.assertIsNone(metrics["accuracy"])
        self.assertIsNone(metrics["macro_f1"])
        self.assertIsNone(metrics["baseline"]["accuracy"])
        self.assertIsNone(metrics["baseline"]["role"])
        for values in metrics["per_class"].values():
            for name in ("precision", "recall", "f1"):
                self.assertIsNone(values[name])
        self.assertEqual(metrics["benchmark_split"]["training_count"], 0)
        self.assertEqual(metrics["benchmark_split"]["held_out_status"], "unknown")
        self.assertEqual(metrics["label_independence"], "unknown")

    def test_confusion_metrics_are_calculated_only_on_supplied_subset(self):
        labels = [label(IDS[0]), label(IDS[1]), label(IDS[2], "transit"), label(IDS[3], "transit")]
        metrics = evaluate_labels(self.analysis, labels)
        self.assertEqual(metrics["evaluated_count"], 4)
        self.assertEqual(metrics["coverage"], .8)
        self.assertEqual(metrics["accuracy"], .75)
        self.assertEqual(metrics["baseline"]["accuracy"], .5)
        self.assertEqual(metrics["confusion_matrix"]["transit"]["consolidator"], 1)
        self.assertAlmostEqual(metrics["per_class"]["consolidator"]["precision"], 2 / 3)
        self.assertEqual(metrics["per_class"]["consolidator"]["recall"], 1)
        self.assertEqual(metrics["per_class"]["consolidator"]["f1"], .8)
        self.assertEqual(metrics["per_class"]["transit"]["precision"], 1)
        self.assertEqual(metrics["per_class"]["transit"]["recall"], .5)
        self.assertAlmostEqual(metrics["macro_f1"], (.8 + 2 / 3) / 2)
        self.assertEqual(len(metrics["confusion_matrix"]), 6)
        self.assertTrue(all(set(row) == set(ROLES) for row in metrics["confusion_matrix"].values()))
        self.assertIsNone(metrics["per_class"]["terminal"]["f1"])
        self.assertIn("not independent validation", metrics["notice"])

    def test_label_validation_rejects_ambiguous_ids_missing_provenance_and_duplicates(self):
        bad_labels = [
            [label(True)], [label(float(IDS[1]))], [label("1.0")], [label("9223372036854775808")],
            [label("1234")], [label(), label()], [label(role="organizer")],
            [{**label(), "source_reference": " "}], [{**label(), "reviewer": ""}],
            [{**label(), "extra": 1}], [{**label(), "source_reference": float("nan")}],
        ]
        original = deepcopy(self.analysis)
        for values in bad_labels:
            with self.subTest(values=values), self.assertRaises(ValueError):
                evaluate_labels(self.analysis, values)
        self.assertEqual(self.analysis, original)

    def test_ids_roundtrip_as_exact_strings_including_int64_limits(self):
        values = [label(int(IDS[0])), label(int(IDS[4]), "terminal")]
        book = update_review(self.analysis, None, {"action": "import_labels", "labels": values})
        serialized = export_casebook(book)
        restored = update_review(self.analysis, json.loads(serialized), {"action": "refresh"})
        self.assertEqual([row["gid"] for row in restored["labels"]], [IDS[0], IDS[4]])
        self.assertTrue(all(isinstance(row["gid"], str) for row in restored["reviews"]))
        self.assertEqual(restored["revision"], 1)

    def test_fingerprint_ignores_order_runtime_and_predictions_but_tracks_observations(self):
        original = dataset_fingerprint(self.analysis)
        changed = deepcopy(self.analysis)
        changed["nodes"].reverse()
        changed["nodes"][0]["role"] = "peripheral"
        changed["meta"]["runtime_seconds"] = 999
        self.assertEqual(dataset_fingerprint(changed), original)
        changed["edges"][0]["sum_kzt"] += 1
        self.assertNotEqual(dataset_fingerprint(changed), original)
        changed = deepcopy(self.analysis)
        changed["nodes"][0]["temporal"]["active_days"] += 1
        self.assertNotEqual(dataset_fingerprint(changed), original)

    def test_producer_source_fingerprint_is_validated_and_retained(self):
        self.analysis["meta"]["dataset_fingerprint"] = "AB" * 32
        self.assertEqual(dataset_fingerprint(self.analysis), "ab" * 32)
        self.assertEqual(empty_casebook(self.analysis)["fingerprint_scope"], "source_records")
        for bad in ("hash", 123, "g" * 64):
            self.analysis["meta"]["dataset_fingerprint"] = bad
            with self.assertRaises(ValueError):
                dataset_fingerprint(self.analysis)

    def test_review_requires_sources_and_explicit_supported_or_rejected_decision(self):
        for changes in ({"source_reference": ""}, {"reviewer": ""},
                        {"status": "in_review"}, {"verified_role": "transit"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                update_review(self.analysis, None, {**supported(), **changes})
        rejected = update_review(self.analysis, None, {**supported(), "status": "rejected", "verified_role": "transit"})
        self.assertEqual(rejected["reviews"][0]["status"], "rejected")
        self.assertEqual(rejected["evaluation"]["accuracy"], 0)
        with self.assertRaises(ValueError):
            update_review(self.analysis, None, {**supported(), "status": "rejected"})

    def test_review_without_role_label_does_not_invent_a_label(self):
        payload = supported()
        payload["verified_role"] = None
        book = update_review(self.analysis, None, payload)
        self.assertEqual(book["reviews"][0]["status"], "supported")
        self.assertEqual(book["labels"], [])
        self.assertIsNone(book["evaluation"]["accuracy"])

    def test_evidence_requires_source_summary_and_known_related_ids(self):
        good = supported()["evidence"][0]
        invalid = [{**good, "source_reference": ""}, {**good, "summary": ""},
                   {**good, "related_gids": ["unknown"]}, {**good, "related_gids": [IDS[0], IDS[0]]},
                   {**good, "kind": "confirmed_criminal"}, {**good, "verification": "bank_verified"},
                   {**good, "id": "forged"}, {**good, "name": "invented person"}]
        for evidence in invalid:
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                update_review(self.analysis, None, {**supported(), "evidence": [evidence]})
        with self.assertRaises(ValueError):
            update_review(self.analysis, None, {**supported(), "evidence": [good, good]})
        book = update_review(self.analysis, None, supported())
        evidence = book["reviews"][0]["evidence"][0]
        self.assertEqual(evidence["verification"], "analyst_asserted")
        self.assertTrue(evidence["id"].startswith("evidence-"))

    def test_failed_import_is_atomic_and_does_not_mutate_existing_casebook(self):
        book = update_review(self.analysis, None, supported())
        original = deepcopy(book)
        bad_batch = [label(IDS[0]), {**label(IDS[3], "transit"), "source_reference": ""}]
        with self.assertRaises(ValueError):
            update_review(self.analysis, book, {"action": "import_labels", "labels": bad_batch})
        self.assertEqual(book, original)
        with self.assertRaises(ValueError):
            update_review(self.analysis, book, {"action": "import_labels", "labels": [label(), label()]})
        self.assertEqual(book, original)

    def test_revision_prevents_stale_writes_and_refresh_does_not_create_history(self):
        book = update_review(self.analysis, None, {**supported(), "expected_revision": 0})
        for revision in (0, True, "1", None):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                update_review(self.analysis, book, {"gid": IDS[1], "notes": "new", "expected_revision": revision})
        refreshed = update_review(self.analysis, book, {"action": "refresh", "expected_revision": 1})
        self.assertEqual(refreshed, book)
        imported = update_review(self.analysis, book, {"action": "import_labels", "labels": []})
        self.assertEqual(imported, book)

    def test_audit_retains_before_and_after_evidence_without_aliasing_inputs(self):
        payload = supported()
        book = update_review(self.analysis, None, payload)
        original = deepcopy(book)
        changed = update_review(self.analysis, book, {"gid": IDS[1], "notes": "New document checked", "evidence": []})
        self.assertEqual(book, original)
        self.assertEqual(changed["revision"], 2)
        change = changed["history"][-1]["changes"][0]
        self.assertEqual(change["previous_record"]["notes"], payload["notes"])
        self.assertEqual(len(change["previous_record"]["evidence"]), 1)
        self.assertEqual(change["record"]["evidence"], [])
        self.assertEqual(change["record"]["notes"], "New document checked")
        self.assertIn("not_tamper_proof", changed["history"][-1]["provenance"])
        changed["reviews"][0]["notes"] = "Modified after update"
        self.assertEqual(change["record"]["notes"], "New document checked")

    def test_explicit_null_label_removes_it_without_removing_previous_audit(self):
        book = update_review(self.analysis, None, supported())
        changed = update_review(self.analysis, book, {"gid": IDS[1], "status": "in_review", "verified_role": None})
        self.assertEqual(changed["labels"], [])
        self.assertEqual(changed["evaluation"]["evaluated_count"], 0)
        self.assertIsNone(changed["evaluation"]["accuracy"])
        self.assertEqual(changed["history"][0]["changes"][0]["verified_role"], "consolidator")

    def test_import_upserts_preserve_notes_and_evidence_and_set_decision(self):
        book = update_review(self.analysis, None, supported())
        changed = update_review(self.analysis, book, {"action": "import_labels", "labels": [label(role="transit")]})
        self.assertEqual(len(changed["labels"]), 1)
        self.assertEqual(changed["reviews"][0]["status"], "rejected")
        self.assertEqual(changed["reviews"][0]["notes"], book["reviews"][0]["notes"])
        self.assertEqual(changed["reviews"][0]["evidence"], book["reviews"][0]["evidence"])

    def test_persistence_rejects_different_datasets_and_inconsistent_labels(self):
        book = update_review(self.analysis, None, supported())
        changed = deepcopy(self.analysis)
        changed["edges"][0]["sum_kzt"] += 5
        with self.assertRaisesRegex(ValueError, "different dataset"):
            update_review(changed, book, {"action": "refresh"})
        corrupted = deepcopy(book)
        corrupted["labels"][0]["verified_role"] = "transit"
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            update_review(self.analysis, corrupted, {"action": "refresh"})

    def test_rule_changes_preserve_prior_assertion_and_recompute_current_agreement(self):
        book = update_review(self.analysis, None, supported())
        changed = deepcopy(self.analysis)
        changed["nodes"][1]["role"] = "transit"
        refreshed = update_review(changed, book, {"action": "refresh"})
        self.assertEqual(refreshed["reviews"][0]["predicted_role_at_review"], "consolidator")
        self.assertEqual(refreshed["reviews"][0]["status"], "supported")
        self.assertEqual(refreshed["evaluation"]["accuracy"], 0)
        edited = update_review(changed, refreshed, {"gid": IDS[1], "notes": "Retain original assertion"})
        self.assertEqual(edited["reviews"][0]["predicted_role_at_review"], "consolidator")
        decided = update_review(changed, edited, {"gid": IDS[1], "status": "rejected"})
        self.assertEqual(decided["reviews"][0]["predicted_role_at_review"], "transit")
        self.assertEqual(decided["labels"][0]["verified_role"], "consolidator")

    def test_csv_template_is_blank_and_never_leaks_predicted_roles_as_labels(self):
        template = labels_csv_template(self.analysis)
        rows = list(csv.DictReader(StringIO(template)))
        self.assertEqual(tuple(rows[0]), LABEL_FIELDS)
        self.assertEqual({row["gid"] for row in rows}, set(IDS))
        self.assertTrue(all(row["verified_role"] == row["source_reference"] == row["reviewer"] == "" for row in rows))
        self.assertEqual(parse_labels_csv(self.analysis, "\ufeff" + template), [])

    def test_csv_quotes_newlines_and_filled_subset_are_preserved(self):
        stream = StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS, lineterminator="\n")
        writer.writeheader()
        filled = {**label(), "source_reference": 'Document "A", page 7\nchecked locally'}
        writer.writerow(filled)
        writer.writerow({"gid": IDS[4], "verified_role": "", "source_reference": "", "reviewer": ""})
        self.assertEqual(parse_labels_csv(self.analysis, stream.getvalue()), [filled])

    def test_csv_rejects_malformed_headers_rows_unknown_ids_and_partial_annotations(self):
        header = ",".join(LABEL_FIELDS) + "\n"
        invalid = ['"unterminated header', "gid,verified_role,source_reference\n", header + "1234,,,\n",
                   header + f"{IDS[1]},,,\n{IDS[1]},,,\n", header + f"{IDS[1]},transit,,\n",
                   header + f"{IDS[1]},transit,source,analyst,extra\n", header + f'{IDS[1]},transit,"unterminated',
                   header + f"{IDS[1]},transit,source\n"]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_labels_csv(self.analysis, text)


if __name__ == "__main__":
    unittest.main()
