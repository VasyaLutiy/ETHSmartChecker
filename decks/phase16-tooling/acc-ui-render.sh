D=/tmp/morph/ui-render-p16; mkdir -p $D; S=$(date +%s)-$$; L=$D/acc-$S.log
cp dashboard/src/render/health.ts $D/0-$S.ts 2>/dev/null
cp dashboard/src/render/events.ts $D/1-$S.ts 2>/dev/null
cp dashboard/src/render/summary.ts $D/2-$S.ts 2>/dev/null
cp dashboard/src/render/clusters.ts $D/3-$S.ts 2>/dev/null
cp dashboard/tests/render.test.ts $D/4-$S.ts 2>/dev/null
(
 set -e
 export NO_COLOR=1 CI=1
cd dashboard
[ -d node_modules ] || npm ci --no-audit --no-fund --prefer-offline > /dev/null 2>&1 || { echo 'npm ci failed'; exit 1; }
P=$PWD/probe/ui-render; rm -rf $P; mkdir -p $P; trap 'rm -rf $P' EXIT
cat > $P/guard.mjs <<'MORPH_GUARD_EOF'
// Phase 16 guard: Frontend Isolation and the test-file rules, on the TypeScript syntax tree.
// node guard.mjs src                         -> every .ts under src/
// node guard.mjs tests <file> <min> <max>    -> one test file
import ts from "typescript";
import fs from "node:fs";
import path from "node:path";

const bad = [];
const HTML = new Set(["innerHTML", "outerHTML", "insertAdjacentHTML"]);
const MAIN_ONLY = new Set(["fetch", "XMLHttpRequest", "WebSocket", "setInterval", "setTimeout",
  "clearInterval", "clearTimeout", "document", "window", "globalThis"]);

function parse(file) {
  return ts.createSourceFile(file, fs.readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true,
    ts.ScriptKind.TS);
}
function line(sf, node) {
  return sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;
}
function report(sf, node, rule) {
  bad.push(`guard: ${sf.fileName}:${line(sf, node)} ${rule}`);
}
function walk(node, fn) {
  fn(node);
  ts.forEachChild(node, (child) => walk(child, fn));
}
// an identifier that refers to a value binding (not a property name, a type, a declared name)
function isValueRef(node) {
  const p = node.parent;
  if (!p) return false;
  if (ts.isPropertyAccessExpression(p) && p.name === node) return false;
  if ((ts.isPropertyAssignment(p) || ts.isPropertyDeclaration(p) || ts.isPropertySignature(p) ||
       ts.isMethodDeclaration(p) || ts.isMethodSignature(p) || ts.isGetAccessor(p) ||
       ts.isSetAccessor(p) || ts.isEnumMember(p)) && p.name === node) return false;
  if (ts.isTypeReferenceNode(p) || ts.isQualifiedName(p) || ts.isTypeQueryNode(p)) return false;
  if ((ts.isParameter(p) || ts.isVariableDeclaration(p) || ts.isFunctionDeclaration(p) ||
       ts.isBindingElement(p)) && p.name === node) return false;
  if (ts.isImportSpecifier(p) || ts.isExportSpecifier(p) || ts.isImportClause(p)) return false;
  if (ts.isLabeledStatement(p) || ts.isBreakOrContinueStatement(p)) return false;
  return true;
}
function srcFiles(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const f = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...srcFiles(f));
    else if (f.endsWith(".ts")) out.push(f);
  }
  return out.sort();
}

function checkSrc() {
  for (const file of srcFiles("src")) {
    const sf = parse(file);
    const rel = file.split(path.sep).join("/");
    const isMain = rel === "src/main.ts";
    const isPure = rel === "src/format.ts" || rel === "src/feed.ts";
    walk(sf, (node) => {
      if (node.kind === ts.SyntaxKind.AnyKeyword) report(sf, node, "explicit any");
      if (ts.isPropertyAccessExpression(node)) {
        const name = node.name.text;
        if (HTML.has(name)) report(sf, node, `${name} (data reaches the DOM by textContent/setAttribute)`);
        if ((name === "write" || name === "writeln") && ts.isIdentifier(node.expression) &&
            node.expression.text === "document") report(sf, node, "document.write");
        if (ts.isIdentifier(node.expression) && node.expression.text === "console")
          report(sf, node, "console (nothing is logged)");
      }
      if (ts.isElementAccessExpression(node) && ts.isStringLiteralLike(node.argumentExpression) &&
          HTML.has(node.argumentExpression.text))
        report(sf, node, `${node.argumentExpression.text} (element access)`);
      if (ts.isIdentifier(node) && !isMain && MAIN_ONLY.has(node.text) && isValueRef(node))
        report(sf, node, `global ${node.text} outside src/main.ts`);
      if (ts.isImportDeclaration(node) || (ts.isExportDeclaration(node) && node.moduleSpecifier)) {
        const spec = node.moduleSpecifier.text;
        if (!spec.startsWith("./") && !spec.startsWith("../"))
          report(sf, node, `import of a package "${spec}" (relative imports only)`);
        if (isPure) report(sf, node, `${rel} imports "${spec}" (format.ts and feed.ts import nothing)`);
      }
      if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword)
        report(sf, node, "dynamic import");
    });
  }
}

function checkTest(file, min, max) {
  if (!fs.existsSync(file)) { bad.push(`guard: ${file} missing`); return; }
  const sf = parse(file);
  let count = 0;
  walk(sf, (node) => {
    if (node.kind === ts.SyntaxKind.AnyKeyword) report(sf, node, "explicit any");
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) &&
        (node.expression.text === "test" || node.expression.text === "it")) count += 1;
    if (ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.expression) &&
        ["test", "it", "describe"].includes(node.expression.text) &&
        ["skip", "only", "todo", "fails"].includes(node.name.text))
      report(sf, node, `${node.expression.text}.${node.name.text}`);
    const declared = (ts.isFunctionDeclaration(node) || ts.isVariableDeclaration(node) ||
      ts.isClassDeclaration(node)) && node.name && ts.isIdentifier(node.name) ? node.name.text : null;
    if (declared && (declared === "fetch" ||
        (!ts.isVariableDeclaration(node) && /^[Ff]ake/.test(declared))))
      report(sf, node, `own stub "${node.name.text}" (stubs come from ./helpers)`);
    if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression) &&
        node.expression.name.text === "stubGlobal")
      report(sf, node, "vi.stubGlobal (pass the fake fetch from ./helpers instead)");
    if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
        ts.isPropertyAccessExpression(node.left) && node.left.name.text === "fetch")
      report(sf, node, "assigns a global fetch");
  });
  if (count < min || count > max)
    bad.push(`guard: ${file} has ${count} test/it calls, expected ${min}..${max}`);
}

const [mode, file, min, max] = process.argv.slice(2);
if (mode === "src") checkSrc();
else if (mode === "tests") checkTest(file, Number(min), Number(max));
else bad.push(`guard: unknown mode ${mode}`);
for (const b of bad) console.log(b);
process.exit(bad.length ? 1 : 0);
MORPH_GUARD_EOF
cat > $P/probe.config.mts <<'MORPH_CONF_EOF'
import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
export default defineConfig({
  root: fileURLToPath(new URL("../..", import.meta.url)),
  test: { environment: "happy-dom", include: ["probe/ui-render/**/*.probe.ts"],
    setupFiles: ["tests/setup.ts"], chaiConfig: { truncateThreshold: 200 } },
});
MORPH_CONF_EOF
cat > $P/ui-render.probe.ts <<'MORPH_PROBE_EOF'
import { test, expect } from "vitest";
import { renderHealth } from "../../src/render/health";
import { renderEvents } from "../../src/render/events";
import { renderSummary } from "../../src/render/summary";
import { renderClusters } from "../../src/render/clusters";
import * as H from "../../tests/helpers";

type Obj = Record<string, any>;
const div = () => document.createElement("div");
const txt = (root: Element, sel: string) => {
  const el = root.querySelector(sel);
  return el === null ? `<no ${sel}>` : (el.textContent ?? "").trim();
};
const unreachable = (root: Element) => Array.from(root.querySelectorAll(".unreachable"))
  .map((e) => (e.textContent ?? "").trim());
const rows = (root: Element) => Array.from(root.querySelectorAll("[data-id]")) as HTMLElement[];
const rowIds = (root: Element) => rows(root).map((r) => r.getAttribute("data-id")).join(",");
const row = (root: Element, id: number) => root.querySelector(`[data-id="${id}"]`) as HTMLElement | null;
const health = () => H.loadFixture("health") as Obj;
const ZERO = { created: 0, fetched: 0, impl: 0, seen: 0, unknown: 0 };
const EMPTY_SUMMARY = { addresses: 0, codes: 0, seeds: 0, origins: { ...ZERO }, implementations_resolved: 0,
  alerts_by_seed: [], recent: { blocks: 300, by_origin: { ...ZERO } } };

test("Render Panels ex1: health strip from the fixture", () => {
  const d = div();
  renderHealth(d, { data: health() as never, error: null });
  expect([txt(d, '[data-field="progress"]'), txt(d, '[data-field="progress_at"]'), txt(d, '[data-field="age"]'),
    txt(d, '[data-field="status"]'), d.querySelector('[data-field="status"]')?.getAttribute("data-status")].join("|"))
    .toBe("26103569|2026-10-02T08:53:15Z|24 s|live|live");
  expect(unreachable(d).length, ".unreachable").toBe(0);
});

test("Render Panels ex2: behind, stalled, unknown", () => {
  const d = div();
  const got: string[] = [];
  for (const sec of [75, 400]) {
    renderHealth(d, { data: { ...health(), seconds_since_progress: sec } as never, error: null });
    got.push(`${txt(d, '[data-field="status"]')}/${txt(d, '[data-field="age"]')}`);
  }
  renderHealth(d, { data: { now: "2026-10-02T08:00:00Z", progress: null, progress_at: null,
    seconds_since_progress: null } as never, error: null });
  got.push(`${txt(d, '[data-field="status"]')}/${txt(d, '[data-field="age"]')}/${txt(d, '[data-field="progress"]')}`);
  expect(got).toStrictEqual(["behind/1 min", "stalled/6 min", "unknown/n/a/"]);
});

test("Render Panels ex3: health unreachable keeps the data", () => {
  const d = div();
  const data = health() as never;
  renderHealth(d, { data, error: "HTTP 500" });
  expect(unreachable(d), "with error").toStrictEqual(["backend unreachable"]);
  expect(txt(d, '[data-field="progress"]'), "data kept").toBe("26103569");
  renderHealth(d, { data, error: null });
  expect(unreachable(d).length, "error cleared").toBe(0);
  renderHealth(d, { data: null, error: "Failed to fetch" });
  expect(unreachable(d), "no data").toStrictEqual(["backend unreachable"]);
});

test("Render Panels ex4: ALERT rows", () => {
  const d = div();
  renderEvents(d, H.fixtureEvents() as never, "ALL", null);
  expect(rowIds(d), "row ids").toBe("8,7,6,5,4,3,2,1");
  expect(rows(d).filter((r) => r.hidden).length, "hidden").toBe(0);
  const r = row(d, 8)!;
  expect([r.getAttribute("data-kind"), txt(r, '[data-badge="kind"]'), txt(r, '[data-badge="origin"]'),
    txt(r, '[data-field="time"]'), txt(r, '[data-field="block"]'), txt(r, '[data-field="label"]'),
    txt(r, '[data-field="score"]')].join("|")).toBe("ALERT|ALERT|seen|08:47:50|26103541|LaunchToken family|1.0000");
  const links = Array.from(r.querySelectorAll("a"));
  expect(links.map((a) => `${a.getAttribute("href")} ${(a.textContent ?? "").trim()} ${a.getAttribute("title")}`))
    .toStrictEqual(["https://etherscan.io/address/0x0be5cfbcbb8a82c8d44af544dd40261b967ab832 0x0be5…b832 " +
      "0x0be5cfbcbb8a82c8d44af544dd40261b967ab832"]);
});

test("Render Panels ex5: an UPGRADE row", () => {
  const d = div();
  renderEvents(d, [H.UPGRADE_EVENT] as never, "ALL", null);
  expect(rowIds(d)).toBe("9");
  const r = row(d, 9)!;
  expect(`${r.getAttribute("data-kind")}|${txt(r, '[data-badge="kind"]')}`).toBe("UPGRADE|UPGRADE");
  expect(Array.from(r.querySelectorAll("a")).map((a) => a.getAttribute("href"))).toStrictEqual([
    "https://etherscan.io/address/0x0c0105334a50db16b51b2911c9956539753a2cf8",
    "https://etherscan.io/address/0x72b971717e088b59f26d4236be222adb6acd393b",
    "https://etherscan.io/address/0xe440cc08a71694c8229323803f59024e3144630e"]);
  expect((r.textContent ?? "").includes("→"), "arrow").toBe(true);
  expect(r.querySelector('[data-badge="origin"]'), "no origin badge").toBeNull();
});

test("Render Panels ex6: rows are kept, not rebuilt", () => {
  const d = div();
  const ev = H.fixtureEvents();
  renderEvents(d, ev as never, "ALL", null);
  const r8 = row(d, 8);
  const nine = { ...ev[0], id: 9 };
  renderEvents(d, [nine, ...ev] as never, "ALL", null);
  expect(rowIds(d), "after adding 9").toBe("9,8,7,6,5,4,3,2,1");
  expect(row(d, 8) === r8, "row 8 is the same node").toBe(true);
  renderEvents(d, [nine, ...ev].filter((e) => e.id >= 3) as never, "ALL", null);
  expect(rowIds(d), "after dropping 2 and 1").toBe("9,8,7,6,5,4,3");
  expect(row(d, 8) === r8, "row 8 still the same node").toBe(true);
});

test("Render Panels ex7: the kind filter hides rows", () => {
  const d = div();
  const all = [H.UPGRADE_EVENT, ...H.fixtureEvents()];
  const vis = () => rows(d).filter((r) => !r.hidden).map((r) => r.getAttribute("data-id")).join(",");
  renderEvents(d, all as never, "UPGRADE", null);
  const u = `${rows(d).length}:${vis()}`;
  renderEvents(d, all as never, "ALERT", null);
  const a = `${rows(d).length}:${vis()}`;
  renderEvents(d, all as never, "ALL", null);
  const l = `${rows(d).length}:${vis()}`;
  expect([u, a, l]).toStrictEqual(["9:9", "9:8,7,6,5,4,3,2,1", "9:9,8,7,6,5,4,3,2,1"]);
});

test("Render Panels ex8: data is text, never markup", () => {
  const d = div();
  const evil = "<img src=x onerror=alert(1)>";
  renderEvents(d, [{ ...H.fixtureEvents()[0], label: evil }] as never, "ALL", "HTTP 503");
  expect(txt(d, '[data-field="label"]'), "label text").toBe(evil);
  expect(d.querySelector("img"), "no img element").toBeNull();
  expect(unreachable(d), "unreachable").toStrictEqual(["backend unreachable"]);
  expect(rowIds(d), "row kept").toBe("8");
});

const seg = (d: Element, bar: string, o: string) => d.querySelector(`[data-bar="${bar}"] [data-origin="${o}"]`) as HTMLElement | null;
test("Render Panels ex9: summary numbers and bars", () => {
  const d = div();
  renderSummary(d, { data: H.loadFixture("summary") as never, error: null });
  expect(["addresses", "codes", "seeds", "implementations_resolved"].map((f) => txt(d, `[data-field="${f}"]`)).join(","))
    .toBe("217009,20374,8,454");
  for (const bar of ["origins", "recent"]) {
    expect(Array.from(d.querySelectorAll(`[data-bar="${bar}"] [data-origin]`)).map((e) => e.getAttribute("data-origin"))
      .join(","), `${bar} segments`).toBe("created,seen,impl,fetched,unknown");
  }
  const s = seg(d, "origins", "seen"), i = seg(d, "recent", "impl");
  expect(`${s?.getAttribute("data-count")} ${s?.style.width}`, "origins seen").toBe("19256 8.9%");
  expect(`${i?.getAttribute("data-count")} ${i?.style.width}`, "recent impl").toBe("387 13.5%");
  expect(`${seg(d, "recent", "seen")?.style.width} ${seg(d, "recent", "unknown")?.style.width}`, "recent seen/unknown")
    .toBe("86% 0%");
});

test("Render Panels ex10: an empty summary has no NaN", () => {
  const d = div();
  renderSummary(d, { data: EMPTY_SUMMARY as never, error: null });
  const widths = Array.from(d.querySelectorAll("[data-origin]")).map((e) => (e as HTMLElement).style.width);
  expect(widths.length, "segments").toBe(10);
  expect(widths.every((w) => w === "0%"), `widths ${widths.join(",")}`).toBe(true);
  expect(d.innerHTML.includes("NaN"), "NaN").toBe(false);
  renderSummary(d, { data: EMPTY_SUMMARY as never, error: "HTTP 500" });
  expect(unreachable(d), "unreachable").toStrictEqual(["backend unreachable"]);
  expect(txt(d, '[data-field="addresses"]'), "kept").toBe("0");
});

test("Render Panels ex11: impl clusters table", () => {
  const d = div();
  const data = H.loadFixture("clusters_impl") as Obj;
  renderClusters(d, { data: data as never, error: null });
  const keys = Array.from(d.querySelectorAll("[data-key]"));
  expect(keys.map((k) => k.getAttribute("data-key")).join(","), "order")
    .toBe(data.clusters.map((c: Obj) => c.key).join(","));
  const first = keys[0];
  expect(`${txt(first, '[data-field="members"]')} ${first.querySelector("a")?.getAttribute("href")}`).toBe(
    "14 https://etherscan.io/address/0x985462c9aa4d6c3ad59ae6e1e9c0c11347ed1598");
  renderClusters(d, { data: data as never, error: "HTTP 500" });
  expect(`${d.querySelectorAll("[data-key]").length} ${unreachable(d).join("")}`).toBe("20 backend unreachable");
});
MORPH_PROBE_EOF
echo '== tsc'; node_modules/.bin/tsc --noEmit
echo '== guard'; node $P/guard.mjs src; node $P/guard.mjs tests tests/render.test.ts 1 5
echo '== probe'; node_modules/.bin/vitest run --config $P/probe.config.mts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== own test'; node_modules/.bin/vitest run tests/render.test.ts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== full'; node_modules/.bin/vitest run  --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
cd ..
git diff --quiet HEAD -- ethsc tests contour.yaml dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts dashboard/index.html dashboard/tests/setup.ts dashboard/tests/helpers.ts dashboard/package-lock.json || { echo "changed outside the targets: $(git diff --name-only HEAD -- ethsc tests contour.yaml dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts dashboard/index.html dashboard/tests/setup.ts dashboard/tests/helpers.ts dashboard/package-lock.json | tr "\n" " ")"; exit 1; }
X=$(git ls-files --others --exclude-standard | grep -vxF -e dashboard/src/render/health.ts -e dashboard/src/render/events.ts -e dashboard/src/render/summary.ts -e dashboard/src/render/clusters.ts -e dashboard/tests/render.test.ts || true); [ -z "$X" ] || { echo "tests left files: $X"; exit 1; }
) > $L 2>&1; rc=$?; cat $L; exit $rc