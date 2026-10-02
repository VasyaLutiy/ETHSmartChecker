# Phase 16 deck tooling (dashboard frontend, TypeScript)

Kept so a follow-up deck (e.g. the stylesheet card) can be built the same way after
/tmp is wiped. Source: /tmp/p16 of the phase-16 orchestrator session, 2026-10-02.

- `build.py` — the one acceptance builder for the whole deck: writes the map entries
  of group dashboard-ui and `decks/phase16-scaffold.json`. `PARTS` now points at
  `parts/` next to this file; `ROOT` is still the absolute project path.
- `group.yaml` — the Contour group as cut for the phase.
- `parts/*.probe.ts`, `parts/guard.mjs` — the per-card probes and the ESLint-free guard
  the acceptances inline.
- `acc*.sh` — the generated acceptances exactly as the cards ran them (output of build.py).
- `live/run.sh`, `live/cdp.mjs` — the live check (listen + dashboard + headless Chrome
  screenshots over CDP); `run.sh` still writes to /tmp/p16/live.
- `live/*.png` — the screenshots of §11 (start, up, 10 min, backend down).

Not kept: run logs, the live SQLite copy, stdout/stderr captures.
