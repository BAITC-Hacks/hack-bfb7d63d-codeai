import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

from moneymap.demo import create_demo_frames
from moneymap.graph import analyze_dataset
from moneymap.reports import export_role_analysis
from moneymap.roles import classify_graph
from scripts.verify_submission import VerificationError, validate_outputs


@pytest.fixture
def submission(tmp_path):
    data, output = tmp_path / "data", tmp_path / "results"
    data.mkdir()
    frames = create_demo_frames()
    for name, frame in frames.items():
        for column in ("gid", "src", "dst"):
            if column in frame:
                frame[column] = frame[column] + (2**63 - 100_000)
        frame.to_parquet(data / f"{name}.parquet", index=False)
    export_role_analysis(classify_graph(analyze_dataset(frames)), output)
    baseline = validate_outputs(data, output)
    assert baseline["nodes"] == baseline["top_nodes"] == 16
    return data, output


def alter(output, name, mutation):
    path = output / name
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        schema, rows = reader.fieldnames, list(reader)
    mutation(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=schema)
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize("tamper,expected", [
    (lambda rows: rows.pop(), "exactly cover input"),
    (lambda rows: rows[0].update(role_score="NaN"), "nonfinite"),
    (lambda rows: rows[0].update(evidence="a" * 201), "exceeds 200"),
])
def test_verifier_rejects_incomplete_nodes_and_invalid_evidence(submission, tamper, expected):
    data, output = submission
    alter(output, "nodes_roles.csv", tamper)
    with pytest.raises(VerificationError, match=expected):
        validate_outputs(data, output)


@pytest.mark.parametrize("tamper,expected", [
    (lambda rows: rows[0].update(sum_kzt_internal="999999999"), "internal turnover"),
    (lambda rows: rows[0].update(n_seed="999"), "incorrect n_seed"),
    (lambda rows: rows[0].update(top_gids=json.dumps(["0"])), "outside cluster"),
])
def test_verifier_rejects_cluster_accounting_and_membership_tampering(submission, tamper, expected):
    data, output = submission
    alter(output, "clusters.csv", tamper)
    with pytest.raises(VerificationError, match=expected):
        validate_outputs(data, output)


def test_verifier_rejects_wrong_top_score_even_with_python_optimized(submission):
    data, output = submission
    alter(output, "top_nodes.csv", lambda rows: rows[0].update(priority_score="0"))
    code = "from scripts.verify_submission import validate_outputs; import sys; validate_outputs(sys.argv[1], sys.argv[2])"
    result = subprocess.run(
        [sys.executable, "-B", "-O", "-c", code, str(data), str(output)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "role/score differs from node" in result.stderr
