"""Bounded, deterministic pattern hypotheses from observed daily transactions.

These detectors describe associations. Daily resolution cannot establish the
order of same-day payments, trace the same money, or prove common control.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict, deque
from datetime import date
import hashlib
import math
import statistics

import numpy as np
import pandas as pd


KINDS = ("activity_spike", "synchronized_payers", "fast_forward",
         "payment_splitting", "peer_outlier", "organizer_candidate")
DEFAULT_CAPS = {
    "max_events": 240, "max_cycles": 60, "max_routes": 80,
    "max_cycle_candidates": 25_000, "max_route_candidates": 50_000,
    "max_route_start_days": 128, "max_route_occurrences": 12,
    "max_replay_calendar_days": 3660, "max_cycle_dates": 128,
}


def _gid(value):
    value = int(value)
    return str(value) if abs(value) > 2**53 - 1 else value


def _day(value):
    return date.fromordinal(value).isoformat()


def _identifier(prefix, values):
    payload = "|".join(map(str, values)).encode("utf-8")
    return prefix + "-" + hashlib.sha256(payload).hexdigest()[:16]


def _amount(value):
    return round(float(value), 2)


class _Events:
    def __init__(self, maximum):
        self.maximum = maximum
        self.per_kind = math.ceil(maximum / len(KINDS)) if maximum else 0
        self.counts = Counter()
        self.pools = defaultdict(list)

    def add(self, kind, gids, day, title, evidence, metrics, strength, discriminator=""):
        item = {
            "id": _identifier("event-" + kind, [*gids, day, discriminator]),
            "kind": kind, "gids": [_gid(gid) for gid in gids],
            "date": _day(day) if day is not None else None,
            "title": title, "evidence": evidence, "metrics": metrics,
        }
        self.counts[kind] += 1
        if not self.per_kind:
            return
        pool = self.pools[kind]
        pool.append((-float(strength), item["id"], item))
        pool.sort(key=lambda entry: (entry[0], entry[1]))
        if len(pool) > self.per_kind:
            pool.pop()

    def finish(self):
        # Round-robin keeps each kind visible even when the global cap is small.
        result = []
        for position in range(self.per_kind):
            for kind in KINDS:
                if position < len(self.pools[kind]):
                    result.append(self.pools[kind][position][2])
                    if len(result) == self.maximum:
                        return result
        return result


def _temporal_occurrences(path, pair_days, caps):
    """Greedy, non-reused edge-day observations; not transaction-level tracing."""
    schedules = [sorted(pair_days[(a, b)]) for a, b in zip(path, path[1:])]
    starts = schedules[0][:caps["max_route_start_days"]]
    consumed = [set() for _ in schedules]
    found = []
    for first in starts:
        if first in consumed[0]:
            continue

        def complete(index, chosen):
            if index == len(schedules):
                return chosen
            previous = chosen[-1]
            schedule = schedules[index]
            begin = bisect_left(schedule, previous)
            end = bisect_right(schedule, min(previous + 2, first + 4))
            for candidate in schedule[begin:end]:
                if candidate not in consumed[index]:
                    answer = complete(index + 1, chosen + [candidate])
                    if answer is not None:
                        return answer
            return None

        sequence = complete(1, [first])
        if sequence is not None:
            found.append(sequence)
            for index, day in enumerate(sequence):
                consumed[index].add(day)
    return found, len(schedules[0]) > len(starts)


def derive_insights(nodes, transactions, *, caps=None):
    """Return (insights, replay, per-node IDs); never alter inputs or role scores.

    ``nodes`` are analytical node records; transactions use the validated source
    schema. ``caps`` exists for reproducible resource limits and bounded tests.
    """
    limits = dict(DEFAULT_CAPS)
    if caps:
        if set(caps) - set(limits):
            raise ValueError("Unknown insight cap")
        limits.update(caps)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in limits.values()):
        raise ValueError("Insight caps must be nonnegative integers")
    by_id = {int(node["gid"]): node for node in nodes}
    incoming = defaultdict(dict)
    outgoing = defaultdict(dict)
    pair_days = defaultdict(dict)
    sender_amounts = defaultdict(list)
    tx = transactions.copy()
    tx["date"] = pd.to_datetime(tx["date"], utc=True).dt.normalize()
    tx = tx.sort_values(["date", "src", "dst", "sum_kzt"], kind="stable")
    all_days = set()
    for row in tx.itertuples(index=False):
        src, dst = int(row.src), int(row.dst)
        day = row.date.date().toordinal()
        amount = float(row.sum_kzt)
        all_days.add(day)
        for table, account, counterparty in ((incoming, dst, src), (outgoing, src, dst)):
            item = table[account].setdefault(day, {"sum_kzt": 0.0, "n_tx": 0, "counterparties": set()})
            item["sum_kzt"] += amount
            item["n_tx"] += 1
            item["counterparties"].add(counterparty)
        item = pair_days[(src, dst)].setdefault(day, {"sum_kzt": 0.0, "n_tx": 0, "amounts": []})
        item["sum_kzt"] += amount
        item["n_tx"] += 1
        item["amounts"].append(amount)
        sender_amounts[(src, day)].append(amount)

    period_days = max(all_days) - min(all_days) + 1 if all_days else 0
    events = _Events(limits["max_events"])
    for direction, table in (("incoming", incoming), ("outgoing", outgoing)):
        for gid in sorted(table):
            daily = table[gid]
            total = math.fsum(item["sum_kzt"] for item in daily.values())
            if period_days < 7 or len(daily) < 3:
                continue
            for day, item in sorted(daily.items()):
                baseline = (total - item["sum_kzt"]) / (period_days - 1)
                if baseline <= 0 or item["n_tx"] < 3 or item["sum_kzt"] < 100_000:
                    continue
                ratio = item["sum_kzt"] / baseline
                share = item["sum_kzt"] / total
                if ratio >= 4 and share >= 0.40:
                    label = "Кіріс" if direction == "incoming" else "Шығыс"
                    events.add("activity_spike", [gid], day, label + " белсенділігінің шарықтауы",
                               f"{item['n_tx']} аударым, {_amount(item['sum_kzt']):,.0f} ₸. Басқа күндердің, нөлдік күндерді қоса, орташа көлемінен {ratio:.1f} есе; кезең көлемінің {share:.0%}-ы.",
                               {"direction": direction, "sum_kzt": _amount(item["sum_kzt"]), "n_tx": item["n_tx"],
                                "baseline_daily_kzt": _amount(baseline), "baseline_days": period_days - 1,
                                "ratio_to_baseline": round(ratio, 6), "period_share": round(share, 6)},
                               ratio, direction)

    for gid in sorted(incoming):
        for day, item in sorted(incoming[gid].items()):
            payers = sorted(item["counterparties"] - {gid})
            if len(payers) >= 4:
                shown = payers[:12]
                events.add("synchronized_payers", [gid, *shown], day, "Бір күндегі бірнеше төлеуші",
                           f"Бір күнде {len(payers)} түрлі төлеушіден {item['n_tx']} аударым, {_amount(item['sum_kzt']):,.0f} ₸. Күн ішіндегі реттілік пен ортақ бақылау белгісіз.",
                           {"payer_count": len(payers), "displayed_payers": len(shown),
                            "sum_kzt": _amount(item["sum_kzt"]), "n_tx": item["n_tx"]}, len(payers))

    for gid in sorted(by_id):
        inbound, outbound = incoming[gid], outgoing[gid]
        total_in = math.fsum(item["sum_kzt"] for item in inbound.values())
        total_out = math.fsum(item["sum_kzt"] for item in outbound.values())
        if by_id[gid].get("is_seed") or total_in <= 0 or total_out <= 0 or total_out > total_in + 0.01:
            continue
        if sum(item["n_tx"] for item in inbound.values()) < 3:
            continue
        available = deque()
        matched, same_day = 0.0, 0.0
        matched_days = []
        for day in sorted(set(inbound) | set(outbound)):
            while available and day - available[0][0] > 2:
                available.popleft()
            if day in inbound:
                available.append([day, inbound[day]["sum_kzt"]])
            remaining = outbound.get(day, {}).get("sum_kzt", 0.0)
            daily_match = 0.0
            while remaining > 0 and available:
                amount = min(remaining, available[0][1])
                remaining -= amount
                available[0][1] -= amount
                matched += amount
                daily_match += amount
                if day == available[0][0]:
                    same_day += amount
                if available[0][1] <= 0:
                    available.popleft()
            if daily_match > 0:
                matched_days.append(day)
        ratio = min(1.0, matched / total_in)
        if ratio >= 0.8:
            events.add("fast_forward", [gid], matched_days[0], "0–2 күндегі кіріс/шығыс сәйкестігі",
                       f"Көрінетін кірістің {ratio:.0%}-ына тең көлем 0–2 күндік терезедегі шығысқа сәйкеседі. Бұл күндік көлемдердің сәйкестігі; дәл сол ақша жіберілді деген дәлел емес.",
                       {"window_days": 2, "in_kzt": _amount(total_in), "out_kzt": _amount(total_out),
                        "matched_kzt": _amount(matched), "matched_inflow_ratio": round(ratio, 6),
                        "matching_outgoing_days": len(matched_days), "same_day_matched_kzt": _amount(same_day),
                        "same_day_order_unknown": same_day > 0}, ratio)

    def splitting(gids, day, amounts, scope):
        if len(amounts) < 4:
            return
        mean = statistics.fmean(amounts)
        coefficient = statistics.pstdev(amounts) / mean
        if max(amounts) / min(amounts) > 1.10 or coefficient > 0.10:
            return
        events.add("payment_splitting", gids, day, "Ұқсас сомалар топтамасы",
                   f"Бір күнде {len(amounts)} ұқсас аударым: {min(amounts):,.0f}–{max(amounts):,.0f} ₸. Бөлшектеу гипотезасы ғана; есептілік шегін айналып өту дәлелі емес.",
                   {"scope": scope, "n_tx": len(amounts), "sum_kzt": _amount(math.fsum(amounts)),
                    "minimum_kzt": _amount(min(amounts)), "maximum_kzt": _amount(max(amounts)),
                    "median_kzt": _amount(statistics.median(amounts)), "coefficient_of_variation": round(coefficient, 6),
                    "max_to_min_ratio": round(max(amounts) / min(amounts), 6)}, len(amounts), scope)

    for (src, dst), daily in sorted(pair_days.items()):
        for day, item in sorted(daily.items()):
            splitting([src, dst], day, item["amounts"], "same_pair")
    for (src, day), amounts in sorted(sender_amounts.items()):
        recipients = sorted(outgoing[src][day]["counterparties"] - {src})
        if len(recipients) >= 2:
            splitting([src, *recipients[:12]], day, amounts, "multiple_recipients")

    peers = defaultdict(list)
    for gid, node in sorted(by_id.items()):
        peers[int(node.get("depth", 0))].append(gid)
    for depth, gids in sorted(peers.items()):
        if len(gids) < 8:
            continue
        counterparties = {}
        for gid in gids:
            neighbors = set()
            for item in [*incoming[gid].values(), *outgoing[gid].values()]:
                neighbors.update(item["counterparties"])
            neighbors.discard(gid)
            counterparties[gid] = len(neighbors)
        feature_values = {
            "observed_volume_kzt": {gid: sum(item["sum_kzt"] for item in incoming[gid].values()) + sum(item["sum_kzt"] for item in outgoing[gid].values()) for gid in gids},
            "counterparties": counterparties,
        }
        flagged = defaultdict(list)
        for name, values in feature_values.items():
            q1, median, q3 = map(float, np.quantile(list(values.values()), [0.25, 0.5, 0.75]))
            minimum = 50_000 if name == "observed_volume_kzt" else 5
            fence = max(q3 + 3 * (q3 - q1), 3 * median, minimum)
            for gid, value in values.items():
                if value > fence:
                    flagged[gid].append({"name": name, "value": _amount(value), "median": _amount(median),
                                         "q1": _amount(q1), "q3": _amount(q3), "upper_fence": _amount(fence)})
        for gid, features in sorted(flagged.items()):
            names = "көлемі" if any(f["name"] == "observed_volume_kzt" for f in features) else "контрагенттер саны"
            events.add("peer_outlier", [gid], None, "Өз буынынан өзгеше профиль",
                       f"{depth}-буындағы {len(gids)} шотпен салыстырғанда {names} жоғарғы робасты шектен асады. Бұл салыстырмалы ауытқу, заңсыздық белгісі емес.",
                       {"depth": depth, "cohort_size": len(gids), "features": features},
                       max(f["value"] / max(f["upper_fence"], 1) for f in features))

    for gid, node in sorted(by_id.items()):
        if node.get("role") != "coordinator":
            continue
        events.add("organizer_candidate", [gid], None, "Үйлестіру гипотезасын тексеру",
                   f"{node.get('in_degree', 0)} кіріс, {node.get('out_degree', 0)} шығыс контрагенті; {node.get('external_communities', 0)} сыртқы қауымдастықпен байланыс. Орталық орын ұйымдастырушы екенін дәлелдемейді.",
                   {"in_degree": int(node.get("in_degree", 0)), "out_degree": int(node.get("out_degree", 0)),
                    "external_communities": int(node.get("external_communities", 0)),
                    "betweenness": float(node.get("betweenness", 0)),
                    "existing_role_score": float(node.get("role_score", 0))}, float(node.get("priority_score", 0)))

    adjacency = defaultdict(list)
    for src, dst in sorted(pair_days):
        if src != dst:
            adjacency[src].append(dst)
    cycles, cycle_count, cycle_scanned, cycle_search_truncated = [], 0, 0, False
    for start in sorted(adjacency):
        stack = [(start, [start], iter(adjacency[start]))]
        while stack:
            current, path, iterator = stack[-1]
            target = next(iterator, None)
            if target is None:
                stack.pop()
                continue
            if cycle_scanned >= limits["max_cycle_candidates"]:
                cycle_search_truncated = True
                break
            cycle_scanned += 1
            if target == start and len(path) >= 2:
                cycle_count += 1
                pairs = list(zip(path, path[1:] + [start]))
                amount = math.fsum(item["sum_kzt"] for pair in pairs for item in pair_days[pair].values())
                observed = sorted({day for pair in pairs for day in pair_days[pair]})
                cycles.append({"id": _identifier("cycle", path), "gids": [_gid(gid) for gid in path],
                               "edges": [{"src": _gid(a), "dst": _gid(b)} for a, b in pairs],
                               "title": f"{len(path)} буынды бағытталған цикл",
                               "evidence": f"{len(path)} бағытталған байланыс тұйық жол құрады; олардың кезеңдік көлемі {amount:,.0f} ₸. Ақшаның уақыт ретімен толық қайтқаны дәлелденбеген.",
                               "observed_dates": [_day(day) for day in observed[:limits["max_cycle_dates"]]],
                               "n_observed_dates": len(observed), "observed_dates_truncated": len(observed) > limits["max_cycle_dates"],
                               "sum_kzt": _amount(amount),
                               "length": len(path), "temporal_order_verified": False})
                cycles.sort(key=lambda item: (-item["sum_kzt"], item["id"]))
                if len(cycles) > limits["max_cycles"]:
                    cycles.pop()
            elif len(path) < 4 and target > start and target not in path:
                stack.append((target, path + [target], iter(adjacency[target])))
        if cycle_search_truncated:
            break
    routes, route_count, route_scanned, route_search_truncated, route_days_truncated = [], 0, 0, False, 0
    for start in sorted(adjacency):
        stack = [(start, [start], iter(adjacency[start]))]
        while stack:
            current, path, iterator = stack[-1]
            target = next(iterator, None)
            if target is None:
                stack.pop()
                continue
            if route_scanned >= limits["max_route_candidates"]:
                route_search_truncated = True
                break
            route_scanned += 1
            if target in path or len(pair_days[(current, target)]) < 2:
                continue
            extended = path + [target]
            if len(extended) >= 3:
                occurrences, days_truncated = _temporal_occurrences(extended, pair_days, limits)
                route_days_truncated += int(days_truncated)
                if len(occurrences) >= 2:
                    route_count += 1
                    routes.append({"id": _identifier("route", extended), "gids": [_gid(gid) for gid in extended],
                                   "edges": [{"src": _gid(a), "dst": _gid(b)} for a, b in zip(extended, extended[1:])],
                                   "title": f"Қайталанатын {len(extended) - 1} буындық маршрут",
                                   "evidence": f"{len(occurrences)} бөлек күндік сәйкестік: әр келесі буын 0–2 күн ішінде, толық терезе ≤4 күн. Бұл бір ақшаның қозғалысын дәлелдемейді; бір күндегі реттілік белгісіз.",
                                   "n_occurrences": len(occurrences),
                                   "occurrences": [{"dates": [_day(day) for day in days], "start_date": _day(days[0]), "end_date": _day(days[-1])} for days in occurrences[:limits["max_route_occurrences"]]],
                                   "occurrences_truncated": len(occurrences) > limits["max_route_occurrences"],
                                   "n_occurrences_is_lower_bound": days_truncated,
                                   "same_day_order_unknown": any(len(set(days)) < len(days) for days in occurrences),
                                   "length": len(extended) - 1})
                    routes.sort(key=lambda item: (-item["n_occurrences"], -item["length"], item["id"]))
                    if len(routes) > limits["max_routes"]:
                        routes.pop()
            if len(extended) < 4:
                stack.append((target, extended, iter(adjacency[target])))
        if route_search_truncated:
            break
    emitted_events = events.finish()
    event_count = sum(events.counts.values())
    replay_truncated = period_days > limits["max_replay_calendar_days"]
    replay_days = sorted(all_days)[:limits["max_replay_calendar_days"]] if replay_truncated else (range(min(all_days), max(all_days) + 1) if all_days else [])
    limits.update({
        "max_events_per_kind": events.per_kind, "events_detected": event_count,
        "events_truncated": event_count > len(emitted_events),
        "cycles_detected": cycle_count, "cycles_truncated": cycle_count > len(cycles),
        "cycle_candidates_scanned": cycle_scanned, "cycle_search_truncated": cycle_search_truncated,
        "routes_detected": route_count, "routes_truncated": route_count > len(routes),
        "route_candidates_scanned": route_scanned, "route_search_truncated": route_search_truncated,
        "route_start_days_truncated": route_days_truncated,
        "replay_calendar_truncated": replay_truncated,
    })
    insights = {
        "summary": {"event_count": len(emitted_events), "events_by_kind": dict(Counter(item["kind"] for item in emitted_events)),
                    "detected_events_by_kind": dict(sorted(events.counts.items())), "cycle_count": len(cycles), "route_count": len(routes)},
        "events": emitted_events, "cycles": cycles, "routes": routes, "limits": limits,
        "methodology": {
            "version": "1.0", "time_resolution": "UTC calendar day",
            "activity_spike": "At least 7 calendar days and 3 active days; >=3 transactions, >=100000 KZT, >=4 times the leave-one-day-out mean including zero days, >=40% of that direction's period volume.",
            "synchronized_payers": ">=4 distinct non-self payers to one recipient on one calendar day; up to 12 payer IDs displayed.",
            "fast_forward": "Non-seed, observed outflow <= inflow, >=3 incoming transactions; FIFO daily-volume overlap in 0–2 days >=80% of observed inflow. No same-money inference. Existing role/priority temporal metric remains unchanged.",
            "payment_splitting": ">=4 payments in a day for one pair or one sender to multiple recipients; max/min <=1.10 and population coefficient of variation <=0.10. No regulatory/reporting threshold is assumed.",
            "peer_outlier": "Same-depth cohort >=8. Volume or unique counterparties strictly above max(Q3+3*IQR,3*median,50000 KZT or 5 counterparties); zero-activity peers remain in the cohort.",
            "organizer_candidate": "Existing coordinator-role hypotheses summarized with observed degree, community links and centrality. Does not establish identity, ownership, or organizational control.",
            "cycles": "Simple directed structural cycles of length 2–4, rotation-deduplicated. Temporal order is not verified; summed edge turnover is not a returned-money amount.",
            "routes": "Simple paths of 2–3 edges, each observed on >=2 dates; >=2 greedily matched sequences with nondecreasing days, 0–2 days per hop and <=4 days total. Edge-day observations are not reused within one route; sequences may overlap across different routes. Counts are descriptive, not a maximum matching.",
            "bounds": "Search examines sorted integer GIDs deterministically. Caps can omit later-ID candidates; counters and truncation flags expose this bias. Events retain strongest examples within each kind.",
            "caveat": "Daily associations and graph motifs are investigative hypotheses. Same-day order, same funds, common control, and illegality are not established.",
        },
    }
    replay = {"days": [_day(day) for day in replay_days],
              "edges": [{"src": _gid(src), "dst": _gid(dst),
                         "days": [{"date": _day(day), "sum_kzt": float(item["sum_kzt"]), "n_tx": item["n_tx"]}
                                  for day, item in sorted(daily.items())]}
                        for (src, dst), daily in sorted(pair_days.items())]}
    node_ids = {gid: [] for gid in by_id}
    for item in [*emitted_events, *cycles, *routes]:
        for gid in dict.fromkeys(int(value) for value in item["gids"]):
            if gid in node_ids:
                node_ids[gid].append(item["id"])
    return insights, replay, node_ids


def enrich_analysis(analysis, transactions):
    """Add insight/replay fields while preserving all existing CSV contracts."""
    insights, replay, references = derive_insights(analysis["nodes"], transactions)
    analysis["insights"] = insights
    analysis["replay"] = replay
    for node in analysis["nodes"]:
        node["insight_ids"] = references[int(node["gid"])]
