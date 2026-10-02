D=/tmp/morph/ui-scaffold-p16; mkdir -p $D; S=$(date +%s)-$$; L=$D/acc-$S.log
cp dashboard/package.json $D/0-$S.json 2>/dev/null
cp dashboard/tsconfig.json $D/1-$S.json 2>/dev/null
cp dashboard/vite.config.ts $D/2-$S.ts 2>/dev/null
cp dashboard/index.html $D/3-$S.html 2>/dev/null
cp dashboard/tests/setup.ts $D/4-$S.ts 2>/dev/null
cp dashboard/tests/helpers.ts $D/5-$S.ts 2>/dev/null
(
 set -e
 export NO_COLOR=1 CI=1
cd dashboard
echo '== npm install'; npm install --no-audit --no-fund > /dev/null 2>&1 || { echo 'npm install failed:'; npm install --no-audit --no-fund 2>&1 | tail -20; exit 1; }
P=$PWD/probe/ui-scaffold; rm -rf $P; mkdir -p $P; trap 'rm -rf $P' EXIT
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
  test: { environment: "happy-dom", include: ["probe/ui-scaffold/**/*.probe.ts"],
    setupFiles: ["tests/setup.ts"], chaiConfig: { truncateThreshold: 200 } },
});
MORPH_CONF_EOF
cat > $P/ui-scaffold.probe.ts <<'MORPH_PROBE_EOF'
import { test, expect } from "vitest";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as H from "../../tests/helpers";

const EV8 = {
  address: "0x0be5cfbcbb8a82c8d44af544dd40261b967ab832", at: "2026-10-02T08:47:50Z", block: 26103541,
  id: 8, kind: "ALERT", label: "LaunchToken family", new_impl: null, old_impl: null, origin: "seen",
  score: 1.0, seed_address: "0x0312eaa7791b5b15a12157b2a6e01d8e30c8b1b6",
};

async function blocked(fn: () => unknown): Promise<boolean> {
  try { await fn(); return false; } catch { return true; }
}

test("Frontend Tree: package.json pins", () => {
  const p = JSON.parse(fs.readFileSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../package.json"), "utf8"));
  expect(Object.keys(p.dependencies ?? {}).length, "runtime dependencies").toBe(0);
  expect(p.devDependencies, "devDependencies").toStrictEqual({
    "@types/node": "22.20.5", "happy-dom": "20.14.5", typescript: "5.9.3", vite: "7.3.6", vitest: "3.2.7",
  });
  expect(p.scripts?.build, "scripts.build").toBe("vite build");
});

async function why(fn: () => unknown): Promise<string> {
  try { await fn(); return "not blocked"; } catch (e) { return String((e as Error)?.message ?? e); }
}
test("Frontend Tree: tests/setup.ts blocks the network", async () => {
  const got = [
    await why(() => fetch("http://127.0.0.1:9/")),
    await why(() => { const x = new XMLHttpRequest(); x.open("GET", "http://127.0.0.1:9/"); x.send(); }),
    await why(() => new WebSocket("ws://127.0.0.1:9/")),
    await why(() => net.connect(9, "127.0.0.1")),
    await why(() => net.createConnection(9, "127.0.0.1")),
  ].map((m) => m.includes("network blocked in tests") ? "blocked" : m);
  expect(got, "fetch, XMLHttpRequest, WebSocket, net.connect, net.createConnection")
    .toStrictEqual(["blocked", "blocked", "blocked", "blocked", "blocked"]);
});

test("helpers: loadFixture reads the four fixtures fresh", () => {
  const h = H.loadFixture("health") as { progress: number };
  expect(h.progress, "health.progress").toBe(26103569);
  h.progress = 1;
  expect((H.loadFixture("health") as { progress: number }).progress, "a fresh parse each call").toBe(26103569);
  expect((H.loadFixture("events") as { events: unknown[] }).events.length, "events").toBe(8);
  expect((H.loadFixture("summary") as { addresses: number }).addresses, "summary").toBe(217009);
  expect((H.loadFixture("clusters_impl") as { clusters: unknown[] }).clusters.length, "clusters").toBe(20);
});

test("helpers: fixtureEvents, syntheticEvents, UPGRADE_EVENT", () => {
  const a = H.fixtureEvents();
  expect(a.map((e) => e.id).join(","), "fixtureEvents ids").toBe("8,7,6,5,4,3,2,1");
  expect(a[0], "event 8").toStrictEqual(EV8);
  a[0].label = "x";
  expect(H.fixtureEvents()[0].label, "fresh copies").toBe("LaunchToken family");
  const s = H.syntheticEvents([1, 600]);
  expect(s.map((e) => `${e.id}/${e.block}`).join(","), "synthetic id/block").toBe("1/1,600/600");
  expect(s[1], "synthetic = event 8 with id and block").toStrictEqual({ ...EV8, id: 600, block: 600 });
  expect(H.UPGRADE_EVENT, "UPGRADE_EVENT").toStrictEqual({
    id: 9, kind: "UPGRADE", block: 26077729, at: "2026-10-02T08:00:00Z",
    address: "0x0c0105334a50db16b51b2911c9956539753a2cf8", seed_address: null, label: null, score: null,
    origin: null, old_impl: "0x72b971717e088b59f26d4236be222adb6acd393b",
    new_impl: "0xe440cc08a71694c8229323803f59024e3144630e",
  });
});

test("helpers: fakeFetch", async () => {
  const f = H.fakeFetch({
    "/a": { body: { x: 1 } }, "/b": { status: 500, body: { error: "boom" } },
    "/c": new TypeError("Failed to fetch"), "/d": { jsonError: true },
  });
  const a = await f.fetch("/a");
  expect(`${a.ok} ${a.status} ${JSON.stringify(await a.json())}`, "/a").toBe('true 200 {"x":1}');
  const b = await f.fetch("/b");
  expect(`${b.ok} ${b.status}`, "/b").toBe("false 500");
  let c = "resolved";
  try { await f.fetch("/c"); } catch (e) { c = (e as Error).name + ":" + (e as Error).message; }
  expect(c, "/c rejects with the Error").toBe("TypeError:Failed to fetch");
  const d = await f.fetch("/d");
  let dj = "resolved";
  try { await d.json(); } catch (e) { dj = (e as Error).name; }
  expect(dj, "/d json() rejects").toBe("SyntaxError");
  const z = await f.fetch("/zzz");
  expect(`${z.ok} ${z.status} ${JSON.stringify(await z.json())}`, "unknown url").toBe('false 404 {"error":"not found"}');
  f.set("/a", { status: 201, body: 1 });
  const a2 = await f.fetch("/a");
  expect(`${a2.ok} ${a2.status}`, "set").toBe("true 201");
  f.failAll(new Error("down"));
  expect(await blocked(() => f.fetch("/a")), "failAll").toBe(true);
  f.failAll(null);
  expect((await f.fetch("/a")).status, "failAll(null)").toBe(201);
  expect(f.calls.join(" "), "calls").toBe("/a /b /c /d /zzz /a /a /a");
});

test("helpers: fixtureFetch", async () => {
  const f = H.fixtureFetch();
  const h = (await (await f.fetch("/api/health")).json()) as { progress: number };
  expect(h.progress, "health").toBe(26103569);
  const e = (await (await f.fetch("/api/events?after=0&limit=500")).json()) as { last_id: number };
  expect(e.last_id, "events").toBe(8);
  const s = (await (await f.fetch("/api/summary")).json()) as { codes: number };
  expect(s.codes, "summary").toBe(20374);
  const c = (await (await f.fetch("/api/clusters?level=impl&n=20")).json()) as { clusters: unknown[] };
  expect(c.clusters.length, "clusters").toBe(20);
  expect((await f.fetch("/api/events?after=8&limit=500")).status, "other url").toBe(404);
});

test("helpers: fakeClock and flush", async () => {
  const k = H.fakeClock();
  const hits: string[] = [];
  const a = k.setInterval(() => hits.push("a"), 5000);
  const b = k.setInterval(() => hits.push("b"), 30000);
  const c = k.setInterval(() => hits.push("c"), 5000);
  expect(`${a},${b},${c}`, "ids").toBe("1,2,3");
  expect(k.timers.map((t) => t.ms).join(","), "timers").toBe("5000,30000,5000");
  k.fire(5000);
  expect(hits.join(""), "fire(5000)").toBe("ac");
  k.clearInterval(1);
  expect(k.cleared.join(","), "cleared").toBe("1");
  k.fire();
  expect(hits.join(""), "fire() skips cleared").toBe("acbc");
  let done = false;
  Promise.resolve().then(() => 1).then(() => 2).then(() => { done = true; });
  await H.flush();
  expect(done, "flush").toBe(true);
});
MORPH_PROBE_EOF
echo '== tsc'; node_modules/.bin/tsc --noEmit
echo '== strict'; node_modules/.bin/tsc --showConfig | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const c=JSON.parse(s).compilerOptions||{};if(c.strict!==true){console.log("tsconfig: strict is not true");process.exit(1)}})'
echo '== probe'; node_modules/.bin/vitest run --config $P/probe.config.mts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== full'; node_modules/.bin/vitest run --passWithNoTests --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
cd ..
git diff --quiet HEAD -- ethsc tests contour.yaml morph-map.json || { echo "changed outside the targets: $(git diff --name-only HEAD -- ethsc tests contour.yaml morph-map.json | tr "\n" " ")"; exit 1; }
X=$(git ls-files --others --exclude-standard | grep -vxF -e dashboard/package.json -e dashboard/tsconfig.json -e dashboard/vite.config.ts -e dashboard/index.html -e dashboard/tests/setup.ts -e dashboard/tests/helpers.ts -e dashboard/package-lock.json || true); [ -z "$X" ] || { echo "tests left files: $X"; exit 1; }
) > $L 2>&1; rc=$?; cat $L; exit $rc