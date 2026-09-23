"""Deterministic, entirely synthetic input data for demonstrating Step 1.

These identifiers and transfers do not represent the competition dataset or
known illicit activity. No role/priority outputs are hardcoded here.
"""

from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo

import pandas as pd


def create_demo_frames() -> dict[str, pd.DataFrame]:
    nodes = pd.DataFrame(
        {
            "gid": range(1001, 1017),
            "depth": [0, 0, 0, 0, 1, 1, 1, 2, 2, 3, 3, 3, 3, 4, 4, 4],
            "is_seed": [True] * 4 + [False] * 12,
        }
    )
    # 1004 is intentionally an isolated seed and must survive validation.
    rows = [
        (1001, 1005, "2026-07-02", 50_000),
        (1001, 1005, "2026-07-03", 25_000),
        (1002, 1005, "2026-07-03", 65_000),
        (1003, 1005, "2026-07-04", 80_000),
        (1002, 1006, "2026-07-04", 35_000),
        (1003, 1007, "2026-07-05", 40_000),
        (1005, 1008, "2026-07-05", 110_000),
        (1005, 1008, "2026-07-06", 90_000),
        (1006, 1009, "2026-07-06", 30_000),
        (1007, 1009, "2026-07-07", 35_000),
        (1008, 1010, "2026-07-08", 50_000),
        (1008, 1011, "2026-07-08", 55_000),
        (1008, 1012, "2026-07-09", 45_000),
        (1009, 1013, "2026-07-10", 60_000),
        (1010, 1014, "2026-07-11", 40_000),
        (1011, 1015, "2026-07-12", 50_000),
        (1013, 1016, "2026-07-13", 55_000),
    ]
    transactions = pd.DataFrame(rows, columns=["src", "dst", "date", "sum_kzt"])
    transactions["date"] = pd.to_datetime(transactions["date"])
    edges = transactions.groupby(["src", "dst"], as_index=False, sort=True).agg(
        sum_kzt=("sum_kzt", "sum"), n_tx=("sum_kzt", "size")
    )
    node_depth = nodes.set_index("gid")["depth"]
    edges["depth"] = edges["dst"].map(node_depth).astype("int64")
    return {"nodes": nodes, "edges": edges, "transactions": transactions}


def create_demo_files() -> dict[str, bytes]:
    files = {}
    for name, frame in create_demo_frames().items():
        output = BytesIO()
        frame.to_parquet(output, index=False, engine="pyarrow")
        files[f"{name}.parquet"] = output.getvalue()
    return files


def create_demo_zip() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in create_demo_files().items():
            entry = ZipInfo(name, date_time=(2026, 7, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, payload)
        readme = (
            "MoneyMap synthetic demo / Толығымен жасанды демо\n\n"
            "These are programmatically generated test inputs, NOT the real case dataset.\n"
            "Бұл файлдар нақты клиенттерді, нақты істі немесе қылмыстық байланыстарды сипаттамайды.\n"
            "16 clients, 15 directed pairs, 17 transactions, July 2026.\n"
            "Client 1004 is an isolated seed; clients 1014–1016 are at depth 4.\n"
        )
        entry = ZipInfo("DEMO_README.txt", date_time=(2026, 7, 1, 0, 0, 0))
        entry.compress_type = ZIP_DEFLATED
        archive.writestr(entry, readme.encode("utf-8"))
    return output.getvalue()
