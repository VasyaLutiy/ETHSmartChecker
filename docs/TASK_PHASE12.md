# TASK_PHASE12 — a seed for a contract that is not in the base

Contract: `contour.yaml`, group cli (Function Command Line: the phase-12 paragraph "Seed
of a contract not in the base", examples 28–35) and group store (Function Manage
Watchlist: `remove_seed`, examples 3–4). Context only: group rpc (`RpcClient.call`),
`ethsc/config.py` `PUBLICNODE_URL`. No change in ingest, cluster, fingerprint, report,
rpc, config.

## 1. Why this

- `seed add <address> --label L` answers exit 2 "unknown address or no code" for every
  address no listen or backfill ever stored. On the live base of 30.09 (48 413
  addresses, 7 509 codes) neither Balancer V2 ComposableStable pool of the Nov 2025
  exploit is present: `0xdacf5fa19b1f720111609043ac67a9818262850c` — 0 rows,
  `0x93d199263632a4ef4bb438f1feb99e57b4b5f0bd` — 0 rows (read-only query, this
  session). Both were deployed long ago and are never in a fresh receipt, so no listen
  stores them; the watchlist cannot name the one family the operator wants to watch.
- The public node serves their code at `latest` with no key and no credits (phase 10,
  measured 30.09: `0xdacf…850c`, 24 280 bytes, equal to Infura's). One `eth_getCode`
  is enough; no backfill by date.
- A seed added by mistake can today only be removed by editing the SQLite file by hand:
  there is no `seed remove`.
- Process: phase 11 took 5 cards, 3 generations, 19 min wall, $0.0506 on glm through
  Morph. This phase is the light path — 2 cards run by Claude Code agents
  (`morph-agent-run`), no `mrph run`, no OpenRouter — and §11 records the same numbers
  for the comparison.

## 2. Contract

### 2.1. INPUT data shapes the code must build

- The rpc: `rpc.call(method, params) -> result` (`ethsc/rpc.py`, `RpcClient.call`;
  contour rpc). `eth_blockNumber` answers a hex string (`"0x18dea21"`), `eth_getCode`
  a `"0x…"` hex string, `"0x"` for no code, or `None` (null, returned as is).
  `RpcError(code, message)`, `str(err) == message` (`ethsc/rpc.py:16`).
- The client built by the cli: `RpcClient(PUBLICNODE_URL, prices={}, max_retries=5)` —
  the same call `ethsc/cli.py` already makes for `--source publicnode`.
- Tests: `FakeRpc(codes={address: text}, head="0x18dea21", fail=None)` of
  `tests/helpers.py:93`; `.calls` is a list of `(method, list(params))`;
  `load_hex(name)` gives the bytes of a fixture.
- The store: `has_address`, `put_code(code) -> code_id`,
  `put_address(address, code_id or None, block)`, `add_seed`, `seeds`, `code_of`
  (`ethsc/store.py`, contour store).

### 2.2. OUTPUT data shapes

- stdout of `seed add --fetch` on success: the ALERT lines of
  `recheck_watchlist(store, seed_addresses=[address])`, exactly as `seed add` prints
  them today. `seed remove`: nothing on stdout.
- stderr lines, one each: `unknown address or no code: <address>` (existing),
  `eth_getCode returned no code: <address>` (new, exit 1), `str(RpcError)` (exit 1),
  `not a seed: <address>` (new, exit 2). `<address>` is the argument as given.
- Rows written by `--fetch`: one `addresses` row with `block = int(eth_blockNumber, 16)`,
  plus one `codes` row for a code answer. `seed remove` deletes one `seeds` row only.

### 2.3. Names

- Flag `--fetch` (`store_true`) of `seed add`; subcommand `seed remove <address>`.
- `Store.remove_seed(address) -> bool`.
- RPC methods and params exactly: `("eth_blockNumber", [])`, then
  `("eth_getCode", [<address lowercase>, "latest"])`.
- New test files: `tests/test_cli_p12.py` (code card smoke), `tests/test_cli_examples_p12.py`
  (judge).

### 2.4. What must not break

- `seed add` without `--fetch`: byte-identical behaviour, no rpc, no client built.
- `infura_url()` is still called only for listen/backfill with `--source infura`; seed
  add `--fetch` never reads a key (phase-10 decision 8).
- Exit codes 0/1/2/3 and one-line stderr (phase-10 decisions 7, 9); only `ethsc/rpc.py`
  imports urllib/http/socket (decision 12); the credit ledger is written by
  follow_chain alone (decision 1) — `--fetch` never calls `spend`.
- All 323 existing tests stay green unchanged. The ripple-by-execution spike (parser
  gains `--fetch` and `seed remove`, full suite) ran 323 passed, 0 red: no old test pins
  the old parser.
- recheck on the live base stays under 2 s (phase 11).

## 3. Acceptance

Built by one script outside the tree (`/tmp/p12/build.py`); every step
`-q --tb=line`, network blocked in the process, `INFURA_API_KEY` removed from the
environment of the probe.

### 3.1. Code card (cli.py + store.py + smoke tests)

1. `ast.parse` of `ethsc/cli.py`, `ethsc/store.py`, `tests/test_cli_p12.py`, 3.9 syntax.
2. Guard over `ast`: No Network In Core and Stdlib Only over `ethsc/*.py`; `ethsc/cli.py`
   has no `Attribute` node starting with `_` on anything but `self` or a module-level
   name of cli itself (the store only through public methods); `tests/test_cli_p12.py`
   has 1..5 `test_*` functions, no class named `Fake*`, no `maxDiff`.
3. The probe (`/tmp/p12/probe_cli.py`, inlined): Manage Watchlist 3–4 and Command Line
   28–35, one readable line per failed example. Measured on HEAD: 17 red lines, every
   one naming its example; 35 passes on HEAD (usage errors already exit 2), kept as a
   guard.
4. `tests/test_cli_p12.py`.
5. The full suite (`tests`), no deselect.
6. No untracked file left besides the targets.

### 3.2. Judge card (`tests/test_cli_examples_p12.py`)

1. `ast.parse`.
2. Guard: between 10 and 20 `test_*` functions — the floor is the 10 new examples
   (Command Line 28–35 = 8, Manage Watchlist 3–4 = 2), one test each; no `Fake*` class,
   stubs from `tests/helpers.py`; no network import; `git diff --quiet HEAD --` on
   `ethsc/` and on every tracked test file (the old judge files are not edited: nothing
   in them contradicts the new contract, the spike showed it).
3. The judge file.
4. The full suite.
5. No untracked file left besides the target.

### 3.3. The live acceptance (the orchestrator's, after the run; not a card)

On a copy of `smoke/20260930/ethsc.sqlite` in `/tmp/p12/live/`, network allowed for the
two `--fetch` commands only:

1. `seed add --fetch 0xdacf5fa19b1f720111609043ac67a9818262850c --label "Balancer V2 ComposableStable, Nov 2025"`
   → exit 0; `seed list` shows it; `cluster 0xdacf…` prints no L1 line yet.
2. The same for `0x93d199263632a4ef4bb438f1feb99e57b4b5f0bd` → exit 0; now
   `cluster 0xdacf…` and `cluster 0x93d1…` each print an L1 line whose members hold both
   pools (one skeleton — measured here, not assumed). If they do not share a skeleton,
   that is recorded as the finding, not fixed.
3. `seed add --fetch 0xdacf…` again: exit 0, no network (the address is stored).
4. `recheck` under 2 s. `seed remove 0x93d1…` exit 0, `seed list` loses it, a second
   remove exits 2.

## 4. Constraints

- Standard library only, Python 3.9 syntax; stdout records, stderr one line.
- The code card owns both `ethsc/cli.py` and `ethsc/store.py`: `remove_seed` and its only
  caller change together. Edit envelope: cli ~40–60 lines, store ~12.
- The judge does not see how the code was written; it writes from the Contour and the
  finished code.
- Every file a test writes goes into a `tempfile.mkdtemp()` directory.
- A test that stubs `ethsc.cli.RpcClient` / `ethsc.cli.infura_url` patches the names in
  `ethsc.cli`.

## 5. Techniques already working here

- `_run_seed_add` already prints `recheck_watchlist(store, seed_addresses=[address])`
  through `_print_alerts`; the fetch only stores the address before it.
- The keyless client construction and the `_UsageError` → exit 2 path already exist in
  `ethsc/cli.py` `main`.
- The hex check of `ingest._is_hex_code` (private: copy the rule, do not import it).

## 6. Intentionally not specified

- Whether the client is built in `main` or in `_run_seed_add` — only that it is built
  lazily, after `has_address` is False.
- KeyboardInterrupt during `--fetch` (a single call; the default traceback is accepted).

## 7. Out of scope

- Historical backfill by date; `eth_getLogs` by factory; any change to similarity,
  fingerprints or clusters; Infura for `--fetch` (Infura stays on listen and backfill
  only, decision 8); a `--source` flag on seed add; refetching the code of a stored
  address or of a stored EOA; `seed remove` deleting the code or address rows; changes
  to ingest, cluster, fingerprint, report, rpc, config.

## 8. How to run

`morph-agent-run`: executor agent (sonnet) on card `cli`, then a fresh judge agent on
`cli-judge`, one commit per card with `Morph-Card` trailers, branch `phase12`. Then
§3.3 by the orchestrator.

## 9. Pre-registration of predictions

- Both cards accepted on the first or second acceptance run each.
- Diff: cli.py +40..70, store.py +10..15, smoke ≤ 80, judge 200..350 lines.
- Wall time from the first agent launch to the judge's commit under 30 min.
- The two pools share a skeleton (L1), both ~24 KB: falsifiable in §3.3 step 2.

## 10. What to record at the end

Cards accepted / burned, acceptance runs per card, wall time, lines, the ccledger API
equivalent of both agents, the live table of §3.3, and the comparison with phase 11.

## 11. Actual

(filled after the run)
