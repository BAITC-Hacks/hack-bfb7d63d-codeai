"""Reproduce installation/tests in an isolated source copy with no .deps fallback.

Run: python scripts/verify_clean.py --data data/challenge
Artifacts and the environment are retained under .build-temp for inspection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--environment", type=Path, help="Reuse an explicitly prepared isolated venv")
    parser.add_argument("--skip-install", action="store_true", help="Only for an already prepared --environment")
    args = parser.parse_args()
    if args.skip_install and not args.environment:
        parser.error("--skip-install requires --environment")
    project = Path(__file__).resolve().parents[1]
    scratch = project / ".build-temp" / ("clean-check-" + uuid.uuid4().hex[:10])
    source = scratch / "source"
    source.mkdir(parents=True)
    for name in ("moneygraph", "web", "tests"):
        shutil.copytree(project / name, source / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("run.py", "requirements.txt", "requirements-dev.txt"):
        if (project / name).exists():
            shutil.copy2(project / name, source / name)
    environment = args.environment.resolve() if args.environment else scratch / "venv"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    env["TEMP"] = env["TMP"] = str(scratch)

    def run(command, **kwargs):
        print("Running:", " ".join(map(str, command)), flush=True)
        return subprocess.run(list(map(str, command)), cwd=source, env=env, check=True, **kwargs)

    if not args.environment:
        run([sys.executable, "-m", "venv", environment])
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        raise ValueError("The selected virtual environment has no Python executable")
    if not args.skip_install:
        dependency_file = "requirements-dev.txt" if (source / "requirements-dev.txt").exists() else "requirements.txt"
        run([python, "-m", "pip", "install", "--no-cache-dir", "-r", dependency_file])
    probe = run([python, "-I", "-c",
                 "import sys,pathlib,json,pandas,numpy,pyarrow,networkx,reportlab; "
                 "assert sys.prefix != sys.base_prefix; "
                 "mods=[pandas,numpy,pyarrow,networkx,reportlab]; "
                 "assert all(pathlib.Path(m.__file__).is_relative_to(sys.prefix) for m in mods); "
                 "print(json.dumps({m.__name__:m.__file__ for m in mods}))"], capture_output=True, text=True)
    run([python, "-m", "unittest", "discover", "-s", "tests", "-v"])
    if args.data:
        data = args.data.resolve()
        copied = source / "data" / "input"
        copied.mkdir(parents=True)
        for name in ("nodes.parquet", "edges.parquet", "transactions.parquet"):
            shutil.copy2(data / name, copied / name)
        flags = ["--data", str(copied)]
    else:
        flags = ["--demo"]
    start = time.perf_counter()
    run([python, "run.py", *flags, "--output", "output"])
    wall_seconds = time.perf_counter() - start
    result = json.loads((source / "output" / "analysis.json").read_text(encoding="utf-8"))
    summary = {"verified_at": datetime.now(timezone.utc).isoformat(),
               "environment": str(environment), "source_copy": str(source),
               "module_locations": json.loads(probe.stdout), "pipeline_wall_seconds": wall_seconds,
               "nodes": result["meta"]["n_nodes"], "transactions": result["meta"]["n_transactions"],
               "all_tests_passed": True, "under_five_minutes": wall_seconds < 300,
               "scope": "Isolated virtualenv on this host; not a fresh operating system."}
    (scratch / "verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    freeze = run([python, "-m", "pip", "freeze"], capture_output=True, text=True)
    (scratch / "installed.txt").write_text(freeze.stdout, encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    if wall_seconds >= 300:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
