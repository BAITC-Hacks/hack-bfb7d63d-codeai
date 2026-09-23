"""Provenance-preserving overlays for explicitly disjoint additional transfers.

This module never rewrites official inputs/CSVs or assigns analytical roles to
new accounts. Original data has no transaction IDs, so disjointness is a caller
declaration, not something the program can establish from aggregate pairs.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
import copy
import hashlib
import json
import math
import re

import pandas as pd


MAX_SUPPLEMENTARY_RECORDS = 50_000
MAX_LEDGER_RECORDS = 200_000
RECORD_FIELDS = {"src", "dst", "date", "sum_kzt", "source_reference", "transaction_id"}


def _integer(value, field):
    if isinstance(value, bool) or not (isinstance(value, int) or isinstance(value, str) and re.fullmatch(r"-?\d{1,19}", value)):
        raise ValueError(f"{field} must be an exact int64 integer or decimal string")
    result = int(value)
    if not -(2**63) <= result < 2**63:
        raise ValueError(f"{field} is outside int64 range")
    return result


def _gid(value):
    value = int(value)
    return str(value) if abs(value) > 2**53 - 1 else value


def _positive(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a positive finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{field} must fit a finite number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be a positive finite number")
    return number


def _text(value, field, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f"{field} must be nonempty text of at most {maximum} characters without control characters")
    # Preserve literal reference/ID identity: do not silently strip whitespace.
    return value


def _record(raw):
    if not isinstance(raw, dict) or set(raw) != RECORD_FIELDS:
        raise ValueError("Every supplementary transaction must contain exactly src, dst, date, sum_kzt, source_reference, transaction_id")
    if not isinstance(raw["date"], str) or not re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[T ])", raw["date"]):
        raise ValueError("Supplementary date must be an ISO date or timestamp string")
    try:
        timestamp = pd.Timestamp(raw["date"])
        if pd.isna(timestamp):
            raise ValueError("Missing date")
        timestamp = timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Supplementary date must be a valid ISO date or timestamp") from exc
    return {
        "src": _gid(_integer(raw["src"], "src")), "dst": _gid(_integer(raw["dst"], "dst")),
        "date": timestamp.isoformat(), "sum_kzt": _positive(raw["sum_kzt"], "sum_kzt"),
        "source_reference": _text(raw["source_reference"], "source_reference", 240),
        "transaction_id": _text(raw["transaction_id"], "transaction_id", 160),
    }


def _summary(graph):
    edges = graph.get("edges", [])
    return {"n_nodes": len(graph.get("nodes", [])), "n_edges": len(edges),
            "n_transactions": sum(int(edge.get("n_tx", 0)) for edge in edges),
            "total_kzt": math.fsum(float(edge["sum_kzt"]) for edge in edges)}


def _base_fingerprint(graph):
    if graph.get("meta", {}).get("dataset_fingerprint"):
        return graph["meta"]["dataset_fingerprint"]
    material = {"nodes": sorted(int(node["gid"]) for node in graph["nodes"]),
                "edges": sorted((int(edge["src"]), int(edge["dst"]), float(edge["sum_kzt"]), int(edge["n_tx"])) for edge in graph["edges"]),
                "daily": graph["replay"]}
    return hashlib.sha256(json.dumps(material, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _daily(graph):
    replay = graph.get("replay")
    if not isinstance(replay, dict) or not isinstance(replay.get("edges"), list):
        raise ValueError("Base analysis needs daily replay data; reanalyze the original files before expansion")
    result = {}
    for edge in replay["edges"]:
        src, dst = int(edge["src"]), int(edge["dst"])
        for row in edge["days"]:
            key = (src, dst, row["date"])
            if key in result:
                raise ValueError("Base replay contains duplicate pair/day records")
            result[key] = {"sum_kzt": float(row["sum_kzt"]), "n_tx": int(row["n_tx"])}
    amounts, counts = defaultdict(list), Counter()
    for (src, dst, day), item in result.items():
        amounts[(src, dst)].append(item["sum_kzt"])
        counts[(src, dst)] += item["n_tx"]
    expected = {(int(edge["src"]), int(edge["dst"])): edge for edge in graph["edges"]}
    if set(amounts) != set(expected):
        raise ValueError("Base replay pairs do not reconcile with graph edges")
    for pair, values in amounts.items():
        edge = expected[pair]
        if counts[pair] != int(edge["n_tx"]) or not math.isclose(math.fsum(values), float(edge["sum_kzt"]), rel_tol=1e-9, abs_tol=0.01):
            raise ValueError("Base replay amounts/counts do not reconcile with graph edges")
    return result


def expand_analysis(analysis, payload):
    """Return an additive overlay, with an explicit unverified-disjointness record.

    Pass a previous result's ``graph`` to accumulate another batch. Its embedded
    normalized ledger makes identical reuploads idempotent across calls.
    """
    if not isinstance(payload, dict) or set(payload) - {"incremental_disjoint", "transactions"}:
        raise ValueError("Expansion expects incremental_disjoint and transactions")
    if payload.get("incremental_disjoint") is not True:
        raise ValueError("Explicit incremental_disjoint=true is required: aggregate base data has no transaction IDs, so uncertain overlap cannot be merged")
    raw_records = payload.get("transactions")
    if not isinstance(raw_records, list) or not 1 <= len(raw_records) <= MAX_SUPPLEMENTARY_RECORDS:
        raise ValueError(f"Supply 1–{MAX_SUPPLEMENTARY_RECORDS} supplementary transactions per batch")
    if isinstance(analysis, dict) and "graph" in analysis:
        analysis = analysis["graph"]
    if not isinstance(analysis, dict) or not isinstance(analysis.get("nodes"), list) or not isinstance(analysis.get("edges"), list):
        raise ValueError("Expansion requires an analyzed graph")
    before = _summary(analysis)
    daily = _daily(analysis)
    original_pairs_days = set(daily)
    previous = analysis.get("expansion", {})
    previous_records = previous.get("records", [])
    if not isinstance(previous_records, list) or len(previous_records) > MAX_LEDGER_RECORDS:
        raise ValueError("Supplementary provenance ledger is invalid or too large")
    ledger = {}
    for raw in previous_records:
        record = _record(raw)
        key = (record["source_reference"], record["transaction_id"])
        if key in ledger and ledger[key] != record:
            raise ValueError("Supplementary provenance ledger has conflicting IDs")
        ledger[key] = record
    accepted, duplicates = [], 0
    for raw in raw_records:
        record = _record(raw)
        key = (record["source_reference"], record["transaction_id"])
        if key in ledger:
            if ledger[key] != record:
                raise ValueError("Conflicting supplementary transaction_id within source_reference")
            duplicates += 1
            continue
        ledger[key] = record
        accepted.append(record)
    if len(ledger) > MAX_LEDGER_RECORDS:
        raise ValueError(f"Supplementary ledger limit is {MAX_LEDGER_RECORDS} unique records")
    try:
        added_amount = math.fsum(record["sum_kzt"] for record in accepted)
    except OverflowError as exc:
        raise ValueError("Supplementary total exceeds supported finite numeric range") from exc
    if not math.isfinite(before["total_kzt"] + added_amount):
        raise ValueError("Expanded total exceeds supported finite numeric range")
    accepted.sort(key=lambda row: (row["date"], int(row["src"]), int(row["dst"]), row["source_reference"], row["transaction_id"]))
    nodes = {int(node["gid"]): copy.deepcopy(node) for node in analysis["nodes"]}
    old_ids = set(nodes)
    old_pairs = {(int(edge["src"]), int(edge["dst"])) for edge in analysis["edges"]}
    overlapping_records = 0
    for record in accepted:
        src, dst = int(record["src"]), int(record["dst"])
        day = record["date"][:10]
        key = (src, dst, day)
        overlapping_records += int(key in original_pairs_days)
        item = daily.setdefault(key, {"sum_kzt": 0.0, "n_tx": 0})
        item["sum_kzt"] += record["sum_kzt"]
        item["n_tx"] += 1
        for gid in (src, dst):
            if gid not in nodes:
                nodes[gid] = {"gid": _gid(gid), "is_seed": False, "depth": None,
                              "role": "unclassified", "role_assigned": False,
                              "role_score": None, "priority_score": None, "cluster_id": None,
                              "evidence": "Қосымша деректе алғаш көрінді. Рөл мен басымдық қайта есептелмеген.",
                              "flags": ["supplementary_only"], "role_scope": "supplementary_only"}
    amount_by_pair, count_by_pair = defaultdict(list), Counter()
    timeline_amounts, timeline_counts = defaultdict(list), Counter()
    pair_days = defaultdict(list)
    for (src, dst, day), item in sorted(daily.items()):
        if not math.isfinite(item["sum_kzt"]):
            raise ValueError("Expanded amount exceeds supported finite numeric range")
        amount_by_pair[(src, dst)].append(item["sum_kzt"])
        count_by_pair[(src, dst)] += item["n_tx"]
        timeline_amounts[day].append(item["sum_kzt"])
        timeline_counts[day] += item["n_tx"]
        pair_days[(src, dst)].append({"date": day, **item})
    incoming, outgoing, in_tx, out_tx = defaultdict(list), defaultdict(list), Counter(), Counter()
    payers, recipients, adjacency = defaultdict(set), defaultdict(set), defaultdict(set)
    edges = []
    for (src, dst), amounts in sorted(amount_by_pair.items()):
        amount = math.fsum(amounts)
        incoming[dst].append(amount)
        outgoing[src].append(amount)
        in_tx[dst] += count_by_pair[(src, dst)]
        out_tx[src] += count_by_pair[(src, dst)]
        if src != dst:
            payers[dst].add(src)
            recipients[src].add(dst)
        adjacency[src].add(dst)
        edges.append({"src": _gid(src), "dst": _gid(dst), "sum_kzt": amount,
                      "n_tx": count_by_pair[(src, dst)], "scope": "expanded_observed"})
    seed_ids = sorted(gid for gid, node in nodes.items() if node.get("is_seed"))
    distances, queue = {gid: 0 for gid in seed_ids}, deque(seed_ids)
    while queue:
        src = queue.popleft()
        for dst in sorted(adjacency[src]):
            if dst not in distances:
                distances[dst] = distances[src] + 1
                queue.append(dst)
    baseline_fields = ("depth", "role", "role_score", "priority_score", "cluster_id", "evidence",
                       "in_degree", "out_degree", "in_kzt", "out_kzt", "in_tx", "out_tx", "flags")
    for gid, node in sorted(nodes.items()):
        if node.get("role_scope") != "supplementary_only":
            node.setdefault("base_metrics", {key: copy.deepcopy(node.get(key)) for key in baseline_fields})
            node["role_scope"] = "base_snapshot"
            node["role_assigned"] = True
        else:
            node["depth"] = distances.get(gid)
        node["gid"] = _gid(gid)
        node["observed_depth"] = distances.get(gid)
        node["in_degree"], node["out_degree"] = len(payers[gid]), len(recipients[gid])
        node["in_kzt"], node["out_kzt"] = math.fsum(incoming[gid]), math.fsum(outgoing[gid])
        node["in_tx"], node["out_tx"] = in_tx[gid], out_tx[gid]
        node["pass_through"] = None
        node["analysis_status"] = "not_reanalyzed"
        node["scope_note"] = "Көрінетін ағындар кеңейтілді. Рөлдер, кластерлер және басымдықтар бастапқы талдауға ғана қатысты; жаңа шоттарға рөл берілмеді."
    all_dates = sorted(timeline_amounts)
    graph = {
        "nodes": [nodes[gid] for gid in sorted(nodes)], "edges": edges,
        "timeline": [{"date": day, "sum_kzt": math.fsum(timeline_amounts[day]), "n_tx": timeline_counts[day]} for day in all_dates],
        "replay": {"days": all_dates, "edges": [{"src": _gid(src), "dst": _gid(dst), "days": days} for (src, dst), days in sorted(pair_days.items())]},
    }
    after = _summary(graph)
    if not math.isfinite(after["total_kzt"]):
        raise ValueError("Expanded total exceeds supported finite numeric range")
    base_summary = copy.deepcopy(previous.get("base_summary", before))
    fingerprint = previous.get("base_fingerprint") or _base_fingerprint(analysis)
    normalized_ledger = sorted(ledger.values(), key=lambda row: (row["source_reference"], row["transaction_id"]))
    sources = Counter(record["source_reference"] for record in normalized_ledger)
    warnings = ["Бастапқы транзакция ID-лері жоқ: қосымша деректің бөлек екені пайдаланушы мәлімдемесі, автоматты дәлел емес.",
                "Бастапқы рөлдер мен басымдықтар қайта есептелмеді; кеңейтілген граф — бөлек зерттеу қабаты."]
    if overlapping_records:
        warnings.append(f"{overlapping_records} қосымша жазба бұрын көрінген жұп/күнге түседі; ID болмағандықтан қайталану тәуекелін дерек иесі тексеруі керек.")
    provenance = {
        "base_fingerprint": fingerprint, "base_summary": base_summary,
        "incremental_disjoint_assertion": True, "disjointness_verified": False,
        "accepted_transactions": len(accepted), "duplicate_transactions": duplicates,
        "total_supplementary_transactions": len(normalized_ledger),
        "same_pair_day_records": overlapping_records,
        "supplementary_sources": [{"source_reference": source, "n_transactions": count} for source, count in sorted(sources.items())],
        "warnings": warnings,
    }
    graph["expansion"] = {**provenance, "records": normalized_ledger}
    graph["meta"] = {**copy.deepcopy(analysis.get("meta", {})), **after,
                     "period_start": all_dates[0] if all_dates else None,
                     "period_end": all_dates[-1] if all_dates else None,
                     "scope": "supplementary_overlay", "roles_recomputed": False,
                     "max_observed_depth": max(distances.values(), default=0),
                     "warnings": warnings}
    comparison = {
        "before": before, "after": after, "base": base_summary,
        "new_nodes": len(set(nodes) - old_ids), "new_edges": len(set(amount_by_pair) - old_pairs),
        "added_kzt": added_amount, "added_transactions": len(accepted),
    }
    return {"graph": graph, "provenance": provenance, "base_comparison": comparison,
            "note": "Тек берілген қосымша операциялар қосылды. Бұл негізгі талдау мен ресми CSV файлдарын өзгертпейтін зерттеу қабаты; ақша иесін немесе ұйымдасқан бақылауды дәлелдемейді."}
