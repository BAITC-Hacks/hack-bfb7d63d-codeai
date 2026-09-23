"""Reproducible CLI for local validation and graph metrics."""

import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

from moneymap.data import load_parquet_files
from moneymap.demo import create_demo_files
from moneymap.graph import analyze_dataset
from moneymap.reports import export_analysis, export_role_analysis, role_export_files
from moneymap.roles import classify_graph, load_config


def main():
    # Piped Windows output may default to cp1251, which lacks Kazakh letters.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="MoneyMap: local validation and graph analysis")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Write clearly synthetic demo Parquet files")
    demo.add_argument("--output-dir", type=Path, default=Path("data/demo"))
    check = commands.add_parser("validate", help="Validate the three input Parquet files")
    check.add_argument("--data-dir", type=Path, required=True)
    check.add_argument("--output", type=Path, default=Path("output/validation_report.json"))
    analysis = commands.add_parser("analyze", help="Validate input, compute Stage 2 graph metrics and export CSV/JSON")
    analysis.add_argument("--data-dir", type=Path, required=True)
    analysis.add_argument("--out", type=Path, default=Path("output/stage2"))
    pipeline = commands.add_parser("run", help="Raw Parquet to all three required role/cluster/priority CSVs")
    pipeline.add_argument("--data-dir", type=Path, required=True)
    pipeline.add_argument("--out", type=Path, default=Path("output/stage3"))
    pipeline.add_argument("--config", type=Path, help="Optional role thresholds and scoring configuration JSON")
    pipeline.add_argument("--top-n", type=int, default=30, help="At least 20; smaller datasets export all nodes")
    pipeline.add_argument("--extended", action="store_true", help="Also export routes, anomalies, intercluster flows, coverage and removal scenarios")
    args = parser.parse_args()
    if args.command == "demo":
        files = create_demo_files()
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            destination = args.output_dir / name
            if destination.exists():
                parser.error(f"Refusing to overwrite existing file: {destination}")
        for name, content in files.items():
            (args.output_dir / name).write_bytes(content)
        print(f"Synthetic demo files created: {args.output_dir.resolve()}")
        return 0
    try:
        started = perf_counter()
        files = {name: (args.data_dir / name).read_bytes() for name in ("nodes.parquet", "edges.parquet", "transactions.parquet") if (args.data_dir / name).is_file()}
        result = load_parquet_files(files)
        if args.command in ("analyze", "run"):
            if not result.valid:
                for issue in result.issues:
                    if issue.severity == "error":
                        print(f"ERROR [{issue.code}]: {issue.message}")
                return 1
            computed = analyze_dataset(result.frames)
            if args.command == "run":
                config = load_config(args.config)
                roles = classify_graph(computed, config=config, top_n=args.top_n)
                metadata = {
                    "input_sha256": {name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()},
                    "config_sha256": hashlib.sha256(json.dumps(roles.config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
                    "versions": {"python": platform.python_version(), **{name: version(name) for name in ("networkx", "pandas", "numpy", "scipy")}},
                    "top_n_requested": args.top_n,
                }
                export_role_analysis(roles, args.out, metadata)
                metadata["raw_to_csv_seconds"] = round(perf_counter() - started, 6)
                (args.out / "run_report.json").write_bytes(role_export_files(roles, metadata)["run_report.json"])
                if args.extended:
                    from moneymap.extended_reports import export_extended_analysis
                    export_extended_analysis(computed, roles, result.frames, args.out / "extended", metadata["input_sha256"])
                    print(f"Extended reports: {(args.out / 'extended').resolve()}")
                print(f"PASS: {len(roles.nodes_roles)} nodes, {len(roles.clusters)} clusters, top {len(roles.top_nodes)}")
                print(f"Raw Parquet to CSV: {metadata['raw_to_csv_seconds']:.2f}s")
                print(f"Stage 3 reports: {args.out.resolve()}")
                return 0
            export_analysis(computed, args.out)
            print(f"PASS: {len(computed.nodes)} nodes, {computed.graph.number_of_edges()} edges, {len(computed.components)} components in {computed.elapsed_seconds:.2f}s")
            print(f"Stage 2 reports: {args.out.resolve()}")
            return 0
        report = {"stage": 1, "valid": result.valid, "metrics": result.metrics, "issues": [asdict(issue) for issue in result.issues]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        parser.exit(2, f"File operation failed: {exc}\n")
    except (ValueError, RuntimeError) as exc:
        parser.exit(2, f"Analysis failed: {exc}\n")
    print(f"{'PASS' if result.valid else 'FAIL'}: {args.output.resolve()}")
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
