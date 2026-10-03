# TASK_PHASE18 — calibrate the similarity alert

Contract: `contour.yaml`, group fingerprint (Code Similarity, new: `code_similarity`,
`opcode_shingles`, `ALERT_MIN`, `CODE_MIN`), group store (Manage Watchlist: the paragraph
"Strict seeds (phase 18)", examples 6–8), group cluster (Interface Hits, new, examples 1–2;
Match Watchlist: the paragraph "Phase 18", example 5; Recheck Watchlist: the paragraph
"Phase 18", example 12), group ingest (Ingest Block: the `watch` sentence and example 12;
Follow Chain: `watch` in the signature and description, example 18), group cli (Command
Line: the subcommand list, the paragraph "Calibration (phase 18)", examples 36, 37 and 39
pinned at `--min 0.8`, new examples 57–62), and the new group calibrate (Evaluate
Calibration, examples 1–4; Load Labels, examples 1–4; dataObject Calibration Labels).
No change in evm, rpc, report, charts, dashboard, config, nor in `score_fingerprints`,
`similarity` or `find_similar`. Standard library only, Python 3.9 syntax.

The operator's brief is `livetests/TZ-fuzzy-signature.md`. Three of its premises were
measured wrong before this spec, and the gate changed the task accordingly (§1).

## 1. Why this

- **What the score is.** `score_fingerprints` (`ethsc/fingerprint.py:43`) is the Jaccard
  index of the two **selector sets**. It is not a byte distance. A fork that differs only in
  immutables keeps its selectors, so it scores 1.0 already. The threshold is 0.8 everywhere:
  `match_watchlist`, `recheck_watchlist`, `recheck --min`, `similar --min`, the `seed add`
  preview, and `listen`/`backfill` through `ingest_block(watch=None)`.
- **The corpus, measured 2026-10-03.** The labels are 95 same-role positive pairs from the
  round-2 catalogue (`livetests/eth-seed-candidates-2.md`) plus 8 hard negative pairs.
  Benign codes are the 19 804 codes of `smoke/20261001-night2/ethsc.sqlite`. Under the
  current rule (selectors, ≥ 0.8):

  | threshold | recall | hard negatives over | benign codes over (per 10k) |
  |---|---|---|---|
  | 0.7 | 0.936 | 1 pair (HeavensGate→JumpFarm 0.733) | 581 (293) |
  | 0.8 | 0.862 | 0 | 196 (99) |
  | 0.9 | 0.606 | 0 | 106 (54) |
  | 1.0 | — | 0 | 77 (39) |

  Two kinds of misses and noise:
  - **Recall misses** are all Compound cTokens of other versions: selectors 0.67–0.79.
  - **About 80% of the benign noise** comes from seeds whose selectors are a common
    interface. The Nimbus and NowSwap UniswapV2-fork pairs match 76–84 UniswapV2 pairs. The
    Saddle LPToken matches 83 plain ERC-20s.

  Nimbus and NowSwap get 1.0 against those pairs while their code similarity stays below
  0.6. No selector threshold reaches the brief's "≤ 1 per 10k".
- **A second signal, measured.** The Jaccard of opcode 5-grams separates code from
  interface:
  - Anyswap/NUM, Peapods, the Unitrollers, the Popsicle vaults and the univ3 pool fixtures
    give 1.0.
  - BELLE against its copy gives 0.99. BELLE against WETH9 gives 0.16.

  Cross-version cTokens give only 0.07–0.3, so code similarity for every seed would drop
  recall to 0.57. It is therefore applied per seed, as a **strict** flag.
- **Strictness is the operator's, not a rule.** Measured on night2:
  - Auto-strict ("≥ 10 stored codes share the selectors but not the code") marks the cToken
    seeds strict. They collect 9–15 such hits, all live Compound forks of other versions,
    and recall falls to 0.63.
  - With strict = {Nimbus, NowSwap} by hand, the reference model gives the following table.
    It counts benign hits against the labelled addresses only: the generic Saddle LPToken
    is not a labelled address here.

  | threshold | recall | negatives | benign | interface-only |
  |---|---|---|---|---|
  | 0.7 | 0.9263 | 2 (HeavensGate↔JumpFarm both ways) | 23 | 13 |
  | **0.75** | **0.8947** | **0** | 21 | 12 |
  | 0.8 | 0.8526 | 0 | 18 | 11 |

  The operator chose **0.75**: every hard negative stays below it, and recall is one pair
  short of 0.90.
- **Brief corrected at the gate.** HeavensGate and QuantumWN have code similarity 0.94: one
  template, so they are a positive pair now. The other OlympusDAO pairs (0.09–0.21) stay
  hard negatives. "228 victims as positives" is not a label: ~115 of them are one-offs, and
  the catalogue mixes clones with their implementations.
- **Throughput.** `opcode_shingles` of a 24 KB code takes 6.6 ms. The strict gate runs only
  for a strict seed that already passed the selector threshold. The match path of a loose
  seed is unchanged, so the chain pace (~1.5 s/block) is not at risk.
- **Ripple spike** (worktree at HEAD; defaults 0.8→0.75 and a `seeds.strict` column):
  **4 of 448** tests red, all in `tests/test_origin_examples_p13.py` (examples 12, 36, 37,
  39). The deploy seed there matches LINK and SHIB at exactly 9/12 = 0.75. A 5-line data edit
  pins those examples at 0.8. With a crude `--min` stub on `backfill` and a `watch` pass-through,
  they went green (31 passed).

## 2. Contract

### 2.1. INPUT data shapes the code must build

- Fingerprint dict and `score_fingerprints`: `ethsc/fingerprint.py:22` and `:43`.
  `strip_metadata(code) -> (body, meta)` and `disassemble(body) -> [(pc, op, arg)]`, from
  `ethsc/evm.py`. The existing helper `_opcode_trigrams` (`ethsc/fingerprint.py:72`) shows
  the shape: 3-grams there, 5-grams here.
- Store: the migration pattern `PRAGMA table_info` → `ALTER TABLE … ADD COLUMN` → commit
  is at `ethsc/store.py:119–149`. The read-only open with its `_ro_no_*` flags is at
  `:98–111`. `_guard_write` is at `:164`, `add_seed` at `:450` (today `INSERT OR REPLACE`,
  which would drop a strict flag), `seeds()` at `:483`, `remove_seed` at `:493`, and
  `code_by_id` at `:398`.
- Cluster: `match_watchlist` is at `ethsc/cluster.py:259` and `recheck_watchlist` at
  `:302`; its pair loop is at `:372–395`. The store is read through public methods only.
- Ingest: `follow_chain` is at `ethsc/ingest.py:621`, and its `ingest_block` call at
  `:849–853`. `ingest_block(…, watch=None, …)` is at `:376`.
- CLI: `_follow` is at `ethsc/cli.py:226`, `_run_backfill` at `:275` and `_run_listen` at
  `:295`. `_run_seed_add` (`:385`) prints the preview with `recheck_watchlist(store,
  seed_addresses=[…])`. `_run_seed_list` is at `:470`, `_run_recheck` at `:476`, the parser
  at `:495–600` and the usage-error class `_UsageError` at `:120–128`.
- Tests: `temp_store()`, `block_store()`, `block_codes()`, `load_hex(name)`,
  `FakeRpc(codes=, receipts=, head=, fail=)` (`.calls`) and `legacy_db(phase)`, all in
  `tests/helpers.py`. `belle_block_db()` and `write_labels(obj)` are new in this phase
  (§2.3).
- The measured values: Interface Hits example 1 store, BELLE code_id
  `8571d00b598627ac40e1ae7bc4d0cb3fd5a77a0d663763fdfc1cd9127b63cb4d`, deploy-seed code_id
  `ee3b081294ee0f2f1804d8aa0204848d1d0f58efe81fae42998e81f1170c9ef9`. BELLE↔SHIB is 11/15
  on selectors and 0.2314 on code. All were measured on HEAD c232fb2 on 2026-10-03 by a
  reference model outside the tree.

### 2.2. OUTPUT data shapes

- `code_similarity(a, b) -> float`, `opcode_shingles(code) -> frozenset` of 5-tuples of
  ints. `ALERT_MIN = 0.75` and `CODE_MIN = 0.6` in `ethsc/fingerprint.py`.
- Table `seeds` gains `strict INTEGER` as its last column. NULL and 0 mean loose.
- `evaluate(...) -> {"rows": [{"threshold", "recall", "negatives", "benign",
  "interface_only"}], "missing": [address], "benign_total": int}`.
- CLI records:
  - `seed audit`: `<address>\t<label>\t<interface_hits>\t<strict|loose>`.
  - `calibrate`: `<threshold>\t<recall>\t<negatives>\t<benign>\t<interface_only>\t<benign_total>`,
    floats `%.4f`, plus at most one stderr line `missing: <a,b,…>`.
  - ALERT lines do not change format.
- `tests/fixtures/calibration_labels.json` (data, committed with this spec): 95 positive
  pairs, 8 negative pairs, 2 strict addresses.

### 2.3. Names

- `ethsc.fingerprint.code_similarity`, `ethsc.fingerprint.opcode_shingles`,
  `ethsc.fingerprint.ALERT_MIN`, `ethsc.fingerprint.CODE_MIN`.
- `Store.set_seed_strict(address, strict) -> bool`, `Store.strict_seeds() -> list`.
- `ethsc.cluster.interface_hits(store, code_id, min_score=ALERT_MIN, code_min=CODE_MIN)`.
- `follow_chain(…, on_upgrades=None, watch=None)`: `watch` is the last parameter.
- New module `ethsc/calibrate.py`: `evaluate(store, labels, thresholds=DEFAULT_GRID,
  code_min=CODE_MIN)`, `load_labels(path)`, `parse_grid(text)`, `DEFAULT_GRID = (0.5, 0.6,
  0.7, 0.75, 0.8, 0.9, 1.0)`. It imports from `ethsc.fingerprint`, never from
  `ethsc.cluster`.
- CLI: `listen … [--min M]`, `backfill … [--min M]`, `seed strict <addr> {on,off}`,
  `seed audit`, `calibrate --labels FILE [--grid LIST]`. `recheck --min` defaults to 0.75;
  `similar --min` stays at 0.8.
- `tests.helpers.belle_block_db()` returns the path (str) of a closed sqlite file in a fresh
  `tempfile.mkdtemp()` directory. The file is written through `Store`. It holds every entry
  of `block_codes()` at block 26077729, as `block_store()` stores them (206 addresses, 130
  codes), plus `code_belle.hex` at `0x34c6211621f2763c60eb007dc2ae91090a2d22f6` and the four
  `code_belle_copy_*.hex` at their addresses (`0x1807090dd15a6f58e00fd769e32ebf20ee610385`,
  `0x2141be5f2afa674c94167ab167a478a56cb539f5`, `0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a`,
  `0x6411bed82614b91ef655d82486e0bd3a13d2eb8c`). Those five go in with `put_address(…, 1)`,
  no origin. The file has no seed and no progress. That is 211 addresses and 135 codes.
- `tests.helpers.write_labels(obj)` returns the path of `labels.json`, `json.dump(obj)`
  written into a fresh `tempfile.mkdtemp()` directory.
- New test files:
  - code-card smoke: `tests/test_fingerprint_p18.py`, `tests/test_store_p18.py`,
    `tests/test_ingest_p18.py`, `tests/test_cluster_p18.py`, `tests/test_calibrate_p18.py`,
    `tests/test_cli_p18.py`;
  - judges: `tests/test_<same>_examples_p18.py`.

### 2.4. What must not break

- `seeds()` keeps exactly three keys. `score_fingerprints`, `similarity` and `find_similar`
  (default 0.8) do not change. The ALERT line format and its order do not change.
- A store with no strict seed is read exactly as before. That is, `code_by_id` is never
  called by `match_watchlist`/`recheck_watchlist` (Recheck Watchlist example 6, whose
  `code_by_id` stub raises, stays green).
- `Store(path)`, every existing migration, no UPDATE of old rows. A read-only open of an
  older file stays possible.
- Exit codes 0/1/2/3. Only `rpc.py` imports the network (plus `dashboard.py`'s
  `http.server`). `cli.py`, `cluster.py`, `calibrate.py` and `dashboard.py` touch no `_`
  attribute except on `self`.
- The 448 existing tests stay green after the data edit of §3.0. Until the cli card lands,
  three of them are red by design (§3.0).

## 3. Acceptance

Every acceptance is built by one script outside the tree (`/tmp/p18/build.py`, kept in
`decks/phase18-tooling/` after the run). Every step uses `-q --tb=line`. The network is
blocked in the process. `INFURA_API_KEY` is a dummy. The first command snapshots the
targets to `/tmp/morph/<card>-p18/`. Every acceptance ends with the untracked-files check.

### 3.0. Data before the run (committed with this spec, after the gate)

- `tests/fixtures/calibration_labels.json` (§2.2), plus a row in `tests/fixtures/README.md`.
- **The 5-line edit of `tests/test_origin_examples_p13.py`**: Ingest Block example 12 gets
  `watch=0.8`; Command Line examples 36, 37 and 39 pass `"--min", "0.8"` to `backfill`, and
  example 39 also passes it to `recheck`. The forcing contract is the default threshold 0.75
  (Match Watchlist and Recheck Watchlist "Phase 18"). The deploy seed of those examples
  matches two ERC-20 tokens at exactly 9/12; they keep their meaning at 0.8. Example 12 is
  green at once (`ingest_block` already takes `watch`). Examples 36, 37 and 39 are red until
  the cli card adds `--min` to `backfill`. So every card that runs the full suite before
  that card deselects these three test ids, from the builder; the cli card and the cli judge
  do not.

### 3.1. Code cards (each card, its own targets)

1. `ast.parse` of every target, `feature_version=(3, 9)`.
2. The guard walks the `ast`, not the text:
   - Stdlib Only and No Network In Core over `ethsc/*.py`.
   - `cli.py`, `cluster.py`, `calibrate.py` and `dashboard.py` touch no `_` attribute except
     on `self`. `cluster.py` and `calibrate.py` do not import sqlite3. `calibrate.py` does
     not import `ethsc.cluster`.
   - Every file changed or added against HEAD is one of the card's targets.
   - The smoke file has 1..5 `test_*` functions, no `Fake*` class and no `maxDiff`.
   - `tests/helpers.py` keeps every name it has at HEAD.
3. The probe (inline), one readable line per failed check, each naming its example:
   - fingerprint: Code Similarity 1–6, plus `similarity`/`score_fingerprints` unchanged on
     the BELLE pair;
   - store: Manage Watchlist 6–8, plus a reopen that keeps the flag;
   - ingest: Follow Chain 18 at `watch=0.8` and `watch=0.75`. A spy shows that `watch`
     reaches `ingest_block`, and that a call without `watch` passes None. `watch` is the last
     parameter;
   - helpers-p18: `belle_block_db()` and `write_labels()` as in §2.3;
   - cluster: Interface Hits 1–2, Match Watchlist 5, Recheck Watchlist 12. The defaults
     (0.75, and `find_similar` 0.8) are read by `inspect`. Then:
     - no strict seed → `code_by_id` never called;
     - a strict seed whose `code_by_id` is None → no alert;
     - `strict_seeds()` read once per call;
     - `interface_hits` calls `code_by_id` only for code_id itself and for the codes that
       reach `min_score`;
   - calibrate: Evaluate Calibration 1–4, Load Labels 1–4, and no row written;
   - cli: Command Line 57–62, plus `similar` still at 0.8 (BELLE: the 4 copies only, SHIB
     absent), plus `seed add` leaves the seed loose.
4. The card's own smoke file.
5. The test files of the touched module (`tests/test_<module>*.py`; for cli also
   `tests/test_origin_examples_p13.py`).
6. The full suite `tests`, with the deselects of §3.0 for every card but cli.
7. No untracked file left besides the targets.

### 3.2. Judge cards

1. `ast.parse`.
2. The guard: the target is a NEW file. Its number of `test_*` functions lies between the
   number of examples and three times that number:
   - fingerprint 6 (Code Similarity 1–6);
   - store 3 (Manage Watchlist 6–8);
   - ingest 1 (Follow Chain 18);
   - cluster 4 (Interface Hits 1–2, Match Watchlist 5, Recheck Watchlist 12);
   - calibrate 8 (Evaluate Calibration 1–4, Load Labels 1–4);
   - cli 6 (Command Line 57–62).

   No `Fake*` class, no network import, and only the target changed against HEAD.
3. The judge file.
4. The full suite (with the deselects of §3.0, except the cli judge).
5. No untracked file left besides the target.

### 3.3. Live acceptance (the orchestrator's, after the run; not a card)

Branch code, on a copy of `smoke/20261001-night2/ethsc.sqlite` in `/tmp/p18/live/`. Only
this step may use the network: the corpus codes are loaded with `seed add --fetch` and then
`seed remove`.

1. `calibrate --labels tests/fixtures/calibration_labels.json`. Required:
   - `missing` is empty;
   - the 0.75 row has recall ≥ 0.89 and negatives 0;
   - interface_only at 0.75 is ≤ 15;
   - the rows agree within ±1 count with the reference model of §1 (0.7: 0.9263/2/23/13;
     0.75: 0.8947/0/21/12; 0.8: 0.8526/0/18/11);
   - one call takes under 60 s.
2. `seed audit` on the copy (its 8 seeds plus the Nimbus seed
   `0xc0a6b8c534fad86df8fa1abb17084a70f86eddc1`). Then `seed strict <Nimbus> on`, and
   `recheck` before and after it. Required:
   - `seed audit` shows Nimbus with interface_hits ≥ 70, and every other seed ≤ 5;
   - the Nimbus alerts drop from ≥ 1 000 to ≤ 5.

   The gate rehearsal on a throwaway reference gave 82 interface_hits, and alerts going from
   3 181 to 1.
3. Throughput: the mean time of `match_watchlist` over the same 1 000 night2 codes is
   measured two ways. First with the copy's seeds plus a strict Nimbus seed, on the branch
   code. Then on HEAD c232fb2 with the same seeds and no strictness. The branch must take
   ≤ 1.2 × the HEAD time. `match_watchlist` reads `store.fingerprints()` on every call
   (phase 11), so the absolute cost is set by the base, not by this phase. Both numbers are
   reported, together with the chain's budget: ~47 codes per 1.5 s block.
4. The table goes into §11.

## 4. Constraints

- Standard library only, Python 3.9 syntax. stdout carries records, stderr one line.
- Cards by file ownership:
  - Generation 0: `fingerprint` (fingerprint.py), `store` (store.py), `ingest` (ingest.py),
    `helpers-p18` (tests/helpers.py).
  - Generation 1: `cluster` (cluster.py; reads fingerprint.py, store.py, helpers.py),
    `calibrate` (calibrate.py, new; reads fingerprint.py, helpers.py), `fingerprint-judge`,
    `store-judge`.
  - Generation 2: `cli` (cli.py; reads cluster.py, calibrate.py, ingest.py), `cluster-judge`,
    `calibrate-judge`, `ingest-judge` (its Follow Chain 18 needs the cluster default).
  - Generation 3: `cli-judge`.

  No file written in a generation is in the context slice of a neighbour in that
  generation. The generation-0 cards do not read tests/helpers.py; their instructions name
  the helpers they import.
- Envelope:

  | card | lines | note |
  |---|---|---|
  | fingerprint | ~35 | |
  | store | ~35 | |
  | ingest | ~6 | |
  | cluster | ~55 | |
  | calibrate | ~140, new file | `variants: 2` |
  | cli | ~55 | label and grid parsing moved into calibrate.py to stay inside 60 |
  | helpers | ~35 | |
- Every file a test writes goes into a `tempfile.mkdtemp()` directory.
- The judge does not see how the code was written. It writes from the Contour and the
  finished code.

## 5. Techniques already working here

- The phase-11/13/14/15 migration in `Store.__init__`, and the read-only `_ro_no_*` flags.
- `main(argv, rpc=…)` with `FakeRpc` runs every cli example offline.
  `FakeRpc(fail=AssertionError(...))` with `.calls == []` proves no rpc call was made.
- `_UsageError` in cli turns a validation into exit 2 with one stderr line.

## 6. Intentionally not specified

- How `add_seed` keeps the flag (an UPSERT `ON CONFLICT(address) DO UPDATE`, or an UPDATE
  first and an INSERT after).
- How `evaluate` caches scores and shingles, as long as Evaluate Calibration's "at most
  once" holds.
- Whether `--min` is validated by argparse `type=` or after parsing, as long as the result
  is exit 2 with one line and no rpc call.
- The wording of the ValueError messages of `load_labels`/`parse_grid` and of the usage
  errors.

## 7. Out of scope

- Auto-strictness of any kind. `seed add` sets no flag, and `interface_hits` is evidence
  only.
- A metric that replaces selector Jaccard (LSH/MinHash, weighted selectors). This is a
  calibration of the existing rule plus a second gate.
- `similar` and `find_similar` (search, not alert; they stay at 0.8). Clusters L0/L1/L2.
- EIP-1967 implementation resolution for corpus proxies (appendix A of the catalogue).
- Tier-2 heuristics (`risk`), scoring/severity, the dashboard and its frontend.
- Re-seeding the live server, and marking its seeds strict. That is the operator's
  deployment act after merge: redeploy, `seed audit`, then `seed strict` on the
  generic-interface seeds.
- Fetching corpus codes inside `calibrate` (`seed add --fetch` + `seed remove` loads them).

## 8. How to run

`mrph plan --spec contour.yaml --map morph-map.json --component fingerprint --component
store --component ingest --component cluster --component calibrate --component cli --judge
--add`, then `mrph deck check`, then `mrph run --processor <the operator's choice>`. After
the run, `git checkout master` by hand. Push and merge are the operator's.

## 9. Pre-registration of predictions

- Cards: 13 (6 code, 6 judges, `helpers-p18`). Every card is accepted in ≤ 3 attempts. At
  least one regeneration falls on calibrate or cli.
- Tests: 448 + 7×(1..5) smoke + 28..84 judge, final count **483..567**.
- Live: the 0.75 row is 0.89..0.90 recall with 0 negatives; Nimbus strict cuts its pair
  alerts by ≥ 90%; `match_watchlist` takes 5..30 ms per code on night2.

## 10. What to record at the end

Accepted, failed and skipped cards; generations; regenerations; minutes per generation; the
final test count; the executor bill separate from the scout's; the live table of §3.3; the
hits and misses against §9.

## 11. Actual

(after the run)
