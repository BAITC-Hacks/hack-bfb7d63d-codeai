"""Reproducible CLI for local validation and graph metrics."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from moneymap.data import load_parquet_files
from moneymap.demo import create_demo_files
from moneymap.graph import analyze_dataset
from moneymap.reports import export_analysis


def main():
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
        files = {name: (args.data_dir / name).read_bytes() for name in ("nodes.parquet", "edges.parquet", "transactions.parquet") if (args.data_dir / name).is_file()}
        result = load_parquet_files(files)
        if args.command == "analyze":
            if not result.valid:
                for issue in result.issues:
                    if issue.severity == "error":
                        print(f"ERROR [{issue.code}]: {issue.message}")
                return 1
            computed = analyze_dataset(result.frames)
            export_analysis(computed, args.out)
            print(f"PASS: {len(computed.nodes)} nodes, {computed.graph.number_of_edges()} edges, {len(computed.components)} components in {computed.elapsed_seconds:.2f}s")
            print(f"Stage 2 reports: {args.out.resolve()}")
            return 0
        report = {"stage": 1, "valid": result.valid, "metrics": result.metrics, "issues": [asdict(issue) for issue in result.issues]}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        parser.exit(2, f"File operation failed: {exc}\n")
    print(f"{'PASS' if result.valid else 'FAIL'}: {args.output.resolve()}")
    return 0 if result.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
