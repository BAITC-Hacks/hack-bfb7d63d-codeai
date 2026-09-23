"""Expert labels stay separate from predictions, missing labels and raw data."""

import csv
from io import StringIO

import pandas as pd
import pytest

from moneymap.demo import create_demo_frames
from moneymap.evaluation import (
    CSV_COLUMNS, dataset_fingerprint, evaluate_reviews, make_review,
    ranked_gids, read_review_csv, review_csv,
)


DIGEST = "a" * 64
IDS = ["100000000000000001", "100000000000000003", "100000000000000005"]


@pytest.fixture
def predictions():
    return pd.DataFrame({"gid": pd.Series([int(gid) for gid in IDS], dtype="int64"),
                         "role": ["transit", "transit", "peripheral"],
                         "role_score": [0.8, 0.7, 0.2], "priority_score": [0.9, 0.6, 0.1],
                         "in_kzt": [10000.0, 20000.0, 0.0]})


def changed_csv(payload, change):
    rows = list(csv.reader(StringIO(payload.decode("utf-8-sig"), newline="")))
    change(rows)
    stream = StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def test_empty_reviews_do_not_invent_truth_or_negative_relevance(predictions):
    result = evaluate_reviews(predictions, DIGEST, {}, k=20)
    assert result.summary["role_reviewed_n"] == 0
    assert result.summary["accuracy"] is None and result.summary["macro_f1"] is None
    assert result.confusion.to_numpy().sum() == 0
    assert result.summary["actual_k"] == 3 and result.summary["requested_k"] == 20
    assert result.summary["relevance_assessed_n"] == 0
    assert result.summary["assessed_precision_at_k"] is None
    assert result.summary["precision_at_k"] is None
    assert result.summary["precision_at_k_lower_bound"] == 0
    assert result.summary["precision_at_k_upper_bound"] == 1


def test_confusion_macro_f1_and_partially_reviewed_top_k_have_explicit_denominators(predictions):
    reviews = {
        IDS[0]: make_review(DIGEST, IDS[0], "transit", "true"),
        IDS[1]: make_review(DIGEST, IDS[1], "terminal", "false"),
        IDS[2]: make_review(DIGEST, IDS[2], "unknown", "unknown", "Әлі дерек жеткіліксіз"),
    }
    result = evaluate_reviews(predictions, DIGEST, reviews, k=3)
    assert result.confusion.loc["transit", "transit"] == 1
    assert result.confusion.loc["terminal", "transit"] == 1
    assert result.confusion.to_numpy().sum() == 2
    assert result.summary["accuracy"] == 0.5
    assert result.summary["macro_f1"] == pytest.approx(1 / 3)
    assert set(result.summary["macro_f1_labels"]) == {"transit", "terminal"}
    assert result.summary["role_coverage"] == pytest.approx(2 / 3)
    assert result.summary["relevance_assessed_n"] == 2
    assert result.summary["assessed_precision_at_k"] == 0.5
    assert result.summary["precision_at_k"] is None
    assert result.summary["precision_at_k_lower_bound"] == pytest.approx(1 / 3)
    assert result.summary["precision_at_k_upper_bound"] == pytest.approx(2 / 3)
    reviews[IDS[2]] = make_review(DIGEST, IDS[2], "unknown", "false")
    complete = evaluate_reviews(predictions, DIGEST, reviews, k=3)
    assert complete.summary["precision_at_k"] == pytest.approx(1 / 3)
    assert complete.summary["relevance_coverage"] == 1
    assert complete.summary["role_reviewed_n"] == 2  # relevance is not a role label


def test_csv_round_trip_preserves_large_gids_duplicate_notes_and_formula_safety(predictions):
    note = '=HYPERLINK("https://example.invalid")\nекінші жол'
    reviews = {gid: make_review(DIGEST, gid, "terminal", "true", note) for gid in IDS}
    payload = review_csv(predictions, DIGEST, reviews)
    rows = list(csv.DictReader(StringIO(payload.decode("utf-8-sig"))))
    assert [row["gid"] for row in rows] == IDS
    assert all(row["reviewer_note"].startswith("'=") for row in rows)
    assert read_review_csv(payload, predictions, DIGEST) == reviews
    assert [row["predicted_role"] for row in rows] == predictions.role.tolist()
    assert all(row["reviewed_role"] == "terminal" for row in rows)


@pytest.mark.parametrize("note", ["=SUM(A1)", " +1", "-1", "@command", "\ttext", "\ntext", "'=formula", "''text", "Кәдімгі мәтін"])
def test_reviewer_note_escape_is_reversible(predictions, note):
    reviews = {IDS[0]: make_review(DIGEST, IDS[0], reviewer_note=note)}
    payload = review_csv(predictions, DIGEST, reviews, [IDS[0]])
    assert read_review_csv(payload, predictions, DIGEST) == reviews


@pytest.mark.parametrize("column,value", [
    ("gid", "100000000000000001.0"), ("gid", "1e17"), ("gid", " 100000000000000001"),
    ("gid", "100000000000000002"), ("gid", "9223372036854775808"),
    ("dataset_sha256", "b" * 64), ("predicted_role", "organizer"),
    ("predicted_role_score", "NaN"), ("predicted_role_score", "inf"),
    ("predicted_role_score", "-0.1"), ("predicted_role_score", "1.01"),
    ("predicted_priority_score", "true"), ("predicted_priority_score", " 0.1"),
    ("reviewed_role", ""), ("reviewed_role", "guilty"),
    ("investigation_relevant", "1"), ("investigation_relevant", "TRUE"),
    ("reviewer_note", "x" * 2001), ("reviewer_note", "nul\x00"),
])
def test_invalid_csv_values_reject_whole_import(predictions, column, value):
    payload = review_csv(predictions, DIGEST)
    invalid = changed_csv(payload, lambda rows: rows[-1].__setitem__(CSV_COLUMNS.index(column), value))
    with pytest.raises(ValueError):
        read_review_csv(invalid, predictions, DIGEST)


@pytest.mark.parametrize("change", [
    lambda rows: rows.append(rows[1].copy()),
    lambda rows: rows[0].__setitem__(1, "dataset_sha256"),
    lambda rows: rows[0].append("extra"),
    lambda rows: rows[1].append("extra"),
    lambda rows: rows[1].pop(),
])
def test_duplicate_ids_and_schema_errors_are_not_silently_accepted(predictions, change):
    payload = changed_csv(review_csv(predictions, DIGEST), change)
    with pytest.raises(ValueError):
        read_review_csv(payload, predictions, DIGEST)


def test_empty_template_and_header_only_import_are_unreviewed(predictions):
    imported = read_review_csv(review_csv(predictions, DIGEST), predictions, DIGEST)
    assert len(imported) == 3
    result = evaluate_reviews(predictions, DIGEST, imported)
    assert result.summary["role_reviewed_n"] == result.summary["relevance_assessed_n"] == 0
    assert read_review_csv(review_csv(predictions, DIGEST, gids=[]), predictions, DIGEST) == {}


def test_same_dataset_new_predictions_do_not_overwrite_expert_labels(predictions):
    reviews = {IDS[0]: make_review(DIGEST, IDS[0], "terminal", "true")}
    payload = review_csv(predictions, DIGEST, reviews, [IDS[0]])
    changed = predictions.copy(deep=True)
    changed.loc[0, "role"] = "terminal"
    changed.loc[0, "role_score"] = 0.5
    imported = read_review_csv(payload, changed, DIGEST)
    assert imported == reviews
    assert evaluate_reviews(predictions, DIGEST, reviews).summary["accuracy"] == 0
    assert evaluate_reviews(changed, DIGEST, imported).summary["accuracy"] == 1


def test_fingerprint_ignores_order_but_detects_money_dates_and_duplicate_transactions():
    frames = create_demo_frames()
    original = dataset_fingerprint(frames)
    shuffled = {name: frame.sample(frac=1, random_state=9) for name, frame in frames.items()}
    assert dataset_fingerprint(shuffled) == original
    changed = {name: frame.copy(deep=True) for name, frame in frames.items()}
    changed["transactions"].loc[0, "date"] = pd.Timestamp("2026-07-30")
    assert dataset_fingerprint(changed) != original
    duplicated = {name: frame.copy(deep=True) for name, frame in frames.items()}
    transaction = duplicated["transactions"].iloc[0]
    duplicated["transactions"] = pd.concat([duplicated["transactions"], duplicated["transactions"].iloc[[0]]], ignore_index=True)
    pair = duplicated["edges"].src.eq(transaction.src) & duplicated["edges"].dst.eq(transaction.dst)
    duplicated["edges"].loc[pair, "sum_kzt"] += transaction.sum_kzt
    duplicated["edges"].loc[pair, "n_tx"] += 1
    assert dataset_fingerprint(duplicated) != original


def test_different_dataset_reviews_cannot_be_evaluated_or_exported(predictions):
    wrong = {IDS[0]: make_review("b" * 64, IDS[0], "terminal")}
    with pytest.raises(ValueError, match="басқа"):
        evaluate_reviews(predictions, DIGEST, wrong)
    with pytest.raises(ValueError, match="басқа"):
        review_csv(predictions, DIGEST, wrong)


def test_exact_ranking_ties_and_selection_validation(predictions):
    predictions["priority_score"] = 0.5
    predictions["in_kzt"] = 0.0
    assert ranked_gids(predictions.iloc[::-1]) == IDS
    with pytest.raises(ValueError):
        review_csv(predictions, DIGEST, gids=[IDS[0], IDS[0]])
    with pytest.raises(ValueError):
        review_csv(predictions, DIGEST, gids=["2"])
    for value in (0, -1, True, 1.5, "20"):
        with pytest.raises(ValueError):
            evaluate_reviews(predictions, DIGEST, {}, k=value)


def test_empty_prediction_table_has_no_spurious_metrics(predictions):
    result = evaluate_reviews(predictions.iloc[:0], DIGEST, {})
    assert result.ranking.empty
    assert result.summary["n_nodes"] == 0 and result.summary["actual_k"] == 0
    assert result.summary["precision_at_k_lower_bound"] is None
    assert result.summary["precision_at_k_upper_bound"] is None
