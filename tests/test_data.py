"""Contract checks for ingestion; no financial role claims are tested here."""

from io import BytesIO
from zipfile import ZipFile

import pandas as pd
import pytest

from moneymap.data import load_parquet_files, validate_dataset
from moneymap.demo import create_demo_files, create_demo_frames, create_demo_zip


def codes(result):
    return {issue.code for issue in result.issues}


def test_demo_is_valid_and_preserves_isolated_seed():
    frames = create_demo_frames()
    result = validate_dataset(frames)
    assert result.valid
    assert result.metrics["nodes"] == 16
    assert result.metrics["edges"] == 15
    assert result.metrics["transactions"] == 17
    assert result.metrics["seeds"] == 4
    assert result.metrics["boundary_nodes"] == 3
    assert result.metrics["isolated_nodes"] == 1
    assert result.metrics["turnover_kzt"] == 915_000
    assert result.metrics["min_date"] == "2026-07-02"
    assert result.metrics["max_date"] == "2026-07-13"
    assert 1004 in result.frames["nodes"]["gid"].values
    assert {"isolated_seeds", "boundary_truncation", "seed_incoming_incomplete"} <= codes(result)
    for name in frames:
        pd.testing.assert_frame_equal(frames[name], create_demo_frames()[name])
        assert frames[name] is not result.frames[name]


def test_parquet_and_zip_round_trip():
    files = create_demo_files()
    assert load_parquet_files(files).valid
    with ZipFile(BytesIO(create_demo_zip())) as archive:
        assert "DEMO_README.txt" in archive.namelist()
        restored = {name: archive.read(name) for name in files}
    assert load_parquet_files(restored).valid


def test_missing_file_and_corrupt_parquet_are_issues():
    files = create_demo_files()
    del files["nodes.parquet"]
    assert "missing_file" in codes(load_parquet_files(files))
    files["nodes.parquet"] = b"not a parquet file"
    result = load_parquet_files(files)
    assert not result.valid
    assert "unreadable_parquet" in codes(result)
    assert not any(issue.code == "missing_file" and issue.file == "nodes.parquet" for issue in result.issues)


def test_missing_columns_do_not_crash_dependent_checks():
    frames = create_demo_frames()
    frames["nodes"] = frames["nodes"].drop(columns=["gid", "is_seed"])
    frames["edges"] = frames["edges"].drop(columns=["sum_kzt"])
    result = validate_dataset(frames)
    assert not result.valid
    assert "missing_columns" in codes(result)


def test_unknown_endpoints_are_not_silently_added():
    frames = create_demo_frames()
    frames["transactions"].loc[0, "dst"] = 999999
    result = validate_dataset(frames)
    assert not result.valid
    assert "unknown_endpoint" in codes(result)
    assert "pair_mismatch" in codes(result)
    assert len(result.frames["nodes"]) == 16


def test_duplicate_nodes_and_edges_are_not_dropped():
    frames = create_demo_frames()
    frames["nodes"] = pd.concat([frames["nodes"], frames["nodes"].iloc[[0]]], ignore_index=True)
    frames["edges"] = pd.concat([frames["edges"], frames["edges"].iloc[[0]]], ignore_index=True)
    result = validate_dataset(frames)
    assert not result.valid
    assert {"duplicate_gid", "duplicate_edge"} <= codes(result)
    assert len(result.frames["nodes"]) == 17
    assert len(result.frames["edges"]) == 16


@pytest.mark.parametrize("bad_value", [1.5, float("inf"), True, 2**63, float(2**53)])
def test_invalid_identifiers_are_rejected(bad_value):
    frames = create_demo_frames()
    frames["nodes"]["gid"] = frames["nodes"]["gid"].astype(object)
    frames["nodes"].loc[0, "gid"] = bad_value
    result = validate_dataset(frames)
    assert not result.valid
    assert "invalid_gid" in codes(result)


def test_large_int64_identifiers_retain_exactness():
    frames = create_demo_frames()
    mapping = {gid: 2**63 - 1 - position for position, gid in enumerate(frames["nodes"]["gid"])}
    frames["nodes"]["gid"] = frames["nodes"]["gid"].map(mapping)
    for name in ("edges", "transactions"):
        for column in ("src", "dst"):
            frames[name][column] = frames[name][column].map(mapping)
    result = validate_dataset(frames)
    assert result.valid
    assert result.frames["nodes"].iloc[0]["gid"] == 2**63 - 1
    assert result.frames["nodes"]["gid"].nunique() == 16


def test_integer_seed_flags_are_supported_but_not_arbitrary_numbers():
    frames = create_demo_frames()
    frames["nodes"]["is_seed"] = frames["nodes"]["is_seed"].astype(int)
    result = validate_dataset(frames)
    assert result.valid
    assert result.frames["nodes"]["is_seed"].dtype == bool
    frames["nodes"].loc[0, "is_seed"] = 2
    assert "invalid_is_seed" in codes(validate_dataset(frames))


@pytest.mark.parametrize("bad_amount", [float("nan"), float("inf"), -1, 0, True])
def test_invalid_money_fails(bad_amount):
    frames = create_demo_frames()
    frames["transactions"]["sum_kzt"] = frames["transactions"]["sum_kzt"].astype(object)
    frames["transactions"].loc[0, "sum_kzt"] = bad_amount
    assert not validate_dataset(frames).valid


def test_fractional_count_and_bad_depth_fail():
    frames = create_demo_frames()
    frames["edges"]["n_tx"] = frames["edges"]["n_tx"].astype(float)
    frames["edges"].loc[0, "n_tx"] = 1.5
    frames["nodes"].loc[0, "depth"] = 5
    result = validate_dataset(frames)
    assert not result.valid
    assert {"invalid_n_tx", "invalid_depth"} <= codes(result)


@pytest.mark.parametrize("bad_date", ["definitely-not-a-date", "2026-02-30", 1234])
def test_bad_dates_fail(bad_date):
    frames = create_demo_frames()
    frames["transactions"]["date"] = frames["transactions"]["date"].astype(object)
    frames["transactions"].loc[0, "date"] = bad_date
    result = validate_dataset(frames)
    assert not result.valid
    assert "invalid_date" in codes(result)


def test_out_of_period_and_small_amount_warn_without_dropping():
    frames = create_demo_frames()
    frames["transactions"].loc[0, "date"] = pd.Timestamp("2026-08-01")
    # Rebuild aggregates to isolate the selection-policy warning.
    frames["transactions"].loc[0, "sum_kzt"] = 4_999
    grouped = frames["transactions"].groupby(["src", "dst"], as_index=False).agg(sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"))
    frames["edges"] = grouped.merge(frames["edges"][["src", "dst", "depth"]], on=["src", "dst"])
    result = validate_dataset(frames)
    assert result.valid
    assert {"out_of_period", "below_threshold"} <= codes(result)
    assert len(result.frames["transactions"]) == 17


def test_aggregation_mismatch_detects_amount_and_count():
    frames = create_demo_frames()
    frames["edges"].loc[0, "sum_kzt"] += 1
    frames["edges"].loc[0, "n_tx"] += 1
    result = validate_dataset(frames)
    assert not result.valid
    assert {"amount_mismatch", "count_mismatch"} <= codes(result)


def test_duplicate_columns_and_nulls_return_errors():
    frames = create_demo_frames()
    frames["nodes"] = pd.concat([frames["nodes"], frames["nodes"][["gid"]]], axis=1)
    frames["transactions"].loc[0, "date"] = pd.NaT
    result = validate_dataset(frames)
    assert not result.valid
    assert {"duplicate_columns", "null_values"} <= codes(result)


def test_seed_depth_inconsistency_is_reported():
    frames = create_demo_frames()
    frames["nodes"].loc[0, "depth"] = 1
    result = validate_dataset(frames)
    assert not result.valid
    assert "inconsistent_seed_depth" in codes(result)


def test_unexpected_upload_is_explicitly_reported():
    files = create_demo_files()
    files["other.parquet"] = b"unrelated"
    result = load_parquet_files(files)
    assert result.valid
    assert "unexpected_file" in codes(result)


def test_large_amount_sum_does_not_wrap_int64():
    frames = create_demo_frames()
    # Each transfer fits int64; their total does not. Integer pandas sums
    # would silently wrap without normalization to monetary floats.
    frames["transactions"]["sum_kzt"] = 2**62
    grouped = frames["transactions"].groupby(["src", "dst"], as_index=False).agg(n_tx=("sum_kzt", "size"))
    grouped["sum_kzt"] = grouped["n_tx"].astype(float) * float(2**62)
    frames["edges"] = grouped.merge(frames["edges"][["src", "dst", "depth"]], on=["src", "dst"])
    result = validate_dataset(frames)
    assert result.valid
    assert result.metrics["turnover_kzt"] == float(17 * 2**62)
    assert result.metrics["turnover_kzt"] > 0


def test_nonfinite_aggregates_are_rejected():
    frames = create_demo_frames()
    frames["transactions"]["sum_kzt"] = 1e308
    result = validate_dataset(frames)
    assert not result.valid
    assert "aggregate_overflow" in codes(result)
    assert "total_overflow" in codes(result)
    assert result.metrics["turnover_kzt"] is None
