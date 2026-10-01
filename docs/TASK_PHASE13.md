# TASK_PHASE13 — where a candidate came from

Contract: `contour.yaml`, group ingest (Discover Candidates: `candidate_origins`, examples
3–4; Ingest Block: the phase-13 paragraph "Origin", examples 11–13), group store (Store
Codes And Contracts: column `origin`, `put_address(..., origin=None)`, `origins()`,
examples 10–12), group cluster (Recheck Watchlist: the key `origin`, example 8; dataObject
Alert), group cli (Command Line: the phase-13 paragraph "Origin of an alert", examples
36–43). No change in rpc, evm, fingerprint, report, charts, config.

## 1. Why this

- In the 12-hour public-node run of 30.09–01.10 the seed "Balancer V1 BPool" gave 30
  ALERT lines at 1.0000. One of them, `0xc351648240e9fc9213e8b6016e566f95c5fa7909`
  ("Balancer: ETH/REPv2 20/80", deployed August 2020), entered the base because a router
  swapped through it in block 26093180 (two logs emitted by the pool, `LOG_CALL
  swapExactAmountIn` and `LOG_SWAP`), not because it was created. Today an ALERT cannot
  tell "a new contract with the seed's code was just deployed" from "an old contract with
  the seed's code was just touched"; forensics needs both, and needs to know which.
- The ALERT record is the product's only output an operator greps. 30 of 30 lines of that
  seed carried no hint; the operator had to open Etherscan per address.
- Process: phase 12 ran 2 cards on Claude Code agents, each accepted on its first
  acceptance run, 15.7 min run wall, $2.71 executor-equivalent. This phase uses the same
  path and §11 records the same numbers.

## 2. Contract

### 2.1. INPUT data shapes the code must build

- Receipts: the list `eth_getBlockReceipts` returns; each element a dict with `to`
  (str or None), `contractAddress` (str or None), `logs` (list of dicts with `address`)
  — `tests/fixtures/receipts_26077729.json`, `tests/helpers.py` `block_receipts()`. The
  code must tolerate non-dict elements, None and missing keys exactly as
  `discover_candidates` does today (`ethsc/ingest.py:22`).
- The store row: `put_address(address, code_id or None, block, origin=None)`
  (`ethsc/store.py:119`), schema `_SCHEMA` (`ethsc/store.py:18`), the phase-11 migration
  pattern in `Store.__init__` (`PRAGMA table_info` → `ALTER TABLE ... ADD COLUMN`).
- The alert dicts: built in `ingest._store_text` (`ethsc/ingest.py:69`) and in
  `cluster.recheck_watchlist` (`ethsc/cluster.py:199`); printed by `cli._print_alerts`
  (`ethsc/cli.py:145`), the one sink of listen, backfill, recheck and seed add.
- Tests: `FakeRpc(codes=None, receipts=None, head="0x18dea21", fail=None)`,
  `block_codes()`, `block_receipts()`, `load_hex(name)`, `block_store()`,
  `NoCodeStore` — all in `tests/helpers.py`.

### 2.2. OUTPUT data shapes

- ALERT record, six tab-separated fields:
  `ALERT\t<address>\t<seed_address>\t<label>\t<score %.4f>\t<origin>`,
  origin ∈ {created, seen, fetched, unknown}.
- Alert dict (ingest and recheck): exactly `address, seed_address, label, score, origin`.
  `match_watchlist` keeps exactly `seed_address, label, score`.
- `candidate_origins(receipts) -> {address: "created" | "seen"}`.
- `Store.origins() -> {address: origin}`, NULL read as `"unknown"`.
- Column `addresses.origin TEXT`, last column in a fresh and a migrated db.

### 2.3. Names

- `ethsc.ingest.candidate_origins`; `Store.put_address(address, code_id, block,
  origin=None)`; `Store.origins()`.
- Origin values exactly `"created"`, `"seen"`, `"fetched"`, `"unknown"`.
- Flags: `--alert-on {created,seen,all}` (default `all`) on `listen` and `backfill`;
  `--origin {created,seen,fetched,unknown}` (default: no filter) on `recheck`.
- New test files: `tests/test_origin_p13.py` (code card smoke),
  `tests/test_origin_examples_p13.py` (judge).

### 2.4. What must not break

- `discover_candidates` keeps signature, result and order; `match_watchlist` keeps its
  three keys; the stats of `ingest_block` and their invariants; the alert order
  everywhere; `--alert-on` never changes store writes, progress, exit codes, the stop
  line or the list `follow_chain` hands to `on_alerts`.
- Old rows are not rewritten on open (no UPDATE over the live base: 48 413 rows on the
  30.09 copy).
- recheck on the live 30.09 copy stays under 2 s (phase 11). Measured on the spike:
  0.22 s, 192 lines, every line `unknown`.
- Exit codes 0/1/2/3 and one-line stderr; only `ethsc/rpc.py` imports
  urllib/http/socket; stdlib only; Python 3.9 syntax.
- The 337 existing tests stay green **after the data edit of §3.0**; nothing else of
  them changes.

## 3. Acceptance

Built by one script outside the tree (`/tmp/p13/build.py`); every step `-q --tb=line`,
network blocked in the process, `INFURA_API_KEY` removed from the probe's environment.

### 3.0. Data edit before the run (orchestrator, after the gate)

The ripple spike (a throwaway mutation in a scratch worktree: the six-field record, the
key `origin` in recheck and ingest alerts, the column, the flags) turned **16 of 337** tests red, every
one pinning the five-field ALERT line or the four-key recheck dict. They are data and
are fixed by hand in one commit, ≤ 5 changed lines per file:

| file | tests | edit |
|---|---|---|
| `tests/test_cli.py` | backfill_prints_alert, alert_survives_interrupted_pass, recheck_and_seed_add | `\tseen` on 2 lines; `split("\t")[-1]` → `[4]` |
| `tests/test_cli_examples.py` | 5 (examples 8–11, cap stop) | `\tseen` (backfilled db) or `\tunknown` (put_address db), 5 lines |
| `tests/test_cli_examples_p12.py` | 28, 29, 34 | `\tunknown` in `_copies_alert_lines` |
| `tests/test_cluster.py` | belle_copies_already_in_store | key list gains `"origin"` |
| `tests/test_cluster_examples.py` | recheck examples 1–3 | `"origin": "unknown"` in 4 dicts |
| `tests/test_cluster_examples_p11.py` | recheck example 6 | `"origin": "unknown"` in 4 dicts |

With the spike code the 6 files run 85 passed; on HEAD they are the 16 red tests of
§3.1 step 5 until the code card lands.

### 3.1. Code card (ingest.py + store.py + cluster.py + cli.py + smoke tests)

1. `ast.parse` of the 4 modules and `tests/test_origin_p13.py`, 3.9 syntax.
2. Guard over `ast`: No Network In Core and Stdlib Only over `ethsc/*.py`; `ethsc/cli.py`
   and `ethsc/cluster.py` touch no `_`-attribute except on `self`; `ethsc/cluster.py`
   does not import sqlite3, and `recheck_watchlist`/`match_watchlist`/`find_similar` read
   neither `code_by_id` nor `similarity` (phase 11); `tests/test_origin_p13.py` has 1..5
   `test_*`, no `Fake*` class, no `maxDiff`.
3. The probe (`/tmp/p13/probe.py`, inlined): the 17 new examples (Discover Candidates
   3–4, Ingest Block 11–13, Store 10–12, Recheck Watchlist 8, Command Line 36–43), one
   readable line per failed check. Measured on HEAD: 31 red lines, every one naming its
   example; Command Line 40 passes on HEAD (unknown flags already exit 2) and is kept as
   a guard. Measured on the spike: `probe OK`, 44 s.
4. `tests/test_origin_p13.py`.
5. The full suite (`tests`), no deselect — the 16 data-edited tests included.
6. No untracked file left besides the targets.

### 3.2. Judge card (`tests/test_origin_examples_p13.py`)

1. `ast.parse`.
2. Guard: between 17 and 30 `test_*` functions — the floor is the 17 new examples, one
   test each; no `Fake*` class; no network import; `git diff --quiet HEAD --` on `ethsc/`
   and `tests/` (no old file needs an edit after §3.0).
3. The judge file.
4. The full suite.
5. No untracked file left besides the target.

### 3.3. Live acceptance (the orchestrator's, after the run; not a card)

Network allowed here only. Branch code, a fresh db in `/tmp/p13/live/`:

1. `seed add --fetch 0x2257aaac34bcb27900291f7b84ee2565a6cbac57 --label "Balancer V1 BPool"`
   → exit 0, no ALERT (the base is empty).
2. `backfill --from 26093180 --to 26093180 --source publicnode` → exit 0; exactly one
   ALERT line: `0xc351648240e9fc9213e8b6016e566f95c5fa7909`, score `1.0000`, origin
   `seen`. Receipts of a mined block are immutable, so this line is reproducible.
3. The same backfill with `--alert-on created` on a second fresh db made by step 1 →
   exit 0, no ALERT line; the store holds `0xc351…` with origin `seen`.
4. `recheck` → the same one line with `seen`; `recheck --origin created` → none.

Offline, on a copy of `smoke/20260930/ethsc.sqlite`: first open adds the column with no
rewrite (`origin IS NULL` count = row count), `recheck` under 2 s, its output equal to
the phase-11 baseline `smoke/p11/recheck.out` plus the field `\tunknown` on every line.

## 4. Constraints

- Standard library only, Python 3.9 syntax; stdout records, stderr one line.
- One code card owns all four modules: the origin travels ingest → store → cluster → cli
  and the 16 data-edited tests span cluster and cli, so a split leaves the suite red
  between cards (the phase-11 rule: an invariant across files gets one owner). Envelope:
  ingest ~25 lines, store ~25, cluster ~6, cli ~30.
- The judge does not see how the code was written; it writes from the Contour and the
  finished code.
- Every file a test writes goes into a `tempfile.mkdtemp()` directory.

## 5. Techniques already working here

- The phase-11 migration in `Store.__init__`: `PRAGMA table_info`, `ALTER TABLE ... ADD
  COLUMN`, commit.
- `_print_alerts` is the single ALERT sink; `follow_chain(..., on_alerts=...)` already
  takes any callable, so a filter is a wrapper around the sink, not a change in ingest.
- argparse `choices=` + the cli's `_UsageError` parser → exit 2, one stderr line, before
  any client is built.

## 6. Intentionally not specified

- How the cli carries the filter to the sink (closure, parameter, functools.partial).
- Whether `candidate_origins` reuses `discover_candidates` internally.

## 7. Out of scope

- Origin for addresses already stored (they stay `unknown`; no backfill of origins, no
  UPDATE); origin in the report; the historical backfill by date; the report facelift;
  trace_* to tell a factory-made contract from a touched one; any change in rpc, evm,
  fingerprint, report, charts, config; a filter on `seed add`.

## 8. How to run

`morph-agent-run`: executor agent (sonnet) on card `origin`, then a fresh judge agent on
`origin-judge`, one commit per card with `Morph-Card` trailers, branch `phase13`. Then
§3.3 by the orchestrator.

## 9. Pre-registration of predictions

- Both cards accepted on the first or second acceptance run each.
- Diff: product code +80..130 over 4 modules, smoke ≤ 100, judge 350..600 lines.
- Run wall (executor start → judge commit) under 30 min.
- §3.3 step 2 gives exactly one line, origin `seen` (the issue's claim, falsifiable).
- The operator's prediction, scored in §11 on the next listen run: most "LaunchToken
  family" alerts are `created`, most "Balancer V1 BPool" alerts are `seen`.
  Orchestrator's counter-forecast, registered before the run: the LaunchToken half
  fails — the five fixture LaunchTokens differ only in immutables (TASK_PHASE1/3), the
  signature of a factory, and a contract made by a factory inside a transaction is never
  a receipt's `contractAddress`, so it reads `seen` (§2 of the Contour paragraph).

## 10. What to record at the end

Cards accepted / burned, acceptance runs per card, wall time, lines, the ccledger API
equivalent of both agents, the live table of §3.3, the prediction with its score, and
the comparison with phase 12.

## 11. Actual

One pass, 2 of 2 cards accepted, 0 red acceptance runs, 2 generations, Claude Code
agents on claude-sonnet-5 (`morph-agent-run`), no `mrph run`, no OpenRouter.

| card | acceptance runs | commit | diff | agent wall | API equivalent (ccledger) |
|---|---|---|---|---|---|
| origin (4 modules + smoke) | 1 | 7592d0f | ingest +61/−10, store +36/−7, cli +56/−11, cluster +11/−3, test_origin_p13.py +110 (3 tests) | 11.7 min | $2.65 (50 calls) |
| origin-judge | 2, both green (re-run before commit) | 33e331c | test_origin_examples_p13.py +946 (17 tests) | 18.4 min | $2.58 (35 calls) |

- Tests 337 → **357**, all green. The judge found no defect; no regeneration, no hand fix
  of code. The 16 old tests edited as data before the run (5694d53) went green with the
  code card, as the spike predicted.
- Wall: run (executor start 07:48:36 → judge commit 08:18:49) **30.2 min**; primer →
  judge commit ≈ 62 min, the operator gate included. Recon: primer + ~12 reads, scout
  skipped (operator's call), one ripple spike that named all 16 tests the data edit
  fixed; the spike also measured every value of the 17 new examples before the gate.
- Bill, API equivalent by ccledger over the session journal: **$13.27** — executors
  $5.23 (85 calls, sonnet), orchestrator ≈ $8.04 (73 calls, opus). A subscription pays
  none of it in cash.
- Against phase 12 (same path): 2 cards, 15.7 min run, $2.71 executors, $4.38
  orchestrator, 93 product lines. Here: 2 cards, 30.2 min, $5.23, $8.04, 164 product
  lines over 4 modules (+31 removed). Executor cost per product line ~$0.032 vs ~$0.029.
- Predictions (§9): both cards first-or-second run — **hit** (1 and 1 green + 1 re-run);
  product diff +80..130 — **missed** (+164, docstrings and the workers path); smoke
  ≤ 100 — **missed** (110); judge 350..600 — **missed** (946); run wall < 30 min —
  **missed by 0.2 min** (the judge ran the 4-min full suite twice); §3.3 step 2 one line
  `seen` — **hit**.

**Live acceptance (§3.3)**, branch code 7592d0f, fresh dbs in `/tmp/p13/live/`, public node:

| step | result |
|---|---|
| `seed add --fetch 0x2257aaac…cac57 --label "Balancer V1 BPool"` | exit 0, 0.96 s, no ALERT; stored as `fetched` |
| `backfill --from 26093180 --to 26093180 --source publicnode` | exit 0, 14.8 s, exactly one line: `ALERT 0xc351648240e9fc9213e8b6016e566f95c5fa7909 0x2257aaac34bcb27900291f7b84ee2565a6cbac57 Balancer V1 BPool 1.0000 seen` |
| the same with `--alert-on created` (second fresh db) | exit 0, 13.0 s, no ALERT; store: 296 addresses, 295 `seen` + 1 `fetched`, `0xc351…` `seen` — identical to the first db |
| `recheck` / `recheck --origin created` | the same one line with `seen` / empty |
| block 26093180 overall | 295 addresses stored, 0 `created` |

Offline on a copy of `smoke/20260930/ethsc.sqlite`: the first open adds `origin` as the
last column and rewrites nothing (48 413 rows, 48 413 NULL); first open + recheck
7.08 s (the phase-11 std_proxy fill of that older copy, as in phase 12), later recheck
**0.13 s**; output = `smoke/p11/recheck.out` with `\tunknown` on every one of its 192
lines (cmp-identical); `--origin unknown` the same bytes, `--origin seen` empty.

**The operator's prediction** (most LaunchToken-family alerts `created`, most Balancer V1
BPool alerts `seen`): **pending** — scored on the next listen run, as agreed at the
gate. Orchestrator's counter-forecast stands: LaunchToken half `seen` (factory deploys).
