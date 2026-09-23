# AQSHA TRACE local API and data contract

Local offline web application and batch pipeline. Python package `moneygraph`, static UI `web/`. Runtime dependencies: pandas, pyarrow, networkx. No paid services or external data. The organizer dataset is loaded from `data/challenge/`; synthetic demo remains a separate mode. All analytical roles are hypotheses.

## Python interface
`from moneygraph.pipeline import analyze`
`analyze(data_dir, output_dir, *, demo=False) -> dict` reads exactly nodes.parquet, edges.parquet, transactions.parquet and writes nodes_roles.csv, clusters.csv, top_nodes.csv, analysis.json. Paths may be pathlib.Path. Use ValueError with useful validation messages.
`from moneygraph.demo import generate_demo`
`generate_demo(data_dir) -> None` creates deterministic plausible synthetic parquet files, at least 100 nodes and >=20 ranked candidates, all roles and censoring examples, plus isolated seeds. Seed integer IDs, fixed random seed. Only declared schema fields.

## Analysis JSON contract (all values finite, JSON-safe)
```
{
  "meta": {"demo": true, "generated_at": "ISO", "runtime_seconds": 0.1, "period_start": "2026-07-01", "period_end": "2026-07-31", "n_nodes": 120, "n_edges": 200, "n_transactions": 350, "n_seeds": 8, "n_clusters": 10, "total_kzt": 12345, "max_depth": 4, "warnings": ["..."]},
  "nodes": [{"gid": 1, "depth": 0, "is_seed": true, "role": "consolidator", "role_score": 0.8, "cluster_id": 0, "priority_score": 0.9, "evidence": "<=200 chars", "in_degree": 8, "out_degree": 2, "in_kzt": 40000, "out_kzt": 35000, "pass_through": 0.875, "betweenness": 0.01, "pagerank": 0.002, "flags": ["boundary_censored", "seed_inflow_incomplete", "outflow_exceeds_observed_inflow", "isolated"], "temporal": {"active_days": 5, "fast_forward_ratio": 0.6, "synchronized_payers": 4}, "next_request": "..."}],
  "edges": [{"src": 1, "dst": 2, "sum_kzt": 10000, "n_tx": 1, "depth": 1}],
  "clusters": [{"cluster_id": 0, "n_nodes": 8, "n_seed": 1, "sum_kzt_internal": 30000, "top_gids": [1,2], "hypothesis": "..."}],
  "top_nodes": [{"rank": 1, "gid": 1, "role": "consolidator", "priority_score": 0.9, "why": "..."}],
  "timeline": [{"date": "2026-07-01", "sum_kzt": 10000, "n_tx": 4}],
  "role_counts": {"consolidator": 3},
  "quality": {"boundary_nodes": 12, "isolated_seeds": 2, "seeds_without_outgoing": 4, "outflow_exceeds_inflow": 8, "weak_components": 5, "requests": [{"gid":1,"reason":"...","request":"..."}]}
}
```
`pass_through` is null when unreliable (seed or no observed inbound). Role labels remain English dictionary keys; UI uses Kazakh labels. Text evidence may be Russian or Kazakh; prefer clear Kazakh. `role_score` is heuristic rule strength, not calibrated probability. Never label depth=4 / zero-out nodes terminal solely by absence of outflow. Preserve ALL nodes including isolates; deterministic clusters. Validate columns, IDs, positive finite amounts, row-level types, edge endpoints, dates. Sum fields represent observed flows, not balances. Avoid time-derived causal proof or claiming the same funds moved onward.

Node JSON also includes `in_tx` and `out_tx`, sums of incoming/outgoing edge `n_tx`. These count transfers, separately from distinct counterparties and amounts. CSV schemas remain unchanged. IDs beyond JavaScript's safe integer range are decimal strings in JSON and exact int64 values in CSV.

## HTTP contract
- `GET /api/analysis`: latest analysis (or JSON error).
- `POST /api/demo` empty JSON: regenerate demo, analyze and return analysis.
- `POST /api/analyze`: JSON `{files:{"nodes.parquet":"base64", "edges.parquet":"base64", "transactions.parquet":"base64"}}`; process and return analysis.
- `GET /api/download/nodes_roles.csv` (and clusters.csv, top_nodes.csv, analysis.json).
- `POST /api/simulate`: JSON `{gids:[1,2]}` returns `{removed:[1,2], before:{n_nodes,n_edges,components,largest_component,reachable_from_seeds}, after:{...}, lost_reachable:number, observed_flow_removed_kzt:number, note:string}`. Decimal integer strings are accepted for int64 IDs that exceed JavaScript's safe integer range. Simulates structural deletion only; never actual account blocking or financial-loss prediction.
- UI may compute local node neighborhoods and filter graph by depth, cluster, role; preserve selected node search across filters.
- UI should work as provided through the local server, no CDN needed. All interactions functional. Full graph rendered via canvas is fine. Mark synthetic demo prominently. Include upload, reset demo, graph view, ranking view, cluster view, blind spots view, node evidence/details, simulation, CSV downloads. Target a polished desktop analytical workspace with responsive layout. No fabricated names/client attributes, no unsupported AI claims. Optional grounded assistant must identify itself as local rules if provided.
