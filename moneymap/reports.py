"""Local, inspectable exports for Stage 2 (not the final role CSVs)."""

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def analysis_summary(analysis):
    return {
        "stage": 2,
        **analysis.summary,
        "elapsed_seconds": round(analysis.elapsed_seconds, 6),
        "methods": {
            "graph": "Directed graph with every nodes.parquet gid, including isolates",
            "components": "Weak components; these are not Louvain communities",
            "pagerank": "Directed PageRank weighted by observed sum_kzt",
            "betweenness": "Exact directed shortest-path betweenness, unweighted",
            "seed_reach": "Directed structural reachability, excludes the node itself",
            "time_pattern": "Strictly later outgoing day; no same-day order or money matching inferred",
            "mean_next_out_days": "Conditional mean lag for eligible incoming transactions with any later outgoing day, including lags over 2 days; missing later exit excluded from mean but retained in share denominator",
        },
        "limitations": [
            "Only observed intra-bank transfers are included.",
            "Seed incoming transfers and depth-4 outgoing transfers are incomplete.",
            "Structural paths do not prove chronological movement of the same funds.",
            "The last two observed days are excluded from the 1–2 day pattern denominator.",
            "No roles, guilt, or investigation priorities are assigned in Stage 2.",
        ],
    }


def export_analysis(analysis, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in (
        ("node_metrics.csv", analysis.nodes),
        ("components.csv", analysis.components),
        ("daily_activity.csv", analysis.daily),
    ):
        frame.to_csv(output_dir / name, index=False, encoding="utf-8-sig")
    (output_dir / "graph_summary.json").write_text(
        json.dumps(analysis_summary(analysis), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def role_export_files(result, metadata=None):
    """Required fixed-schema CSVs plus a reproducibility report, all local."""
    files = {
        filename: frame.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")
        for filename, frame in (
            ("nodes_roles.csv", result.nodes_roles),
            ("clusters.csv", result.clusters),
            ("top_nodes.csv", result.top_nodes),
        )
    }
    report = {
        "stage": 3,
        "summary": result.summary,
        "config": result.config,
        "role_elapsed_seconds": round(result.elapsed_seconds, 6),
        "run": metadata or {},
        "interpretation": "Roles are hypotheses from observed transfers; role_score is uncalibrated rule support. Priority is a separate review score, not a probability of guilt.",
    }
    files["run_report.json"] = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    return files


def export_role_analysis(result, output_dir, metadata=None):
    files = role_export_files(result, metadata)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (output_dir / name).write_bytes(content)


def role_export_zip(files):
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            entry = ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, payload)
    return buffer.getvalue()
