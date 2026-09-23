# Validation record

Executed locally on 2026-09-23 using Python 3.12, pandas 3.0.1, NumPy 2.3.5,
PyArrow 21.0.0 and NetworkX 3.5. The organizer dataset was supplied after the
initial synthetic validation and has now also been processed and reconciled.

## Investigation lab and local model verification, 2026-09-23

**107 tests passed**, 9.376 seconds, in a separate source copy using the
isolated Python environment above. Full official-data CLI wall time was
**3.425 seconds**, including process startup and artifact writes, for
2,248 nodes / 3,119 edges / 4,840 transfers. The recorded run is
`.build-temp/clean-check-e92f9eec24/verification.json` on this workstation.
The supplied dataset still has no verified role labels, so no case accuracy
is reported. All added evaluation assertions use explicitly synthetic tests.

New coverage includes evidence/audit persistence, dataset isolation, stale
revisions, atomic label imports, confusion metrics and null missing metrics;
source-scoped supplementary deduplication/conflicts and exact large IDs;
strict dates/finite amounts, neutral new-node roles, preserved original
predictions; resumable paths/cycles, forged/stale cursors and exact 21-hop
shortest paths; recovery at 0%/100% including isolated seeds; loopback model
configuration, unavailable/malformed responses, citation checks and the
deterministic missing-identity guard and unsupported-number fallback. Eight HTTP tests exercise these routes
with isolated temporary storage, including rejection of writes from a stale dataset page.

Browser QA used a separate synthetic server/storage on port 8767 for writes.
A review was saved, two synthetic labels imported (one match, one mismatch:
50% agreement, 0.9% coverage), and one documented 1,000 KZT transfer added.
The overlay showed 215 nodes/384 edges while the base remained 214/383.
The new 19-digit GID opened a card with no assigned role and a source reference;
the expanded-scope shortest path reached it. Official-data read-only checks
covered six-hop paths with continuation and a TOP-5 25% recovery scenario.
The lab fit a 390px viewport without horizontal page overflow.

Qwen3-1.7B Q8_0 and llama.cpp b10964 were downloaded from official sources
and SHA-256 verified. Actual CPU inference returned a Kazakh explanation
with an exact existing account citation; a cold larger request took about
31 seconds. The initial small-model outputs showed weak language and
unsupported claims, so the prompt was tightened and missing identity/guilt
requests receive an explicitly labeled deterministic guard. This is not
a model-quality benchmark: small-model wording/factual errors remain possible,
and valid references do not certify the generated text. The model uses only
loopback HTTP; private artifacts and its local key are ignored by Git.

The CI matrix for Windows, Ubuntu and macOS is configured, but was not run
remotely in this task. The automatic model installer targets Windows x64.
JavaScript syntax and Git whitespace checks pass.

## Expanded feature verification, 2026-09-23

**51 tests passed** in a fresh isolated Python 3.12 virtual environment,
installed from the pinned requirements using PyPI. `scripts/verify_clean.py`
copied source, assets and tests into a separate directory without `.deps`,
cleared inherited Python import overrides, verified all five runtime libraries
loaded from that venv, and executed the tests and official-data CLI there.
The full CLI, including process startup and artifact writing, took **2.637 s**
for 2,248 nodes / 3,119 directed pairs / 4,840 transfers. Analysis metadata
was 1.408 s and excludes serialization. This verifies an isolated environment
on this Windows host, not a separate clean operating system or other hardware.

The 28 added tests cover bounded positive/negative pattern detection, correct
date ordering and no edge-day reuse, peer cohorts, exact daily conservation,
large nested GIDs, empty/long-period inputs, multilingual grounded responses,
unknown IDs, unsupported identity questions, PDF bytes/Unicode/dates/font
license/page wrapping, HTTP integration and every-prefix removal curves.
Production requirements add ReportLab 4.4.9; test requirements add pypdf 6.10.0.

Official-data patterns retained: 135 events (315 detected), 60 cycles (167
found before the cycle search cap), and 80 routes (155 found; route search did
not hit its candidate cap). These are heuristic observations, not confirmed
offences or an exhaustive list. All truncation is exported and shown in the UI.
The original CSV schemas, role decisions and scores remain unchanged.

The full TOP-20 removal experiment produced 21 points in approximately
0.385 s. It removed 20 nodes, leaving 2,228 nodes / 2,225 edges and 1,123
seed-reachable nodes; 1,105 surviving nodes lost seed reachability. This is
structural reachability, not frozen money or a prediction of group rebuilding.

Browser checks on the organizer data covered event/route filters, highlighted
paths, all 2,248 nodes, daily/cumulative replay and period reset, TOP-20 results
and curve, assistant answers and exact-ID citation navigation, expanded node
metrics/next request, a real PDF download and all five investigation steps.
For example July 16 displays 224 transfers; cumulative through July 16 shows
2,511. The mobile 390px viewport showed no horizontal page overflow in the
insights and simulation views, and long IDs wrapped inside cards.

PDF QA rendered and inspected every page of a six-page summary and five-page
node report. Kazakh/Cyrillic text and 18-digit IDs extract correctly; no clipped
text or overlapping table rows were observed. The font is bundled unchanged
with its redistribution license. JavaScript syntax and Git whitespace checks
pass. These checks establish functioning software and arithmetic, not the
real-world correctness of assigned roles.

## Initial baseline checks (before the expanded features)

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
