D=/tmp/morph/ui-main-p16; mkdir -p $D; S=$(date +%s)-$$; L=$D/acc-$S.log
cp dashboard/src/main.ts $D/0-$S.ts 2>/dev/null
cp dashboard/tests/main.test.ts $D/1-$S.ts 2>/dev/null
(
 set -e
 export NO_COLOR=1 CI=1
cd dashboard
[ -d node_modules ] || npm ci --no-audit --no-fund --prefer-offline > /dev/null 2>&1 || { echo 'npm ci failed'; exit 1; }
P=$PWD/probe/ui-main; rm -rf $P; mkdir -p $P; trap 'rm -rf $P' EXIT
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
  test: { environment: "happy-dom", include: ["probe/ui-main/**/*.probe.ts"],
    setupFiles: ["tests/setup.ts"], chaiConfig: { truncateThreshold: 200 } },
});
MORPH_CONF_EOF
cat > $P/ui-main.probe.ts <<'MORPH_PROBE_EOF'
import { test, expect, vi, beforeEach, afterEach } from "vitest";
import { start } from "../../src/main";
import * as H from "../../tests/helpers";

beforeEach(() => {
  document.body.replaceChildren();
  const app = document.createElement("div");
  app.id = "app";
  document.body.appendChild(app);
});
afterEach(() => { vi.restoreAllMocks(); });

const q = (sel: string) => document.querySelector(sel);
const txt = (sel: string) => (q(sel)?.textContent ?? `<no ${sel}>`).trim();
const rows = () => Array.from(document.querySelectorAll("#events [data-id]")) as HTMLElement[];
const URLS = ["/api/health", "/api/events?after=0&limit=500", "/api/summary", "/api/clusters?level=impl&n=20"];

async function page() {
  const f = H.fixtureFetch();
  const k = H.fakeClock();
  const stop = start(document, f.fetch, k);
  await H.flush();
  return { f, k, stop };
}

test("Wire Page ex1: the page and its first requests", async () => {
  const { f, k } = await page();
  for (const id of ["health", "events", "summary", "clusters"])
    expect(q(`#app #${id}`), `#${id} inside #app`).not.toBeNull();
  const sel = q("#app select#kind-filter") as HTMLSelectElement | null;
  expect(sel, "select#kind-filter").not.toBeNull();
  expect(Array.from(sel!.options).map((o) => o.value).join(","), "options").toBe("ALL,ALERT,UPGRADE");
  expect(f.calls, "first requests").toStrictEqual(URLS);
  expect(k.timers.map((t) => t.ms).sort((a, b) => a - b).join(","), "intervals").toBe("5000,5000,30000,60000");
  expect(txt('#health [data-field="progress"]'), "health").toBe("26103569");
  expect(`${rows().length} ${document.querySelectorAll("#clusters [data-key]").length}`, "events/clusters rows").toBe("8 20");
});

test("Wire Page ex2: polling with after=last_id appends", async () => {
  const { f, k } = await page();
  const r8 = document.querySelector('#events [data-id="8"]');
  f.set("/api/events?after=8&limit=500", { body: { events: [{ ...H.fixtureEvents()[0], id: 9, block: 26103550 }], last_id: 9 } });
  k.fire(5000);
  await H.flush();
  expect(f.calls.includes("/api/events?after=8&limit=500"), "after=8 requested").toBe(true);
  expect(rows().map((r) => r.getAttribute("data-id")).join(","), "rows").toBe("9,8,7,6,5,4,3,2,1");
  expect(document.querySelector('#events [data-id="8"]') === r8, "row 8 same node").toBe(true);
  k.fire(5000);
  await H.flush();
  expect(f.calls.includes("/api/events?after=9&limit=500"), "after=9 requested").toBe(true);
});

test("Wire Page ex3: backend down keeps every panel's data", async () => {
  const { f, k } = await page();
  const err = vi.spyOn(console, "error").mockImplementation(() => {});
  f.failAll(new TypeError("Failed to fetch"));
  k.fire();
  await H.flush();
  for (const id of ["health", "events", "summary", "clusters"]) {
    const u = Array.from(document.querySelectorAll(`#${id} .unreachable`)).map((e) => (e.textContent ?? "").trim());
    expect(u, `#${id} .unreachable`).toStrictEqual(["backend unreachable"]);
  }
  expect(`${txt('#health [data-field="progress"]')} ${rows().length} ${document.querySelectorAll("#clusters [data-key]").length}`,
    "kept data").toBe("26103569 8 20");
  expect(err.mock.calls.length, "console.error").toBe(0);
});

test("Wire Page ex4: the kind filter re-renders without fetching", async () => {
  const { f, k } = await page();
  f.set("/api/events?after=8&limit=500", { body: { events: [H.UPGRADE_EVENT], last_id: 9 } });
  k.fire(5000);
  await H.flush();
  const n = f.calls.length;
  const sel = q("#kind-filter") as HTMLSelectElement;
  sel.value = "UPGRADE";
  sel.dispatchEvent(new Event("change"));
  await H.flush();
  expect(f.calls.length, "no new request").toBe(n);
  expect(rows().filter((r) => !r.hidden).map((r) => r.getAttribute("data-id")).join(","), "visible").toBe("9");
  expect(rows().filter((r) => r.hidden).length, "hidden").toBe(8);
});

test("Wire Page ex5: stop clears the four intervals", async () => {
  const { k, stop } = await page();
  stop();
  expect([...k.cleared].sort((a, b) => a - b).join(","), "cleared").toBe("1,2,3,4");
});
MORPH_PROBE_EOF
echo '== tsc'; node_modules/.bin/tsc --noEmit
echo '== guard'; node $P/guard.mjs src; node $P/guard.mjs tests tests/main.test.ts 1 5
echo '== probe'; node_modules/.bin/vitest run --config $P/probe.config.mts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== own test'; node_modules/.bin/vitest run tests/main.test.ts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== full'; node_modules/.bin/vitest run  --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== build'; rm -rf dist; npm run build > /dev/null
[ "$(ls -A dist | tr '\n' ' ')" = 'assets index.html ' ] || { echo "dist holds: $(ls -A dist | tr '\n' ' ')"; exit 1; }
M=$(find dist -name '*.map'); [ -z "$M" ] || { echo "source maps: $M"; exit 1; }
cd ..
git diff --quiet HEAD -- ethsc tests contour.yaml dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts dashboard/index.html dashboard/tests/setup.ts dashboard/tests/helpers.ts dashboard/package-lock.json || { echo "changed outside the targets: $(git diff --name-only HEAD -- ethsc tests contour.yaml dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts dashboard/index.html dashboard/tests/setup.ts dashboard/tests/helpers.ts dashboard/package-lock.json | tr "\n" " ")"; exit 1; }
X=$(git ls-files --others --exclude-standard | grep -vxF -e dashboard/src/main.ts -e dashboard/tests/main.test.ts || true); [ -z "$X" ] || { echo "tests left files: $X"; exit 1; }
) > $L 2>&1; rc=$?; cat $L; exit $rc