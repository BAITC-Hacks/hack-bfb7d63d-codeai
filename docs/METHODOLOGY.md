# AQSHA TRACE analytical methodology

This is a local, reproducible rule-based analysis of an **observed**, incomplete
transaction graph. A role is an investigation hypothesis. A score is an
uncalibrated heuristic strength or investigation priority, never a probability
of guilt, ownership, coordination, or criminal activity. The pipeline does not
invent names, organizations, devices, relationships, or customer attributes.

## Input contract and quality checks

The three Parquet files have exactly these columns:

| File | Columns |
| --- | --- |
| `nodes.parquet` | `gid` (int64), `depth` (integer 0–4), `is_seed` (boolean) |
| `edges.parquet` | `src`, `dst` (int64), `sum_kzt` (positive finite number), `n_tx` (positive integer), `depth` (official discovery hop 1–4; parser also accepts 0 for compatibility) |
| `transactions.parquet` | `src`, `dst` (int64), `date` (date/datetime/date string), `sum_kzt` (positive finite number) |

IDs must be unique in nodes; both endpoints of every edge and transaction must
exist in nodes. Integer-looking strings, fractional IDs, booleans as amounts,
missing values, invalid dates, nonfinite amounts, duplicate aggregated edges,
and missing or unexpected columns are rejected with `ValueError`. Seed status
must agree with depth zero. Dates are normalized to UTC calendar days.
The official dataset defines edge depth as the discovery hop, 1–4. The parser
also accepts zero for compatibility with other exports using source depth;
this is not the official file's convention. Edge annotations are preserved.
Node depth, rather than the edge annotation, determines the four-hop boundary
flag.

An edge represents one directed pair. Its amount must equal the sum of that
pair's transaction rows, with a tolerance of 0.01 KZT plus 1e-9 relative; `n_tx`
must equal the row count exactly. Each transaction row therefore represents one
transfer, not an already aggregated daily count. Pair sets must agree exactly.
Repeated equal transaction rows are retained: without transaction IDs they
cannot safely be called duplicates. Inputs are never overwritten.

The challenge describes outbound expansion to four hops, transfers from 5,000
KZT and July 2026. Below-threshold or other-period supplied rows produce a
warning and remain in analysis; no silent filtering takes place. Meta dates
are the earliest/latest **observed transaction dates**, not a guarantee of
complete observation over that interval. A supplied node depth inconsistent
with visible shortest seed paths is warned about and preserved. All nodes,
including isolated nonseeds and isolated seeds, are retained.

## Features and censoring

- Degrees count distinct other accounts. Self-transfers remain in flow sums
  and the graph, are flagged, but do not count as independent counterparties.
- `in_kzt` and `out_kzt` sum observed directed edge amounts. Their difference
  is not a balance, profit, retained cash, or the value of criminal proceeds.
- `in_tx` and `out_tx` sum incoming/outgoing edge `n_tx` values and report the
  number of observed transfers, including self-transfers in each direction.
  They are integers in every node's JSON record; isolates receive zero. One
  large transfer and many smaller transfers can have identical amount totals
  but different counts. These raw counts provide context alongside distinct
  counterparties and amounts; they do not change the priority formula below.
- `pass_through` is observed outflow / observed inflow, bounded at one for
  rounding tolerance. It is `null` for every seed (inbound extraction can be
  incomplete), no observed inbound, or materially greater outflow than inflow.
  Excess uses the same 0.01 KZT / 1e-9 tolerance and gets an explicit flag.
- `boundary_censored` marks every depth-four account, even if an outgoing
  edge happens to be present. `no_observed_outflow` does not mean no real outflow.
- Directed, unweighted betweenness measures intermediary positions on visible
  shortest paths. Amount is not treated as a distance. For more than 1,000
  nodes, 256 source nodes are sampled with a fixed seed (1729); metadata states
  when this approximation is used. Otherwise betweenness is exact.
- Weighted PageRank uses observed edge amounts, damping 0.85, uniform teleport
  and dangling distribution. It is implemented with NumPy, avoiding a hidden
  SciPy dependency. It represents graph prominence, not an organizer's identity.
- Community participation is `1 - sum(p_c ** 2)`, where `p_c` is the fraction
  of distinct incident neighbors in community `c`. It is zero when neighbors
  all belong to one community. `external_communities` also gives the number of
  other communities directly touched by a node.

### Temporal association

`active_days` counts UTC calendar days with any incident transaction. The
maximum number of distinct incoming senders on one calendar day is reported
as `synchronized_payers`; the name denotes day-level co-occurrence, not proven
coordination or exact simultaneous timestamps.

For `fast_forward_ratio`, inbound daily amounts remain available for that day
and the next calendar day. Outbound daily amounts are paired with these
amounts in oldest-day order, with each amount used at most once. The sum of
paired amounts divided by observed inbound gives a bounded temporal-volume
overlap proxy. The ratio is null wherever pass-through is unreliable.

**This does not identify the same money.** Same-day transaction order is
unknown, pre-existing funds can finance outflow, and aggregation hides timing.
The result describes a temporal association; it is not a causal money trail.

## Formal role rules

Rules are evaluated in the following order. `I`/`O` denote distinct incoming /
outgoing counterparties; `r` is a reliable pass-through ratio. Thresholds are
transparent starting choices for an unlabelled hackathon dataset, not trained
or validated AML decision thresholds.

| Role key | Required observed pattern |
| --- | --- |
| `coordinator` | I >= 3, O >= 3, min(I,O)/max(I,O) >= 0.5, positive directed betweenness at or above the empirical 75th percentile of positive values |
| `consolidator` | I >= 3 and I >= 2 × max(O,1) |
| `distributor` | O >= 3 and O >= 2 × max(I,1) |
| `transit` | Not a seed; I >= 1, O >= 1, max(I,O) <= 3; reliable 0.80 <= r <= 1 |
| `terminal` | Not a seed; depth < 4; I >= 2; **positive** outflow and 0 < r <= 0.15; inbound on at least 3 days; last inbound at least 2 days before the dataset's last observed date |
| `peripheral` | No preceding rule matches, including nodes with insufficient or censored evidence |

A zero-outflow account is never assigned `terminal` by this implementation.
A depth-four account is also never terminal. Even the conservative terminal
rule means only “observed sink-like pattern”: a longer window or omitted
transfers can overturn it. Peripheral is a fallback for unresolved function,
not a claim that the account is unimportant.

`role_score` gives rule strength, not model confidence or calibrated probability:

- Coordinator: `min(.95, .65 + .20*betweenness_percentile + .10*min(min(I,O)/6,1))`.
- Consolidator: `min(.95, .55 + .20*min(I/10,1) + .20*(1-O/I))`.
- Distributor: `min(.95, .55 + .20*min(O/10,1) + .20*(1-I/O))`.
- Transit: `min(.95, .55 + .25*r + .15*fast_forward_ratio)`.
- Terminal: `min(.80, .50 + .20*(1-r) + .10*min(incoming_active_days/7,1))`.
- Peripheral: .25 for unresolved connected patterns, zero for isolated nodes.

Depth-four role strength is capped at .55; seed functional role strength at
.70; observed outflow exceeding inflow caps strength at .65. These cautionary
caps do not lower investigation priority or remove a node from view.

## Investigation priority and explanations

The current formula explicitly weights counterparties and observed amounts;
transaction counts are presented for review and have no separate priority
weight. This separates the implemented scoring rule from additional context
rather than implying that transfer frequency already changes the ranking.

Priority is a weighted sum of seven interpretable features, each within [0,1]:

| Feature | Weight |
| --- | ---: |
| Directed betweenness | .25 |
| Total observed inbound plus outbound volume | .20 |
| Incoming distinct counterparties | .15 |
| Outgoing distinct counterparties | .10 |
| Weighted PageRank (zero for isolates) | .10 |
| Community participation | .10 |
| Temporal association | .10 |

The first six features use empirical percentiles **among positive values**:
`count(positive value <= account value) / count(positive values)`. Zeros stay
zero; ties receive identical values. Temporal association is half the reliable
fast-forward ratio (zero when unavailable), plus half the positive percentile
of `max(synchronized_payers - 1, 0)`. A single payer cannot by itself create
the multi-payer synchrony signal.

Every node includes normalized `priority_features` and weighted
`priority_contributions`, so users can reconstruct its score. The score uses
no manually selected account IDs. Top nodes sort by descending score and then
ascending numeric gid; the first 20 are exported (all nodes if fewer than 20).
No score is labelled a crime probability. Role evidence and ranking reasons
are at most 200 Unicode characters and quote actual observable features.

## Communities, output, and reproducibility

Louvain runs on an undirected support graph whose weight between two nodes is
the sum of both directed amounts. Each weak component is processed separately
with resolution 1 and seed 1729. Isolates receive their own singleton community.
Graph insertion order is sorted; final community IDs are ordered by their
smallest gid. Each account belongs to exactly one community. Internal amount
counts each observed directed edge once, including self-transfers. Community
membership is a flow grouping, not proof of a common organization.

CSV schemas are deliberately small and fixed:

- `nodes_roles.csv`: gid, role, role_score, cluster_id, priority_score, evidence.
- `clusters.csv`: cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids, hypothesis.
- `top_nodes.csv`: rank, gid, role, priority_score, why.

`top_gids` is a JSON array of up to five highest-priority cluster members. CSV
files use UTF-8 with BOM for spreadsheet compatibility. `analysis.json` adds
the observed graph, temporal features, component counts, explicit flags,
per-feature contributions, timeline, and concrete requests for more data.
Numeric account IDs outside JavaScript's exact-integer range (absolute value
greater than 2^53 − 1) become decimal strings everywhere in the returned JSON,
including edge endpoints and member lists. This preserves int64 identity in
the browser; CSV identifiers retain their integer decimal representation.
Output artifacts are staged before replacement and JSON rejects NaN/Infinity.
Runtime metadata excludes final disk serialization. Apart from timestamps and
runtime, identical input data and dependency versions produce identical output.

Data requests follow the observed gap: expand depth-four outflow; recover seed
inbound and prior balances; inspect prior inflow when outflow exceeds observed
inflow; extend dates and remove low-value filters for apparently isolated or
receiving-only accounts. These are requests, not fabricated observations.

## Limits and validation scope

With no labelled real dataset, precision, recall, false-positive rate, and
probability calibration cannot be established. Synthetic tests establish
schema handling, arithmetic consistency, determinism, coverage of isolated
nodes, censoring behavior, score bounds, and reproducible graph outputs only.
Louvain can be sensitive to weight distribution and the chosen resolution;
stable output under a fixed seed is not evidence of a uniquely true grouping.
Legal payment processors, marketplaces, payroll and family transfers can
produce the same motifs. Human review and appropriate additional records are
needed to interpret the hypotheses.
