import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

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
