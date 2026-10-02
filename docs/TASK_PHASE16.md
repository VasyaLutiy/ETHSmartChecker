# TASK_PHASE16 — the dashboard frontend, TypeScript, built by Morph

Contract: `contour.yaml`, the new group **dashboard-ui** (`language: typescript`): Fetch
Endpoints (examples 1–8), Format Values (1–7), Merge Feed (1–5), Render Panels (1–11), Wire
Page (1–5); the new Requirement **Frontend Tree** and Guardrail **Frontend Isolation**; the
Requirement Stdlib Only now says it covers `ethsc/` and `tests/` only. The JSON it reads is
the phase-15 dataObject Dashboard JSON of group dashboard, recorded as
`tests/fixtures/dashboard_{health,events,summary,clusters_impl}.json`: those four files are
the source of truth for every shape. No change in `ethsc/`, the Python tests or the Python
project's stdlib-only rule. The frontend is a separate tree, `dashboard/`, whose only product
is `dashboard/dist/`, which `ethsc dashboard --static` already serves (default
`dashboard/dist`).

## 1. Why this

- Phase 15 left a backend and no page: watching the listener means `curl` over four JSON
  endpoints. Its live run (02.10) put **8 ALERT events** and **52 blocks in 600 s** into the
  store; `seconds_since_progress` peaked at **34 s** with 3 of 545 samples over 30 s, so a
  status strip must say "behind" from 60 s, not 30 (phase 15 §11).
- The first TypeScript deck for Morph. Morph's typescript profile (`cards/language.py`,
  merged 28.09) has never cut a real deck; glm has **0** measured TypeScript cards against
  **71 accepted Python cards** here ($0.0145 per accepted card, primer of 02.10). This phase
  measures both: generations and regenerations per card are pre-registered in §9 and scored
  in §11.
- Known gaps of the profile, measured in the code on 02.10: the default targets are
  `ethsc/<name>.ts` and `tests/<name>.test.ts` (root-relative, would land in the Python
  package and suite); the default acceptance runs `npx tsc --noEmit` at the root, where there
  is no `package.json`; the profile has no guard table (`guards={}`). The syntax gate is
  ready: `mrph` runs on `MorphProject/mrph/venv` (its shebang; `venv_mrph/bin/python` is a
  bare system python), which has tree-sitter 0.26.0 and tree-sitter-typescript 0.23.2, and
  `check_tree_sitter` passed a valid `.ts` line and failed `const a: = ;` at line 1 (02.10).
  Every card of this deck therefore has its targets, acceptance and instruction set in
  the map.
- Ripple spike (§3.0): a `dashboard/` tree with `dist/`, `node_modules/`, `package.json` and a
  `src/api.ts` in a worktree at HEAD: **448 passed, 0 failed**. No Python test reads
  `dashboard/` (two pin only the default `--static` value, through a stubbed `make_server`).

## 2. Contract

### 2.1. INPUT data shapes the code must build

- The four fixtures, verbatim answers of the phase-15 live run (sizes 123, 2706, 478 and
  5749 bytes): health `{now, progress, progress_at, seconds_since_progress}`; events
  `{events: [8 ALERT events, ids 8..1], last_id: 8}`; summary (217 009 addresses); clusters
  `{level: "impl", n: 20, clusters: [20 × {key, level, members}]}`. An event has exactly the
  eleven keys of dataObject Event (`contour.yaml`, group store). There is no UPGRADE in the
  fixtures; the UPGRADE used by the examples is Record Events example 1, with id 9.
- The empty answers of a fresh db: dashboard Answer Request example 2.
- `tests/helpers.ts` (§2.3) builds every stub; a test writes none of its own.

### 2.2. OUTPUT data shapes

- `dashboard/dist/`: `index.html` and `assets/` and nothing else, no `.map` file, made by
  `npm run build` (`vite build`).
- The DOM contract of each panel: the selectors in Render Panels behavior
  (`[data-field=…]`, `[data-id]`, `[data-kind]`, `[data-badge=…]`, `[data-bar=…]`
  `[data-origin=…]`, `[data-key]`, `.unreachable`) and the ids of Wire Page (`#health`,
  `#events`, `#summary`, `#clusters`, `select#kind-filter`).
- Requests: exactly `/api/health`, `/api/events?after=<last_id>&limit=500`, `/api/summary`,
  `/api/clusters?level=impl&n=20`, same origin.

### 2.3. Names

- `dashboard/src/api.ts`: types `Health`, `Kind`, `DashEvent`, `EventsPage`, `OriginKey`,
  `OriginCounts`, `Summary`, `Cluster`, `ClustersPage`, `ApiResult<T>`, `Panel<T>`,
  `FetchLike`; `parseHealth`, `parseEvents`, `parseSummary`, `parseClusters`; `getHealth(f)`,
  `getEvents(after, f)`, `getSummary(f)`, `getClusters(level, n, f)`.
- `dashboard/src/format.ts`: `formatScore`, `formatAge`, `statusOf`, `shortAddress`,
  `etherscanUrl`, `formatTime`, `originShares`.
- `dashboard/src/feed.ts`: `mergeEvents(kept, incoming, cap = 500)`, `filterByKind(events,
  kind)`.
- `dashboard/src/render/health.ts` `renderHealth`, `render/events.ts` `renderEvents`,
  `render/summary.ts` `renderSummary`, `render/clusters.ts` `renderClusters`.
- `dashboard/src/main.ts`: `start(doc, fetchFn, clock?)` → `stop`.
- `dashboard/tests/setup.ts`: no exports; blocks `globalThis.fetch`, `XMLHttpRequest`,
  `WebSocket` and `node:net` `connect`/`createConnection` (each throws "network blocked in
  tests") unless a test stubs them.
- `dashboard/tests/helpers.ts` (the one stub module; signatures are the contract):
  - `type FixtureName = "health" | "events" | "summary" | "clusters_impl"`;
    `loadFixture(name): unknown` — a fresh `JSON.parse` of
    `tests/fixtures/dashboard_<name>.json`, the path built with `node:path` from
    `fileURLToPath(import.meta.url)` (`../../tests/fixtures/` from `dashboard/tests/`), never
    a copy. Not `new URL(…)`: under the happy-dom environment the global `URL` is happy-dom's,
    and `fs.readFileSync` refuses it ("The URL must be of scheme file", measured 02.10).
  - `interface FixtureEvent` — the eleven Event keys with the TypeScript types of
    `DashEvent` (declared here, structurally equal; helpers does not import `src/`).
  - `fixtureEvents(): FixtureEvent[]` — fresh copies of the 8 fixture events.
  - `syntheticEvents(ids: readonly number[]): FixtureEvent[]` — copies of fixture event 8
    with `id` and `block` set to each i.
  - `UPGRADE_EVENT: FixtureEvent` — Record Events example 1 as an event with id 9 (Merge Feed
    example 5).
  - `type FakeReply = {status?: number; body?: unknown; jsonError?: boolean} | Error`;
    `interface FakeResponse {ok: boolean; status: number; json(): Promise<unknown>}`;
    `fakeFetch(routes?: Record<string, FakeReply>): {fetch(url: string):
    Promise<FakeResponse>; calls: string[]; set(url, reply): void; failAll(e: Error | null):
    void}` — status defaults to 200 and ok is 200..299; an Error reply rejects with it;
    `jsonError` makes `json()` reject with a SyntaxError; an unknown URL answers 404 `{"error":
    "not found"}`; `failAll(e)` makes every call reject with e until `failAll(null)`; every
    call's URL is pushed to `calls` first.
  - `fixtureFetch()` — `fakeFetch` with the four fixtures on `/api/health`,
    `/api/events?after=0&limit=500`, `/api/summary`, `/api/clusters?level=impl&n=20`.
  - `fakeClock(): {setInterval(fn, ms): number; clearInterval(id): void; timers: {id, fn,
    ms}[]; cleared: number[]; fire(ms?: number): void}` — ids 1, 2, 3, … in registration
    order; `fire(ms)` calls every timer not cleared with that ms (every one without ms), in
    registration order.
  - `flush(): Promise<void>` — waits five macrotask turns (`setImmediate` of
    `node:timers/promises`).

### 2.4. What must not break

- `ethsc/`, `tests/` (Python), `contour.yaml` groups other than dashboard-ui: byte for byte.
  The Python suite stays **448 passed**.
- The scaffold files (§3.0) after they are committed: no later card writes `package.json`,
  `package-lock.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `tests/setup.ts` or
  `tests/helpers.ts`.

## 3. Acceptance

All of it is built by one script outside the tree (`/tmp/p16/build.py`). Every command runs
`cd dashboard &&`; dense output is `--reporter=dot`. The first command snapshots the targets
to `/tmp/morph/<card>-p16/`. node_modules comes from the committed lock (`npm ci
--prefer-offline` only when `node_modules` is missing). The probe and the guard are written
by the acceptance into `dashboard/probe/` (git-ignored, removed on exit) and are never in the
tree.

### 3.0. Data before the run, and the scaffold

- `.gitignore` gains `dashboard/node_modules/`, `dashboard/dist/`, `dashboard/probe/` (three
  lines, committed by hand as data).
- The scaffold (`package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`,
  `tests/setup.ts`, `tests/helpers.ts`, all under `dashboard/`) is written by one Morph card,
  `ui-scaffold`, run alone first (run A). Its acceptance runs `npm install`, which writes
  `package-lock.json` (untracked; allowed by its own last step). After run A the orchestrator
  commits that lock file as data: it is npm's output, not hand-written. Run B (every other
  card) starts from that commit; its acceptances use `npm ci`.
- Ripple spike: 448 passed with a `dashboard/` tree in place (§1).

### 3.1. ui-scaffold (run A)

1. `npm install --no-audit --no-fund` exits 0; `package.json` has no `dependencies` and
   exactly the five devDependencies of Frontend Tree, exact versions (read by `node`, JSON
   parsed); `scripts.build` is `vite build`.
2. `npx tsc --noEmit` (strict, read back from `tsc --showConfig`).
3. The probe (`probe/scaffold.probe.ts`, vitest with a probe config that includes only
   `probe/`): every helper of §2.3 behaves as written; `fetch("http://example.com")`,
   `new XMLHttpRequest()`, `net.connect(80, "example.com")` throw; `loadFixture("health")`
   has progress 26103569.
4. `npx vitest run --reporter=dot --passWithNoTests` (the setup file loads).
5. Nothing outside `dashboard/` changed; no untracked file except the targets and
   `dashboard/package-lock.json`.

### 3.2. Code cards (ui-api, ui-format, ui-feed, ui-render, ui-main)

1. `npx tsc --noEmit`.
2. The guard (`probe/guard.mjs`, the TypeScript compiler API walking every file of
   `src/`, never grep): Frontend Isolation item by item, each violation one line
   `guard: <file>:<line> <rule>`; also no `console` in `src/`. Over the card's own test file:
   1..5 `test`/`it` calls, no `any`.
3. The probe (`probe/<card>.probe.ts`), one vitest test per Contour example, named
   `<Function> ex<N>`, each failure one readable line.
4. The card's own test file.
5. The full vitest suite.
6. ui-main only: `npm run build`; `dist/` lists exactly `assets` and `index.html`; no
   `*.map` under `dist/`; `dist/index.html` references one `assets/*.js`.
7. `git diff --quiet HEAD --` over `ethsc tests contour.yaml` and the scaffold files; no
   untracked file except the targets.

### 3.3. Judge cards (ui-api-judge, ui-format-judge, ui-feed-judge, ui-render-judge, ui-main-judge)

1. `npx tsc --noEmit`.
2. The guard: the number of `test`/`it` calls lies between the number of examples (one test
   each) and that number + 12 — api 8..20, format 7..19, feed 5..17, render 11..23, main
   5..17 (counts from the Contour); no `any`; the file imports stubs from `./helpers` only
   and defines no `fetch` of its own.
3. The judge file.
4. The full vitest suite.
5. `git diff --quiet HEAD --` over `dashboard/src`, the scaffold, `ethsc`, `tests`; no
   untracked file except the target.

### 3.4. Live acceptance (the orchestrator's, after run B; not a card)

0. `cd dashboard && npm ci && npx tsc --noEmit && npx vitest run && npm run build` exits 0;
   `dist/` holds `index.html` plus `assets/` and nothing else, no source maps.
1. On a copy of the night db (`smoke/…/ethsc.sqlite` in `/tmp/p16/live/`):
   `ethsc --db COPY dashboard --static dashboard/dist --port 8090` plus `listen --source
   publicnode` on the same copy for 10 minutes. The page in a browser: the health strip
   "live", ALERT rows appear without reload, the impl table fills, the summary bars draw.
   Then the backend is stopped for 20 s: every panel shows "backend unreachable" and keeps
   its data; restarted, they recover. Screenshot in §11.

## 4. Constraints

- Cards by file ownership, generations by physical reading. Run A: `ui-scaffold`. Run B,
  generation 0: `ui-api`, `ui-format`, `ui-feed` (each reads only the scaffold and the
  fixtures; feed is generic over `{id}` / `{kind}` and format types its origin parameter
  itself, so neither imports anything). Generation 1:
  `ui-render` (reads `api.ts`, `format.ts`) and the judges of generation 0. Generation 2:
  `ui-main` (reads `api.ts`, `feed.ts`, `render/*.ts`) and `ui-render-judge`. Generation 3:
  `ui-main-judge`. No file written in a generation is in the slice of a neighbour in it.
- Envelope: api ~170 lines, render ~260 over four files (one owner, `variants: 2`), main ~110,
  format ~70, feed ~30, scaffold ~200 over six files (`variants: 2`).
- `tests/helpers.ts` and the `contour.yaml` are in the slice of every card that writes tests;
  every fixture a card's examples name is in its slice explicitly (Morph's slice whitelist
  takes `.ts`, `.tsx`, `.js`, `package.json`, not other `.json`).
- The code card's own test file is at most five smoke tests on scalars (`toBe`), no
  `toEqual` on fixture-sized values. Completeness is judged by the probe and the judge.
- A test writes no file. Nothing touches the network: `tests/setup.ts` throws on it.
- The judge does not see how the code was written; it writes from the Contour and the
  finished module.
- A fix does not affect the current run.

## 5. Techniques already working here

- Phase 15's builder pattern (one script, shared steps, inline probe, snapshot first,
  untracked check last).
- Generic pure modules (feed over `{id}`) cut a generation out of the deck.
- The DOM is reached through `root.ownerDocument` and the timers through an injected clock,
  so every panel and the whole page are testable without globals.

## 6. Intentionally not specified

- CSS, colours, layout and the exact markup beyond the selectors of Render Panels.
- How a parser is written (a hand-written guard per key or a small schema helper inside
  `api.ts`), and the exact error texts beyond "non-empty, one line, names the status".
- How main skips a poll that is still pending.
- The page's title and the text labels of the panels.

## 7. Out of scope

- Any change to the Python backend, its tests or its stdlib-only rule.
- A UI framework, charts beyond simple bars, mobile layout polish, a dark theme toggle.
- Deploying `dist/` to the server (the operator copies it).
- Websockets, SSE, a push of any kind (the page polls).
- Events missed in a burst of more than 500 in one 5-s poll (the backend returns the newest
  500 with `id > after`; there is no paging back), and a backend that restarts on a
  different db with smaller ids (the page is reloaded by hand).
- ESLint: the guard is the compiler-API script of §3.2, no ESLint dependency.
- Local time: times are shown in UTC as the backend writes them.

## 8. How to run

Run A: `mrph plan --spec contour.yaml --map morph-map.json --component dashboard-ui --judge
--add` cuts the full deck; for run A the deck holds `ui-scaffold` alone (the other cards are
added after the lock commit). `mrph deck check`, `mrph run --processor glm` (route sync).
`git checkout master` by hand; commit `dashboard/package-lock.json`. Run B: the rest, the
same way. Push and merge are the operator's.

## 9. Pre-registration of predictions

- Cards: 11 (1 scaffold, 5 code, 5 judges). Every card accepted in ≤ 3 attempts. At least two
  regenerations in total, at least one of them on `tsc` (strict null checks on the parsers or
  on the DOM types of render).
- glm on TypeScript vs its Python record here (37 regenerations over 71 accepted cards, 0.52
  per card): 0.5..1.2 regenerations per card.
- Tests: 5×(1..5) smoke + 36..96 judge, **41..121** vitest tests. Python stays 448.
- `dist/`: one `index.html`, one JS asset (plus at most one CSS), total < 40 KB.
- The syntax gate reports `tree-sitter` `passed` (not `skipped`) on every `.ts` target.

## 10. What to record at the end

Accepted, failed and skipped cards per run; generations; regenerations per card and their
first failing step (tsc, guard, probe, own test, full suite); minutes per generation; the
vitest count; the glm bill per run; whether the syntax gate ran on `.ts`; the live check of
§3.4 with a screenshot; hits and misses against §9.

## 11. Actual

**Run A** `20261002-113200-c11806d4`, glm, route sync, 11:32–11:33, **1.7 min**: `ui-scaffold`
accepted on retry 1 (v1 tsc: a FakeReply union without `jsonError` on one arm, setup.ts
assigning functions to `XMLHttpRequest`/`WebSocket`; v2 tsc: a type annotation on a constructor;
r1.v1 probe: WebSocket not blocked; r1.v2 green). 4 requests, **$0.0226**. Then
`dashboard/package-lock.json` (npm's output, 111 packages) committed as data (9bb4504).

**Run B** `20261002-113535-0ad30337`, glm, 11:35–11:50, **14 min** over 4 generations.
**10 of 10 accepted, 0 failed, 0 skipped.** 30 requests, **$0.1237**. Both runs: 11/11 cards,
**$0.146**, $0.013 per accepted card (Python here: $0.0145).

| gen | card | attempts | first red step of each failed variant |
|---|---|---|---|
| 1 | ui-api | 1 (v2) | v1: own test (a URL assertion of its own) |
| 1 | ui-format | 1 | — |
| 1 | ui-feed | 1 | — |
| 2 | ui-feed-judge | 1 (v1) | v2: guard, 1 `test` call (a loop) for 5 examples |
| 2 | ui-api-judge | 2 | guard: assigned a global fetch ×2; tsc: a `Mock` type |
| 2 | ui-format-judge | 2 | judge file: its own extra rule test expected `0x1234…90a` (the code's `…890a` is right) ×2 |
| 2 | ui-render | 2 | probe: rows `hidden` under "ALL"; tsc: `FixtureEvent.kind` is `string` |
| 3 | ui-render-judge | 2 | tsc: `Element` vs `HTMLElement`; tsc: `FixtureEvent` vs `DashEvent` |
| 3 | ui-main | 3 | probe: no panels in `#app`; tsc: `Timeout` vs `number` ×2; own test ×2 |
| 4 | ui-main-judge | 1 | — |

- Regenerations: 7 retries over 11 cards (**0.64 per card**; Python here 0.52). By first red
  step over every failed variant: **tsc 8**, guard 3, probe 3, own test/judge file 5. tsc is the
  main teacher on TypeScript, as predicted.
- **One criterion fault of mine**, cost ≈ 2 tsc reds: the scaffold probe checked the helpers'
  values, not their types. glm declared `FixtureEvent.kind: string` (§2.3 says the types of
  `DashEvent`), so every test that hands fixture events to `renderEvents` needed a cast. A
  probe for a structurally equal type should hold a type-level assertion
  (`const _: DashEvent = fixtureEvents()[0]` under tsc).
- **One product gap of mine**: §6 left CSS "not specified" and no card owned a stylesheet.
  The page works, but it is raw: no panel headings, no column separators, the origin bars have
  width and no background (invisible). See the screenshot. A follow-up card should own
  `dashboard/src/style.css` (imported by main.ts) plus panel titles.
- Syntax gate: **tree-sitter `passed`** on every `.ts` target of both runs (skipped only on
  `.json`/`.html`: no grammar wheel). It passed `setup.ts` with TS1093, which tsc caught.
- Product: `src/` 893 lines (api 362 with its test, render 368, main 264 …). Tests: **89 vitest**
  (22 smoke, 67 judge) in 1.25 s. Python: `ethsc/` and `tests/` untouched (empty diff vs master),
  448 unchanged.
- Recon: no scout (every target new); the scout named 0, I moved 0 roles. The ripple spike
  (448/448 green with a `dashboard/` tree) found nothing either.

**§3.4 step 0**: `rm -rf node_modules dist && npm ci && tsc --noEmit && vitest run && npm run
build` exit 0; `dist/` = `index.html` (0.25 kB) + `assets/index-B275kLxx.js` (10.87 kB, 3.32 kB
gzip), no `.map`, 11 117 bytes in total.

**§3.4 step 1**, copy of `smoke/20261001-night2/ethsc.sqlite` in `/tmp/p16/live/`, progress set
to head−1 (26104179), `dashboard --static dashboard/dist --port 8090` + `listen --source
publicnode`, headless Chrome driven over CDP (`/tmp/p16/live/cdp.mjs`), sampled every 30 s
(10:56–11:07 UTC):

| check | result |
|---|---|
| health strip | status "live" in all 22 samples, age 1..28 s, progress 26104179 → 26104216 |
| ALERT rows without reload | 0 → 6 rows (ids 1..6) as listen printed **6 ALERT lines: the same 6 addresses, labels, scores**; 1 navigation entry all along; the first row's node is the same object in every sample |
| impl table | 0 → 16 rows as listen resolved proxies |
| summary | addresses 214 132 → 216 482 |
| backend stopped 20 s | `.unreachable` on health and events (5-s panels), data kept; summary and clusters had not polled yet in that window (30 s / 60 s), so they still showed their last data without the mark — as the contract says: a panel learns of the outage from its own request |
| backend restarted, 65 s | no `.unreachable` anywhere, progress moving, clusters 16 |

Screenshot (backend down): `docs/phase16-live.png`. Page console errors were not captured
(the CDP script read the DOM only).

- Predictions (§9): 11 cards, each ≤ 3 attempts — **hit** (max 3, ui-main); ≥ 2 regenerations,
  one on tsc — **hit** (7, tsc first on 8 variants); 0.5..1.2 regenerations per card — **hit**
  (0.64); 41..121 vitest tests — **hit** (89); Python 448 — **hit**; dist one JS < 40 KB —
  **hit** (10.9 KB); gate `passed` on `.ts` — **hit**.
