"""Directed route exploration with finite scope and resumable work budgets."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import secrets

import networkx as nx


_CURSOR_SECRET = secrets.token_bytes(32)
MAX_BUDGET = 100_000
MAX_RESULTS = 100


def _integer(value, name):
    if isinstance(value, bool) or not (isinstance(value, int) or isinstance(value, str) and re.fullmatch(r"-?\d{1,19}", value)):
        raise ValueError(f"{name} must be an exact int64 integer or decimal string")
    result = int(value)
    if not -(2**63) <= result < 2**63:
        raise ValueError(f"{name} is outside int64 range")
    return result


def _gid(value):
    return str(value) if abs(value) > 2**53 - 1 else value


def _bounded(value, name, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def _digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _encode_cursor(value):
    body = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(_CURSOR_SECRET, body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature + body).decode().rstrip("=")


def _decode_cursor(value):
    if not isinstance(value, str) or not value or len(value) > 8192:
        raise ValueError("Invalid exploration cursor")
    try:
        packed = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        signature, body = packed[:32], packed[32:]
        if not hmac.compare_digest(signature, hmac.new(_CURSOR_SECRET, body, hashlib.sha256).digest()):
            raise ValueError("signature")
        decoded = json.loads(body)
        if not isinstance(decoded, dict):
            raise ValueError("structure")
        return decoded
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("Cursor is invalid or expired; restart exploration after server restart") from exc


def explore_paths(analysis, payload):
    """Find observed simple directed paths/cycles, or an exact shortest path.

    A cursor is authenticated, carries only a DFS stack/counters, and is bound
    to the graph and search scope. It does not retain a background server job.
    """
    allowed = {"start_gid", "end_gid", "max_hops", "max_results", "budget", "kind", "cursor"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError("Invalid exploration fields")
    if isinstance(analysis, dict) and "graph" in analysis:
        analysis = analysis["graph"]
    if not isinstance(analysis, dict) or not isinstance(analysis.get("nodes"), list) or not isinstance(analysis.get("edges"), list):
        raise ValueError("Exploration requires an analyzed graph")
    start = _integer(payload.get("start_gid"), "start_gid")
    end = _integer(payload["end_gid"], "end_gid") if payload.get("end_gid") is not None else None
    kind = payload.get("kind", "paths")
    if kind not in {"paths", "cycles", "shortest"}:
        raise ValueError("kind must be paths, cycles, or shortest")
    if kind == "shortest" and end is None:
        raise ValueError("Shortest-path search requires end_gid")
    if kind == "cycles" and end not in {None, start}:
        raise ValueError("A cycle ends at start_gid; omit end_gid or set it to start_gid")
    max_hops = _bounded(payload.get("max_hops", 4), "max_hops", 12)
    max_results = _bounded(payload.get("max_results", 20), "max_results", MAX_RESULTS)
    budget = _bounded(payload.get("budget", 20_000), "budget", MAX_BUDGET)
    graph = nx.DiGraph()
    graph.add_nodes_from(int(node["gid"]) for node in analysis["nodes"])
    for edge in sorted(analysis["edges"], key=lambda row: (int(row["src"]), int(row["dst"]))):
        src, dst = int(edge["src"]), int(edge["dst"])
        if src not in graph or dst not in graph or graph.has_edge(src, dst):
            raise ValueError("Graph endpoints must exist and directed edge pairs must be unique")
        amount, count = float(edge["sum_kzt"]), int(edge.get("n_tx", 0))
        if not math.isfinite(amount) or amount < 0 or count < 0:
            raise ValueError("Graph edge amounts/counts must be finite and nonnegative")
        graph.add_edge(src, dst, sum_kzt=amount, n_tx=count)
    if start not in graph or end is not None and end not in graph:
        raise ValueError("Requested start_gid or end_gid is absent from the observed graph")
    material = {"nodes": sorted(graph.nodes), "edges": sorted((src, dst, row["sum_kzt"], row["n_tx"]) for src, dst, row in graph.edges(data=True))}
    fingerprint = _digest(material)
    scope_identity = {"kind": kind, "start": start, "end": end, "max_hops": max_hops if kind != "shortest" else None, "graph": fingerprint}
    scope_hash = _digest(scope_identity)
    scope = {"kind": kind, "start_gid": _gid(start), "end_gid": _gid(end) if end is not None else None,
             "max_hops": max_hops if kind != "shortest" else None,
             "graph_fingerprint": fingerprint, "directed": True, "simple_paths": True,
             "temporal_order_verified": False, "graph_nodes": graph.number_of_nodes(), "graph_edges": graph.number_of_edges()}

    def route(path):
        arcs = [{"src": _gid(src), "dst": _gid(dst), **graph[src][dst]} for src, dst in zip(path, path[1:])]
        amount = math.fsum(edge["sum_kzt"] for edge in arcs)
        return {"id": "explore-" + _digest([kind, path])[:20], "gids": [_gid(gid) for gid in path],
                "edges": arcs, "length": len(arcs), "observed_volume_kzt": amount,
                "evidence": f"{len(arcs)} нақты бағытталған байланыс; кезеңдік қабырға сомаларының қосындысы {amount:,.0f} ₸. Бұл бір ақшаның жолы немесе уақыт ретімен өткен аударымдар деген дәлел емес.",
                "temporal_order_verified": False}

    note = "Нәтиже берілген граф пен сұралған шекте ғана толық болуы мүмкін. Көрінбейтін аударымдар, нақты ақша сәйкестігі және уақыттық реттілік анықталмайды."
    if kind == "shortest":
        if payload.get("cursor"):
            raise ValueError("Shortest-path search does not use a cursor")
        try:
            shortest = route(nx.shortest_path(graph, start, end))
        except nx.NetworkXNoPath:
            shortest = None
        return {"routes": [shortest] if shortest else [], "shortest_path": shortest, "scope": scope,
                "limits": {"result_limit": 1, "results_returned": int(shortest is not None),
                           "budget_applies": False, "algorithm": "unweighted bidirectional BFS", "hop_limit_applies": False},
                "complete_within_scope": True, "next_cursor": None, "cursor": None, "note": note}

    adjacency = {gid: sorted(graph.successors(gid)) for gid in graph.nodes}
    cumulative_work, cumulative_results = 0, 0
    stack = [[start, 0]]
    if payload.get("cursor"):
        saved = _decode_cursor(payload["cursor"])
        if saved.get("version") != 1 or saved.get("scope") != scope_hash:
            raise ValueError("Cursor belongs to a different graph or search scope; restart exploration")
        stack = saved.get("stack")
        if not isinstance(stack, list) or not 1 <= len(stack) <= max_hops + 1:
            raise ValueError("Invalid cursor stack")
        path = []
        for frame in stack:
            if not isinstance(frame, list) or len(frame) != 2:
                raise ValueError("Invalid cursor frame")
            gid, index = frame
            if gid not in graph or isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= len(adjacency[gid]):
                raise ValueError("Invalid cursor position")
            if gid in path or path and not graph.has_edge(path[-1], gid):
                raise ValueError("Invalid cursor path")
            path.append(gid)
        if path[0] != start:
            raise ValueError("Invalid cursor root")
        cumulative_work, cumulative_results = int(saved.get("work", 0)), int(saved.get("results", 0))
    routes, work = [], 0
    while stack and work < budget and len(routes) < max_results:
        current, index = stack[-1]
        if index >= len(adjacency[current]):
            stack.pop()
            continue
        target = adjacency[current][index]
        stack[-1][1] += 1
        work += 1
        path = [frame[0] for frame in stack]
        if kind == "cycles" and target == start:
            if len(path) <= max_hops:
                routes.append(route(path + [start]))
            continue
        if target in path or len(path) > max_hops:
            continue
        extended = path + [target]
        if len(path) < max_hops and not (kind == "paths" and target == end):
            stack.append([target, 0])
        if kind == "paths" and (end is None or target == end):
            routes.append(route(extended))
    while stack and stack[-1][1] >= len(adjacency[stack[-1][0]]):
        stack.pop()
    complete = not stack
    token = None if complete else _encode_cursor({"version": 1, "scope": scope_hash, "stack": stack,
                                                "work": cumulative_work + work, "results": cumulative_results + len(routes)})
    return {"routes": routes, "shortest_path": None, "scope": scope,
            "limits": {"work_budget": budget, "budget_used": work, "cumulative_work": cumulative_work + work,
                       "result_limit": max_results, "results_returned": len(routes),
                       "cumulative_results": cumulative_results + len(routes),
                       "budget_applies": True, "budget_exhausted": not complete and work >= budget,
                       "result_limit_reached": not complete and len(routes) >= max_results,
                       "cursor_resumable": not complete},
            "complete_within_scope": complete, "next_cursor": token, "cursor": token, "note": note}
