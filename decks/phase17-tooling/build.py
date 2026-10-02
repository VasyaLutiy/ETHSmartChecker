#!/usr/bin/env python3
"""Phase 17 deck builder, cut 2: ui-shell (main.ts) -> ui-style (style.css), + ui-shell-judge.

Cut 1 (one card owning main.ts + style.css) failed: 5 of 6 glm answers ran to
finish_reason=length at 48 000 output tokens. Cut 2 splits by file and keeps contour.yaml
(291 KB, ~75 % of the 90 k-token input) out of the slices: the instruction carries the
Contour text of the one Function the card implements, verbatim, read from contour.yaml here.

Reuses the shared steps of decks/phase16-tooling/build.py. Writes the map entries and
decks/phase17-deck.json (three cards cut by `mrph plan`, filtered, for `mrph deck add`).
"""
import importlib.util
import json
import os
import subprocess

import yaml

ROOT = "/home/john/Documents/Work2026/ETHSmartChecker"
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("b16", os.path.join(ROOT, "decks/phase16-tooling/build.py"))
b16 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b16)
b16.PARTS = os.path.join(HERE, "parts")


def snapshot17(card, targets):
    lines = [f"D=/tmp/morph/{card}-p17; mkdir -p $D; S=$(date +%s)-$$; L=$D/acc-$S.log"]
    for n, t in enumerate(targets):
        ext = os.path.splitext(t)[1] or ".txt"
        lines.append(f"cp {t} $D/{n}-$S{ext} 2>/dev/null")
    return "\n".join(lines) + "\n"


b16.snapshot = snapshot17  # wrap() looks the name up in b16 at call time

TASK = "docs/TASK_PHASE17.md"
SCAFFOLD = b16.SCAFFOLD
FROZEN_UI = ["dashboard/src/api.ts", "dashboard/src/feed.ts", "dashboard/src/format.ts",
             "dashboard/src/render", "dashboard/package-lock.json"]
SHELL = ["dashboard/src/main.ts", "dashboard/tests/shell.test.ts"]
STYLE = ["dashboard/src/style.css"]
JUDGE = "dashboard/tests/look.examples.test.ts"
RENDER = ["dashboard/src/render/health.ts", "dashboard/src/render/events.ts",
          "dashboard/src/render/summary.ts", "dashboard/src/render/clusters.ts"]

BUILD = ("echo '== build'; rm -rf dist; npm run build > /dev/null\n"
         "[ \"$(ls -A dist | tr '\\n' ' ')\" = 'assets index.html ' ] || { echo \"dist holds: $(ls -A dist | tr '\\n' ' ')\"; exit 1; }\n"
         "M=$(find dist -name '*.map'); [ -z \"$M\" ] || { echo \"source maps: $M\"; exit 1; }\n")
CSS_ASSET = ("[ \"$(ls dist/assets | sed 's/.*\\.//' | sort | tr '\\n' ' ')\" = 'css js ' ] || "
             "{ echo \"dist/assets holds: $(ls dist/assets | tr '\\n' ' ') (want one .js and one .css)\"; exit 1; }\n")


def contour_text(*names):
    rec = yaml.safe_load(open(os.path.join(ROOT, "contour.yaml")))
    group = [g for g in rec["System"]["groups"] if g["name"] == "dashboard-ui"][0]
    parts = []
    for f in group["functions"]:
        if f["name"] in names:
            parts.append(f"### Function {f['name']}\n\n{f['description'].strip()}\n\n"
                         f"Behavior: {f['behavior'].strip()}\n\nExamples:\n" + "\n".join(
                             f"{i}. given {e['given'].strip()}; when {e['when'].strip()}; then {e['then'].strip()}"
                             for i, e in enumerate(f.get("examples", []), 1)))
    for kind in ("Requirement", "Guardrail"):
        for d in rec.get(kind, []):
            if d["name"] in ("Frontend Tree", "Frontend Isolation"):
                parts.append(f"### {kind} {d['name']}\n\n{d['description'].strip()}")
    return "\n\n".join(parts)


def shell_acceptance():
    card = "ui-shell"
    body = ("cd dashboard\n" + b16.NPM_CI + b16.probe_setup(card, "ui-look.probe.ts")
            + "echo '== tsc'; node_modules/.bin/tsc --noEmit\n"
            + "echo '== guard'; node $P/guard.mjs src; node $P/guard.mjs tests tests/shell.test.ts 1 5\n"
            + "echo '== probe (Wire Page 1-9)'; " + b16.vt("--config $P/probe.config.mts")
            + "echo '== own test'; " + b16.vt("tests/shell.test.ts")
            + "echo '== full'; " + b16.vt("")
            + BUILD
            + "cd ..\n" + b16.frozen([b16.FROZEN_PY, "dashboard/tests", "dashboard/src/style.css"]
                                    + SCAFFOLD + FROZEN_UI) + b16.untracked(SHELL))
    return b16.wrap(card, SHELL, body)


def style_acceptance():
    card = "ui-style"
    body = ("cd dashboard\n" + b16.NPM_CI + b16.probe_setup(card)
            + b16.heredoc("$P/layout.mjs", b16.part("layout.mjs"), "MORPH_LAYOUT_EOF")
            + BUILD + CSS_ASSET
            + "echo '== layout (headless Chrome, Style Page examples 1-8)'; node $P/layout.mjs $D/look-$S.png\n"
            + "echo '== tsc'; node_modules/.bin/tsc --noEmit\n"
            + "echo '== full'; " + b16.vt("")
            + "cd ..\n" + b16.frozen([b16.FROZEN_PY, "dashboard/tests", "dashboard/src/main.ts"]
                                    + SCAFFOLD + FROZEN_UI) + b16.untracked(STYLE))
    return b16.wrap(card, STYLE, body)


def judge_acceptance():
    card = "ui-shell-judge"
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


SHELL_INSTRUCTION = (
    f"Read {TASK} sections 1, 2 and 7 FIRST. The contract of your file is below, verbatim from "
    f"contour.yaml.\n\n" + contour_text("Wire Page") + "\n\n"
    f"## Your task\n\nYou own exactly two files. (1) dashboard/src/main.ts: the phase-16 file is in your "
    f"context. Keep its polling, timers, error handling and exports exactly as they are (examples 1-5 "
    f"still hold) and add only the paragraph \"Phase 17 (layout)\": `import \"./style.css\";` (the file "
    f"exists; another card writes its rules), #app class \"dash\", the four sections with h2.panel-title "
    f"and p.panel-caption, the select and [data-field=\"feed-meta\"] and the static .feed-head inside "
    f"#events, the static ul.legend inside #summary, and document.title (set to \"ethsc\" at once in "
    f"start, then after every health poll). Note example 9: the title is \"ethsc\" synchronously, "
    f"before any await. Use statusOf and formatTime from ./format. (2) dashboard/tests/shell.test.ts: "
    f"a smoke test. Write each file once, completely, with no alternatives and no commentary outside "
    f"the files.\n\n{b16.COMMON}\n\n{b16.ISOLATION}\n\n{b16.SMOKE}")

STYLE_INSTRUCTION = (
    f"Read {TASK} sections 1, 2 and 7 FIRST. The contract of your file is below, verbatim from "
    f"contour.yaml.\n\n" + contour_text("Style Page") + "\n\n"
    f"## Your task\n\nYou own exactly one file: dashboard/src/style.css (now a one-line placeholder; "
    f"main.ts already imports it). Plain CSS, 150 to 300 lines, written once, completely, with no "
    f"alternatives and no commentary outside the file. The DOM you style is made by "
    f"dashboard/src/main.ts and the four renderers in dashboard/src/render/ (all in your context: read "
    f"their element types, classes and data attributes; do not change them). Write exactly these rule "
    f"groups, in this order:\n"
    f"1. :root with every custom property of the behavior, with exactly its values.\n"
    f"2. html/body: margin 0, background var(--page), colour var(--ink-2), font system-ui at 13 px.\n"
    f"3. #app.dash: a CSS grid, #health across the top, #events in a left column of about two "
    f"thirds, #summary over #clusters on the right; min-width: 0 on the panels; it must not scroll "
    f"sideways at 1024 px.\n"
    f"4. section.panel (background var(--surface), padding, no shadow), .panel-title (small, "
    f"uppercase, var(--muted)), .panel-caption (small, var(--muted)).\n"
    f"5. The health strip: its data box as a flex row with gap 16 px; [data-field=\"progress\"] 24 px "
    f"var(--ink); the status pill per data-status (live, behind, stalled, unknown) with dark text "
    f"#0d0d0d except stalled with #ffffff, 24 px; ::before labels \"block\", \"at\", \"age\".\n"
    f"6. The feed: .feed-head and the ALERT rows share one grid-template-columns (kind, time, block, "
    f"label, score, origin, address) with a column gap; UPGRADE rows their own template; cells "
    f"white-space nowrap with text-overflow ellipsis; `#events [hidden] {{ display: none; }}`; a "
    f"var(--grid) hairline between rows; kind badge coloured by data-kind (--k-alert, --k-upgrade), "
    f"origin badge with a left border in its origin colour; tabular-nums on time, block, score.\n"
    f"7. The summary: its data box as a flex row with gap 16 px for the four counters with their "
    f"::before labels; each [data-bar] display flex, height 10 px, position relative, margin-top for "
    f"its label; segments display block, flex none, background by data-origin; the bar labels as "
    f"absolutely positioned ::before; ul.legend as one flex line, list-style none, li::before swatches "
    f"by data-legend.\n"
    f"8. The clusters table: cell padding, members right-aligned with tabular-nums and padding-left "
    f"16 px.\n"
    f"9. Links var(--link), no underline until hover; .unreachable as a band: background "
    f"var(--stalled), colour #ffffff, padding.\n"
    f"No @import, no url(), no web font, no animation, no gradient, no shadow. The acceptance builds "
    f"the page and measures it in headless Chrome against the four fixtures (Style Page examples "
    f"1-8): every failed check prints one line \"Style Page exN: ...\".")

JUDGE_INSTRUCTION = (
    f"Read {TASK} sections 2.3 and 3.2 FIRST. The contract is below, verbatim from contour.yaml.\n\n"
    + contour_text("Wire Page") + "\n\n"
    f"## Your task\n\nExamples 6, 7, 8 and 9 of Wire Page (the phase-17 layout) are the tests you write, "
    f"one vitest `test` per example, named \"Wire Page ex<N>: <short what>\", in example order; you may "
    f"add up to 12 more tests for rules of its \"Phase 17 (layout)\" paragraph. Examples 1-5 are already "
    f"tested in tests/main.examples.test.ts: do not repeat them. Write ONLY {JUDGE}; do not write or "
    f"modify dashboard/src/main.ts -- the author of the criterion is not the author of the code. Read "
    f"the code to learn how to call it, never to decide what it should return: the contract decides."
    f"\n\n{b16.COMMON}\n\nImport from \"vitest\", start from \"../src/main\" and every stub from "
    f"\"./helpers\" (loadFixture, fixtureEvents, fixtureFetch, fakeFetch, fakeClock, flush); declare no "
    f"fetch or Fake* of your own, do not stub globals (vi.spyOn on console is fine). Give every test a "
    f"fresh <div id=\"app\"> in document.body. No test.skip/only/todo. A test writes no file. The "
    f"global `document` is happy-dom's.")


def main():
    path = os.path.join(ROOT, "morph-map.json")
    with open(path) as fh:
        m = json.load(fh)
    m["groups"].pop("ui-look", None)
    m["groups"].pop("ui-main", None)
    m["groups"]["ui-shell"] = ["Wire Page"]
    m["groups"]["ui-style"] = ["Style Page"]
    for old in ("ui-look", "ui-look-judge"):
        m["cards"].pop(old, None)
    base = [TASK, "dashboard/tests/helpers.ts", "dashboard/tsconfig.json"]
    m["cards"]["ui-shell"] = {
        "intent": "patch", "targets": SHELL,
        "context_slice": base + ["dashboard/src/api.ts", "dashboard/src/format.ts", "dashboard/src/feed.ts"]
                        + RENDER + ["tests/fixtures/dashboard_health.json"],
        "depends_on": [], "variants": 2, "max_tokens": 48000, "reasoning_max_tokens": 2500,
        "acceptance": shell_acceptance(), "instruction": SHELL_INSTRUCTION}
    m["cards"]["ui-style"] = {
        "intent": "patch", "targets": STYLE,
        "context_slice": [TASK, "dashboard/index.html", "dashboard/src/main.ts"] + RENDER,
        "depends_on": ["ui-shell"], "variants": 2, "max_tokens": 48000, "reasoning_max_tokens": 2500,
        "acceptance": style_acceptance(), "instruction": STYLE_INSTRUCTION}
    m["cards"]["ui-shell-judge"] = {
        "intent": "generate", "targets": [JUDGE],
        "context_slice": base + ["dashboard/src/main.ts", "dashboard/src/format.ts",
                                 "tests/fixtures/dashboard_health.json", "tests/fixtures/dashboard_events.json"],
        "depends_on": ["ui-shell"], "variants": 2, "max_tokens": 32000, "reasoning_max_tokens": 2500,
        "acceptance": judge_acceptance(), "instruction": JUDGE_INSTRUCTION}
    with open(path, "w") as fh:
        json.dump(m, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    out = subprocess.run([os.path.expanduser("~/Documents/python_venv/venv_mrph/bin/mrph"), "plan", "--spec",
                          "contour.yaml", "--map", "morph-map.json", "--component", "dashboard-ui", "--judge"],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    want = ("ui-shell", "ui-style", "ui-shell-judge")
    cards = [c for c in json.loads(out.stdout)["cards"] if c["custom_id"] in want]
    assert sorted(c["custom_id"] for c in cards) == sorted(want), [c["custom_id"] for c in cards]
    with open(os.path.join(ROOT, "decks/phase17-deck.json"), "w") as fh:
        json.dump(cards, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    for c in cards:
        print(c["custom_id"], c["targets"], c.get("depends_on"), "instr", len(c["instruction"]),
              "slice", c["context_slice"])


if __name__ == "__main__":
    main()
