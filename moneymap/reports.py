"""Local, inspectable exports for Stage 2 (not the final role CSVs)."""

import json
from pathlib import Path


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
