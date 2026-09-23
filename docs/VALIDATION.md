# Validation record

Executed locally on 2026-09-23 using Python 3.12, pandas 3.0.1, NumPy 2.3.5,
PyArrow 21.0.0 and NetworkX 3.5. The organizer dataset was supplied after the
initial synthetic validation and has now also been processed and reconciled.

## Automated checks

`python -m unittest discover -s tests -v`: **23 tests passed**.

- Thirteen pipeline tests: output schemas and every-node coverage; all six roles
  in the synthetic fixture; depth-four censoring; incomplete seed ratios;
  finite score bounds; deterministic output and unchanged input files; cluster
  membership and internal flow; ranking consistency; invalid/orphan input
  rejection; lossless int64 IDs above the JavaScript safe integer range;
  incoming/outgoing transfer counts reconciled with transaction rows; numeric
  evidence including isolated accounts.
- Ten simulation and HTTP tests: directed reachability, isolated nodes, removing
  all nodes, exact incident-flow sums, invalid IDs, safe integer-string IDs,
  API retrieval and exports, rejected uploads preserving prior state, local
  host restrictions.

## Synthetic performance check

| Input | Nodes | Directed pairs | Transactions | Analysis wall time |
|---|---:|---:|---:|---:|
| Demo fixture | 214 | 383 | 1,520 | about 0.17 s |
| Scaled synthetic fixture | 2,248 | 3,830 | 15,200 | 2.404 s |

The scaled check repeats independent motifs with disjoint identifiers and adds
isolated nodes; it is **not the official dataset** and does not establish
accuracy or guarantee runtime on other graphs/hardware. It produced exactly
2,248 rows in `nodes_roles.csv` and 376 communities. Timing excludes package
installation and browser rendering; the scale wall time includes writing the
analysis artifacts. Both observed times are below the challenge's 5-minute
batch budget on this machine.

## Reproduction

Install `requirements.txt` in a Python 3.12 environment, run the test command
above, then run `python run.py --demo --output output` to regenerate the demo
artifacts. CSVs in `examples/demo-output/` are explicitly synthetic examples,
not case findings.

## Organizer dataset check

`python run.py --data data/challenge --output output/challenge` successfully
processes the supplied **2,248 nodes, 3,119 edges, 4,840 transactions and 81
seeds**. Measured pipeline runtime on this machine: approximately **1.4–1.6
seconds** (metadata excludes final artifact serialization).

- Output: 2,248 unique node rows, 110 communities and 20 ranked nodes.
- All source GIDs exceed JavaScript's safe integer range. They remain exact
  int64 in CSV and decimal strings in JSON; no floating-point GID conversion.
- Incoming and outgoing node transfer counts each sum to all 4,840 source
  transactions. Every node explanation includes observed numbers.
- All 444 depth-four nodes are marked as censored and are not terminal.
- Edge amounts/counts reconcile with transactions; maximum pair-sum rounding
  difference was 5.82e-11 KZT. Observed aggregate turnover is 365,890,012.01 KZT.
- The 35 weak components include 19 isolated seeds. Excluding these gives the
  16 nontrivial components mentioned in the brief.
- There are 377 accounts with outflow above observed inflow: 354 have positive
  inflow and 23 are seeds with zero observed inflow. These count definitions
  explain the apparent difference from the brief's 354.
- Seed accounts without outgoing edges: 31 = 19 isolated + 12 receiving-only.

Roles are still rule-based hypotheses without ground-truth labels. Matching
input totals validates arithmetic and coverage, not classification accuracy.
Private source data and generated case outputs remain outside Git.

## Browser smoke checks

Verified against the running local server using the in-app browser:

- Demo metadata and a rendered directed canvas; exact GID search opens the
  selected account and its two-link neighborhood.
- Ranking with terminal-role filtering; community cards; localized data-gap
  reasons and next-request text.
- A node-removal scenario returns populated before/after connectivity metrics.
- Selecting all three actual demo Parquet files in the browser and submitting
  them completes analysis and switches the source badge to uploaded data.
- Returning to synthetic demo via the upload dialog restores the demo badge.
- The CSV export dialog initiates a `nodes_roles.csv` download.
- No JavaScript errors were reported during these paths. Narrow sidebar
  controls have accessible labels even when their visible text is collapsed.
- Repeated exact-ID search and node-removal simulation on the organizer data
  with an 18-digit GID; confirmed 2,248 accounts, 81 seeds, 110 communities,
  incoming/outgoing transfer counts, source-mode badge and no page overflow.
