import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd

from moneymap.demo import create_demo_frames
from moneymap.extended_reports import extended_export_files
from moneymap.graph import analyze_dataset
from moneymap.roles import classify_graph


def test_extended_reports_reproducible_and_provenance_complete():
    frames = create_demo_frames()
    graph = analyze_dataset(frames)
    roles = classify_graph(graph)
    result = extended_export_files(graph, roles, frames, {"nodes.parquet": "test-input-hash"})
    assert result == extended_export_files(graph, roles, frames, {"nodes.parquet": "test-input-hash"})
    assert len(result) == 12
    report = json.loads(result["extended_report.json"])
    assert report["input_sha256"]["nodes.parquet"] == "test-input-hash"
    assert report["role_config"] == roles.config
    assert report["role_config_sha256"] == hashlib.sha256(json.dumps(roles.config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert set(report["output_sha256"]) == set(result) - {"extended_report.json"}
    assert all(report["output_sha256"][name] == hashlib.sha256(payload).hexdigest()
               for name, payload in result.items() if name != "extended_report.json")
    from io import BytesIO
    review = pd.read_csv(BytesIO(result["expert_review_template.csv"]), dtype="string", keep_default_na=False)
    assert len(review) == len(graph.nodes)
    assert review.dataset_sha256.eq(report["dataset_fingerprint"]).all()
    assert set(review.reviewed_role) <= {"", "unknown"}
    assert set(review.investigation_relevant) <= {"", "unknown"}
    assert "unknown" == report["network"]["full_coverage"]


def test_extended_cli_exports_required_and_supplementary_results(tmp_path):
    for name, frame in create_demo_frames().items():
        frame.to_parquet(tmp_path / f"{name}.parquet", index=False)
    out = tmp_path / "result"
    run = subprocess.run([sys.executable, "-B", "-m", "moneymap", "run", "--data-dir", str(tmp_path),
                          "--out", str(out), "--extended"], cwd=Path(__file__).resolve().parents[1], capture_output=True)
    assert run.returncode == 0, run.stderr.decode("utf-8", errors="replace")
    assert (out / "nodes_roles.csv").is_file()
    assert (out / "clusters.csv").is_file()
    assert (out / "top_nodes.csv").is_file()
    report = json.loads((out / "extended/extended_report.json").read_text(encoding="utf-8"))
    assert len(report["input_sha256"]) == 3
    assert report["network"]["total_turnover_kzt"] > 0
    assert len(list((out / "extended").iterdir())) == 12
