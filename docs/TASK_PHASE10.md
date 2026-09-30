# TASK_PHASE10 — a second data source: the public node next to Infura

The contract is in `contour.yaml`, groups **rpc**, **ingest** and **cli** (the phase-10
paragraphs and examples, committed with this spec). This document says why, what must
not break, and how it is accepted.

## 1. Why this

- The free Infura tier gives **3 000 000 credits a day**. One block costs
  1 000 (`eth_getBlockReceipts`) + 80 per `eth_getCode`; the live run of 30.09 stopped
  on the budget after **~1 h 20 min**, about **500 blocks of the ~7 200** the chain
  makes a day.
- The public node `https://ethereum-rpc.publicnode.com` has no credits. Measured
  30.09 without a key: `eth_chainId` 0x1; `eth_getCode` at `latest` equals Infura's
  (Balancer pool 0xdacf5fa1…850c, 24 280 bytes); `eth_getBlockReceipts` serves the
  whole history (blocks 1 000 000 … 26 000 000, both sides of the Merge);
  `eth_getCode` ~0.3 s sequential (60 in 18 s), **159 in 2.4 s in 20 threads, no
  refusal**.
- Sequentially the public node cannot follow the chain: a block brings up to 206
  candidates, ~0.3 s each, against a block every 12 s. Hence bounded parallelism.
- Three facts found at recon (30.09, this session), none in the brief:
  1. the node answers the urllib default agent with **HTTP 403 "error code: 1010"**;
     with `User-Agent: ethsc/0.1` it answers 200. Without a fix the public node does
     not work at all;
  2. `eth_getCode` on a block number ~200 behind the head (and on 26077729) is refused:
     **403, -32602 "Archive requests require a personal token"**; `latest` and
     head−5 answer. Backfill on the public node is possible only with `latest`;
  3. `eth_getBlockReceipts` sometimes answers `result: null`: block 20 000 000
     **2 times of 3** (morning 30.09) and **1 of 10** (evening); 0 of 40 on four other
     blocks; a block 3 past the head — null. Today null reaches `discover_candidates`
     and dies on a `TypeError`: a traceback from the CLI.

## 2. Contract

### 2.1. INPUT data shapes the code must build

| shape | where it is defined |
|---|---|
| a JSON-RPC body with `"result": null` | `{"jsonrpc":"2.0","id":1,"result":null}` — verbatim answer of the node, 30.09 |
| the receipts body | `tests/fixtures/receipts_26077729.json` (`{"jsonrpc","id","result":[218 receipts]}`) |
| the `eth_getCode` answers | `tests/fixtures/codes_26077729.json`: address → `"0x…"`, 206 keys, 59 of them `"0x"` |
| `urllib.request.Request` | standard library; `get_header("User-agent")` is how a header set as `User-Agent` reads back |
| a thread pool | `concurrent.futures.ThreadPoolExecutor(max_workers=K)`, standard library |
| `RpcError(code, message)` | `ethsc/rpc.py:15` |
| the fakes | `tests/helpers.py`: `FakeTransport` (:69), `FakeRpc` (:91), `InterruptAfter`, `temp_store`, `block_codes`, `block_receipts`, `load_hex`; phase-10 additions in 2.3 |

### 2.2. OUTPUT data shapes

No new output record. stdout/stderr records, exit codes and the stop line are those of
the cli group. New stderr lines are single-line usage errors (exit 2) and the text of
`RpcError(None, "eth_getBlockReceipts returned null")` (exit 1).

### 2.3. Names

- `ethsc/config.py`: `PUBLICNODE_URL = "https://ethereum-rpc.publicnode.com"`;
  `PRICES` unchanged.
- `ethsc/rpc.py`: header `User-Agent: ethsc/0.1` in the default transport; message
  `"eth_getBlockReceipts returned null"`.
- `ethsc/ingest.py`: `ingest_block(..., on_alerts=None, workers=None)`;
  `follow_chain(..., on_alerts=None, workers=None, code_tag=None)`; `code_tag` values
  `None` | `"latest"`.
- `ethsc/cli.py`: `--source {infura,publicnode}` (default `infura`) and `--workers K`
  (default 1 for infura, 8 for publicnode) on `listen` and `backfill`; the public
  client `RpcClient(PUBLICNODE_URL, prices={}, max_retries=5)`; `follow_chain` gets
  `workers=`, `code_tag=`, `prices=` as keyword arguments.
- `tests/helpers.py`, phase-10 additions:
  - `FakeRpc(..., null_receipts=False)`: when True, `eth_getBlockReceipts` answers
    `None`; `calls` is appended under a lock (thread-safe);
  - `CodeServer(codes=None, hold=0.0, raises=None)`: a `get_code(address, block)`
    callable serving `codes` (None → `block_codes()`), raising `raises[address]` when
    the address is a key of that dict, holding each call `hold` seconds; records
    `calls` (list of `(address, block)`), `peak` (most calls in flight at once) and
    `threads` (set of `threading.get_ident()` of the callers), all under a lock;
  - `FakeUrlopen(status=200, body=b"...")`: a stand-in for `urllib.request.urlopen`
    that records each `Request` in `requests` and returns an object usable in `with`,
    with `getcode()` and `read()`.
- New test files: `tests/test_rpc_p10.py`, `tests/test_ingest_p10.py`,
  `tests/test_cli_p10.py` (smoke of the code cards); `tests/test_rpc_examples_p10.py`,
  `tests/test_ingest_examples_p10.py`, `tests/test_cli_examples_p10.py` (judges).

### 2.4. What must not break

All 265 existing tests stay green and **no existing test file changes**: this phase
adds files, it does not rewrite them. **One exception, decided at the operator gate
after run 1 (30.09):** `tests/test_rpc_examples.py` example 5 fed `eth_getBlockReceipts`
`ok_body(None)` — a null result — as a success, which requirement (4) makes a failure; its
first answer becomes `ok_body([])`. Run 2 gave it to rpc-judge: three attempts rewrote the
whole file (+42/−41) and the guard refused them; by the operator's decision the line was
committed by hand before run 3. Recon missed it: the grep looked for a literal null, not
`ok_body(None)`. Infura without `--source` behaves byte for byte as
before. Inherited decisions this phase keeps (reviewed at the operator gate, 30.09):

| # | decision | where recorded |
|---|---|---|
| 1 | Follow Chain is the only writer of the credit ledger; `on_spend` is not wired | contour.yaml rpc/ingest; f9cd56f |
| 2 | the budget is checked before the call | contour.yaml Follow Chain behaviour; Budget Respected |
| 3 | `set_progress` only for a complete block; a rerun resumes it | contour.yaml Follow Chain |
| 4 | the ledger day is resolved before `eth_blockNumber` and before each block | contour.yaml Follow Chain; b27fea9 |
| 5 | `on_alerts` exactly once per `ingest_block`, KeyboardInterrupt included | contour.yaml Ingest Block; b27fea9 |
| 6 | ALERT lines at the end of each block, never printed twice | contour.yaml Command Line; b27fea9 |
| 7 | KeyboardInterrupt anywhere in listen/backfill — exit 0, no traceback | contour.yaml Command Line; b27fea9 |
| 8 | `infura_url()` only on the way into listen/backfill | contour.yaml Command Line; effd07a |
| 9 | exit codes 0/1/2/3 and the `stopped:` line | contour.yaml Command Line |
| 10 | retry 1/2/4 s; `RpcError` without URL or key, `from None` | contour.yaml RPC Client; f9cd56f |
| 11 | prices live in configuration | contour.yaml RPC Client; Budget Respected |
| 12 | only `ethsc/rpc.py` imports urllib/http/socket | Guardrail No Network In Core |
| 13 | a failing `get_code` is `failed` and does not hold the block | contour.yaml Ingest Block |
| 14 | standard library only, 3.9 syntax | Requirement Stdlib Only |
| 15 | deterministic output | Guardrail Deterministic Output |
| 16 | `eth_getCode` at the block number (`hex(block)`) — kept for Infura | docs/TASK_PHASE4.md:119 |
| 17 | no budget by default (`--daily-budget` default None) | cli.py:316, :320; **the decision itself: not found in history** |
| 18 | a judge extends an existing example file by a new file | motive in docs/TASK_PHASE9.md:27, TASK_PHASE8.md:272 (51c48f3); **the rule itself: not found in project history** |

## 3. Acceptance

Baseline: **265 tests**, green, 115 s (`venv/bin/python -m pytest tests -q`). Each area
below has a locally runnable acceptance, stepped narrow → broad:

1. `ast.parse(..., feature_version=(3,9))` of every target;
2. guards over the `ast` (never grep): no module of `ethsc/` but `rpc.py` imports
   urllib/http/socket; every import of `ethsc/` is standard library or `ethsc` (plus
   matplotlib in `charts.py`); a smoke file has at most 5 `test_*` functions and does
   not set `maxDiff`; a judge file has at least N and at most N + 6 `test_*`
   functions, N = the number of phase-10 examples of its group in `contour.yaml`
   (rpc 5, ingest 10 = Ingest Block 5 + Follow Chain 5, cli 7) — derived, not guessed;
3. the **orchestrator probe**: exact values from the fixtures, one line per failing
   example, network blocked;
4. the card's own new file, `-q --tb=short`;
5. the full suite `tests -q --tb=line` with `--ignore-glob='tests/test_*_p10.py'` (the
   phase-10 files of the peers must not red a card; step 4 already ran the card's own).

The network is blocked in every pytest and probe step (`socket.getaddrinfo`,
`socket.socket.connect`, `socket.create_connection` raise).

Probe content per area (numbers from the fixtures and the Contour examples):

- **helpers** — `FakeRpc(null_receipts=True).call("eth_getBlockReceipts", ["0x18dea21"])`
  is None and is recorded; `FakeRpc()` still answers 218 receipts; `CodeServer()` serves
  `block_codes()` (206 keys), `CodeServer(raises={a: OSError("x")})` raises for `a`,
  `hold=0.01` over 8 threads gives `peak` between 2 and 8; `FakeUrlopen` records one
  Request and returns status/body. Then the full suite (unchanged: 265).
- **rpc** — `PUBLICNODE_URL`; `PRICES` unchanged; header `ethsc/0.1` and
  `application/json` on a Request recorded through `FakeUrlopen`; null, null, receipts →
  218 receipts, 3 transport calls, sleeps [1, 2], one on_spend of 1000; always null with
  `max_retries=5` → `RpcError(None, "eth_getBlockReceipts returned null")`, 6 calls,
  sleeps [1, 2, 4, 8, 16], no on_spend; with the default `max_retries` → 4 calls, sleeps
  [1, 2, 4]; null for `eth_getCode` → None, 1 call, no sleep.
- **ingest** — `workers=8` over block 26077729: stats equal to the sequential ones
  (206/0/206/147/59/0/0/True/[]), `counts()` equal; `max_calls=50, workers=8`: fetched
  50, deferred 156, the called addresses are the first 50 of `discover_candidates`;
  `workers=4, hold=0.01`: 2 ≤ peak ≤ 4; `workers=None`: peak 1 and one calling thread;
  OSError on 0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc under `workers=8`: failed 1,
  contracts 146; the BELLE KeyboardInterrupt under `workers=8`: propagates, one sink
  call with one alert for 0x1807090dd15a6f58e00fd769e32ebf20ee610385 at 0.8667, the
  address stored. `follow_chain`: `code_tag="latest"` → all 206 `eth_getCode` params end
  in `"latest"`, `None` → `"0x18dea21"`; `workers=8`, Infura prices, budget 3 000 000 →
  spent 17 560; budget 10 000 → `"budget"`, 111 calls, spent 9 960, progress 26077728;
  `null_receipts` → `RpcError`, progress 26077728, no `eth_getCode`, spent 80;
  `prices={}` → spent 0.
- **cli** — publicnode backfill with a fake rpc: exit 0, empty stdout/stderr, 206
  addresses / 130 codes, all `eth_getCode` at `"latest"`, spent today 0; default backfill:
  `"0x18dea21"`, spent 17 560; a recorder in place of `ethsc.cli.follow_chain` sees
  (workers 1, code_tag None, prices == PRICES), (8, "latest", {}), (3, "latest", {});
  with `rpc=None` a recorder in place of `ethsc.cli.RpcClient` sees
  `("https://ethereum-rpc.publicnode.com", prices={}, max_retries=5)` and `infura_url`
  is never called; without `--source` it sees the `infura_url()` value; exit 2, one
  stderr line, empty stdout and zero rpc calls for `--daily-budget` with publicnode (on
  backfill and on listen), for `--workers 0` and for `--source alchemy`; listen on
  publicnode with null receipts: exit 1, one stderr line containing
  `eth_getBlockReceipts returned null`, no `Traceback`, progress 26077728, sleep never
  called.
- **judges** — each writes one test per phase-10 example of its group into its new
  `_examples_p10.py` file, naming the Function and the example in the docstring; the
  file must pass against the code of its generation; the old example file is not a
  target and stays byte for byte.

## 4. Constraints

- Edit envelope: `rpc.py` +~20, `config.py` +2, `ingest.py` +~50 (a pool branch and
  the null check), `cli.py` +~40, `helpers.py` +~70. Past 60 lines on one existing
  module → split, do not widen the slice.
- One file, one owner per generation (`deck check`); a file a card writes is not in a
  neighbour's slice of the same generation (otherwise `stale-context`). A fix does not
  affect the current run: the modules are already imported.
- The store is a sqlite3 connection and is used only from the calling thread; a store
  call in a worker raises `ProgrammingError` — the probe numbers (spent 17 560) catch
  it, since a failed charge makes the `eth_getCode` count as failed.
- Code and its smoke test travel in one card; a smoke file holds at most five tests,
  scalars and short values, no fixture-sized diffs.
- Every card that writes tests imports the stubs from `tests/helpers.py`, never writes
  its own.

## 5. Techniques already working here

- Probes compute exact values from the fixtures and print one line per failing
  example; guards walk `ast`; the forbidden token is not written as prose in the
  instruction.
- Snapshot of every target into `/tmp/morph/<card>/` as the first command of the
  acceptance, so a failed attempt can be read after the rollback.
- A judge extends an example file by a new file (phase 9 lesson).

## 6. Intentionally not specified

Card count, boundaries, slices, order, acceptance wording beyond §3, the inner layout of
the pool code, how the charges of a parallel block are carried to the calling thread.

## 7. Out of scope

- Archive access and `trace_*`; the code of self-destructed contracts. **Accepted
  limitation (30.09):** with `code_tag "latest"` a contract that self-destructed after
  its block answers `"0x"` and is stored as an address without code, known from then on
  — a special case of this item.
- **Accepted limitation (30.09):** a Ctrl-C during a parallel block exits cleanly
  (exit 0), but may wait for up to K calls already in flight (typically 0.3 s each, at
  most the 30 s transport timeout).
- Automatic failover between sources; a failure of one source is an `RpcError`, exit
  1, also in `listen` — no new semantics for a null that outlived the retries.
- An upper bound on `--workers`; per-source rate limiting beyond the retry schedule.
- Own node, BigQuery, any other provider.
- Speeding up `report` and `recheck`.
- Any change to `store`, `cluster`, `evm`, `fingerprint`, `report`, `charts`, and to any
  existing test file.

## 8. How to run

```bash
cd /home/john/Documents/Work2026/ETHSmartChecker
set -a; source /home/john/Documents/Work2026/MorphProject/morph-lab/.env; set +a
~/Documents/python_venv/venv_mrph/bin/mrph run --processor glm
```

Executor: `glm`. The tree must be clean before start. After the run: `git checkout
master` by hand; push and merge are the operator's.

## 9. Pre-registration of predictions

| quantity | prediction |
|---|---|
| cards in the deck | 7 (helpers, rpc, ingest, cli + 3 judges) |
| generations | 4 |
| executor bill | $0.05–0.12 |
| cards with regeneration | 2–3 (ingest and cli most likely) |
| `write-write` conflicts at preflight | 0 |
| tests | 265 + 22 judge + ≤15 smoke + helpers ≈ 290–305 |

**Falsifiable claim:** after the run, a live
`python -m ethsc --db /tmp/p10.sqlite backfill --from 26077729 --to 26077729 --source publicnode`
exits 0 without `INFURA_API_KEY`, stores **206 addresses**, **147 ± 5 with code** (the
code is read at `latest`: an EIP-7702 delegation set or cleared since the block moves an
address across),
and `listen --source publicnode` holds the head: `progress` falls behind the head by no
more than 3 blocks over 10 minutes.

## 10. What to record at the end

`/cost` of the session; the provider bill (scout and executors as separate lines);
queue time per generation; regenerations; final test count; dollars per accepted card;
the two recon numbers (scout targets named vs the deck's final targets; roles moved).

## 11. Actual

Three runs, 7 of 7 cards accepted in the end; final branch
`morph/20260930-195929-64b7eafc` (stacked on the two before it).

| run | cards | written / failed / skipped | generations | minutes | executor bill |
|---|---|---|---|---|---|
| 20260930-190412-72c26543 | 7 | 3 / 1 / 3 | 4 | 28 | $0.0302 |
| 20260930-193712-5002a9fb | 4 | 2 / 2 / 0 | 3 | 17 | $0.0372 |
| 20260930-195929-64b7eafc | 2 | 2 / 0 / 0 | 1 | 9 | $0.0115 |
| **total** | | **7 accepted** | | **54** | **$0.0789** |

- Regenerations: 10 (run 1: rpc ×2, both `finish_reason=error`, $0; run 2: rpc ×1,
  rpc-judge ×2, cli-judge ×2; run 3: rpc-judge ×1, cli-judge ×2).
- Tests: 265 → **302**, all green (+15 smoke, +22 judge = one per phase-10 example).
  Old test files: one line changed (`tests/test_rpc_examples.py`, see §2.4).
- Edit envelope: `ingest.py` +153/−52 in its card (planned ~50) — accepted, over the gate.
- Every failure was a criterion fault, none an executor bug in product code:
  1. run 1, `rpc`: old `test_rpc_examples.py` example 5 fed `ok_body(None)` as a
     successful `eth_getBlockReceipts`; recon grepped for a literal null and missed it;
  2. run 2, `cli-judge`: the deselect of that test was put on two cards of four;
  3. run 2, `rpc-judge`: asked to change one line of the old file, it rewrote 42 lines on
     all three attempts; the guard refused them; the line was committed by hand
     (operator's decision);
  4. run 2: a rolled-back `cli-judge` attempt left a 1.2 MB SQLite file `x` in the root;
     removed, and the acceptance now refuses files left in the tree.
- Debt: `tests/test_cli_examples_p10.py:25` uses `datetime.utcnow()` — 2
  DeprecationWarnings in the suite.

**Recon.** Scout 104 s, $0.0026, `stop_reason` "the model answered on its own",
`spent` reads 0 / calls 0 / rounds 1 (the primer seed used the round-zero budget).
Targets named: **3 of the deck's 11** (`rpc.py`, `ingest.py`, `cli.py`; the other 8: six
new test files, `config.py`, `tests/helpers.py`). Roles moved by the orchestrator: **3**
(`config.py` and `tests/helpers.py` context → target at the gate;
`tests/test_rpc_examples.py` context → target after run 1). The three facts that made the
phase work (403 on urllib, archive refusal, null past the head) came from live probes of
the node, not from the scout.

**Falsifiable claim — confirmed** (live, 30.09, no `INFURA_API_KEY`):
- `backfill --from 26077729 --to 26077729 --source publicnode`: exit 0 in 8.2 s,
  206 addresses, 147 with code, 130 codes, 0 credits;
- `listen --source publicnode` for 10 min: 50 blocks, lag to the head 1 block at the end
  (2 at minute 8.5), 5 903 addresses, 2 010 codes, 0 credits, empty stderr.

Skill lessons (ripple by execution, grep the value, one acceptance builder, known-red
deck-wide, small edits as data, stray-file step) went into
`~/.claude/skills/morph-orchestrator/SKILL.md` the same day.
