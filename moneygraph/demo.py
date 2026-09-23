"""Reproducible synthetic input with the same schema as the competition extract.

The fixture is an illustration of observable network patterns, not a labelled
criminal network or ground truth for the heuristic role classifier.
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import random

import pandas as pd


def generate_demo(data_dir: str | Path) -> None:
    """Write three deterministic Parquet inputs containing 214 synthetic nodes.

    Four repeated motifs include fan-in, retained observed inflow, near-balanced
    transit, fan-out, intermediate zero-outflow recipients and depth-four leaves.
    Three motifs have a bridge; the fourth is disconnected. Receiving-only and
    isolated seeds represent extraction limitations explicitly. No role, name or
    other invented client attribute is written into the source data.
    """
    destination = Path(data_dir)
    destination.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20260701)
    seeds: set[int] = set()
    all_gids: list[int] = []
    rows: list[dict] = []
    next_gid = 100001

    def allocate(count: int, *, seed: bool = False) -> list[int]:
        nonlocal next_gid
        gids = list(range(next_gid, next_gid + count))
        next_gid += count
        all_gids.extend(gids)
        if seed:
            seeds.update(gids)
        return gids

    def transfer(src: int, dst: int, amount: int, day: int) -> None:
        assert amount >= 5_000
        rows.append({"src": src, "dst": dst,
                     "date": pd.Timestamp(2026, 7, day), "sum_kzt": amount})

    groups: list[dict[str, list[int]]] = []
    for _ in range(4):
        groups.append({
            "seeds": allocate(8, seed=True),
            "collectors": allocate(5),
            "transits": allocate(5),
            "coordinators": allocate(1),
            "distributors": allocate(5),
            "recipients": allocate(2),
            "boundary": allocate(25),
            "receiving_seed": allocate(1, seed=True),
        })

    # Distinct integer GIDs are the only identities. These are not real clients.
    allocate(4, seed=True)
    allocate(2)

    for group_index, group in enumerate(groups):
        coordinator = group["coordinators"][0]
        for first_day in (2, 9, 16, 23):
            for seed in group["seeds"]:
                for collector in group["collectors"]:
                    transfer(seed, collector,
                             rng.randrange(20_000, 40_001, 1_000), first_day)

            for offset, collector in enumerate(group["collectors"]):
                transfer(collector, group["transits"][offset], 30_000, first_day + 1)
                transfer(collector, coordinator, 30_000, first_day + 1)
                transfer(collector, group["recipients"][offset % 2], 10_000, first_day + 1)

            # A small recurring directed cycle tests that reachability terminates.
            cycle = group["collectors"][:3]
            for src, dst in zip(cycle, cycle[1:] + cycle[:1]):
                transfer(src, dst, 5_000, first_day + 1)

            for offset, transit in enumerate(group["transits"]):
                # One node per motif has observed outflow greater than inflow.
                # This illustrates missing input, and must not be called profit.
                amount = 45_000 if offset == 0 else 28_500
                transfer(transit, group["distributors"][offset], amount, first_day + 2)

            for distributor in group["distributors"]:
                transfer(coordinator, distributor, 24_000, first_day + 2)

            # The first three motifs form one weak component with nonlocal paths.
            if group_index < 3:
                adjacent = groups[(group_index + 1) % 3]
                transfer(coordinator, adjacent["distributors"][0], 8_000, first_day + 2)

            for offset, distributor in enumerate(group["distributors"]):
                for recipient in group["boundary"][offset * 5:(offset + 1) * 5]:
                    transfer(distributor, recipient, 10_000, first_day + 3)

            transfer(group["collectors"][-1], group["receiving_seed"][0],
                     5_000, first_day + 1)

        # A low but positively observed onward transfer distinguishes this
        # intermediate retained-flow example from unobserved boundary outflow.
        transfer(group["recipients"][1], group["recipients"][0], 5_000, 25)

    transactions = pd.DataFrame(rows, columns=["src", "dst", "date", "sum_kzt"])
    transactions = transactions.sort_values(["date", "src", "dst"], kind="stable").reset_index(drop=True)
    for column in ("src", "dst", "sum_kzt"):
        transactions[column] = transactions[column].astype("int64")

    adjacency: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        adjacency[row["src"]].add(row["dst"])
    depths = {gid: 0 for gid in seeds}
    queue = deque(sorted(seeds))
    while queue:
        src = queue.popleft()
        for dst in sorted(adjacency[src]):
            if dst not in depths:
                depths[dst] = depths[src] + 1
                queue.append(dst)

    # An isolated non-seed's depth is supplied by the original extraction; there
    # is no observed route left in this filtered fixture. Keep it, do not invent one.
    nodes = pd.DataFrame({
        "gid": all_gids,
        "depth": [depths.get(gid, 4) for gid in all_gids],
        "is_seed": [gid in seeds for gid in all_gids],
    }).astype({"gid": "int64", "depth": "int64", "is_seed": "bool"})
    edges = transactions.groupby(["src", "dst"], as_index=False, sort=True).agg(
        sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size"))
    # Edge depth is the traversal step at its source, including back/cross edges.
    edges["depth"] = [min(depths.get(int(src), 3) + 1, 4) for src in edges["src"]]
    edges = edges[["src", "dst", "sum_kzt", "n_tx", "depth"]].astype("int64")

    nodes.to_parquet(destination / "nodes.parquet", index=False)
    edges.to_parquet(destination / "edges.parquet", index=False)
    transactions.to_parquet(destination / "transactions.parquet", index=False)
