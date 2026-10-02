#!/usr/bin/env python3
"""Phase 17 deck builder: ui-look (main.ts + style.css) and ui-look-judge.

Reuses the shared steps of the phase-16 builder (decks/phase16-tooling/build.py) so every
acceptance of the dashboard keeps one shape. Writes the map entries (group ui-look, cards
ui-look and ui-look-judge) and decks/phase17-deck.json (the two cards, cut by `mrph plan`
and filtered, for `mrph deck add`).
"""
import importlib.util
import json
import os
import subprocess

ROOT = "/home/john/Documents/Work2026/ETHSmartChecker"
spec = importlib.util.spec_from_file_location("b16", os.path.join(ROOT, "decks/phase16-tooling/build.py"))
b16 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b16)
b16.PARTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parts")

TASK = "docs/TASK_PHASE17.md"
FIX = b16.FIX
SCAFFOLD = b16.SCAFFOLD
FROZEN_UI = ["dashboard/src/api.ts", "dashboard/src/feed.ts", "dashboard/src/format.ts",
             "dashboard/src/render", "dashboard/tests", "dashboard/package-lock.json"]
LOOK = ["dashboard/src/main.ts", "dashboard/src/style.css", "dashboard/tests/look.test.ts"]
JUDGE = "dashboard/tests/look.examples.test.ts"
RENDER = ["dashboard/src/render/health.ts", "dashboard/src/render/events.ts",
          "dashboard/src/render/summary.ts", "dashboard/src/render/clusters.ts"]


def look_acceptance():
    card = "ui-look"
    body = ("cd dashboard\n" + b16.NPM_CI + b16.probe_setup(card, "ui-look.probe.ts")
            + b16.heredoc("$P/layout.mjs", b16.part("layout.mjs"), "MORPH_LAYOUT_EOF")
            + "echo '== tsc'; node_modules/.bin/tsc --noEmit\n"
            + "echo '== guard'; node $P/guard.mjs src; node $P/guard.mjs tests tests/look.test.ts 1 5\n"
            + "echo '== probe'; " + b16.vt("--config $P/probe.config.mts")
            + "echo '== own test'; " + b16.vt("tests/look.test.ts")
            + "echo '== full'; " + b16.vt("")
            + "echo '== build'; rm -rf dist; npm run build > /dev/null\n"
            "[ \"$(ls -A dist | tr '\\n' ' ')\" = 'assets index.html ' ] || { echo \"dist holds: $(ls -A dist | tr '\\n' ' ')\"; exit 1; }\n"
            "[ \"$(ls dist/assets | sed 's/.*\\.//' | sort | tr '\\n' ' ')\" = 'css js ' ] || { echo \"dist/assets holds: $(ls dist/assets | tr '\\n' ' ') (want one .js and one .css)\"; exit 1; }\n"
            "M=$(find dist -name '*.map'); [ -z \"$M\" ] || { echo \"source maps: $M\"; exit 1; }\n"
            + "echo '== layout (headless Chrome, Style Page examples)'; node $P/layout.mjs $D/look-$S.png\n"
            + "cd ..\n" + b16.frozen([b16.FROZEN_PY] + SCAFFOLD + FROZEN_UI) + b16.untracked(LOOK))
    return b16.wrap(card, LOOK, body)


def judge_acceptance():
    card = "ui-look-judge"
    rel = JUDGE[len("dashboard/"):]
    body = ("cd dashboard\n" + b16.NPM_CI + b16.probe_setup(card)
            + "echo '== tsc'; node_modules/.bin/tsc --noEmit\n"
            + f"echo '== guard'; node $P/guard.mjs tests {rel} 4 16\n"
            + "echo '== judge'; " + b16.vt(rel)
            + "echo '== full'; " + b16.vt("")
            + "cd ..\n" + b16.frozen([b16.FROZEN_PY, "dashboard/src"] + SCAFFOLD
                                    + ["dashboard/package-lock.json"])
            + b16.untracked([JUDGE]))
    return b16.wrap(card, [JUDGE], body)


LOOK_INSTRUCTION = (
    f"Read {TASK} FIRST (all of sections 1-4, 6 and 7), then in contour.yaml group dashboard-ui: "
    f"Wire Page (description, behavior with its paragraph \"Phase 17 (layout)\", examples 1-9) and "
    f"Style Page (description, behavior, examples 1-8), the Requirement Frontend Tree and the "
    f"Guardrail Frontend Isolation. Every id, class, data attribute, text and colour value you need "
    f"is there; do not invent names.\n\n"
    f"You own three files. (1) dashboard/src/main.ts: the phase-16 file is in your context; keep its "
    f"polling, timers, error handling and exports exactly as they are (examples 1-5 still hold) and "
    f"add the phase-17 layout: `import \"./style.css\";`, the sections with titles and captions, the "
    f"select inside #events with [data-field=\"feed-meta\"], the static .feed-head and ul.legend, "
    f"class \"dash\" on #app, and doc.title. Use statusOf and formatTime from ./format; no logic of "
    f"your own beyond wiring. (2) dashboard/src/style.css, new: the whole look, plain CSS, styling the "
    f"elements main.ts and the four renderers make (the renderers are in your context and must not "
    f"change: read their element types and data attributes). Use the custom properties of Style Page "
    f"with exactly its values. Aim for a page an analyst leaves on a second monitor all night: calm "
    f"and dense, the status pill and block number readable from across the room, the event feed the "
    f"largest panel, everything else quiet context; small uppercase muted panel titles; thin "
    f"--grid hairlines between feed rows; no shadows, gradients, animation or decoration. Watch the "
    f"traps the browser check measures: a grid or flex display on rows overrides the hidden "
    f"attribute unless you add [hidden] {{ display: none }}; the bars' ::before labels must be "
    f"absolutely positioned so they are not flex items; percentage widths of bar segments must not "
    f"be squeezed (flex: none), and segments as blocks. (3) dashboard/tests/look.test.ts: a smoke "
    f"test of the layout.\n\n{b16.COMMON}\n\n{b16.ISOLATION}\n\n{b16.SMOKE}\n\n"
    f"The acceptance builds the page and measures it in headless Chrome against the four fixtures "
    f"(Style Page examples 1-8): every failed check prints one line \"Style Page exN: ...\".")

JUDGE_INSTRUCTION = (
    f"Read {TASK} FIRST (sections 2.3 and 3.2), then in contour.yaml group dashboard-ui the Function "
    f"Wire Page: its examples 6, 7, 8 and 9 (the phase-17 layout) are the tests you write, one vitest "
    f"`test` per example, named \"Wire Page ex<N>: <short what>\", in example order; you may add up to "
    f"12 more tests for rules of its \"Phase 17 (layout)\" paragraph. Examples 1-5 are already tested "
    f"in tests/main.examples.test.ts and Style Page is measured in a browser by the orchestrator's "
    f"probe: do not test either. Write ONLY {JUDGE}; do not write or modify dashboard/src/main.ts or "
    f"dashboard/src/style.css -- the author of the criterion is not the author of the code. Read the "
    f"code to learn how to call it, never to decide what it should return: the Contour decides.\n\n"
    f"{b16.COMMON}\n\nImport from \"vitest\", start from \"../src/main\" and every stub from "
    f"\"./helpers\" (loadFixture, fixtureEvents, fixtureFetch, fakeFetch, fakeClock, flush); declare "
    f"no fetch or Fake* of your own, do not stub globals (vi.spyOn on console is fine). Give every "
    f"test a fresh <div id=\"app\"> in document.body. No test.skip/only/todo. A test writes no file. "
    f"The global `document` is happy-dom's.")


def main():
    path = os.path.join(ROOT, "morph-map.json")
    with open(path) as fh:
        m = json.load(fh)
    m["groups"]["ui-main"] = []
    m["groups"].pop("ui-main")
    m["groups"]["ui-look"] = ["Wire Page", "Style Page"]
    base = [TASK, "contour.yaml", "dashboard/tests/helpers.ts", "dashboard/tsconfig.json"]
    m["cards"]["ui-look"] = {
        "intent": "patch", "targets": LOOK,
        "context_slice": base + ["dashboard/index.html", "dashboard/src/api.ts", "dashboard/src/feed.ts",
                                 "dashboard/src/format.ts"] + RENDER
                        + ["tests/fixtures/dashboard_health.json", "tests/fixtures/dashboard_events.json",
                           "tests/fixtures/dashboard_summary.json"],
        "depends_on": [], "variants": 2, "max_tokens": 48000, "reasoning_max_tokens": 2500,
        "acceptance": look_acceptance(), "instruction": LOOK_INSTRUCTION}
    m["cards"]["ui-look-judge"] = {
        "intent": "generate", "targets": [JUDGE],
        "context_slice": base + ["dashboard/src/main.ts", "dashboard/src/format.ts",
                                 "tests/fixtures/dashboard_health.json", "tests/fixtures/dashboard_events.json"],
        "depends_on": ["ui-look"], "variants": 2, "max_tokens": 32000, "reasoning_max_tokens": 2500,
        "acceptance": judge_acceptance(), "instruction": JUDGE_INSTRUCTION}
    with open(path, "w") as fh:
        json.dump(m, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    out = subprocess.run([os.path.expanduser("~/Documents/python_venv/venv_mrph/bin/mrph"), "plan", "--spec",
                          "contour.yaml", "--map", "morph-map.json", "--component", "dashboard-ui", "--judge"],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    cards = [c for c in json.loads(out.stdout)["cards"] if c["custom_id"] in ("ui-look", "ui-look-judge")]
    assert [c["custom_id"] for c in cards] == ["ui-look", "ui-look-judge"], [c["custom_id"] for c in cards]
    with open(os.path.join(ROOT, "decks/phase17-deck.json"), "w") as fh:
        json.dump(cards, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("deck:", [(c["custom_id"], c["targets"], c.get("depends_on")) for c in cards])


if __name__ == "__main__":
    main()
