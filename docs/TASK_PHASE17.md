# TASK_PHASE17 — make the dashboard a page someone keeps open

Contract: `contour.yaml`, group **dashboard-ui**: Wire Page (the new behavior paragraph "Phase
17 (layout)", new examples 6–9; examples 1–5 unchanged) and the new Function **Style Page**
(`dashboard/src/style.css`, examples 1–8, measured in a real browser). No change in the
renderers, `api.ts`, `feed.ts`, `format.ts`, the scaffold, `package.json` or its lock, the
Python backend or its JSON. Plain TypeScript and CSS, no UI framework, no new dependency.

## 1. Why this

- Phase 16 delivered a correct page (6/6 live ALERT rows without reload, the unreachable
  state, 89 vitest tests) that nobody would keep open: `decks/phase16-tooling/live/*.png`.
  Measured on those screenshots and the phase-16 DOM: **0 panel titles** (four blocks of
  bare numbers), the health strip renders `26104210` `2026-10-02T11:06:03Z` `7 s` `live` with
  **0 px** between them, feed cells have **0 px** gaps (`ALERT11:05:0426104205LaunchToken
  family0.9333seen…`), the origin bars are **0 px** high (spans without display), the
  clusters table separates key and count by **4 px**, the kind filter sits under the last
  table. No card owned a stylesheet (phase 16 §11).
- The page's job, in order: is the listener alive (from across the room), did anything happen
  and what (the event feed, the largest panel), then context (summary, impl clusters).
- The phase-16 DOM already carries everything a stylesheet needs (`data-field`, `data-status`,
  `data-kind`, `data-badge`, `data-bar`, `data-origin`, `data-key`, `.unreachable`). What it
  lacks is structure only `main.ts` can add: titles, a column head, a legend, the filter's
  place, a tab title.
- Ripple spike (§3.0): a crude `main.ts` mutation (sections, titles, select moved into
  `#events`, `import "./style.css"`, `doc.title`) turned **1 of 89** vitest tests red:
  `tests/main.examples.test.ts` "Wire Page ex10 (extra)", which pins the children of `#app`
  as `[health, events, summary, clusters, kind-filter]`. A 40-line throwaway stylesheet over
  the spike passed the browser probe's first version, so the criteria are satisfiable; the
  stricter version (gaps, legend) went red on it per check, as intended.

## 2. Contract

### 2.1. INPUT data shapes the code must build

- The phase-16 DOM, unchanged: `dashboard/src/render/{health,events,summary,clusters}.ts`
  (element types: health and summary fields are `span[data-field]` inside a
  `div[data-role="data"]`; feed rows are `div[data-id][data-kind]` of spans and `a` inside
  `div[data-role="list"]`, ALERT children in the order kind badge, time, block, label, score,
  origin badge, address link; UPGRADE: kind, time, block, address link, arrow span, old link,
  new link; bars are `div[data-bar]` of `span[data-origin][data-count]` with an inline
  `width: <percent>%`; clusters are a `table[data-role="data"]` of `tr[data-key]` with a link
  cell and `td[data-field="members"]`; `.unreachable` is a div appended to the panel).
- `dashboard/src/main.ts` as of phase 16 (polling, timers, `start`), and `statusOf`,
  `formatTime` of `format.ts`.
- The colour values: the dataviz reference palette, dark mode, validated 2026-10-02 with its
  `validate_palette.js` (`--mode dark --surface #1a1a19`): the four origin hues pass the
  lightness band, CVD (worst adjacent ΔE 8.4) and contrast; `unknown` is a deliberate neutral
  (`#6b6a65`, chroma 0.008: it is "no category", 90 % of the bar, and must not compete).
  Contrast on `#1a1a19`: ink-2 9.72, muted 4.85, link 7.03, live 5.19, behind 9.49, stalled
  3.62 (its pill text is white, 4.8:1).

### 2.2. OUTPUT data shapes

- `dist/`: `index.html` and `assets/` with exactly one `.js` and one `.css`, no `.map`.
- The DOM of Wire Page "Phase 17 (layout)": `#app.dash` > four `section.panel` (ids
  unchanged) each starting with `h2.panel-title` and one `p.panel-caption`; in `#events`
  `select#kind-filter`, `[data-field="feed-meta"]`, `.feed-head` (seven spans), then the
  renderer's list; in `#summary` `ul.legend` of five `li[data-legend]`; `document.title`.

### 2.3. Names

- Classes: `dash`, `panel`, `panel-title`, `panel-caption`, `feed-head`, `legend`.
- Attributes: `data-field="feed-meta"`, `data-legend="<origin>"`.
- Titles: "Listener", "Events", "Summary", "Impl clusters". Head texts: "kind", "time UTC",
  "block", "label", "score", "origin", "address".
- Tab title: "ethsc"; "<status> · <progress> · ethsc"; "unreachable · ethsc" (U+00B7).
- Custom properties (Style Page): `--page --surface --ink --ink-2 --muted --grid --link`,
  `--live --behind --stalled --unknown`, `--o-created --o-seen --o-impl --o-fetched
  --o-unknown`, `--k-alert --k-upgrade`.
- `dashboard/tests/look.test.ts` (smoke), `dashboard/tests/look.examples.test.ts` (judge).

### 2.4. What must not break

- Every phase-16 test except the one line of §3.0, and the phase-16 probes of Wire Page 1–5
  (re-run in the acceptance).
- `src/api.ts`, `src/feed.ts`, `src/format.ts`, `src/render/*`, the scaffold, the lock,
  `ethsc/`, `tests/` (Python), byte for byte.

## 3. Acceptance

Built by one script outside the tree (`/tmp/p17/build.py`, which imports the shared steps of
`decks/phase16-tooling/build.py`). Same shape as phase 16: snapshot first, `cd dashboard`,
`npm ci` only when `node_modules` is missing, probes written into `dashboard/probe/<card>/`
and removed on exit, vitest failures filtered to one line each.

### 3.0. Data before the run

- `dashboard/tests/main.examples.test.ts`, "Wire Page ex10 (extra)": the expected children of
  `#app` become `["health", "events", "summary", "clusters"]` (one line; the select moves into
  `#events` by the new contract). Committed by hand as data.

### 3.1. ui-look (main.ts + style.css + smoke test)

1. `tsc --noEmit`.
2. The phase-16 guard over `src/` (Frontend Isolation, AST) and over `tests/look.test.ts`
   (1..5 tests, no `any`, no own stubs).
3. The probe: Wire Page examples 1–9 in vitest (1–5 are the phase-16 probe, unchanged).
4. The own test, then the full vitest suite.
5. `npm run build`: `dist/` = `index.html` + `assets/`; `assets/` = one `.js` + one `.css`; no
   `.map`.
6. **The browser probe** (`layout.mjs`): a loopback server serves `dist/` and the four
   fixtures as the backend; headless Chrome loads the page at 1400 × 900, the script reads
   computed styles and boxes over CDP and checks Style Page examples 1–8 one by one (theme
   colours and contrast, no `@import`/`url()`, grid placement and no sideways scroll at 1400
   and 1024, the status pill in four states, health labels and gaps, feed column alignment
   with the head, `[hidden]` rows without a box, bar heights/colours/widths/labels, legend,
   counter gaps, clusters alignment and link colour, then the backend answers 500 and
   `.unreachable` must be a visible band while the data stays). One line per failed check,
   `Style Page exN: …`. A screenshot of each attempt goes to `/tmp/morph/ui-look-p17/`.
7. `git diff --quiet HEAD` over everything outside the three targets; no untracked file.

### 3.2. ui-look-judge

`tsc`; the guard: 4..16 tests (Wire Page examples 6–9, + 12), no `any`, no own stubs; the
judge file; the full suite; `dashboard/src` and the rest unchanged; no untracked file.

### 3.3. Live acceptance (the orchestrator's, after the run; not a card)

0. `npm ci && tsc --noEmit && vitest run && npm run build`, exit 0; `dist/` as in 3.1.5.
1. The phase-16 live check (`decks/phase16-tooling/live/run.sh`, paths moved to `/tmp/p17`):
   copy of the night db, progress at head−1, `dashboard --static dashboard/dist` + `listen`
   for 10 min, headless Chrome over CDP at 1400 × 900. Required: ALERT rows arrive without
   reload; the browser probe's checks hold on the live page; screenshots at start, 10 min,
   backend down, backend back. The 10-min one goes into §11.

## 4. Constraints

- One card owns `main.ts` and `style.css`: the stylesheet styles the structure `main.ts`
  builds, an invariant across two files (skill rule). Envelope: `main.ts` +40..70 lines over
  206, `style.css` 150..300 new. `variants: 2`.
- The judge (`ui-look-judge`) reads `main.ts` and the Contour, depends on `ui-look`.
- The deck is cut by `mrph plan --component dashboard-ui --judge` and filtered to these two
  cards (`decks/phase17-deck.json`, `mrph deck add`): a plain `--add` would re-cut every
  phase-16 card of the component.
- The browser probe needs `google-chrome` on the operator's machine (present: the phase-16
  live check used it). It binds and connects to 127.0.0.1 only (Offline Tests).

## 5. Techniques already working here

- The phase-16 builder, guard and probe config; the phase-16 CDP live script.
- Attribute-driven styling: `data-status`, `data-kind`, `data-origin` were put in the DOM by
  phase 16 for tests, and serve the stylesheet unchanged.

## 6. Intentionally not specified

- Spacing, font sizes beyond the minimums, radii, the exact grid template, caption texts.
- How `main.ts` organises the new structure (helpers, one builder function).
- Light theme: the page is dark only (an overnight second monitor).

## 7. Out of scope

- Any change to the renderers (row markup, a clusters table head, tooltips on bar segments),
  to `api.ts`, `feed.ts`, `format.ts`, the backend or its JSON.
- A UI framework, a CSS preprocessor, web fonts, icons, any new dependency.
- Charts beyond the two bars; animation; a light theme or a theme toggle; mobile layout below
  1024 px.
- Deploying `dist/` (the operator copies it).

## 8. How to run

`python3 /tmp/p17/build.py` (map entries + `decks/phase17-deck.json`), commit; `mrph deck
clear && mrph deck reset && mrph deck add --file decks/phase17-deck.json && mrph deck check`;
`mrph run --processor glm`. `git checkout master` by hand after the run; push and merge are the
operator's.

## 9. Pre-registration of predictions

- Cards: 2, both accepted, `ui-look` in 2..3 attempts (the browser probe has 8 examples and
  ~40 checks; at least one regeneration on it, most likely on feed column alignment or the
  `[hidden]` trap), the judge in 1..2.
- Tests: 89 + 1..5 smoke + 4..16 judge = **94..110** vitest tests.
- `dist/assets/*.css` 3..10 KB; the JS grows by < 2 KB.
- Live: the browser probe's checks hold on the live page too.

## 10. What to record at the end

Cards, attempts and the first red step of each failed variant (in particular which Style Page
checks failed); minutes; the glm bill; vitest count; CSS size; the live screenshots; hits and
misses against §9.

## 11. Actual

_(after the run)_
