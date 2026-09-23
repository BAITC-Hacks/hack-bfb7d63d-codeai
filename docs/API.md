# AQSHA TRACE local API and data contract

Local web application and batch pipeline. Python package `moneygraph`, static UI `web/`. Core runtime dependencies include pandas, pyarrow, networkx and ReportLab. No paid service is required. The organizer dataset is loaded from `data/challenge/`; synthetic demo remains a separate mode. Supplementary records and analyst assertions are explicit user inputs. An optional language model runs on a separate loopback server. All analytical roles are hypotheses.

## Python interface
`from moneygraph.pipeline import analyze`
`analyze(data_dir, output_dir, *, demo=False) -> dict` reads exactly nodes.parquet, edges.parquet, transactions.parquet and writes nodes_roles.csv, clusters.csv, top_nodes.csv, analysis.json. Paths may be pathlib.Path. Use ValueError with useful validation messages.
`from moneygraph.demo import generate_demo`
`generate_demo(data_dir) -> None` creates deterministic plausible synthetic parquet files, at least 100 nodes and >=20 ranked candidates, all roles and censoring examples, plus isolated seeds. Seed integer IDs, fixed random seed. Only declared schema fields.

## Analysis JSON contract (all values finite, JSON-safe)
```
{
  "meta": {"demo": true, "generated_at": "ISO", "runtime_seconds": 0.1, "period_start": "2026-07-01", "period_end": "2026-07-31", "n_nodes": 120, "n_edges": 200, "n_transactions": 350, "n_seeds": 8, "n_clusters": 10, "total_kzt": 12345, "max_depth": 4, "warnings": ["..."]},
  "nodes": [{"gid": 1, "depth": 0, "is_seed": true, "role": "consolidator", "role_score": 0.7, "cluster_id": 0, "priority_score": 0.9, "evidence": "<=200 chars", "in_degree": 8, "out_degree": 2, "in_kzt": 40000, "out_kzt": 35000, "pass_through": null, "betweenness": 0.01, "pagerank": 0.002, "flags": ["seed_inflow_incomplete"], "temporal": {"active_days": 5, "fast_forward_ratio": null, "synchronized_payers": 4}, "next_request": "..."}],
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

## Investigative extensions

`insights` contains `summary`, `events`, `cycles`, `routes`, `limits` and
`methodology`. `summary` distinguishes retained records from
`detected_events_by_kind`. Each event has `id,kind,gids,date,title,evidence,metrics`.
Kinds are `activity_spike,synchronized_payers,fast_forward,payment_splitting,
peer_outlier,organizer_candidate`. Period-wide events can have a null date.
Cycles/routes have `id,gids,edges:[{src,dst}],title,evidence`; cycles also have
`observed_dates,sum_kzt,length,temporal_order_verified:false`; routes include
`n_occurrences,occurrences:[{dates,start_date,end_date}],length,
same_day_order_unknown` and occurrence truncation metadata.

`limits` is a flat dictionary: numeric caps, `events_detected`,
`cycles_detected`, `routes_detected`, candidate counters, and individual
storage/search truncation flags. Display truncation explicitly. Do not describe
retained counts as exhaustive. `methodology` has a version and human-readable
definitions for each detector. Node `insight_ids` references retained records.

`replay` is `{days:[ISODate],edges:[{src,dst,days:[{date,sum_kzt,n_tx}]}]}`.
The calendar normally includes empty days. Each pair's daily totals reconcile
with its period totals. GIDs remain exact in every nested object. Replay filters
edges; role/priority scores still refer to the full analysis period.

## HTTP contract
- Investigation writes (`/api/reviews`, `/api/expand`) accept optional `expected_dataset_fingerprint`, checked under the state lock against the current source fingerprint. A stale browser request is rejected before writing to another dataset; the UI supplies this field. It is not passed into the pure review/expansion functions.
- `GET /api/analysis`: latest analysis (or JSON error).
- `POST /api/demo` empty JSON: regenerate demo, analyze and return analysis.
- `POST /api/analyze`: JSON `{files:{"nodes.parquet":"base64", "edges.parquet":"base64", "transactions.parquet":"base64"}}`; process and return analysis.
- `GET /api/download/nodes_roles.csv` (and clusters.csv, top_nodes.csv, analysis.json).
- `POST /api/simulate`: JSON `{gids:[1,2]}` returns `{removed:[1,2], before:{n_nodes,n_edges,components,largest_component,reachable_from_seeds}, after:{...}, lost_reachable:number, observed_flow_removed_kzt:number, note:string}`. Decimal integer strings are accepted for int64 IDs that exceed JavaScript's safe integer range. Simulates structural deletion only; never actual account blocking or financial-loss prediction.
- The simulation also accepts `{top_n:5,curve:true}` instead of `gids`. Ranking is by priority descending, exact numeric GID ascending for ties. `top_n` is an integer from 1 to 100; small graphs use all available accounts. `requested_n`, `actual_n`, and `selection` describe the selection. With `curve:true`, `curve` contains baseline `n=0` followed by every removal prefix, each with `n,before,after,removed,lost_reachable,observed_flow_removed_kzt`. Do not assume `lost_reachable` is monotonic: already removed accounts are excluded from that number. No graph is mutated.
- `POST /api/assistant`: `{question:"Неге бұл шот маңызды?",gid:"100009",mode:"local_rules"}`; `gid` and `mode` are optional. Default mode returns `{answer,citations:[{gid,label}],suggestions,mode:"local_rules"}` from local rules. Optional `mode:"local_llm"` uses the separate model service as documented below. Unknown explicit IDs and invalid questions return HTTP 400.
- `GET /api/report.pdf` downloads a summary PDF. `GET /api/report.pdf?gid=...` downloads an individual investigation card with evidence and limitations. The portable embedded font supports Kazakh and Cyrillic. Unknown/malformed IDs return HTTP 400; no arbitrary paths are accepted.
- UI may compute local node neighborhoods and filter graph by depth, cluster, role; preserve selected node search across filters.
- The interface uses local assets without a CDN. Source and assistant modes must remain visible; model-generated explanations must not be presented as rule output or verified facts.

## Analyst reviews and supplied labels

`GET /api/reviews` returns the casebook for the current **base dataset**:
`{schema_version,dataset_fingerprint,fingerprint_scope,revision,reviews,labels,
history,evaluation,notice}`. `GET /api/reviews/export.json` downloads that object.
`GET /api/reviews/template.csv` downloads exact base GIDs with blank columns
`gid,verified_role,source_reference,reviewer`; predicted roles are not prefilled.

`POST /api/reviews` accepts one of these actions:

```json
{
  "action": "set_review",
  "expected_revision": 0,
  "gid": "100009",
  "status": "in_review",
  "reviewer": "Analyst 1",
  "source_reference": "Internal record A",
  "notes": "Additional transaction dates requested.",
  "verified_role": null,
  "evidence": [{
    "kind": "transaction",
    "source_reference": "Internal record A, section 2",
    "summary": "Analyst-supplied description of the cited record.",
    "related_gids": ["100009"]
  }]
}
```

- `set_review` is the default action. Known base GID is required. Omitted
  fields retain prior values; explicit `verified_role:null` removes a label.
- Status is `unreviewed`, `in_review`, `supported` or `rejected`. Non-unreviewed
  records require a reviewer; finalized records require a source reference.
  A non-null verified role requires finalized status. `supported` must agree
  with the reviewed prediction; `rejected` with a supplied role must disagree.
- Evidence kinds are `ownership,control,transaction,other`, with at most 50
  evidence records per review and 50 known `related_gids` per record. Source
  reference and summary are required. The service assigns stable evidence IDs
  and `verification:"analyst_asserted"`; it does not fetch or verify documents.
- `{"action":"import_labels","labels":[{"gid":"100009",
  "verified_role":"consolidator","source_reference":"Review A",
  "reviewer":"Analyst 1"}]}` upserts explicit labels. Duplicate/unknown GIDs
  and incomplete records fail. HTTP accepts JSON label records; the Python
  helper `parse_labels_csv(analysis,text)` validates the CSV template format.
- `{"action":"refresh"}` recomputes the casebook view without advancing its
  revision. Optional `expected_revision` on actions rejects stale writes with
  HTTP 400. History records previous/current values; it is not tamper-proof.

Evaluation returns coverage, evaluated count, accuracy, per-class
precision/recall/F1, a confusion matrix, macro F1 and a majority-label baseline.
Undefined values are null. These measure agreement on the supplied subset;
`benchmark_split.held_out_status` and `label_independence` are `"unknown"`.
There is no training or automatic change to predictions, scores or CSVs.

## Additional observed transfers

`POST /api/expand` requires an explicit disjointness declaration:

```json
{
  "incremental_disjoint": true,
  "transactions": [{
    "src": "100027",
    "dst": "200001",
    "date": "2026-08-01T10:00:00+05:00",
    "sum_kzt": 8000,
    "source_reference": "Authorized additional export A",
    "transaction_id": "export-A-row-1"
  }]
}
```

Each record has exactly those six fields. IDs accept exact int64 numbers or
decimal strings; dates accept ISO dates/timestamps and normalize to UTC;
amounts must be positive and finite. Source reference and transaction ID are
nonempty strings. Maximums are 50,000 submitted records per batch and 200,000
unique supplementary records in the accumulated ledger.

The key `(source_reference,transaction_id)` deduplicates identical records
within a batch and after reloading the persisted overlay. Reusing that key
with conflicting contents rejects the request. Different source references
form different ID namespaces. The base extract has no transaction IDs:
`incremental_disjoint:true` is a user assertion, **not verified disjointness**.
Same-pair/same-day overlap is counted and warned about; uncertainty is never
silently resolved by deleting or inventing a base transaction.

Response:

```text
{
  available: true,
  graph: {nodes,edges,replay,timeline,meta,expansion},
  provenance: {
    base_fingerprint,base_summary,incremental_disjoint_assertion,
    disjointness_verified:false,accepted_transactions,duplicate_transactions,
    total_supplementary_transactions,same_pair_day_records,
    supplementary_sources:[{source_reference,n_transactions}],warnings
  },
  base_comparison: {before,after,base,new_nodes,new_edges,added_kzt,added_transactions},
  note
}
```

Each comparison summary has `n_nodes,n_edges,n_transactions,total_kzt`.
`graph.expansion` contains provenance plus the normalized `records` ledger.
Existing node roles have `role_scope:"base_snapshot"` and retained
`base_metrics`; updated degrees, counts and amounts describe the overlay.
New nodes have `role:"unclassified",role_assigned:false`, null role/priority
scores and no assigned community. `observed_depth` is directed shortest
distance from a known seed, or null when unreachable; new-node `depth` uses
that distance. Existing extraction depth is retained. All nodes have
`analysis_status:"not_reanalyzed"`. Overlay `replay.days` lists observed days.

`GET /api/expansion` returns the saved overlay, or `{available:false}`.
The base `/api/analysis`, its PDF/CSV exports and its role predictions are
unchanged. Only explicitly supplied operations enter the overlay.

## Deeper directed paths and resumable exploration

`POST /api/explore` accepts:

```json
{
  "scope": "base",
  "kind": "paths",
  "start_gid": "100009",
  "end_gid": "100027",
  "max_hops": 8,
  "max_results": 20,
  "budget": 20000
}
```

- `scope` is `base` (default) or `expanded`; expanded scope requires a saved
  overlay. `kind` is `paths`, `cycles` or `shortest`. Start GID must exist;
  optional end GID must also exist.
- Paths/cycles use deterministic depth-first exploration, `max_hops` 1–12
  (default 4), `max_results` 1–100 (default 20), and an edge-expansion `budget`
  1–100,000 (default 20,000). Paths are simple and nonempty. Without an end,
  eligible prefixes are results. Cycles close at the requested start; an end
  must be absent or equal to start. Self-transfer cycles may have one edge.
- `kind:"shortest"` requires an end GID and computes an exact unweighted
  directed shortest path with bidirectional BFS. The enumeration hop/work
  limits do not apply; a shortest path may exceed 12 hops. There is no cursor.

Response has `routes,shortest_path,scope,limits,complete_within_scope,
next_cursor,cursor,note`. Each route has
`id,gids,edges:[{src,dst,sum_kzt,n_tx}],length,observed_volume_kzt,evidence,
temporal_order_verified:false`. Volume sums the observed period amounts of
its edges; it is not traced money. A cycle's GID list repeats its start at end.

For enumeration, `limits` reports per-call/cumulative work and results,
`budget_exhausted`, `result_limit_reached` and `cursor_resumable`. Continue
with `cursor:next_cursor` and the same start/end/kind/hop scope. Page size and
work budget may change. An authenticated cursor stores only traversal state,
is bound to the current graph, and expires after server restart. Cancelling
means stopping further requests; there is no retained background search job.
`complete_within_scope:true` means traversal exhausted that finite observed
scope, never all possible real-world money routes. Empty complete shortest
results mean no directed path in that graph.

## Assumed post-removal recovery

`POST /api/recovery` takes `{top_n:5,replacement_fraction:0.5}` or explicit
`gids` instead of `top_n`. Defaults are top 5 and fraction 0.5; fraction must
be finite in [0,1]. It runs against the base graph, independently of overlays.

Response: `mode:"assumption_scenario",baseline,post_removal,scenario,removed,
replacement_fraction,restored_edge_fraction,hypothetical_nodes,assumed_edges,
observed_survivors_reconnected,reference_turnover_kzt,assumptions,note`.
Hypothetical node IDs such as `hypothetical-1` are scenario identifiers, not
GIDs. Every hypothetical node and assumed edge carries `synthetic:true`.
These do not enter the observed graph or supplementary ledger.

## Optional local language model

`GET /api/assistant/status` returns `{available,model,mode:"local_llm",offline,
note}` and `busy` when available. `POST /api/assistant` with
`{question,gid?,mode:"local_llm"}` requests actual generation from the loopback
model service. Successful generation returns
`{answer,citations,suggestions,mode:"local_llm",model,note}`.

Recognized unsupported identity/guilt/actual-balance/real-accuracy questions
are handled by a deterministic guard, returning `mode:"local_rules_guard",
guarded:true,model:null`; do not label these replies as model-generated.
Generated numeric tokens absent from the evidence also trigger an explicitly
labeled rules fallback; its `note` explains that the model output was rejected.
Unavailable/busy models or rejected generated responses return HTTP 503;
invalid questions, IDs or mode return HTTP 400. The rules mode remains
independently available; no silent model-success claim is made on failure.

The evidence pack contains network totals and up to four selected/explicit
accounts (or four highest-priority accounts), with numeric observations,
stored evidence and next requests. Questions are limited to 2,000 characters.
Responses are bounded to 500 characters and four reference tokens. Reference
membership, JSON shape, truncation and unknown long account numbers are
checked. **This validates references, not the truth of generated prose.**

The configured `AQSHA_LLM_URL` defaults to `http://127.0.0.1:8766` and must be
HTTP loopback with an explicit port, no credentials/path/query/fragment.
Redirects and proxies are disabled. The service uses OpenAI-compatible
`/v1/models` and `/v1/chat/completions`; that protocol does not imply a call to
OpenAI or another cloud provider. A local key may be read from
`.local/model-key.txt`. Model installation/startup is separate from the core
application. This is inference, with no training or threshold calibration.

## Persistence and unchanged official outputs

The normal server stores casebooks and overlays under `data/investigations/`,
keyed by the base dataset fingerprint, with atomic replacement. The pipeline
fingerprint is SHA-256 over sorted input names and exact Parquet file bytes.
Reviews and supplementary records therefore survive restart for the same
input snapshot and remain separate when source bytes change. Legacy analyses
without that fingerprint use a documented observed-data fallback.
Exploration cursors are process-bound and do not survive restart. None of
these investigation endpoints rewrites the three official role/cluster/top
CSV exports, changes source files, or trains a model.
