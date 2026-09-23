"""Verify the local submission independently; no live API or network is used."""

from __future__ import annotations

import argparse
import csv
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
from time import perf_counter

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ("nodes.parquet", "edges.parquet", "transactions.parquet")
SCHEMAS = {
    "nodes_roles.csv": ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"],
    "clusters.csv": ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"],
    "top_nodes.csv": ["rank", "gid", "role", "priority_score", "why"],
}
ROLES = {"consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"}
GUARD_MARKER = "MONEYMAP_NETWORK_GUARD="
CHILD = r'''
import json, os, runpy, socket, sys
attempts = []
def blocked(name):
    def deny(*args, **kwargs):
        attempts.append(name)
        raise RuntimeError("Acceptance runner blocks socket/network calls")
    return deny
for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
    setattr(socket, name, blocked(name))
for name in ("connect", "connect_ex", "sendto", "sendmsg"):
    if hasattr(socket.socket, name):
        setattr(socket.socket, name, blocked("socket." + name))
os.environ["MONEYMAP_AI_ENABLED"] = "false"
sys.argv = ["moneymap", "run", "--data-dir", sys.argv[1], "--out", sys.argv[2]]
try:
    runpy.run_module("moneymap", run_name="__main__")
finally:
    print("MONEYMAP_NETWORK_GUARD=" + json.dumps({"installed": True, "attempts": attempts}))
'''


class VerificationError(ValueError):
    """A concrete acceptance failure, including when Python runs with -O."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def integer(value, label):
    require(isinstance(value, str) and re.fullmatch(r"-?\d+", value) is not None, f"{label}: expected exact integer")
    result = int(value)
    require(-(2**63) <= result < 2**63, f"{label}: outside int64")
    return result


def number(value, label, score=False):
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise VerificationError(f"{label}: expected number") from exc
    require(math.isfinite(result), f"{label}: nonfinite number")
    require(not score or 0 <= result <= 1, f"{label}: score outside 0..1")
    return result


def read_csv(path, schema):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == schema, f"{path.name}: schema mismatch")
        rows = list(reader)
    require(bool(rows), f"{path.name}: empty table")
    require(all(set(row) == set(schema) and all(isinstance(value, str) and value.strip() for value in row.values()) for row in rows), f"{path.name}: missing/extra/empty cells")
    return rows


def validate_outputs(data_dir, output_dir):
    """Check exported contracts and accounting without using pipeline functions."""
    data_dir, output_dir = Path(data_dir), Path(output_dir)
    inputs = pd.read_parquet(data_dir / "nodes.parquet")
    edges = pd.read_parquet(data_dir / "edges.parquet")
    expected = {int(row.gid): bool(row.is_seed) for row in inputs.itertuples(index=False)}
    require(len(expected) == len(inputs) > 0, "input nodes: empty or duplicate gids")
    rows, clusters, top = [read_csv(output_dir / name, schema) for name, schema in SCHEMAS.items()]
    nodes, groups = {}, {}
    for row in rows:
        gid = integer(row["gid"], "nodes gid")
        require(gid not in nodes, "nodes_roles.csv: duplicate gid")
        require(row["role"] in ROLES, "nodes_roles.csv: unknown role")
        row["role_score"] = number(row["role_score"], "role_score", score=True)
        row["priority_score"] = number(row["priority_score"], "priority_score", score=True)
        require(len(row["evidence"]) <= 200, "nodes_roles.csv: evidence exceeds 200 characters")
        require(re.search(r"\d", row["evidence"]) is not None, "nodes_roles.csv: evidence must contain numeric facts")
        cluster = integer(row["cluster_id"], "node cluster_id")
        groups.setdefault(cluster, set()).add(gid)
        nodes[gid] = row
    require(set(nodes) == set(expected), "nodes_roles.csv: gids do not exactly cover input")
    internal = {cluster: [] for cluster in groups}
    membership = {gid: cluster for cluster, gids in groups.items() for gid in gids}
    for row in edges.itertuples(index=False):
        src, dst = int(row.src), int(row.dst)
        require(src in nodes and dst in nodes, "input edge: unknown endpoint")
        if membership[src] == membership[dst]:
            internal[membership[src]].append(float(row.sum_kzt))
    seen = set()
    for row in clusters:
        cluster = integer(row["cluster_id"], "cluster_id")
        require(cluster in groups and cluster not in seen, "clusters.csv: duplicate or unknown cluster")
        seen.add(cluster)
        members = groups[cluster]
        require(integer(row["n_nodes"], "n_nodes") == len(members), "clusters.csv: incorrect n_nodes")
        require(integer(row["n_seed"], "n_seed") == sum(expected[gid] for gid in members), "clusters.csv: incorrect n_seed")
        amount = number(row["sum_kzt_internal"], "sum_kzt_internal")
        require(math.isclose(amount, math.fsum(internal[cluster]), rel_tol=1e-12, abs_tol=0.01), "clusters.csv: incorrect internal turnover")
        try:
            gids = json.loads(row["top_gids"])
        except json.JSONDecodeError as exc:
            raise VerificationError("clusters.csv: invalid top_gids JSON") from exc
        require(isinstance(gids, list) and 1 <= len(gids) <= min(5, len(members)), "clusters.csv: invalid top_gids list")
        gids = [integer(gid, "top_gids entry") for gid in gids]
        require(len(set(gids)) == len(gids) and set(gids) <= members, "clusters.csv: top_gids outside cluster or duplicate")
    require(seen == set(groups), "clusters.csv: missing cluster")
    require(min(20, len(nodes)) <= len(top) <= len(nodes), "top_nodes.csv: insufficient/excessive rows")
    top_ids, previous = set(), math.inf
    for rank, row in enumerate(top, 1):
        gid = integer(row["gid"], "top gid")
        require(gid in nodes and gid not in top_ids, "top_nodes.csv: unknown or duplicate gid")
        top_ids.add(gid)
        score = number(row["priority_score"], "top priority_score", score=True)
        require(integer(row["rank"], "rank") == rank, "top_nodes.csv: rank is not sequential")
        require(score == nodes[gid]["priority_score"] and row["role"] == nodes[gid]["role"], "top_nodes.csv: role/score differs from node")
        require(score <= previous, "top_nodes.csv: priority order incorrect")
        previous = score
    require(not any(nodes[gid]["priority_score"] > previous for gid in set(nodes) - top_ids), "top_nodes.csv: higher-priority node omitted")
    for row in inputs.itertuples(index=False):
        role = nodes[int(row.gid)]["role"]
        require(int(row.depth) != 4 or role == "peripheral", "depth-4 node violates documented role mask")
        require(not row.is_seed or role not in {"consolidator", "transit", "terminal"}, "seed node violates ratio-role mask")
    transactions = pd.read_parquet(data_dir / "transactions.parquet")
    days = pd.to_datetime(transactions["date"], utc=True).dt.tz_localize(None).dt.normalize()
    dated = transactions.assign(day=days)
    first_in = dated.groupby("dst")["day"].min()
    last_out = dated.groupby("src")["day"].max()
    for gid, row in nodes.items():
        contradiction = gid in first_in and gid in last_out and last_out.loc[gid] < first_in.loc[gid]
        require(not contradiction or row["role"] != "transit", "transit node has all outgoing before first incoming day")
    return {"nodes": len(nodes), "clusters": len(clusters), "top_nodes": len(top), "evidence_max_characters": max(len(row["evidence"]) for row in rows)}


def hashes(directory, names):
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}


def run_offline(data_dir, output_dir):
    env = dict(os.environ, MONEYMAP_AI_ENABLED="false", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    started = perf_counter()
    process = subprocess.run([sys.executable, "-B", "-c", CHILD, str(data_dir), str(output_dir)], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    elapsed = perf_counter() - started
    require(process.returncode == 0, f"CLI failed with exit code {process.returncode}: {process.stderr[-1500:]}")
    receipts = [line[len(GUARD_MARKER):] for line in process.stdout.splitlines() if line.startswith(GUARD_MARKER)]
    require(len(receipts) == 1, "Missing network-guard receipt")
    guard = json.loads(receipts[0])
    require(guard == {"installed": True, "attempts": []}, "CLI attempted socket/network use")
    run_report = json.loads((output_dir / "run_report.json").read_text(encoding="utf-8"))
    cli_seconds = number(run_report["run"]["raw_to_csv_seconds"], "raw_to_csv_seconds")
    require(0 < cli_seconds < 300 and 0 < elapsed < 300, "Runtime exceeds the 300-second limit")
    require(run_report["run"]["input_sha256"] == hashes(data_dir, INPUTS), "CLI input hashes differ from source")
    return {"subprocess_wall_seconds": round(elapsed, 6), "raw_to_csv_seconds": cli_seconds, "network_guard": guard, "validation": validate_outputs(data_dir, output_dir)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/case"))
    parser.add_argument("--out", type=Path, default=Path("output/submission/results"))
    args = parser.parse_args(argv)
    data_dir, output_dir = ((ROOT / path).resolve() for path in (args.data_dir, args.out))
    repeat_dir = output_dir.parent / "verification-repeat"
    report = {"status": "FAIL", "ai_enabled": False, "network_scope": "Python socket outbound/DNS APIs blocked inside each CLI subprocess; not OS network isolation", "environment": {"python": platform.python_version(), "executable": sys.executable, "platform": platform.platform()}, "runs": []}
    try:
        require(output_dir != repeat_dir, "Output and verification-repeat directories must differ")
        require(not data_dir.is_relative_to(output_dir) and not data_dir.is_relative_to(repeat_dir), "Output directory must not contain the input directory")
        report["environment"]["versions"] = {name: version(name) for name in ("pandas", "pyarrow", "networkx", "numpy", "scipy")}
        report["input_sha256_before"] = hashes(data_dir, INPUTS)
        for directory in (output_dir, repeat_dir):
            report["runs"].append(run_offline(data_dir, directory))
        report["csv_sha256"] = hashes(output_dir, SCHEMAS)
        require(report["csv_sha256"] == hashes(repeat_dir, SCHEMAS), "CSV outputs differ between repeat runs")
        report["input_sha256_after"] = hashes(data_dir, INPUTS)
        require(report["input_sha256_before"] == report["input_sha256_after"], "Source Parquet files changed")
        report.update(status="PASS", csv_byte_identical=True, input_unchanged=True)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / "acceptance_report.json"
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    except OSError as exc:
        print(f"FAIL: cannot write acceptance report: {exc}", file=sys.stderr)
        return 1
    print(f"{report['status']}: {destination}")
    if report["status"] != "PASS":
        print(report.get("error", "Acceptance failed"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
