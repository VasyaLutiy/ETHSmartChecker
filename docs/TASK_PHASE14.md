# TASK_PHASE14 — see through standard proxies

Contract: `contour.yaml`, group store (Store Codes And Contracts: column `implementation`,
`set_implementation`, `implementation`, `implementations()`, the paragraph "Implementation
(phase 14)", examples 10, 12 changed, 13–15 new; Manage Watchlist: the paragraph "Seeding
through the implementation", example 5; dataObject Code Database), group cluster (Build
Clusters: level `impl`, examples 4–5; Find Similar: the paragraph "Through the
implementation", example 3; Match Watchlist: example 4; Recheck Watchlist: the paragraph
"Through the implementation", examples 9–11; dataObjects Cluster, Alert), group ingest
(Ingest Block: `get_storage`, `on_upgrades`, `IMPL_SLOT`, `BEACON_SLOT`, `slot_address`,
`fetch_implementation`, the paragraph "Standard proxies (phase 14)", examples 14–20; Follow
Chain: `on_upgrades`, `summary["upgrades"]`, the paragraph "Phase 14", examples 11–13),
group cli (Command Line: the paragraph "Standard proxies (phase 14)", examples 44–50), group
rpc (RPC Client example 10: `PRICES` gains `eth_getStorageAt`). No change in evm,
fingerprint, report, charts.

## 1. Why this

- Since phase 9 a standard EIP-1967 / UUPS / beacon proxy scores 0.0 against everything
  (`is_std_proxy`). That killed 380 false alerts of one seed, and made every proxy-based
  protocol invisible. On the 01.10 base (`smoke/20261001-rt1h/ethsc.sqlite`): 19 574 codes,
  1 907 of them standard proxies; 210 952 addresses, 5 092 of them standard proxies. The
  seed "TransparentUpgradeableProxy" (`0x0c0105334a50db16b51b2911c9956539753a2cf8`) has
  alerted on nothing since 30.09.
- The protocol lives in the implementation, whose address is in storage slot
  `0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc` (beacon proxies:
  `0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50`). Measured 01.10 on
  the public node, no key: the seed proxy reads
  `0x72b971717e088b59f26d4236be222adb6acd393b` (8 032 bytes, 20 selectors, not a proxy). Of
  120 live proxies sharing the seed proxy's bytecode, 42 distinct implementations; 23 point
  at `0x72b9…393b`, 19 at `0xe440cc08a71694c8229323803f59024e3144630e`. With the
  implementation resolved, the seed's 380 false alerts become 22 true ones (same
  implementation), and a seed on any implementation finds every proxy of it.
- Of 60 other live standard proxies sampled: 53 implementation slot set, 3 beacon slot set,
  4 neither (UUPS implementations carry the slot constant themselves and are flagged
  `is_std_proxy`; they read zero and keep phase 9). The 20 standard-proxy addresses of
  the fixture block 26077729: 17 implementation, 3 beacon, 0 neither.
- Cost of the upgrade re-read, measured on the live copy over 5 blocks after its
  progress (26096377–26096381): 29 known-proxy touches per block on average (38, 30,
  37, 6, 34), 0.26 s per sequential slot read on the public node. Under 50, so the re-read
  is default-on and there is no `--watch-upgrades` flag.
- The Ajna pool of the issue (`0xad24fc773e125edb223c38a39657cb64bc7c178e`) is not an
  EIP-1967 proxy: 182 bytes, `is_std_proxy` False, both slots zero (a
  clone-with-immutable-args). It cannot be seen through by this phase; live acceptance
  step 2 uses a second live proxy of `0x72b9…393b` instead (§3.3).
- Process: phase 13 ran 2 cards on Claude Code agents, 0 red acceptance runs, 30.2 min
  run wall, $5.23 executor-equivalent for 164 product lines. Same path here.

## 2. Contract

### 2.1. INPUT data shapes the code must build

- Slot words: the `result` of `eth_getStorageAt`, a str `"0x"` + 64 hex digits; an address
  is the last 40 digits when the first 24 are zero. Fixture
  `tests/fixtures/storage_26077729.json`: `{address: {slot: word}}` for the 20 standard-proxy
  addresses of block 26077729 plus `0x0c01…2cf8` and `0x069c4c579671f8c120b1327a73217d01ea2ec5ea`,
  both slots each, as read on the public node 2026-10-01.
- The implementation's code: `tests/fixtures/code_impl_72b97171.hex` (the `eth_getCode`
  text of `0x72b9…393b`), read with `load_hex`.
- The store row: `put_address(address, code_id, block, origin=None)` (`ethsc/store.py:132`),
  schema `_SCHEMA` (`ethsc/store.py:21`), the migration pattern in `Store.__init__`
  (`PRAGMA table_info` → `ALTER TABLE ... ADD COLUMN`, `ethsc/store.py:60`).
- `fingerprint(code)["std_proxy"]` (`ethsc/fingerprint.py:22`) tells a standard proxy;
  `store.fingerprints()` gives it for stored codes. `is_std_proxy` in `ethsc/evm.py:105`
  (unchanged; its slot constants are private, ingest declares its own).
- The alert dicts: built in `ingest._store_text` (`ethsc/ingest.py:107`) and
  `cluster.recheck_watchlist` (`ethsc/cluster.py:202`); printed by `cli._print_alerts`
  (`ethsc/cli.py:152`). The upgrade dict is new: `{"address", "old", "new", "block"}`.
- The rpc: `RpcClient.call(method, params)` (`ethsc/rpc.py:73`); the get_code closures of
  `follow_chain` (`ethsc/ingest.py:386`) are the pattern for `get_storage`.
- Tests: `FakeRpc(codes=None, receipts=None, head="0x18dea21", fail=None,
  null_receipts=False)`, `block_codes()`, `block_receipts()`, `load_hex(name)`,
  `temp_store()`, `block_store()`, `CodeServer` — all in `tests/helpers.py`. `FakeRpc`
  gains `storage=None` in this phase (§2.3).

### 2.2. OUTPUT data shapes

- Column `addresses.implementation TEXT`, last column in a fresh and a migrated db;
  `implementation(address) -> str | None`; `implementations() -> {address: {"implementation":
  str | None, "code_id": str | None}}` over standard-proxy addresses only.
- `ingest_block` stats: exactly `candidates, known, fetched, contracts, eoas, failed,
  deferred, complete, alerts, upgrades`; `follow_chain` summary: exactly `blocks, stopped,
  progress, alerts, day, upgrades`. An upgrade is `{"address", "old", "new", "block"}`.
- Alert dicts unchanged (`address, seed_address, label, score, origin`); origin gains the
  value `"impl"`. ALERT record unchanged. New record
  `UPGRADE\t<proxy>\t<old_impl>\t<new_impl>\t<block>`.
- Cluster level `"impl"`, key = implementation address, members = proxy addresses.
- `PRICES["eth_getStorageAt"] == 80`.

### 2.3. Names

- `ethsc.ingest.IMPL_SLOT`, `ethsc.ingest.BEACON_SLOT`, `ethsc.ingest.slot_address(word)`,
  `ethsc.ingest.fetch_implementation(store, address, block, get_storage, get_code)`;
  `ingest_block(..., get_storage=None, on_upgrades=None)`; `follow_chain(...,
  on_upgrades=None)`.
- `Store.set_implementation(address, implementation)`, `Store.implementation(address)`,
  `Store.implementations()`.
- Cluster level string `"impl"`; `_LEVEL_RANK["impl"] == 4`.
- Origin value `"impl"`; `recheck --origin` choices gain `impl`.
- `tests.helpers.FakeRpc(..., storage=None)`: `eth_getStorageAt` answers
  `storage[params[0]][params[1]]` when `storage` is a dict, the zero word
  (`"0x" + 64 * "0"`) when the address or the slot is absent, and raises `KeyError(method)`
  as before when `storage` is None; the call is recorded in `calls` either way.
- Fixtures: `tests/fixtures/code_impl_72b97171.hex`, `tests/fixtures/storage_26077729.json`.
- New test files: `tests/test_proxy_p14.py` (code card smoke), `tests/test_proxy_examples_p14.py`
  (judge).

### 2.4. What must not break

- Stats invariants `candidates = known + fetched + deferred`, `fetched = contracts + eoas +
  failed`; slot reads and implementation fetches count in none of them and are outside
  `max_calls`.
- `match_watchlist` signature and result; `discover_candidates`, `candidate_origins`; the
  alert order everywhere; `--alert-on` touches ALERT lines only.
- A proxy without a resolved implementation behaves exactly as in phase 9: 0.0 against
  everything, in no impl cluster. Recheck example 5 (phase 9) still gives `[]`.
- No rewrite of old rows on open (210 952 rows on the live copy); `set_implementation` is
  the one UPDATE of a stored row.
- `recheck` on the live 01.10 copy under 2 s after the first open (phase 11 rule).
- Exit codes 0/1/2/3; only `ethsc/rpc.py` imports urllib/http/socket; stdlib only; Python
  3.9 syntax; `cluster.py` reads the store through public methods, never `code_by_id` or
  `similarity` in the three searches (phase 11).
- The 357 existing tests stay green **after the data edit of §3.0**.

## 3. Acceptance

Built by one script outside the tree (`/tmp/p14/build.py`); every step `-q --tb=line`;
network blocked in the process; `INFURA_API_KEY` set to a dummy for the cli paths.

### 3.0. Data before the run (orchestrator, after the gate)

The ripple spike (a throwaway mutation in a scratch worktree: the column, the price, an
`eth_getStorageAt` after every standard-proxy `eth_getCode`, the `upgrades` keys, the
`impl` rank) turned **5 of 357** tests red, every one pinning the column list or the
`PRICES` dict. Fixed by hand in one commit, ≤ 5 changed lines per file:

| file | tests | edit |
|---|---|---|
| `tests/test_origin_examples_p13.py` | store examples 10, 12 | column list gains `"implementation"`; "last column" becomes `implementation` |
| `tests/test_rpc.py` | `ConfigPrices.test_prices_table` | dict gains `"eth_getStorageAt": 80` |
| `tests/test_rpc_examples_p10.py` | RPC Client example 10 | the same |
| `tests/test_rpc_p10.py` | `test_publicnode_url_and_prices_unchanged` | the same |

No test pinned the rpc call list of a backfill or of `seed add --fetch`, so the extra
calls ripple nowhere else. The same commit adds the two fixtures and their rows in
`tests/fixtures/README.md`.

### 3.1. Code card (ingest.py + store.py + cluster.py + cli.py + config.py + helpers.py + smoke tests)

1. `ast.parse` of the 5 modules, `tests/helpers.py` and `tests/test_proxy_p14.py`, 3.9 syntax.
2. Guard over `ast`: No Network In Core and Stdlib Only over `ethsc/*.py`; `ethsc/cli.py`
   and `ethsc/cluster.py` touch no `_`-attribute except on `self`; `ethsc/cluster.py` does
   not import sqlite3, and `recheck_watchlist`/`match_watchlist`/`find_similar` read neither
   `code_by_id` nor `similarity`; `ethsc/evm.py`, `ethsc/fingerprint.py`, `ethsc/report.py`,
   `ethsc/charts.py` unchanged (`git diff --quiet HEAD --`); `tests/test_proxy_p14.py` has
   1..5 `test_*`, no `Fake*` class, no `maxDiff`; `tests/helpers.py` keeps every class and
   function it has at HEAD.
3. The probe (`/tmp/p14/probe.py`, inlined): the 28 new examples (Store 13–15, Manage
   Watchlist 5, Build Clusters 4–5, Find Similar 3, Match Watchlist 4, Recheck 9–11, Ingest
   Block 14–20, Follow Chain 11–13, Command Line 44–50) plus the `FakeRpc(storage=)`
   contract, one readable line per failed check, the example named. Measured on HEAD:
   red on every example's first import or attribute.
4. `tests/test_proxy_p14.py`.
5. The full suite (`tests`), no deselect — the 5 data-edited tests included.
6. No untracked file left besides the targets.

### 3.2. Judge card (`tests/test_proxy_examples_p14.py`)

1. `ast.parse`.
2. Guard: between 28 and 45 `test_*` functions — the floor is the 28 new examples, one
   test each; no `Fake*` class; no network import; `git diff --quiet HEAD --` on `ethsc/`
   and `tests/` (no old file needs an edit after §3.0).
3. The judge file.
4. The full suite.
5. No untracked file left besides the target.

### 3.3. Live acceptance (the orchestrator's, after the run; not a card)

Network allowed here only. Branch code, fresh dbs in `/tmp/p14/live/`, public node:

1. `seed add --fetch 0x0c0105334a50db16b51b2911c9956539753a2cf8 --label proxy-seed` → exit 0;
   the store holds `implementation("0x0c01…2cf8") == "0x72b971717e088b59f26d4236be222adb6acd393b"`
   and that address with the code of `code_impl_72b97171.hex`, origin `impl`; stdout one
   line `ALERT 0x72b9…393b 0x0c01…2cf8 proxy-seed 1.0000 impl`.
2. On a second fresh db: `seed add --fetch 0x72b971717e088b59f26d4236be222adb6acd393b --label
   impl-seed` (exit 0, no ALERT), then `seed add --fetch 0x069c4c579671f8c120b1327a73217d01ea2ec5ea
   --label sibling` → exit 0, stdout `ALERT 0x72b9…393b 0x069c…5ea sibling 1.0000 fetched`;
   then `recheck` → exactly two lines, the first `ALERT 0x069c…5ea 0x72b9…393b impl-seed
   1.0000 fetched` (the proxy alerts at 1.0000 against the implementation seed — the
   prediction to score in §11).
3. On a copy of `smoke/20261001-rt1h/ethsc.sqlite`: first open adds the column with no
   rewrite (`implementation IS NULL` count = row count); `recheck` before and after, time
   and line count; then `listen --source publicnode` for 10 minutes; then the count of
   std-proxy addresses whose implementation is not NULL, the UPGRADE lines, and `recheck`
   again.

## 4. Constraints

- Standard library only, Python 3.9 syntax; stdout records, stderr one line.
- One code card owns the five modules plus `tests/helpers.py`: the implementation travels
  ingest → store → cluster → cli, the budget rule spans ingest and config, and the judge's
  tests need the new `FakeRpc` argument. Envelope: ingest ~110 lines, store ~60, cluster
  ~70, cli ~45, config 1, helpers ~8. Over the 60-line gate on three files — accepted at
  the gate as in phase 13 (one agent executor, iterative, no regeneration window).
- The judge does not see how the code was written; it writes from the Contour and the
  finished code.
- Every file a test writes goes into a `tempfile.mkdtemp()` directory.

## 5. Techniques already working here

- The phase-11/13 migration in `Store.__init__`: `PRAGMA table_info`, `ALTER TABLE ... ADD
  COLUMN`, commit, no UPDATE.
- The get_code closures of `follow_chain` (sequential: charge inside; workers: count under
  a lock, charge after) — the same shape for `get_storage`, plus the budget check.
- `_print_alerts` is the single ALERT sink; `_alert_on_sink` wraps it; an `on_upgrades`
  sink is one more small function next to them.
- `fetch_implementation` is one function used by `ingest_block` and by `seed add --fetch`.

## 6. Intentionally not specified

- How cluster builds the per-address effective fingerprint (a dict address → code_id, or a
  grouping of proxies by implementation code_id).
- Whether the workers path runs the slot reads in the pool (allowed, not required).
- How `seed add --fetch` on a held proxy shares code with the fresh-fetch path.

## 7. Out of scope

- Calling the beacon (its implementation stays unknown; the beacon address is stored and
  groups the proxies); EIP-1167 (already by target); clones with immutable args (the Ajna
  pools: 182-byte code, the implementation as a PUSH20, no slot); Diamond (EIP-2535);
  non-standard slots; UUPS implementations flagged `is_std_proxy` by their own slot
  constant (read zero, keep phase 9); the history of upgrades before the store saw the
  proxy; a watchlist check of the new implementation on an UPGRADE (the record is the
  signal; `recheck` does the rest); resolving the 5 092 old proxy rows in bulk (they
  resolve when touched, or by `seed add --fetch`); balances in alerts; any change in
  evm, fingerprint, report, charts; `--watch-upgrades` (measured 29 touches a block, under
  the 50 of the issue).

## 8. How to run

`morph-agent-run`: executor agent (sonnet) on card `proxy`, then a fresh judge agent on
`proxy-judge`, one commit per card with `Morph-Card` trailers, branch `phase14`. Then
§3.3 by the orchestrator.

## 9. Pre-registration of predictions

- Both cards accepted within three acceptance runs each; the executor needs at least one
  red run (the budget example 12 of Follow Chain or the call-order examples 44/49).
- Diff: product code +260..340 over 5 modules, helpers ≤ 15, smoke ≤ 120, judge 900..1400
  lines (28 examples, the phase-13 judge wrote 946 for 17).
- Run wall (executor start → judge commit) 35..60 min.
- §3.3 step 2 gives exactly two recheck lines, the first `0x069c…5ea` at 1.0000 against
  `impl-seed` (falsifiable: the slot of `0x069c…5ea` still reads `0x72b9…393b` at run time).
- §3.3 step 3: after 10 minutes of listen on the live copy (≈ 50 blocks), 200..600 of the
  5 092 std-proxy rows resolved (29 touches a block, many repeated), 0..2 UPGRADE lines;
  `recheck` after grows from its pre-run count by the proxies of the seeds'
  implementations — at least the 22 siblings of the TransparentUpgradeableProxy seed
  that get touched, if the seed itself resolves (it must be touched or re-seeded with
  `--fetch`).

## 10. What to record at the end

Cards accepted / burned, acceptance runs per card, wall time, lines, the ccledger API
equivalent of both agents, the live table of §3.3, the predictions with their score, and
the comparison with phase 13.

## 11. Actual

_Filled in after the run._
