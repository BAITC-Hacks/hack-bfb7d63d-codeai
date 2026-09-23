"""Deterministic supplementary reports; required CSV schemas remain unchanged."""

import hashlib
import json
from pathlib import Path

from moneymap.anomalies import analyze_anomalies
from moneymap.investigation import analyze_routes, resilience_analysis
from moneymap.network_insights import analyze_network, compare_removal_strategies
from moneymap.evaluation import dataset_fingerprint, review_csv


def extended_export_files(analysis, roles, frames, input_sha256=None):
    network = analyze_network(analysis, roles)
    routes = analyze_routes(analysis, frames["transactions"])
    anomalies = analyze_anomalies(analysis, frames["transactions"])
    ranked = roles.details.sort_values(["priority_score", "in_kzt", "gid"], ascending=[False, False, True], kind="stable")
    resilience = resilience_analysis(analysis, ranked.gid.tolist(), top_n=min(5, len(ranked)))
    strategies, strategy_summary = compare_removal_strategies(analysis, roles)
    tables = {
        "cluster_flows.csv": network.flows, "bridge_nodes.csv": network.bridges,
        "node_coverage.csv": network.coverage, "data_requests.csv": network.requests,
        "cycles.csv": routes.cycles, "reciprocal_pairs.csv": routes.reciprocal,
        "repeated_routes.csv": routes.routes, "resilience.csv": resilience.comparison,
        "removal_strategies.csv": strategies, "anomalies.csv": anomalies.alerts,
    }
    files = {name: frame.to_csv(index=False, lineterminator="\n").encode("utf-8-sig") for name, frame in tables.items()}
    fingerprint = dataset_fingerprint(frames)
    files["expert_review_template.csv"] = review_csv(roles.details, fingerprint)
    report = {
        "schema_version": 1, "input_sha256": input_sha256 or {}, "dataset_fingerprint": fingerprint,
        "role_config": roles.config,
        "role_config_sha256": hashlib.sha256(json.dumps(roles.config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
        "network": network.summary, "routes": routes.summary,
        "anomalies": anomalies.summary, "removal_strategies": strategy_summary,
        "limitations": list(dict.fromkeys((*network.limitations, *routes.limitations, *anomalies.limitations, *resilience.limitations))),
        "output_sha256": {name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()},
    }
    files["extended_report.json"] = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    return files


def export_extended_analysis(analysis, roles, frames, output_dir, input_sha256=None):
    files = extended_export_files(analysis, roles, frames, input_sha256)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    for name, payload in files.items():
        (destination / name).write_bytes(payload)
    return files
