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
`meta.dataset_fingerprint` hashes each sorted input name followed by its exact
Parquet file bytes with SHA-256. The fingerprint ties saved investigation data
to that source snapshot, independently of role predictions. Re-encoding a
Parquet file can change this fingerprint even if its logical rows are unchanged.

Data requests follow the observed gap: expand depth-four outflow; recover seed
inbound and prior balances; inspect prior inflow when outflow exceeds observed
inflow; extend dates and remove low-value filters for apparently isolated or
receiving-only accounts. These are requests, not fabricated observations.

## Additional investigative patterns

The `insights` extension leaves all original role/priority formulas and the
three CSV schemas unchanged. It adds inspectable hypotheses, not training
labels or a calibrated fraud model. Every event contains participating GIDs,
an observed date when applicable, numeric evidence and threshold metrics.

| Pattern | Rule |
|---|---|
| Activity spike | At least 7 calendar days and 3 active days; the candidate day has at least 3 transfers and 100,000 KZT, at least 4 times the mean of all other days including zero days, and at least 40% of the period's volume in that direction. This is retrospective, not a live forecast. |
| Same-day payers | At least 4 distinct non-self payers to one recipient on the same UTC day. It does not establish second-level synchrony or coordination. |
| Fast forwarding | Non-seed with positive observed inflow/outflow and outflow no greater than inflow; at least 3 incoming transfers; FIFO daily volume overlap in a 0–2 day window reaches 80% of observed inflow. The original 0–1 day role/priority feature remains unchanged. |
| Possible splitting | At least 4 transfers in one day within one directed pair or from one sender to multiple recipients; maximum/minimum amount <=1.10 and population coefficient of variation <=0.10. No reporting threshold or intent to evade one is inferred. |
| Peer outlier | Compare within the same extraction depth, minimum cohort 8 including inactive nodes. Volume or unique counterparties must strictly exceed max(Q3+3×IQR,3×median,50,000 KZT or 5 counterparties). |
| Organizer candidate | Summarize existing coordinator-role evidence, counterparties, centrality and external-community links. It cannot identify an owner or establish organizational control. |

Simple directed cycles of 2–4 edges are deduplicated by rotation. They are
structural patterns: their edges need not have occurred in a chronological
round trip. Summed edge turnover is not the amount of money returned.

Repeated routes are simple paths of 2–3 edges, each observed on at least two
dates. A route needs at least two matched sequences with nondecreasing days,
0–2 days between hops and at most 4 days end-to-end. Greedy matches do not reuse
an edge-day observation inside one route. Separate routes may share evidence;
counts are descriptive and do not claim a maximum matching. Same-day order
and identity of the funds remain unknown.

Search is deterministic and bounded: 25,000 cycle candidate expansions,
50,000 route candidate expansions, 128 starting dates per route and 12 stored
occurrences. Up to 60 cycles, 80 routes and 240 events are retained, with at
most 40 strongest events per kind. `insights.limits` includes counts and
separate search/storage truncation flags. Search traverses sorted numeric
GIDs; hitting a search cap may omit later IDs. A missing retained motif is
not proof of its absence. Methodology strings and limits also travel with
the exported JSON.

## Replay, assistant, reports and removal experiments

`replay` contains exact daily directed-pair aggregates and a calendar. Empty
days are included for periods up to 3,660 days; longer extracts retain at most
the first 3,660 observed dates and set `replay_calendar_truncated`. Pair/day
records remain available in the JSON. The interface can display
one day's edges or accumulated edges through that day. Replay does not alter
the period-wide node roles or priority scores. Animated direction markers
are not individual transfers or within-day timestamps.

TOP-N simulation removes the original ranking's prefixes from an unchanged
observed graph. Each curve point recalculates weak components, largest
component, directed seed reachability and incident observed flow. Incident
edges are counted once even when both endpoints are removed. The count of
surviving nodes losing seed reachability need not increase monotonically,
because later steps may remove those nodes themselves. This experiment does
not execute blocking or estimate frozen funds. A separate recovery scenario
uses explicit assumptions, described below; it does not predict adaptation.

The default offline assistant recognizes supported question intents and
retrieves facts from the current analysis. This mode is explicitly labelled
as rule-based, preserves exact GIDs in citations and declines unsupported
facts. Optional local language-model inference is a separate mode described
below. PDF summaries and node reports use stored evidence and carry
limitations and next-data requests. PDF generation uses ReportLab and a
redistributable embedded DejaVu font.

## Explicit supplementary-data overlays

`moneygraph.expansion.expand_analysis` adds only supplied supplementary
transaction records to a separate observed graph. It requires the caller's
explicit `incremental_disjoint:true` declaration. The original extract lacks
transaction IDs, so an aggregate pair/day amount cannot establish whether a
new record is the same payment. The tool neither deduplicates uncertain base
overlap nor asserts that the declaration has been verified. It reports the
number of accepted records sharing a previously observed pair/day and carries
this limitation with the result.

Supplementary record identity is `(source_reference,transaction_id)`.
Identical records with that key are counted as duplicate submissions;
different contents under the same key reject the complete request. The
normalized ledger survives JSON persistence, making reuploads idempotent.
Different source references form separate ID namespaces, so cross-source
duplication still requires the data supplier's review. ISO timestamps become
UTC; full normalized timestamps remain in the ledger while replay aggregates
by UTC day. Amounts are positive finite values; supplied below-threshold and
later-period records can extend what the original filtered extract observed.
The batch and accumulated limits are 50,000 and 200,000 records respectively.

The overlay recomputes degrees, observed amounts, transfer counts, timelines
and shortest directed distance from known seeds over the combined observed
edges. It can reveal paths beyond four hops because those additional edges
were supplied, not because the algorithm inferred unseen transactions.
An unreachable node has null observed seed distance. Original extraction
depths are preserved for original nodes; a new node's depth is its observed
distance when reachable. New accounts are never silently made seeds.

Existing role/priority/community information is retained with
`role_scope:"base_snapshot"` and an original `base_metrics` snapshot. It has
not been recomputed from the overlay. New accounts are `unclassified`, with
`role_assigned:false`, null role/priority scores and no assigned community.
Every overlay node states `analysis_status:"not_reanalyzed"`; pass-through is
left null. The official source files and three CSV exports remain unchanged.
Comparison counters distinguish this batch's additions, current totals and
the original base totals. The overlay is separate from hypothetical recovery
edges and from analyst assertions about control or ownership.

## Deeper exploration with finite scope

`moneygraph.exploration.explore_paths` searches a selected observed base or
expanded graph. It does not alter the four-hop source extract or the fixed
batch detector settings. Directed simple paths and start-anchored cycles use
sorted numeric GIDs and deterministic depth-first traversal. Enumeration is
limited to 1–12 edges, 1–100 returned routes per request and 1–100,000 examined
edge extensions per request. Without a requested end, nonempty eligible path
prefixes are results. A cycle returns to its requested start, which may be a
seed; self-transfers can produce one-edge cycles.

When a page or work limit interrupts traversal, the response includes an
authenticated continuation containing the DFS stack and cumulative counters.
The cursor is bound to graph contents and start/end/kind/hop scope; tampering,
a changed graph or a changed scope rejects it. Page size and work budget can
change between requests. Cursors expire when the server process restarts.
No background search is retained: a user pauses by stopping requests and can
resume with the cursor while that process and graph remain available.

`complete_within_scope` becomes true only when the traversal stack is
exhausted. This establishes completeness for that finite observed graph and
search definition, not an exhaustive view of all real-world routes. Results
are traversal-order pages, not an amount-ranked list. Many pages may be
required for dense graphs; reaching a computational bound is not evidence
that a route is absent.

An explicit shortest-path request instead uses exact unweighted directed
bidirectional BFS. Its output may exceed 12 hops; enumeration work/hop caps
do not apply and the response says so. A start equal to its end has a
zero-edge shortest path. A disconnected result means no directed path in the
provided graph, not no economic connection outside the extract.

Each returned edge is an existing directed edge. Reported route volume is
the sum of its edges' observed period amounts, not a conserved amount of
money flowing from first to last account. This exploration makes no temporal
ordering claim. It differs from the short repeated daily-route detector,
whose day-matching rules are described above.

## Analyst review, evidence references and evaluation

`moneygraph.review` keeps analyst assertions separate from predictions.
Reviews have a known base GID, status (`unreviewed`, `in_review`, `supported`
or `rejected`), reviewer, source reference, notes and optional supplied role.
Finalized reviews require source references. A supported supplied label must
match the reviewed prediction; a rejected supplied label must differ. An
explicit null supplied role removes the label. The role and score produced
by the pipeline are never overwritten by this workflow.

Evidence records accept `ownership`, `control`, `transaction` or `other`,
with a source reference, analyst-written summary and known related GIDs.
References are not fetched, document contents are not checked and no owner
identity or organizational control is inferred. `verification:"analyst_asserted"`
states exactly what has been established: an analyst submitted the assertion.
It is not independent verification or a judicial finding.

The casebook is bound to the dataset fingerprint. Optional expected revisions
reject stale updates; revision history retains previous and current records.
Persistence uses atomic local replacement, but the audit record is not
tamper-proof or a cryptographically signed chain of custody. CSV label
templates contain blank labels rather than copying predictions. Imports
reject unknown/duplicate GIDs, partial labels and missing reviewer/source
references. No supplied labels means no invented evaluation result.

With explicit supplied labels, evaluation compares the current fixed role
predictions on that labelled subset:

- Confusion matrix rows are supplied roles; columns are predicted roles.
- Accuracy is matching labels divided by evaluated labels. Coverage is
  evaluated labels divided by all base nodes.
- Precision is TP / predicted class count; recall is TP / supplied class
  support; F1 is 2TP / (support + predicted count). Undefined divisions are
  null. Macro F1 averages only classes with supplied label support.
- The majority-label baseline is calculated on the same evaluated subset.
  It is descriptive, not an independent benchmark.

This is not a held-out evaluation: `held_out_status` and label independence
are unknown, training count is zero and no model is retrained. If the labels
were influenced by the predictions or chosen thresholds, agreement does not
establish independent validation. Selection bias, class coverage and analyst
disagreement remain material limitations. A high subset score cannot become
a claim about real-world detection accuracy or guilt probabilities.

## Assumed network recovery after removal

`moneygraph.recovery.recovery_scenario` is separate from observed expansion.
After explicit-GID or top-N removal, the caller sets a replacement fraction
from zero to one. Incident observed edges are sorted by descending historical
amount, then exact source/destination GID. The first
`floor(incident_edge_count * fraction)` are restored through explicitly
synthetic replacement nodes for removed accounts. It is a deterministic
sensitivity scenario, not a learned adversary or a prediction of behavior.

Synthetic replacement IDs use a `hypothetical-` prefix and never enter the
observed graph. A replacement for a removed seed is assumed to retain seed
function. At fraction one, even removed isolated accounts receive replacement
nodes; partial scenarios introduce only replacements needed by selected
edges. Fraction zero restores nothing. Selected-edge fraction may differ
from the requested fraction because of rounding, and both are returned.

Outputs compare baseline, post-removal and assumed-recovery connectivity.
Reconnected survivors are original surviving nodes newly reachable from
surviving/assumed replacement seeds. Historical edge amounts are reference
turnover only; no new transfer amount, timing, success probability or actual
restoration is predicted. The supplied fraction is an assumption, not a
parameter estimated from the transaction extract.

## Optional local language-model explanation

The default assistant remains deterministic rules. Optional `local_llm` mode
runs actual inference through a separate OpenAI-compatible server restricted
to HTTP loopback. This is a local protocol connection, not a cloud API call.
Model weights/runtime must be installed and started separately; the core
analysis works without them. There is no model training, fine-tuning or
automatic adjustment of AML thresholds.

The model receives a bounded evidence pack: network counts/period and up to
four explicit/selected accounts, or four highest-priority accounts when none
are specified. The pack contains observed amounts/counterparty counts,
existing role hypotheses, priority, stored evidence and next-data requests.
It does not contain the full transaction ledger, referenced documents or
external identity information. Prompts treat evidence values as data, not
instructions, and ask the model to use only that evidence.

The response must fit a JSON structure and bounded answer/reference lengths.
Unknown reference tokens, unknown long account numbers and truncated model
responses are rejected. Citations resolve to exact known IDs. These checks
validate reference membership and response structure; they do not verify
every statement, number, causal inference or language choice in generated
prose. An analyst must compare generated text with cited observations.
Generation can vary between identical requests; the batch pipeline's
determinism claim does not extend to language-model wording.

Recognized requests for unavailable identities, actual organizers, guilt,
balances or real-world accuracy are answered by a deterministic data-limit
guard. Such responses explicitly use `mode:"local_rules_guard"`, `guarded:true`
and no model identifier, rather than claiming model generation. Model
unavailability, concurrent inference or invalid generated output is reported
as unavailable; the interface can separately select the working rules mode.

## Limits and validation scope

Without supplied labels, real-data precision/recall and accuracy are
unavailable; probability calibration and real-world accuracy are not
established by the optional subset agreement described above. Synthetic tests establish
schema handling, arithmetic consistency, determinism, coverage of isolated
nodes, censoring behavior, score bounds, and reproducible graph outputs only.
Louvain can be sensitive to weight distribution and the chosen resolution;
stable output under a fixed seed is not evidence of a uniquely true grouping.
Legal payment processors, marketplaces, payroll and family transfers can
produce the same motifs. Human review and appropriate additional records are
needed to interpret the hypotheses.
