D=/tmp/morph/ui-api-p16; mkdir -p $D; S=$(date +%s)-$$; L=$D/acc-$S.log
cp dashboard/src/api.ts $D/0-$S.ts 2>/dev/null
cp dashboard/tests/api.test.ts $D/1-$S.ts 2>/dev/null
(
 set -e
 export NO_COLOR=1 CI=1
cd dashboard
[ -d node_modules ] || npm ci --no-audit --no-fund --prefer-offline > /dev/null 2>&1 || { echo 'npm ci failed'; exit 1; }
P=$PWD/probe/ui-api; rm -rf $P; mkdir -p $P; trap 'rm -rf $P' EXIT
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
  test: { environment: "happy-dom", include: ["probe/ui-api/**/*.probe.ts"],
    setupFiles: ["tests/setup.ts"], chaiConfig: { truncateThreshold: 200 } },
});
MORPH_CONF_EOF
cat > $P/ui-api.probe.ts <<'MORPH_PROBE_EOF'
import { test, expect, vi, afterEach } from "vitest";
import * as A from "../../src/api";
import * as H from "../../tests/helpers";

type Obj = Record<string, any>;
const fx = (n: H.FixtureName) => H.loadFixture(n) as Obj;
function spyConsole() {
  return [vi.spyOn(console, "error").mockImplementation(() => {}),
          vi.spyOn(console, "warn").mockImplementation(() => {})];
}
const calls = (spies: { mock: { calls: unknown[] } }[]) => spies.reduce((n, s) => n + s.mock.calls.length, 0);
afterEach(() => { vi.restoreAllMocks(); });

test("Fetch Endpoints ex1: parseHealth(health fixture)", () => {
  const s = spyConsole();
  const h = A.parseHealth(fx("health")) as Obj | null;
  expect(h, "parseHealth returned null").not.toBeNull();
  expect([h!.progress, h!.progress_at, h!.seconds_since_progress, h!.now].join("|"))
    .toBe("26103569|2026-10-02T08:53:15Z|24|2026-10-02T08:53:39Z");
  expect(calls(s), "console calls").toBe(0);
});

test("Fetch Endpoints ex2: parseEvents(events fixture)", () => {
  const s = spyConsole();
  const p = A.parseEvents(fx("events")) as Obj | null;
  expect(p, "parseEvents returned null").not.toBeNull();
  expect(p!.last_id, "last_id").toBe(8);
  expect(p!.events.map((e: Obj) => e.id).join(","), "ids").toBe("8,7,6,5,4,3,2,1");
  const e = p!.events[0];
  expect([e.kind, e.block, e.at, e.address, e.label, e.score, e.origin, e.seed_address, e.old_impl, e.new_impl]
    .map(String).join("|"), "events[0]").toBe(
    "ALERT|26103541|2026-10-02T08:47:50Z|0x0be5cfbcbb8a82c8d44af544dd40261b967ab832|LaunchToken family|1|seen|" +
    "0x0312eaa7791b5b15a12157b2a6e01d8e30c8b1b6|null|null");
  expect(calls(s), "console calls").toBe(0);
});

test("Fetch Endpoints ex3: parseSummary(summary fixture)", () => {
  const s = spyConsole();
  const p = A.parseSummary(fx("summary")) as Obj | null;
  expect(p, "parseSummary returned null").not.toBeNull();
  expect([p!.addresses, p!.codes, p!.seeds, p!.implementations_resolved].join(","), "counts").toBe("217009,20374,8,454");
  expect(JSON.stringify(p!.origins, Object.keys(p!.origins).sort()), "origins")
    .toBe('{"created":109,"fetched":0,"impl":387,"seen":19256,"unknown":197257}');
  expect(p!.alerts_by_seed.length, "alerts_by_seed").toBe(1);
  expect(`${p!.alerts_by_seed[0].count}|${p!.alerts_by_seed[0].label}|${p!.alerts_by_seed[0].seed_address}`)
    .toBe("8|LaunchToken family|0x0312eaa7791b5b15a12157b2a6e01d8e30c8b1b6");
  expect(p!.recent.blocks, "recent.blocks").toBe(300);
  expect(JSON.stringify(p!.recent.by_origin, Object.keys(p!.recent.by_origin).sort()), "recent.by_origin")
    .toBe('{"created":16,"fetched":0,"impl":387,"seen":2474,"unknown":0}');
  expect(calls(s), "console calls").toBe(0);
});

test("Fetch Endpoints ex4: parseClusters(clusters fixture)", () => {
  const s = spyConsole();
  const p = A.parseClusters(fx("clusters_impl")) as Obj | null;
  expect(p, "parseClusters returned null").not.toBeNull();
  expect(`${p!.level}|${p!.n}|${p!.clusters.length}`).toBe("impl|20|20");
  const c = p!.clusters[0];
  expect(`${c.level}|${c.key}|${c.members.length}|${c.members[0]}`)
    .toBe("impl|0x985462c9aa4d6c3ad59ae6e1e9c0c11347ed1598|14|0x0752163d221d3d5d4b6e98bd616b22bd2b453964");
  expect(p!.clusters.map((x: Obj) => x.members.length).join(","), "member counts")
    .toBe("14,8,5,4,3,3,3,3,3,3,3,3,3,2,2,2,2,2,2,2");
  expect(calls(s), "console calls").toBe(0);
});

const ZERO = { created: 0, fetched: 0, impl: 0, seen: 0, unknown: 0 };
test("Fetch Endpoints ex5: the answers of a fresh db parse", () => {
  const h = A.parseHealth({ now: "2026-10-02T08:00:00Z", progress: null, progress_at: null,
    seconds_since_progress: null }) as Obj | null;
  expect(h, "health null").not.toBeNull();
  expect(`${h!.progress}|${h!.seconds_since_progress}`).toBe("null|null");
  const e = A.parseEvents({ events: [], last_id: 0 }) as Obj | null;
  expect(e, "events null").not.toBeNull();
  expect(`${e!.events.length}|${e!.last_id}`).toBe("0|0");
  const s = A.parseSummary({ addresses: 0, codes: 0, seeds: 0, origins: { ...ZERO }, implementations_resolved: 0,
    alerts_by_seed: [], recent: { blocks: 300, by_origin: { ...ZERO } } }) as Obj | null;
  expect(s, "summary null").not.toBeNull();
  expect(`${s!.addresses}|${s!.recent.by_origin.seen}`).toBe("0|0");
});

test("Fetch Endpoints ex6: malformed values give null, never throw", () => {
  const s = spyConsole();
  const bad: [string, (x: unknown) => unknown, unknown][] = [];
  const h1 = fx("health"); h1.progress = "x"; bad.push(["health progress x", A.parseHealth, h1]);
  const h2 = fx("health"); delete h2.now; bad.push(["health without now", A.parseHealth, h2]);
  const e1 = fx("events"); e1.events[3].kind = "FOO"; bad.push(["events kind FOO", A.parseEvents, e1]);
  bad.push(["events without last_id", A.parseEvents, { events: [] }]);
  const s1 = fx("summary"); delete s1.origins.unknown; bad.push(["summary without origins.unknown", A.parseSummary, s1]);
  const c1 = fx("clusters_impl"); c1.clusters[0].members = "x"; bad.push(["clusters members x", A.parseClusters, c1]);
  for (const [name, p] of [["parseHealth", A.parseHealth], ["parseEvents", A.parseEvents],
    ["parseSummary", A.parseSummary], ["parseClusters", A.parseClusters]] as const) {
    for (const v of [null, 42, "x", []]) bad.push([`${name}(${JSON.stringify(v)})`, p, v]);
  }
  const wrong: string[] = [];
  for (const [name, p, v] of bad) {
    try { if (p(v) !== null) wrong.push(`${name}: not null`); } catch (err) { wrong.push(`${name}: threw ${err}`); }
  }
  expect(wrong, "malformed").toStrictEqual([]);
  expect(calls(s), "console calls").toBe(0);
});

test("Fetch Endpoints ex7: the fetchers request the four URLs", async () => {
  const f = H.fixtureFetch();
  const h = await A.getHealth(f.fetch) as Obj;
  const e = await A.getEvents(0, f.fetch) as Obj;
  const s = await A.getSummary(f.fetch) as Obj;
  const c = await A.getClusters("impl", 20, f.fetch) as Obj;
  expect([h.ok, e.ok, s.ok, c.ok].join(","), "ok").toBe("true,true,true,true");
  expect(`${h.data.progress}|${e.data.last_id}|${e.data.events.length}|${s.data.codes}|${c.data.clusters.length}`)
    .toBe("26103569|8|8|20374|20");
  expect(f.calls, "URLs").toStrictEqual(["/api/health", "/api/events?after=0&limit=500", "/api/summary",
    "/api/clusters?level=impl&n=20"]);
  await A.getEvents(8, f.fetch);
  expect(f.calls[4], "getEvents(8)").toBe("/api/events?after=8&limit=500");
});

test("Fetch Endpoints ex8: failures give {ok: false}, never throw", async () => {
  const s = spyConsole();
  const urls = ["/api/health", "/api/events?after=0&limit=500", "/api/summary", "/api/clusters?level=impl&n=20"];
  const cases: [string, H.FakeReply][] = [
    ["a reject", new TypeError("Failed to fetch")], ["b 500", { status: 500, body: { error: "boom" } }],
    ["c json rejects", { jsonError: true }], ["d bad body", { body: { x: 1 } }]];
  const wrong: string[] = [];
  for (const [name, reply] of cases) {
    const f = H.fakeFetch(Object.fromEntries(urls.map((u) => [u, reply])));
    const results: [string, Promise<unknown>][] = [["getHealth", A.getHealth(f.fetch)],
      ["getEvents", A.getEvents(0, f.fetch)], ["getSummary", A.getSummary(f.fetch)],
      ["getClusters", A.getClusters("impl", 20, f.fetch)]];
    for (const [fn, pr] of results) {
      let r: Obj;
      try { r = (await pr) as Obj; } catch (err) { wrong.push(`${name} ${fn}: threw ${err}`); continue; }
      if (r.ok !== false) wrong.push(`${name} ${fn}: ok is ${r.ok}`);
      else if (typeof r.error !== "string" || r.error.length === 0 || r.error.includes("\n"))
        wrong.push(`${name} ${fn}: error ${JSON.stringify(r.error)}`);
      else if (name === "b 500" && !r.error.includes("500")) wrong.push(`${name} ${fn}: error lacks 500`);
    }
  }
  expect(wrong, "failures").toStrictEqual([]);
  expect(calls(s), "console calls").toBe(0);
});
MORPH_PROBE_EOF
echo '== tsc'; node_modules/.bin/tsc --noEmit
echo '== guard'; node $P/guard.mjs src; node $P/guard.mjs tests tests/api.test.ts 1 5
echo '== probe'; node_modules/.bin/vitest run --config $P/probe.config.mts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== own test'; node_modules/.bin/vitest run tests/api.test.ts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== full'; node_modules/.bin/vitest run  --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
cd ..
git diff --quiet HEAD -- ethsc tests contour.yaml dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts dashboard/index.html dashboard/tests/setup.ts dashboard/tests/helpers.ts dashboard/package-lock.json || { echo "changed outside the targets: $(git diff --name-only HEAD -- ethsc tests contour.yaml dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts dashboard/index.html dashboard/tests/setup.ts dashboard/tests/helpers.ts dashboard/package-lock.json | tr "\n" " ")"; exit 1; }
X=$(git ls-files --others --exclude-standard | grep -vxF -e dashboard/src/api.ts -e dashboard/tests/api.test.ts || true); [ -z "$X" ] || { echo "tests left files: $X"; exit 1; }
) > $L 2>&1; rc=$?; cat $L; exit $rc