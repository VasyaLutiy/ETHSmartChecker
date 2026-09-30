# TASK_PHASE9 — remove the live-base false positives

Contract lives in `contour.yaml`, groups **evm**, **fingerprint**, **cluster**,
**report**, **cli**. This file is the spec; the card breakdown is not here.

## 1. Why this

A full offline recheck of the live 30.09 base (761 blocks, 7 509 codes, 48 413
addresses; `smoke/20260930/ethsc.sqlite`, `smoke/20260930/report.json`) showed the
detector is dominated by noise:

1. **380 of 572 recheck alerts are one false family.** The seed
   `TransparentUpgradeableProxy` (0x0c0105334a50db16b51b2911c9956539753a2cf8) alerts
   at score 1.0 against 380 addresses. Its five selectors are the generic OZ proxy
   admin functions; every other transparent proxy shares them, so the selector
   Jaccard is 1.0, and where a candidate has no selectors the old opcode-3gram
   fallback also returns 1.0. 1 458 codes (19 %) have no selectors at all. Two empty
   or near-empty selector surfaces must not score 1.0.
2. **`mutable_delegatecall` fires on 1 449 codes (19.3 %).** Among them every standard
   EIP-1967 / UUPS / Beacon proxy, whose implementation lives in an audited storage
   slot by design. On the live base 913 of the 1 449 reference a standard EIP-1967
   slot. The flag must separate a standard upgradeable proxy from a genuinely
   non-standard DELEGATECALL to a storage address.
3. **The largest clusters are EIP-7702 delegations** (800, 450, 176 … addresses).
   These are delegating EOAs — wallets — not deployed contracts; they distort the
   cluster ranking and the contract statistics.
4. **The phase-8 judge rewrote `tests/test_cli_examples.py` and dropped two phase 5–6
   checks:** that a cap-stop prints its alert *before* the stop line, and that a
   budget stop line reports the real spend and the unchanged progress. Both must
   return.

Measured effect of the fix, verified offline against the two bases before writing
this spec:

| quantity | before | after |
|---|---|---|
| recheck alerts (live base) | 572 | **192** (LaunchToken family only) |
| — TransparentUpgradeableProxy alerts | 380 | **0** |
| — LaunchToken family alerts | 192 | **192** (kept) |
| `mutable_delegatecall` codes (live base) | 1 449 | **585** |
| `mutable_delegatecall` codes (block 26077729) | 29 | **12** |
| cli `risk` lines (block 26077729) | 34 | **14** |

## 2. Contract

### 2.1. INPUT data shapes the code must build

- **Fingerprint** (`ethsc/fingerprint.py`, `fingerprint()`): dict `code_id, size,
  skeleton_hash, selectors (list of "0x"+8hex), proxy (Proxy Info or None)`. Defined
  in `contour.yaml` group `fingerprint`, dataObject *Fingerprint*.
- **Proxy Info** (`ethsc/evm.py`, `detect_proxy()`): `{"kind": "eip1167"|"eip7702",
  "target": "0x"+40hex}` or None. Group `evm`, dataObject *Proxy Info*.
- **Risk Flags** (`ethsc/evm.py`, `risk_flags()`): `{"selfdestruct": bool,
  "mutable_delegatecall": bool}` in that fixed key order. Group `evm`, dataObject
  *Risk Flags*.
- **Cluster** (`ethsc/cluster.py`, `build_clusters()`): `{level: "L0"|"L1"|"proxy"|
  "eip7702", key, members: sorted lowercase addresses}`. Group `cluster`, dataObject
  *Cluster* (the level enum gains `"eip7702"`).
- **Alert** (`ethsc/cluster.py`): `{address, seed_address, label, score}`. Group
  `cluster`, dataObject *Alert*. Unchanged.
- **Report Data** (`ethsc/report.py`, `collect()`): the nine-key structure of group
  `report`, dataObject *Report Data*. `levels` gains an `eip7702` entry `{clusters,
  addresses, share}` and the keys `eip7702_codes`, `eip7702_code_share`; `proxy` now
  counts EIP-1167 only.
- The store is read only through its public methods (`fingerprints`, `code_by_id`,
  `addresses_of`, `code_of`, `seeds`, `counts`, `spent`, `ledger_days`) — see group
  `store`. No card touches `ethsc/store.py`.
- Fixtures the tests load (all in `tests/fixtures/`, documented in its README):
  `code_proxy_seed_0c010533.hex` (2059 B, 5 selectors, is_std_proxy True),
  `code_proxy_046eee2c.hex` (2227 B, 0 selectors, is_std_proxy True), plus the
  existing `code_*.hex` and `codes_26077729.json` / `receipts_26077729.json`. Test
  stubs (FakeRpc, block_store, temp_store, load_hex, block_codes …) come from
  `tests/helpers.py` — every test card has it in its slice and imports from it; no
  card writes its own stubs.

### 2.2. OUTPUT data shapes

No new serialized entity. `similarity()` still returns a plain `float`. The report
JSON keeps its nine top-level keys; the only additions are inside `levels` (the
`eip7702` sub-dict and the two `eip7702_*` scalars) — one shape, in `collect()`,
rendered once by `render_html`. `build_clusters` returns the same dict shape with one
new value in the existing `level` field.

### 2.3. Names

New public evm function **`is_std_proxy(code: bytes) -> bool`** (group *Standard
Proxy*), imported by `ethsc/fingerprint.py` and used by `risk_flags`. The audited slot
constants:
- EIP-1967 / UUPS implementation:
  `0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc`
- EIP-1967 beacon:
  `0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50`

New cluster level string **`"eip7702"`**. New report keys **`eip7702_codes`**,
**`eip7702_code_share`**, and the **`eip7702`** entry of `levels`. No subcommand name,
flag, or exit code changes. No change to `similarity`'s signature.

### 2.4. What must not break (byte for byte)

- Exit codes and the stdout/stderr format of every existing subcommand (`listen`,
  `backfill`, `clusters`, `cluster`, `similar`, `seed`, `recheck`, `report`, `risk`).
- Determinism: two runs of `report`, `recheck`, `risk`, `clusters` on an unchanged db
  give byte-identical output; `collect()` twice gives equal structures.
- The **non-proxy, selector-bearing** similarity examples: WETH9/USDT 9/34,
  UniV2/WETH 9/29, BELLE/BELLE-copy 13/15, WETH9/BELLE 9/16 — all unchanged.
- The recheck / find_similar examples over the UniV2 pair seed (4 alerts) and the
  BELLE seed (4 copies at 13/15) — unchanged: their codes carry real selectors.
- The skeletons section of the report (`non_proxy_codes` 118, etc.) — EIP-7702 and
  EIP-1167 both already count as proxy there, so it does not move.
- `ethsc/store.py`, `ethsc/ingest.py`, `ethsc/rpc.py`, `ethsc/charts.py`,
  `ethsc/config.py` and all their tests stay green: no card changes them and their
  pinned values (ledger spend, BELLE ingest alert at 0.8667, proxy-shape read) do not
  depend on the changed logic.
- No new import of `urllib`, `http`, `socket`, `requests`, or any network/eth library
  in a core module; no `eth_getStorageAt`.

## 3. Acceptance

Baseline: **248 tests** collected (`venv/bin/python -m pytest tests -q --co`). Each
area below has a locally runnable acceptance. Every code card carries, besides its own
`tests/test_<group>.py`, an **orchestrator probe** that computes the exact values from
the fixtures and prints a dense diagnosis; guards on imports/forbidden calls walk the
`ast`, never grep the source. The final full-suite step of every phase-9 card runs
`tests -q --tb=line` **with `--ignore` of all ten phase-9 test files** (they migrate
together, so a half-migrated peer must not red a card); the card's own targeted test
runs unignored. Value-comparison probes lift `maxDiff` and use `--tb=short`; one-line
probes use `--tb=line`.

The concrete criteria, per area (full commands assembled in the map at deck-cutting):

- **evm — `is_std_proxy` + `risk_flags`.** Probe over the fixtures:
  `is_std_proxy(code_proxy_seed_0c010533)` True, `is_std_proxy(code_proxy_046eee2c)`
  True, a constructed `PUSH32 <beacon slot> SLOAD DELEGATECALL` True, `is_std_proxy`
  of WETH9 / the EIP-1167 clone / `b""` all False; `risk_flags(code_proxy_seed_…)`
  both False; over a store from `codes_26077729.json` exactly **12** codes /
  **13** addresses `mutable_delegatecall`, **1** / **1** `selfdestruct`, no overlap.
  Then `pytest tests/test_evm.py -q --tb=short`, then the ignored full suite.
- **fingerprint — `similarity`.** Probe: clone-270 vs clone-2ca (different EIP-1167
  targets) **0.0**; clone-270 vs itself **1.0**; seed-proxy vs 046eee2c **0.0**;
  seed-proxy vs WETH9 **0.0**; the four selector examples unchanged
  (0.2647, 0.3103, 0.8667, 0.5625); `similarity(b"", b"")` 0.0. Guard: `ast` shows no
  opcode-3gram helper is *called* by `similarity` (the fallback is gone). Then
  `pytest tests/test_fingerprint.py`, then the ignored full suite.
- **cluster — `build_clusters` + the recheck fix.** Probe over the block-26077729
  store: **2** proxy clusters over **5** addresses (eip1167 0x4181f370… ×3,
  0x8b72b9b8… ×2), **4** eip7702 clusters over **9** (0xd2e28229… ×3, and
  0x0000fb7702…, 0x490aac77…, 0x63c0c19a… ×2), L0 7/16 and L1 2/13 unchanged; the
  UniV2-seed recheck still 4 alerts; a store of two `code_proxy_seed_…` addresses
  seeded at one gives `recheck_watchlist` **[]**. Then `pytest tests/test_cluster.py`,
  then the ignored full suite.
- **report — `collect` + `render_html`.** Probe: `levels` = L0 7/16, L1 2/13,
  proxy 2/5, eip7702 4/9, shares 16/147, 13/147, 5/147, 9/147, `proxy_codes` 5,
  `proxy_code_share` 5/130, `eip7702_codes` 7, `eip7702_code_share` 7/130; `risk`
  mutable 12 codes / 13 addresses, selfdestruct 1/1; the level table of `render_html`
  has an eip7702 row; two `collect()` calls equal; empty db still nine keys, no
  exception. Then `pytest tests/test_report.py`, then the ignored full suite.
- **cli (test only) + cli-judge.** `ethsc/cli.py` is **not** changed — its output
  shifts only because `risk_flags`/`build_clusters` changed. Restore in the examples:
  `backfill … --max-calls-per-block 1` on a seeded db → exit 3, stdout the one BELLE
  ALERT at 0.8667, stderr `stopped: cap, spent 1160 credits, progress none`, alert
  before the stop line; `backfill … --daily-budget 10000` with progress 26077728 →
  exit 3, empty stdout, stderr `stopped: budget, spent 9960 credits, progress
  26077728`. Re-pin `risk` to **14** lines (first
  `0x11b74d6995904232ad5cdf78b421f7bba1e8e646 mutable_delegatecall`, last
  `0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc selfdestruct`) and the `cluster`
  example to `0xe6b738da243e8fa2a0ed5915645789add5de5152` (an L0 pair still flagged
  `mutable_delegatecall`). The judge's own file is the example tests; the code card's
  `tests/test_cli.py` keeps its smoke assertions but with the new numbers.

## 4. Constraints

- Edit envelope on each existing module is small: evm +~15 (one helper + one
  condition), fingerprint ~−12/+15 (rewrite `similarity`, drop the 3-gram fallback),
  cluster +~10 (an eip7702 branch + rank), report +~15 (an eip7702 level entry + a
  render row). Anything past 60 lines → split, do not widen the slice.
- One file, one owner per generation (`deck check`). A file a card writes is not in a
  neighbour's slice. Fixes do not affect the current run (modules already imported).
- Code and its own smoke test travel in one card via `targets`; the judge is a
  separate card owning the `_examples.py` file.
- The full-suite coupling (every acceptance runs `tests`) is handled by ignoring the
  ten phase-9 test files in the suite step and by a dependency chain that puts new
  code in place before any card that imports it runs.

## 5. Techniques already working here

- Fixtures are real artifacts: the two new proxy fixtures are the verbatim
  `eth_getCode` bytes of two addresses of the live base, not composed.
- Card idiom and acceptance shape taken from the phase-8 `.morph` runs.
- Guards walk `ast` (`Import`/`ImportFrom`/`Call`/`Attribute`), never grep, and the
  forbidden token is never written as prose into the instruction.

## 6. Intentionally not specified

Card count, boundaries, slices, order, acceptance wording, test file names.

## 7. Out of scope

- Any network read to resolve a proxy's implementation (`eth_getStorageAt`) — the
  whole fix is bytecode-only and offline.
- MinHash / LSH or any change to the similarity algorithm beyond the proxy/selector
  rule above.
- Speeding up `report` or `recheck`.
- mint / blacklist / fee heuristics.
- Any change to `store`, `ingest`, `rpc`, `charts`, `config` or their tests.
- Re-seeding or changing the watchlist contents; the seeds stay as they are.

## 8. How to run

```bash
cd /home/john/Documents/Work2026/ETHSmartChecker
set -a; source /home/john/Documents/Work2026/MorphProject/morph-lab/.env; set +a
~/Documents/python_venv/venv_mrph/bin/mrph run --processor glm
```

Executor: `glm`. The tree must be clean before start.

## 9. Pre-registration of predictions

| quantity | prediction |
|---|---|
| cards in the deck | 10 (evm, fingerprint, cluster, report, cli + 5 judges) |
| generations | 5–6 |
| executor bill | $0.06–0.12 |
| orchestrator session bill | ~$4–6 |
| cards with regeneration | 2–3 |
| `write-write` conflicts at preflight | 0 |
| tests | > 248 |

**Falsifiable claim:** after the run, a fresh full recheck over the same live base
(`smoke/20260930/ethsc.sqlite`) yields **exactly 192 recheck alerts** — the
LaunchToken family only, zero for the TransparentUpgradeableProxy seed — and the
report's `mutable_delegatecall` code count drops from 1 449 to **585**.

## 10. What to record at the end

`/cost` of the session; the provider bill (scout and executors as separate lines);
queue time per generation; regenerations; final test count; dollars per accepted card;
the two recon numbers (scout targets named vs deck's final targets; roles moved).

## 11. Actual

_Filled after the run._
