#!/usr/bin/env python3
"""Phase 16 deck builder: the map entries of group dashboard-ui and the scaffold card.

One builder for the whole deck: every acceptance is built from the same steps here.
Writes morph-map.json (groups + cards for ui-*), decks/phase16-scaffold.json.
"""
import json
import os

ROOT = "/home/john/Documents/Work2026/ETHSmartChecker"
PARTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parts")  # was /tmp/p16/parts
TASK = "docs/TASK_PHASE16.md"
FIX = ["tests/fixtures/dashboard_health.json", "tests/fixtures/dashboard_events.json",
       "tests/fixtures/dashboard_summary.json", "tests/fixtures/dashboard_clusters_impl.json"]
SCAFFOLD = ["dashboard/package.json", "dashboard/tsconfig.json", "dashboard/vite.config.ts",
            "dashboard/index.html", "dashboard/tests/setup.ts", "dashboard/tests/helpers.ts"]
FROZEN_PY = "ethsc tests contour.yaml"


def part(name):
    with open(os.path.join(PARTS, name)) as fh:
        return fh.read()


def heredoc(path, body, tag):
    assert tag not in body
    return f"cat > {path} <<'{tag}'\n{body.rstrip()}\n{tag}\n"


def probe_config(card):
    return (
        'import { defineConfig } from "vitest/config";\n'
        'import { fileURLToPath } from "node:url";\n'
        'export default defineConfig({\n'
        '  root: fileURLToPath(new URL("../..", import.meta.url)),\n'
        f'  test: {{ environment: "happy-dom", include: ["probe/{card}/**/*.probe.ts"],\n'
        '    setupFiles: ["tests/setup.ts"], chaiConfig: { truncateThreshold: 200 } },\n'
        '});\n')


def snapshot(card, targets):
    lines = [f"D=/tmp/morph/{card}-p16; mkdir -p $D; S=$(date +%s)-$$; L=$D/acc-$S.log"]
    for n, t in enumerate(targets):
        ext = os.path.splitext(t)[1] or ".txt"
        lines.append(f"cp {t} $D/{n}-$S{ext} 2>/dev/null")
    return "\n".join(lines) + "\n"


def untracked(targets, extra=()):
    keep = " ".join(f"-e {t}" for t in list(targets) + list(extra))
    return ('X=$(git ls-files --others --exclude-standard | grep -vxF ' + keep + ' || true); '
            '[ -z "$X" ] || { echo "tests left files: $X"; exit 1; }\n')


def frozen(paths):
    p = " ".join(paths)
    return (f'git diff --quiet HEAD -- {p} || {{ echo "changed outside the targets: '
            f'$(git diff --name-only HEAD -- {p} | tr "\\n" " ")"; exit 1; }}\n')


def probe_setup(card, probe_file=None):
    s = (f"P=$PWD/probe/{card}; rm -rf $P; mkdir -p $P; trap 'rm -rf $P' EXIT\n"
         + heredoc(f"$P/guard.mjs", part("guard.mjs"), "MORPH_GUARD_EOF")
         + heredoc(f"$P/probe.config.mts", probe_config(card), "MORPH_CONF_EOF"))
    if probe_file:
        s += heredoc(f"$P/{card}.probe.ts", part(probe_file), "MORPH_PROBE_EOF")
    return s


def vt(args):
    return (f"node_modules/.bin/vitest run {args} --reporter=dot > $P/vt.log 2>&1 || "
            "{ grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }\n")


NPM_CI = "[ -d node_modules ] || npm ci --no-audit --no-fund --prefer-offline > /dev/null 2>&1 || { echo 'npm ci failed'; exit 1; }\n"


def wrap(card, targets, body):
    return (snapshot(card, targets) + "(\n set -e\n export NO_COLOR=1 CI=1\n" + body + ") > $L 2>&1; rc=$?; cat $L; exit $rc")


def code_acceptance(card, targets, own_test, build=False):
    rel_test = own_test[len("dashboard/"):]
    body = ("cd dashboard\n" + NPM_CI + probe_setup(card, f"{card}.probe.ts")
            + "echo '== tsc'; node_modules/.bin/tsc --noEmit\n"
            + "echo '== guard'; node $P/guard.mjs src; node $P/guard.mjs tests " + rel_test + " 1 5\n"
            + "echo '== probe'; " + vt("--config $P/probe.config.mts")
            + "echo '== own test'; " + vt(rel_test)
            + "echo '== full'; " + vt(""))
    if build:
        body += ("echo '== build'; rm -rf dist; npm run build > /dev/null\n"
                 "[ \"$(ls -A dist | tr '\\n' ' ')\" = 'assets index.html ' ] || { echo \"dist holds: $(ls -A dist | tr '\\n' ' ')\"; exit 1; }\n"
                 "M=$(find dist -name '*.map'); [ -z \"$M\" ] || { echo \"source maps: $M\"; exit 1; }\n")
    body += "cd ..\n" + frozen([FROZEN_PY] + SCAFFOLD + ["dashboard/package-lock.json"]) + untracked(targets)
    return wrap(card, targets, body)


def judge_acceptance(card, target, lo, hi):
    rel = target[len("dashboard/"):]
    body = ("cd dashboard\n" + NPM_CI + probe_setup(card)
            + "echo '== tsc'; node_modules/.bin/tsc --noEmit\n"
            + f"echo '== guard'; node $P/guard.mjs tests {rel} {lo} {hi}\n"
            + "echo '== judge'; " + vt(rel)
            + "echo '== full'; " + vt("")
            + "cd ..\n" + frozen([FROZEN_PY, "dashboard/src"] + SCAFFOLD + ["dashboard/package-lock.json"])
            + untracked([target]))
    return wrap(card, [target], body)


def scaffold_acceptance(targets):
    body = ("cd dashboard\n"
            "echo '== npm install'; npm install --no-audit --no-fund > /dev/null 2>&1 || { echo 'npm install failed:'; npm install --no-audit --no-fund 2>&1 | tail -20; exit 1; }\n"
            + probe_setup("ui-scaffold", "scaffold.probe.ts")
            + "echo '== tsc'; node_modules/.bin/tsc --noEmit\n"
            + "echo '== strict'; node_modules/.bin/tsc --showConfig | node -e 'let s=\"\";process.stdin.on(\"data\",d=>s+=d).on(\"end\",()=>{const c=JSON.parse(s).compilerOptions||{};if(c.strict!==true){console.log(\"tsconfig: strict is not true\");process.exit(1)}})'\n"
            + "echo '== probe'; " + vt("--config $P/probe.config.mts")
            + "echo '== full'; " + vt("--passWithNoTests")
            + "cd ..\n" + frozen([FROZEN_PY, "morph-map.json"])
            + untracked(targets, ["dashboard/package-lock.json"]))
    return wrap("ui-scaffold", targets, body)


COMMON = (
    "You write TypeScript for dashboard/, a Node project of its own inside a Python repository "
    "(package.json, tsconfig.json and vite.config.ts are in dashboard/; every command runs there). "
    "TypeScript strict, ESM imports with relative paths and no file extension (\"./api\"), no `any` "
    "(use `unknown` and narrow). ")
SMOKE = (
    "Your own test file is smoke only: 1 to 5 vitest `test(...)` calls, comparing scalars and short "
    "values with `toBe`, never `toEqual` on fixture-sized arrays or objects. Import `test`/`expect` from "
    "\"vitest\" and every stub (fixtures, fake fetch, fake clock, synthetic events) from \"./helpers\"; "
    "declare no fetch or Fake* of your own and do not stub globals. A test writes no file and opens no "
    "connection. Completeness is judged by a probe built from the Contour examples, not by your test.")
ISOLATION = (
    "Guardrail Frontend Isolation is checked on the syntax tree of every file in dashboard/src: no "
    "explicit any; data reaches the DOM only through textContent and setAttribute (no HTML-string "
    "properties); no console; the globals fetch, XMLHttpRequest, WebSocket, the timer functions, "
    "document, window and globalThis are named only in src/main.ts; src/format.ts and src/feed.ts "
    "import nothing; only relative imports.")


def code_instruction(fn, module_desc, own_test, extra=""):
    return (
        f"Read {TASK} FIRST (sections 2.1-2.4, 4 and 7), then in contour.yaml group dashboard-ui the "
        f"Function {fn} (description, behavior, every example), the Requirement Frontend Tree and the "
        f"Guardrail Frontend Isolation. Every name, selector and URL you need is there; do not invent "
        f"names, keys or files.\n\n{COMMON}\n\nWrite {module_desc}, and the smoke test {own_test}. "
        f"{extra}\n\n{ISOLATION}\n\n{SMOKE}")


def judge_instruction(fn, n, target, modules):
    return (
        f"Read {TASK} FIRST (sections 2.3 and 3.3), then in contour.yaml group dashboard-ui the "
        f"Function {fn}: its {n} examples are the tests you write, one vitest `test` per example, "
        f"named \"{fn} ex<N>: <short what>\", in example order; you may add up to 12 more tests for "
        f"rules of its behavior paragraph. Write ONLY {target}; do not write or modify {modules} -- "
        f"the author of the criterion is not the author of the code. Read the code to learn how to "
        f"call it, never to decide what it should return: the Contour decides.\n\n{COMMON}\n\n"
        f"Import from \"vitest\", the module(s) under test by relative path (\"../src/...\") and every "
        f"stub from \"./helpers\" (loadFixture, fixtureEvents, syntheticEvents, UPGRADE_EVENT, "
        f"fakeFetch, fixtureFetch, fakeClock, flush); declare no fetch or Fake* of your own, do not "
        f"stub globals (spying on console with vi.spyOn is fine). No test.skip/only/todo. Values "
        f"come from the fixtures or the example text verbatim. A test writes no file. The global "
        f"`document` is happy-dom's (vitest environment happy-dom).")


SCAFFOLD_INSTRUCTION = (
    f"Read {TASK} FIRST: sections 2.3 (tests/setup.ts and tests/helpers.ts: every signature there is "
    f"the contract), 2.4, 3.1 and 4; then in contour.yaml the Requirement Frontend Tree and, in group "
    f"dashboard-ui, the Function descriptions (the module layout) and Merge Feed example 5 (the "
    f"UPGRADE event). The four fixtures are in your context.\n\n"
    f"You write the scaffold of dashboard/, a Node project of its own inside a Python repository, "
    f"six files and nothing else:\n"
    f"- dashboard/package.json: name \"ethsc-dashboard\", private true, type \"module\", scripts "
    f"{{\"build\": \"vite build\", \"test\": \"vitest run\"}}, no dependencies, devDependencies exactly "
    f"{{\"@types/node\": \"22.20.5\", \"happy-dom\": \"20.14.5\", \"typescript\": \"5.9.3\", \"vite\": "
    f"\"7.3.6\", \"vitest\": \"3.2.7\"}} (exact versions, no ^ or ~).\n"
    f"- dashboard/tsconfig.json: strict true, noEmit true, target and lib ES2022 plus DOM and "
    f"DOM.Iterable, module ESNext, moduleResolution bundler, types [\"vite/client\", \"node\"], "
    f"skipLibCheck true, include [\"src\", \"tests\"].\n"
    f"- dashboard/vite.config.ts: defineConfig from \"vitest/config\"; build {{outDir \"dist\", "
    f"sourcemap false, emptyOutDir true}}; test {{environment \"happy-dom\", include "
    f"[\"tests/**/*.test.ts\"], setupFiles [\"tests/setup.ts\"], chaiConfig {{truncateThreshold "
    f"200}}}}. No public directory.\n"
    f"- dashboard/index.html: a minimal HTML5 page titled \"ethsc dashboard\" with <div id=\"app\"> "
    f"and <script type=\"module\" src=\"/src/main.ts\"></script> (src/ is written by later cards).\n"
    f"- dashboard/tests/setup.ts: replaces globalThis.fetch, XMLHttpRequest and WebSocket, and the "
    f"connect and createConnection of the default export of \"node:net\", with functions that throw "
    f"Error(\"network blocked in tests\"); a test that needs fetch passes a fake from helpers.\n"
    f"- dashboard/tests/helpers.ts: exactly the exports of section 2.3, behaving as written there. "
    f"Read the fixtures with node:fs at path.resolve(path.dirname(fileURLToPath(import.meta.url)), "
    f"\"../../tests/fixtures/dashboard_<name>.json\") (fileURLToPath from node:url, given the string "
    f"import.meta.url; never new URL(...): under happy-dom the global URL is not Node's and node:fs "
    f"refuses it); FixtureEvent is declared here (helpers imports nothing from src/). "
    f"fixtureEvents and syntheticEvents return fresh objects every call; syntheticEvents copies the "
    f"fixture event with id 8 and sets id and block to each i.\n\n"
    f"{COMMON}\n\nWrite no test file: the scaffold is checked by a probe. Do not write "
    f"package-lock.json: the acceptance runs npm install, which writes it.")


def main():
    with open(os.path.join(ROOT, "morph-map.json")) as fh:
        m = json.load(fh)

    m["groups"].update({
        "ui-api": ["Fetch Endpoints"], "ui-format": ["Format Values"], "ui-feed": ["Merge Feed"],
        "ui-render": ["Render Panels"], "ui-main": ["Wire Page"]})

    helpers = "dashboard/tests/helpers.ts"
    base = [TASK, "contour.yaml", helpers, "dashboard/tsconfig.json"]
    render_files = ["dashboard/src/render/health.ts", "dashboard/src/render/events.ts",
                    "dashboard/src/render/summary.ts", "dashboard/src/render/clusters.ts"]
    cards = {}

    def code(card, targets, slice_, deps, variants, mt, fn, desc, extra="", build=False):
        own = targets[-1]
        cards[card] = {
            "intent": "generate", "targets": targets, "context_slice": slice_, "depends_on": deps,
            "variants": variants, "max_tokens": mt, "reasoning_max_tokens": 2500,
            "acceptance": code_acceptance(card, targets, own, build),
            "instruction": code_instruction(fn, desc, own, extra)}

    def judge(card, fn, n, slice_, deps, modules):
        target = f"dashboard/tests/{card[:-len('-judge')].replace('ui-', '')}.examples.test.ts"
        cards[card] = {
            "intent": "generate", "targets": [target], "context_slice": slice_, "depends_on": deps,
            "variants": 2, "max_tokens": 48000, "reasoning_max_tokens": 2500,
            "acceptance": judge_acceptance(card, target, n, n + 12),
            "instruction": judge_instruction(fn, n, target, modules)}

    code("ui-api", ["dashboard/src/api.ts", "dashboard/tests/api.test.ts"], base + FIX, [], 2, 48000,
         "Fetch Endpoints", "dashboard/src/api.ts (every type, the four parsers, the four fetchers)",
         "The fetchers take the fetch function as a parameter and never name the global fetch.")
    code("ui-format", ["dashboard/src/format.ts", "dashboard/tests/format.test.ts"],
         base + ["tests/fixtures/dashboard_summary.json"], [], 1, 32000,
         "Format Values", "dashboard/src/format.ts (pure functions; the module imports nothing)")
    code("ui-feed", ["dashboard/src/feed.ts", "dashboard/tests/feed.test.ts"],
         base + ["tests/fixtures/dashboard_events.json"], [], 1, 32000,
         "Merge Feed", "dashboard/src/feed.ts (pure and generic; the module imports nothing)")
    code("ui-render", render_files + ["dashboard/tests/render.test.ts"],
         base + ["dashboard/src/api.ts", "dashboard/src/format.ts"] + FIX, ["ui-api", "ui-format"], 2, 56000,
         "Render Panels",
         "the four modules dashboard/src/render/health.ts, events.ts, summary.ts and clusters.ts (types "
         "imported with `import type` from \"../api\", text from \"../format\")",
         "Create every element with root.ownerDocument.createElement, never the global document.")
    code("ui-main", ["dashboard/src/main.ts", "dashboard/tests/main.test.ts"],
         base + ["dashboard/index.html", "dashboard/src/api.ts", "dashboard/src/feed.ts",
                 "dashboard/src/format.ts"] + render_files + ["tests/fixtures/dashboard_events.json"],
         ["ui-api", "ui-feed", "ui-render"], 2, 48000,
         "Wire Page", "dashboard/src/main.ts (wiring and timers only: it calls api, feed and render)",
         "The timers come from the clock parameter, whose default wraps the global setInterval and "
         "clearInterval; the self-start at the end of the module is guarded by "
         "import.meta.env.MODE !== \"test\". The page must also build: `npm run build` runs in the "
         "acceptance.", build=True)

    judge("ui-api-judge", "Fetch Endpoints", 8, base + ["dashboard/src/api.ts"] + FIX, ["ui-api"],
          "dashboard/src/api.ts")
    judge("ui-format-judge", "Format Values", 7, base + ["dashboard/src/format.ts",
          "tests/fixtures/dashboard_summary.json"], ["ui-format"], "dashboard/src/format.ts")
    judge("ui-feed-judge", "Merge Feed", 5, base + ["dashboard/src/feed.ts",
          "tests/fixtures/dashboard_events.json"], ["ui-feed"], "dashboard/src/feed.ts")
    judge("ui-render-judge", "Render Panels", 11, base + ["dashboard/src/api.ts", "dashboard/src/format.ts"]
          + render_files + FIX, ["ui-render"], "dashboard/src/render/*.ts")
    judge("ui-main-judge", "Wire Page", 5, base + ["dashboard/src/main.ts", "dashboard/src/api.ts"]
          + render_files + ["tests/fixtures/dashboard_events.json"], ["ui-main"], "dashboard/src/main.ts")

    m["cards"].update(cards)
    with open(os.path.join(ROOT, "morph-map.json"), "w") as fh:
        json.dump(m, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    scaffold = {
        "custom_id": "ui-scaffold", "intent": "generate", "targets": SCAFFOLD,
        "context_slice": [TASK, "contour.yaml"] + FIX, "depends_on": [],
        "variants": 2, "max_tokens": 32000, "reasoning_max_tokens": 2500,
        "acceptance": scaffold_acceptance(SCAFFOLD), "instruction": SCAFFOLD_INSTRUCTION}
    with open(os.path.join(ROOT, "decks/phase16-scaffold.json"), "w") as fh:
        json.dump([scaffold], fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("cards:", ", ".join(["ui-scaffold"] + list(cards)))


if __name__ == "__main__":
    main()
