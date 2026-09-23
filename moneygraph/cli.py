"""Reproducible CLI for a local, single-batch analysis."""
import argparse
import json
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description="AQSHA TRACE — local transaction network analysis")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--data", type=Path, help="Directory containing the three input Parquet files")
    source.add_argument("--demo", action="store_true", help="Generate explicitly synthetic demo inputs")
    parser.add_argument("--output", type=Path, default=Path("output"), help="CSV and analysis.json directory")
    parser.add_argument("--serve", action="store_true", help="Start the local web interface after analysis")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if not args.data and not args.demo:
        parser.error("choose --data PATH or --demo")
    try:
        from .pipeline import analyze
        if args.demo:
            from .demo import generate_demo
            data_dir = Path("data/demo")
            generate_demo(data_dir)
        else:
            data_dir = args.data
        result = analyze(data_dir, args.output, demo=args.demo)
        meta = result["meta"]
        print(json.dumps({"status": "ok", "demo": args.demo, "nodes": meta["n_nodes"],
                          "edges": meta["n_edges"], "seconds": meta["runtime_seconds"],
                          "output": str(args.output.resolve())}, ensure_ascii=True), flush=True)
        if args.serve:
            from .server import serve
            serve(result, args.output, port=args.port)
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, FileNotFoundError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
