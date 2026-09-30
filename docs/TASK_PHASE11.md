# TASK_PHASE11 — the offline commands fast on the live database, output unchanged

The contract is in `contour.yaml`, groups **fingerprint** (Fingerprint Code, the new
Score Fingerprints, Similarity Score, the Fingerprint schema), **store** (Store Codes And
Contracts, Code Database) and **cluster** (Find Similar, Match Watchlist, Recheck
Watchlist) — the phase-11 paragraphs and examples, committed with this spec. This
document says why, what must not break, and how it is accepted.

## 1. Why this

Measured 30.09 on a copy of `smoke/20260930/ethsc.sqlite` (7 509 codes, 48 413
addresses, 2 seeds), master `78f7bfc`:

| command | alone, one core | four at once (baseline capture) |
|---|---|---|
| `clusters top --n 50` (`build_clusters`) | 200 s | 282 s |
| `similar <address>` (`find_similar`) | 241 s | 305 s |
| `recheck` (`recheck_watchlist`) | 29–31 s | 38 s |
| `report --out` | — | 553 s |

Two causes, both in the data path, not in the arithmetic:

1. `addresses` has no index on `code_id`: `addresses_of()` scans 48 413 rows, and
   `build_clusters` calls it 7 509 times. With the index `build_clusters` takes
   **0.12–0.14 s**; the index builds in **0.05–0.11 s**.
2. `similarity(code_a, code_b)` disassembles both codes on every call (2–6 ms a pair):
   profiled, 15 018 recheck pairs cost 72 s under the profiler, 66 531 `disassemble`
   calls in one `report`. `selectors` and `proxy` are already stored; only
   `is_std_proxy` is not. Jaccard over the stored selector sets: **0.03 s** for all
   15 018 pairs, the identical float on every pair (0 mismatches).

The ALTER + backfill of `std_proxy` on the live copy: **9.2 s** once (864 of 7 509
codes are standard proxies); a later open reads the NULL count in **5 ms**;
`fingerprints()` with the extra column: **0.02 s**, the same as without.

What stays slow and is not this phase: `report` also disassembles every code twice in
`report.py` (the instruction count of the Spearman row, 8.7 s, and `risk_flags`, 9.3 s).
With the index alone `report` took **50.4 s**, of which `recheck` **30.6 s**: after this
phase ≈ **20 s**, not under 5 s. The operator accepted `< 25 s` at the gate (§3.6).

## 2. Contract

### 2.1. INPUT data shapes the code must build

| shape | where it is defined |
|---|---|
| a Fingerprint dict | `ethsc/fingerprint.py:22` `fingerprint()`; schema in `contour.yaml` group fingerprint, dataObject Fingerprint (phase 11: six keys) |
| Proxy Info `{kind, target}` | `ethsc/evm.py` `detect_proxy`; `contour.yaml` group evm, dataObject Proxy Info |
| the phase-10 schema (for a migration test) | `ethsc/store.py:17` `_SCHEMA` at master `78f7bfc` — seven codes columns `code_id .. code`, no index |
| an Alert | `ethsc/cluster.py` `match_watchlist` / `recheck_watchlist`; unchanged |
| fixtures | `tests/fixtures/codes_26077729.json` (206 addresses, 147 with code, 130 codes, 17 of them `is_std_proxy`), `tests/fixtures/code_*.hex` (19 files, two of them standard proxies: `code_proxy_seed_0c010533.hex`, `code_proxy_046eee2c.hex`) |
| helpers | `tests/helpers.py`: `load_hex`, `block_codes`, `temp_store`, `block_store` |

### 2.2. OUTPUT data shapes

No output record changes. Every stdout/stderr byte of `recheck`, `similar`, `clusters`,
`cluster`, `risk`, `seed` and `report` stays as it is. `fingerprint()` and
`Store.fingerprints()` gain one key, `std_proxy` (bool).

### 2.3. Names

- `ethsc/fingerprint.py`: `fingerprint(code)` → key `"std_proxy"`;
  **`score_fingerprints(fp_a, fp_b) -> float`** (new); `similarity(code_a, code_b)`
  keeps its signature and returns `score_fingerprints(fingerprint(code_a),
  fingerprint(code_b))`.
- `ethsc/store.py`: column `codes.std_proxy INTEGER` (0/1, last column, after `code`);
  index **`addresses_code_id`** on `addresses(code_id)`, created by
  `CREATE INDEX IF NOT EXISTS` in `_SCHEMA` after the `addresses` table;
  `fingerprints()` → key `"std_proxy"` as `bool`.
- `ethsc/cluster.py`: `find_similar`, `match_watchlist`, `recheck_watchlist` import and
  call `score_fingerprints`; none of the three calls `code_by_id` or `similarity`.
  `build_clusters` unchanged.

### 2.4. What must not break

- Every existing test except three, which pin the old shapes and are changed **as data
  before the run** (one commit, ≤ 4 lines each, message naming this contract):
  `tests/test_fingerprint.py:86` and `tests/test_store_read.py:74` (the five-key list
  gains `"std_proxy"`), `tests/test_store.py:215` (the column list gains `"std_proxy"`
  after `"code"`). Found by grep and confirmed by a throwaway mutation run on a scratch
  worktree: exactly these three went red, 299 passed.
- `tests/test_cluster.py:323,464` compare cluster scores with `similarity()` — they stay
  green because `similarity` keeps its contract; they are context, not targets.
- The live outputs (§3.6) byte for byte.
- `cluster` imports no `sqlite3`, `urllib`, `http`, `socket`, and touches no private
  attribute of the store.

## 3. Acceptance

Baseline: **302 tests**, green. Each card's acceptance, narrow → broad:

1. `ast.parse(..., feature_version=(3,9))` of every target;
2. guards over the `ast` (never grep): every import of `ethsc/` is standard library or
   `ethsc` (matplotlib in `charts.py`); no module of `ethsc/` but `rpc.py` imports
   urllib/http/socket; `cluster.py` imports no `sqlite3` and has no `Attribute` whose
   name starts with `_` on a name other than `self`; in `cluster.py` the bodies of
   `find_similar`, `match_watchlist`, `recheck_watchlist` contain no `Attribute`/`Name`
   `code_by_id` and no call of `similarity`; a smoke file has 1–5 `test_*` functions and
   no `maxDiff`; a judge file has N..N+6 `test_*` functions, N = the phase-11 examples of
   its scope in `contour.yaml` (derived: fingerprint 1 + 5 = 6 — Fingerprint Code
   example 5, Score Fingerprints 1–5; store 4 — Store Codes And Contracts examples 6–9;
   cluster 2 — Recheck Watchlist examples 6–7); old test names all survive;
3. the **orchestrator probe**: exact values from the fixtures, one line per failing
   example, network blocked;
4. the card's own new file, `-q --tb=short`;
5. the full suite `tests -q --tb=line`, `--ignore-glob='tests/test_*_p11.py'` for the
   peers' new files;
6. no file left in the tree by the tests (untracked files other than the targets →
   red).

Probe content per area:

- **fingerprint + store** — `fingerprint` of the two proxy fixtures: `std_proxy` True,
  of `code_weth9.hex` False; six keys exactly; `fingerprint(b"")` None;
  `score_fingerprints` on the five Score Fingerprints examples (13/15 exactly; 0.0 for
  proxy pairs; 0.0 / 1.0 for the forced-`std_proxy` dicts; 0.0 with None on either or
  both sides); all 361 ordered pairs of the 19 `code_*.hex` fixtures: `score_fingerprints
  (fingerprint(a), fingerprint(b)) == similarity(a, b)` and `similarity` equals its
  phase-10 value recorded in the probe (the three Similarity Score fractions); fresh db:
  column list with `std_proxy` last, index `addresses_code_id` on `(code_id)`; block
  store: 130 fingerprints, 17 `std_proxy` True, each equal to `fingerprint(code)`; a
  phase-10 db (seven columns, no index, plain INSERTs of the 130 codes and 147
  addresses) opened by `Store`: column and index present, `fingerprints()` equal to a
  fresh db's, no NULL; the NULL-reset db reopened: filled, equal; second `Store(path)`
  of a migrated db does not change `fingerprints()`.
- **cluster** — Find Similar examples 1–2, Match Watchlist 1–3, Recheck Watchlist 1–7
  with exact values; the stubbed store (`code_by_id` raises) and
  `ethsc.cluster.similarity` patched to raise give the same results; `match_watchlist
  (store, b"", min_score=0.0)` gives one 0.0 alert; a store of the 130 block codes with
  three seeds (`0xb4e16d01…`, a std-proxy address, a clone address) — `recheck_watchlist`
  equal to the phase-10 algorithm recomputed in the probe with `similarity` over
  `code_by_id` (pair-exact).
- **judges** — one test per phase-11 example of the scope in a NEW
  `tests/test_<group>_examples_p11.py`, docstring naming the Function and the example
  number; the old example files are neither targets nor edited.

### 3.6. The live acceptance (the orchestrator's, after the run; not a card)

On the copy `smoke/p11/ethsc.sqlite` (made from `smoke/20260930/ethsc.sqlite`, opened
only by master code so far) with the merged branch:

| command | baseline file (`smoke/p11/baseline/`, sha256) | limit |
|---|---|---|
| `recheck` | `recheck.out` 13d85d5c…d713, 192 lines | < 2 s |
| `similar 0x004f611a9682ffd7f9dd06012e0f4b835b8b2298` | `similar.out` 50477dc3…2f9b, 192 lines | < 2 s |
| `clusters top --n 50` | `clusters.out` 86997c0e…1a91 | (0.12 s measured; no limit given) |
| `report --out smoke/p11/report-base.html` | `report.out` 64a69f5d…598a, `report-base.html.json` 071791d6…67c8, `report-base.html.html` 3afb82d2…3311 | **< 25 s** (agreed at the gate, 30.09) |
| second `Store(path)` of the migrated copy | — | < 1 s |

Byte-identical: `cmp` of every stdout and of both report files against the baseline.
The first command on the copy pays the one-time migration (~9 s) and is timed
separately; the limits are for the runs after it. Timings: `/usr/bin/time`, one process
at a time. Plus: `fingerprints()` of the migrated copy equals `fingerprints()` of a
fresh phase-11 db filled by `put_code` with the same codes, on a sample of 500 codes
(every 15th by `code_id`, plus all 864 `std_proxy` ones).

The `< 25 s` for `report` is derived, not the requested `< 5 s`: with the index alone
`report` measured 50.4 s, `recheck` inside it 30.6 s, so 19.8 s remains in `report.py`'s
own per-code disassembly (8.7 s + 9.3 s), which this phase does not touch; 25 s = that
plus ~25 %.

## 4. Constraints

- Edit envelope: `fingerprint.py` +~25 (the new function, `similarity` shrinks),
  `store.py` +~30 (schema line, ALTER + fill, the key), `cluster.py` ±~40 (three
  functions rewired). Past 60 lines on one module → split, do not widen the slice.
- `fingerprint.py` and `store.py` change together: the Store contract says every element
  of `fingerprints()` equals `fingerprint(code)`; changing one without the other reddens
  the suite in between. One owner for both in one generation.
- One file, one owner per generation; a file a card writes is not in a neighbour's
  slice in the same generation (otherwise `stale-context`).
- No threads, no multiprocessing, no cache outside the call (no module-level memo of
  fingerprints): every call reads the store afresh.
- Code and its smoke test travel in one card; a smoke file holds at most five tests,
  scalars and short values; every file a test writes goes into `tempfile.mkdtemp()`.
- Every card that writes tests imports stubs from `tests/helpers.py`.

## 5. Techniques already working here

- Probes compute exact values from the fixtures; guards walk `ast`; forbidden tokens are
  not written as prose into instructions.
- Snapshot of every target into `/tmp/morph/<card>/` first in the acceptance.
- A judge extends an example file by a new `_p11` file; old names survive.
- Small edits of old tests go in as data before the run (phase 10 lesson).

## 6. Intentionally not specified

Card boundaries and order beyond §4; whether `find_similar` takes the query fingerprint
from `fingerprint(code_of(address))` or from the stored list by its `code_id`; the SQL
of the fill (one `executemany` or row by row), as long as it commits once it is done.

## 7. Out of scope

- Multiprocessing, threads, any process pool.
- Any change to the L0/L1/proxy/eip7702 rules, to the three similarity rules, to the
  alert format, to the cluster order.
- Any change to `rpc`, `ingest`, `cli`, `report`, `charts`, `evm`; the Infura and
  public-node paths (phase 10); the daily budget.
- The per-code disassembly inside `report.py` (instruction count, `risk_flags`): ≈ 18 s
  on the live copy; a phase of its own (store the instruction count and the risk flags
  like `std_proxy`).
- Concurrent writers during the one-time migration (a `listen` on the same file while
  another process opens it for the first time) — sqlite's default 5 s lock timeout
  applies; no retry logic.
- An index on anything else; `VACUUM`; changing the column order of an existing db.

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
| cards in the deck | 5 (store+fingerprint, cluster, 3 judges) |
| generations | 3 |
| executor bill | $0.03–0.08 |
| cards with regeneration | 1–2 (store most likely: the migration) |
| tests | 302 + 12 judge + ≤10 smoke ≈ 316–324 |

**Falsifiable claim:** on the live copy, after the one-time migration, `recheck` and
`similar` each finish in under 2 s and `report` in under 25 s, and all six outputs are
byte-identical to the baseline.

## 10. What to record at the end

The provider bill (scout and executors as separate lines); queue time per generation;
regenerations; final test count; the live timings of §3.6; the two recon numbers.

## 11. Actual
