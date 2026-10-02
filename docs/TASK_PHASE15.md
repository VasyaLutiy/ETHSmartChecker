# TASK_PHASE15 — a live dashboard backend for the listener

Contract: `contour.yaml`, group store (Store Codes And Contracts: the paragraph "Phase 15",
examples 16–17; Track Progress: `progress_at`, example 2; Base Counts: `origin_counts`,
example 4; Record Events: new, examples 1–5; Open Read Only: new, examples 1–4; dataObjects
Code Database, Event), group ingest (Follow Chain: the paragraph "Phase 15 (events)",
examples 14–17), group cli (Command Line: `dashboard` in the subcommand list, the paragraph
"Dashboard (phase 15)", examples 51–56), the new group dashboard (Answer Request, examples
1–12; Serve Dashboard, examples 1–2; dataObject Dashboard JSON), Requirement Offline Tests
(loopback allowed) and Guardrail No Network In Core (dashboard.py may import http.server).
No change in rpc, evm, fingerprint, cluster rules, report, charts, config. Standard library
only, Python 3.9 syntax.

## 1. Why this

- Watching `listen` today means ssh plus grep over `listen.out`. ALERT and UPGRADE lines
  exist only in stdout and are lost with the log. Nothing outside the process tells whether
  the listener is alive or behind: `progress` holds a block number and no time.
- Target load: the 12-h run of 02.10 (server 168337972). Its base,
  `smoke/20261001-night2/ethsc.sqlite`, has **214 132 addresses**, progress 26 099 873,
  245 MB, journal mode `delete`, and the **phase-13 schema**: no `addresses.implementation`.
  It has 8 seeds and resolved 543 proxies in the first minutes.
- In a `delete`-mode (rollback journal) file a reader's SHARED lock makes the writer's
  commit wait, by SQLite's documented locking. A 1-second poller over a 214k-row base would
  therefore put "database is locked" into the listener. With `journal_mode=WAL` the writer
  and the readers never block each other. This was not measured here; acceptance §3.3 step 1
  measures it. Measured 02.10 on SQLite 3.45.1 (the venv): a `mode=ro` reader on a `delete`-mode file leaves no file next to
  it. A `mode=ro` reader on a WAL file **with no writer attached** leaves an empty `-wal`
  and a 32 KB `-shm` after closing. That is SQLite's own behaviour and is allowed (Open Read
  Only).
- Ripple spike (§3.0): a crude mutation added the events table, the progress column, WAL on
  open and an `add_events` call in `follow_chain`. It turned **0 of 393** tests red. No data
  edit is needed before the run.
- Process: phases 12–14 ran on Claude Code agents. This phase runs on the batch processor
  `glm` (the operator's choice), as phases 1–11 did. Those 19 glm runs: 62 of 79 cards
  accepted, $0.87 in total, $0.014 per accepted card.

## 2. Contract

### 2.1. INPUT data shapes the code must build

- The store: `Store.__init__` (`ethsc/store.py:64`) shows the migration pattern `PRAGMA
  table_info` → `ALTER TABLE … ADD COLUMN` → commit, with no UPDATE. The schema script is
  `_SCHEMA` (`ethsc/store.py:25`). `set_progress` is at `ethsc/store.py:304`. `counts()` is
  at `ethsc/store.py:392` and is the pattern for a pure aggregate read.
- The alert dict, as `ingest_block` hands it to `on_alerts`: `{"address", "seed_address",
  "label", "score", "origin"}`, sorted by address (`_deliver_alerts`, `ethsc/ingest.py:316`).
  The upgrade dict, as `on_upgrades` receives it: `{"address", "old", "new", "block"}`
  (`_deliver_upgrades`, `ethsc/ingest.py:324`). Both are delivered once per `ingest_block`
  call, on the normal return and on the KeyboardInterrupt path (`ethsc/ingest.py:531`).
- `follow_chain` (`ethsc/ingest.py:621`): the `ingest_block` call and the
  `set_progress` after it are at `ethsc/ingest.py:818–835`.
- The CLI: `main` is at `ethsc/cli.py:584`. Every subcommand opens `store = Store(args.db)` at
  `ethsc/cli.py:616`, and `dashboard` must branch before that line. `_build_parser` is at
  `ethsc/cli.py:495`. The sinks `_print_alerts` / `_print_upgrades` are at `ethsc/cli.py:164`
  and `:203` and stay unchanged.
- Clusters: `build_clusters(store)` (`ethsc/cluster.py:39`) returns a list of `{level, key,
  members}`. It reads `fingerprints()`, `code_by_id()`, `addresses_of()` and
  `implementations()`.
- Tests: `temp_store()`, `block_store()`, `block_codes()`, `load_hex(name)`, `FakeRpc(codes=,
  receipts=, head=, storage=)` and `InterruptAfter(inner, n)`, all in `tests/helpers.py`.
  `legacy_db(phase)` is new in this phase (§2.3).
- The measured values in the examples come from `block_store()`. On it `build_clusters`
  gives 7 L0, 2 L1, 2 proxy, 4 eip7702 and 0 impl clusters. The code_id of `code_belle.hex`
  is `8571d00b…cb4d` (full value in the Contour). The BELLE alert of Follow Chain example 14
  has score `0.8666666666666667` and origin `"seen"`. All were measured on HEAD 5ba1977 on
  2026-10-02.

### 2.2. OUTPUT data shapes

- Table `events(id INTEGER PRIMARY KEY, kind, block, at, address, seed_address, label, score
  REAL, origin, old_impl, new_impl)`, in that column order. Column `progress.updated_at TEXT`
  is last. The file is in `journal_mode=WAL` after any writable open.
- An Event is a dict with exactly the eleven keys above (dataObject Event).
  `event_counts()` returns `{"kinds": {"ALERT": a, "UPGRADE": u}, "seeds": [{"label",
  "seed_address", "count"}]}`.
- `origin_counts(since_block=None)` returns `{origin text or "unknown": int}`.
- HTTP: every JSON body is `json.dumps(obj, sort_keys=True)` in UTF-8, with content type
  `application/json; charset=utf-8`. The four endpoints are in the Contour, Answer Request
  behavior. Errors are `{error}` with 400, 404, 405 or 500.
- CLI `dashboard`: stdout empty. On start, one stderr line `serving http://<host>:<port>/`.
  Exit 0 on Ctrl-C. Exit 2 with one stderr line on a missing db, a busy port or a bad
  `--port`.
- Fixtures recorded after the live acceptance: `tests/fixtures/dashboard_health.json`,
  `dashboard_events.json`, `dashboard_summary.json`, `dashboard_clusters_impl.json`, each the
  body of one live answer.

### 2.3. Names

- `ethsc.store.Store(path, readonly=False)`, `ethsc.store.ReadOnlyStoreError`,
  `Store.add_events(events)`, `Store.events(after_id=0, limit=100)`, `Store.event_counts()`,
  `Store.progress_at()`, `Store.origin_counts(since_block=None)`.
- `ethsc.dashboard.respond(db_path, target, static_dir=None, now=None, cache=None)` →
  `(status, content_type, body)`. `ethsc.dashboard.make_server(db_path, host="127.0.0.1",
  port=8080, static_dir=None)` returns a bound `http.server.ThreadingHTTPServer`.
- Event kinds `"ALERT"` and `"UPGRADE"`. Event keys `old_impl` and `new_impl` (the upgrade
  dict's `old` and `new`).
- `tests.helpers.legacy_db(phase)`, where phase is 13 or 14. It returns the path of a new
  sqlite file in a fresh `tempfile.mkdtemp()` directory. The file is built with plain
  `sqlite3`, never with `Store`, and uses that phase's schema: codes with `std_proxy`;
  addresses `(address, code_id, block, origin)`, plus `implementation` for 14; progress
  `(key, block)`; seeds; ledger; no events table; journal mode `delete`. It holds the 130
  codes (columns from `fingerprint()`, `selectors` as JSON text, `std_proxy` 0/1), the 206
  addresses of `codes_26077729.json` at block 26077729 with origin (and implementation)
  NULL, and the row `("progress", 26077729)`. The connection is closed before it returns.
- New test files: `tests/test_store_p15.py`, `tests/test_ingest_p15.py`,
  `tests/test_dashboard_p15.py`, `tests/test_cli_p15.py` (code-card smoke).
  `tests/test_store_examples_p15.py`, `tests/test_ingest_examples_p15.py`,
  `tests/test_dashboard_examples_p15.py`, `tests/test_cli_examples_p15.py` (judges).

### 2.4. What must not break

- `Store(path)` with one positional argument. Every existing read and write. The phase-11/13/14
  migrations. No UPDATE of old rows on open: the 214 132 rows of night2 stay as they are, and
  so does the `progress` row (its `updated_at` stays NULL until the next `set_progress`).
- The `follow_chain` summary keys, the stats, the ledger, and the printed ALERT and UPGRADE
  lines and their order. `--alert-on` still filters stdout only.
- Exit codes 0/1/2/3. Only `ethsc/rpc.py` imports urllib, http or socket; the one exception is
  `ethsc/dashboard.py` with `http.server`. Stdlib only, Python 3.9 syntax. `cluster.py`
  reads the store through public methods. `cli.py`, `cluster.py` and `dashboard.py` touch no
  `_` attribute except on `self`.
- The 393 existing tests stay green. No data edit (§3.0).

## 3. Acceptance

All of it is built by one script outside the tree (`/tmp/p15/build.py`). Every step uses
`-q --tb=line`. The network is blocked in the process (getaddrinfo, create_connection, and
connect to anything but `127.0.0.1`). `INFURA_API_KEY` is set to a dummy. The first command
snapshots the targets to `/tmp/morph/<card>-p15/`.

### 3.0. Data before the run

None. The ripple spike (worktree at HEAD, mutation: events table + `progress.updated_at` +
WAL on open + `add_events` after every block in `follow_chain`) ran **393 passed, 0 failed**.
No test pins the table set, the progress columns, the journal mode or the files next to the
db (the scout reached the same conclusion; see the gate report).

### 3.1. Code cards (each card, its own targets)

1. `ast.parse` of every target, `feature_version=(3, 9)`.
2. The guard walks the `ast`, not the text:
   - Stdlib Only and No Network In Core over `ethsc/*.py`. `ethsc/dashboard.py` may import
     `http.server` only: no urllib, `http.client` or socket.
   - `cli.py`, `cluster.py` and `dashboard.py` touch no `_` attribute except on `self`.
   - `cluster.py` does not import sqlite3.
   - `rpc.py`, `evm.py`, `fingerprint.py`, `cluster.py`, `report.py`, `charts.py` and
     `config.py` are unchanged (`git diff --quiet HEAD --`).
   - The card's smoke file has 1..5 `test_*`, no `Fake*` class and no `maxDiff`. Only
     `test_dashboard_*` and `test_cli_*p15` may import socket.
   - `tests/helpers.py` keeps every name it has at HEAD.
3. The probe (inline), one readable line per failed check, each naming its example:
   - store: Store 16–17, Track Progress 2, Base Counts 4, Record Events 1–5, Open Read
     Only 1–4.
   - ingest: Follow Chain 14–17, plus Follow Chain 1 and 5 unchanged.
   - dashboard: Answer Request 1–12, Serve Dashboard 1–2.
   - cli: Command Line 51–56.
   - helpers-p15: `legacy_db(13)` and `legacy_db(14)` have the shape of §2.3.
4. The card's own test file.
5. The full suite `tests`, with no deselect.
6. No untracked file left besides the targets.

### 3.2. Judge cards

1. `ast.parse`.
2. The guard: the number of `test_*` functions lies between the number of examples (one test
   each) and that number + 12. Store judge: 13 (Store 16–17, Track Progress 2, Base Counts 4,
   Record Events 1–5, Open Read Only 1–4). Ingest judge: 4. Dashboard judge: 14 (12 + 2). CLI
   judge: 6. No `Fake*` class and no network import, except socket in the dashboard and cli
   judges. `git diff --quiet HEAD -- ethsc tests/helpers.py`.
3. The judge file.
4. The full suite.
5. No untracked file left besides the target.

### 3.3. Live acceptance (the orchestrator's, after the run; not a card)

Branch code, run on a copy of `smoke/20261001-night2/ethsc.sqlite` in `/tmp/p15/live/`. Only
this step may use the network.

0. The sha256 of the copy. Then `dashboard --db copy --port 8090` alone, with `/api/health`,
   `/api/summary` and `/api/clusters?level=impl` polled. Ctrl-C. The sha256 must be unchanged
   and no `-wal`, `-shm` or `-journal` file left behind (contract item 4).
1. `listen --source publicnode` for 10 min on the copy, with progress set to head−1 first.
   `dashboard` runs next to it, and a loop polls `/api/health`, `/api/events?after=<last_id>`
   and `/api/summary` once a second. Required: zero "database is locked" in the listener's
   stderr and in the poller's log, and a progress lag of ≤ 3 blocks at the end.
2. Every ALERT and UPGRADE line listen printed is in the polled events exactly once, with the
   same fields.
3. `/api/summary` and `/api/clusters?level=impl` each answer in under 1 s on the 214k base
   (cold cache for clusters). `/api/health` `seconds_since_progress` stays below 30 while
   listen runs.
4. The answers of step 1 are recorded as `tests/fixtures/dashboard_*.json`, with a row each
   in `tests/fixtures/README.md`.

## 4. Constraints

- Standard library only, Python 3.9 syntax. stdout carries records, stderr one line.
- Cards by file ownership. Generation 0: `helpers-p15` (tests/helpers.py) and `store`
  (store.py). Generation 1: `ingest` (ingest.py) and `dashboard` (dashboard.py), both reading
  store.py, plus `store-judge`. Generation 2: `cli` (cli.py, reads dashboard.py and needs
  ingest for its events examples), `ingest-judge` and `dashboard-judge`. Generation 3:
  `cli-judge`. No file written in a generation is in the context slice of a neighbour in that
  generation.
- Envelope: store ~110 lines, over the 60-line gate (8 write-method guards, 3 reads, events
  and the migration all belong to one file with one owner), so `variants: 2`. Ingest ~30.
  CLI ~35. dashboard.py is new, ~250 lines of pure logic, `variants: 2`. Helpers ~35.
- Every file a test writes goes into a `tempfile.mkdtemp()` directory. A test that serves
  binds `127.0.0.1` port 0 and talks over a raw socket, never through getaddrinfo.
- The judge does not see how the code was written. It writes from the Contour and the
  finished code.

## 5. Techniques already working here

- The phase-11/13/14 migration in `Store.__init__`.
- `_alert_on_sink` in cli wraps a sink without touching ingest. The recording sinks of
  `follow_chain` use the same shape: record, then forward.
- `InterruptAfter` already drives the KeyboardInterrupt paths in tests.
- `main(argv, rpc=…)` with `FakeRpc` is how every cli example runs offline.

## 6. Intentionally not specified

- How `respond` routes (a dict of handlers, an if-chain) and how it parses the query
  (`urllib.parse` is **not** importable outside rpc, so the query is split by hand on `&`
  and `=` and the path is percent-decoded by hand. Any correct stdlib approach that keeps
  the guard green is fine).
- Whether the read-only guard is a decorator or a check at the top of each write method.
- How the tolerance for missing tables and columns is detected (`PRAGMA table_info` once at
  open, or catching `sqlite3.OperationalError`).
- The exact text of the placeholder page and of error messages, beyond what the examples
  require.

## 7. Out of scope

- The TypeScript frontend (`dashboard/`, its `package.json`, the build into
  `dashboard/dist`). That is the next phase, built against `tests/fixtures/dashboard_*.json`.
- Authentication, TLS, CORS, and any bind beyond localhost by default (access is an ssh
  tunnel).
- Websockets and SSE (the frontend polls).
- Balances, prices, anything that needs a new rpc method.
- Events from `recheck` and `seed add`. Backfilling events from old `listen.out` logs.
- Deleting or pruning events, and retention.
- Read-only support for databases older than phase 13 (they answer 500 `{error}`).
- The `-wal`/`-shm` pair that SQLite leaves after a read-only read of a WAL file with no
  writer.

## 8. How to run

`mrph plan --spec contour.yaml --map morph-map.json --component store --component ingest
--component dashboard --component cli --judge --add`, then `mrph deck check`, then
`mrph run --processor glm` (route sync). After the run, `git checkout master` by hand.
Push and merge are the operator's.

## 9. Pre-registration of predictions

- Cards: 9 in total (4 code cards, 4 judges, `helpers-p15`).
  Every card is accepted in ≤ 3 attempts. At least one card needs a regeneration (store or
  dashboard, the two wide ones).
- Tests: 393 + 4×(1..5) smoke + 37..85 judge, final count **440..495**.
- Live: zero "database is locked" in 10 minutes. `/api/summary` 0.2..0.8 s on 214k.
  `/api/clusters?level=impl` cold 0.4..1.0 s, warm < 0.05 s. 0..5 ALERT lines in 10 minutes,
  every one in events.

## 10. What to record at the end

Accepted, failed and skipped cards; generations; regenerations; minutes per generation; the
final test count; the glm bill (executors) separate from the scout's bill; the live table of
§3.3; the hits and misses against §9.

## 11. Actual

_(after the run)_
