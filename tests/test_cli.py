import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from moneymap.demo import create_demo_frames


def test_analyze_cli_exports_complete_case_with_exact_large_ids(tmp_path):
    frames = create_demo_frames()
    shift = 2**63 - 100_000
    for name, frame in frames.items():
        for col in ("gid", "src", "dst"):
            if col in frame:
                frame[col] = frame[col] + shift
        frame.to_parquet(tmp_path / f"{name}.parquet", index=False)
    out = tmp_path / "reports"
    result = subprocess.run(
        [sys.executable, "-m", "moneymap", "analyze", "--data-dir", str(tmp_path), "--out", str(out)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    nodes = pd.read_csv(out / "node_metrics.csv", dtype={"gid": "string"})
    assert set(nodes.gid) == {str(gid) for gid in frames["nodes"].gid}
    assert len(nodes) == 16
    daily = pd.read_csv(out / "daily_activity.csv")
    parts = pd.read_csv(out / "components.csv")
    summary = json.loads((out / "graph_summary.json").read_text(encoding="utf-8"))
    assert summary["stage"] == 2
    assert daily.n_tx.sum() == 17
    assert parts.n_nodes.sum() == 16
    assert daily.sum_kzt.sum() == parts.sum_kzt_internal.sum() == summary["turnover_kzt"]


def test_analyze_cli_does_not_export_invalid_input(tmp_path):
    out = tmp_path / "reports"
    result = subprocess.run(
        [sys.executable, "-m", "moneymap", "analyze", "--data-dir", str(tmp_path), "--out", str(out)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
    )
    assert result.returncode == 1
    assert not out.exists()


def test_run_cli_fixed_schemas_exact_ids_and_reproducible_csvs(tmp_path):
    frames = create_demo_frames()
    for name, frame in frames.items():
        for column in ("gid", "src", "dst"):
            if column in frame:
                frame[column] = frame[column] + (2**63 - 100_000)
        frame.to_parquet(tmp_path / f"{name}.parquet", index=False)
    out = tmp_path / "run"
    command = [sys.executable, "-m", "moneymap", "run", "--data-dir", str(tmp_path), "--out", str(out)]
    process = subprocess.run(command, capture_output=True, cwd=Path(__file__).resolve().parents[1])
    assert process.returncode == 0, process.stderr
    nodes = pd.read_csv(out / "nodes_roles.csv", dtype={"gid": "string"})
    clusters = pd.read_csv(out / "clusters.csv")
    top = pd.read_csv(out / "top_nodes.csv", dtype={"gid": "string"})
    assert list(nodes) == ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
    assert list(clusters) == ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]
    assert list(top) == ["rank", "gid", "role", "priority_score", "why"]
    assert set(nodes.gid) == set(top.gid) == {str(gid) for gid in frames["nodes"].gid}
    assert not nodes.isna().any().any()
    assert nodes.evidence.str.len().between(1, 200).all()
    assert nodes.role_score.between(0, 1).all()
    assert nodes.priority_score.between(0, 1).all()
    assert top.priority_score.is_monotonic_decreasing
    assert clusters.n_nodes.sum() == 16
    for gids in clusters.top_gids.map(json.loads):
        assert all(isinstance(gid, str) and gid in set(nodes.gid) for gid in gids)
    report = json.loads((out / "run_report.json").read_text(encoding="utf-8"))
    assert report["stage"] == 3
    assert report["run"]["raw_to_csv_seconds"] > 0
    assert len(report["run"]["input_sha256"]) == 3
    before = {name: (out / name).read_bytes() for name in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv")}
    repeat = subprocess.run(command, capture_output=True, cwd=Path(__file__).resolve().parents[1])
    assert repeat.returncode == 0
    assert all((out / name).read_bytes() == value for name, value in before.items())


@pytest.mark.parametrize("invalid_config", [False, True])
def test_run_cli_rejects_invalid_input_or_config_without_outputs(tmp_path, invalid_config):
    command = [sys.executable, "-m", "moneymap", "run", "--data-dir", str(tmp_path), "--out", str(tmp_path / "out")]
    if invalid_config:
        for name, frame in create_demo_frames().items():
            frame.to_parquet(tmp_path / f"{name}.parquet", index=False)
        config_path = tmp_path / "invalid.json"
        config_path.write_text('{"nonexistent": 123}', encoding="utf-8")
        command.extend(["--config", str(config_path)])
    result = subprocess.run(command, capture_output=True, cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == (2 if invalid_config else 1)
    assert not (tmp_path / "out").exists()
