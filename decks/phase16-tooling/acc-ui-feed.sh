D=/tmp/morph/ui-feed-p16; mkdir -p $D; S=$(date +%s)-$$; L=$D/acc-$S.log
cp dashboard/src/feed.ts $D/0-$S.ts 2>/dev/null
cp dashboard/tests/feed.test.ts $D/1-$S.ts 2>/dev/null
(
 set -e
 export NO_COLOR=1 CI=1
cd dashboard
[ -d node_modules ] || npm ci --no-audit --no-fund --prefer-offline > /dev/null 2>&1 || { echo 'npm ci failed'; exit 1; }
P=$PWD/probe/ui-feed; rm -rf $P; mkdir -p $P; trap 'rm -rf $P' EXIT
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
  test: { environment: "happy-dom", include: ["probe/ui-feed/**/*.probe.ts"],
    setupFiles: ["tests/setup.ts"], chaiConfig: { truncateThreshold: 200 } },
});
MORPH_CONF_EOF
cat > $P/ui-feed.probe.ts <<'MORPH_PROBE_EOF'
import { test, expect } from "vitest";
import * as M from "../../src/feed";
import * as H from "../../tests/helpers";

const ids = (xs: readonly { id: number }[]) => xs.map((e) => e.id).join(",");

test("Merge Feed ex1: merging the same events twice", () => {
  const ev = H.fixtureEvents();
  const empty: H.FixtureEvent[] = [];
  const a = M.mergeEvents(empty, ev);
  expect(ids(a), "first").toBe("8,7,6,5,4,3,2,1");
  const b = M.mergeEvents(a, ev);
  expect(ids(b), "second").toBe("8,7,6,5,4,3,2,1");
  expect(b !== a, "a new array").toBe(true);
  expect(b.every((e, i) => e === a[i]), "same objects").toBe(true);
  expect(`${empty.length} ${ev.length} ${a.length}`, "arguments unchanged").toBe("0 8 8");
});

test("Merge Feed ex2: ascending input comes out newest first", () => {
  expect(ids(M.mergeEvents([], H.syntheticEvents([1, 2, 3])))).toBe("3,2,1");
});

test("Merge Feed ex3: the cap", () => {
  const many = H.syntheticEvents(Array.from({ length: 600 }, (_, i) => i + 1));
  const r = M.mergeEvents([], many);
  expect(`${r.length} ${r[0].id} ${r[r.length - 1].id}`, "default cap").toBe("500 600 101");
  expect(ids(M.mergeEvents([], many, 3)), "cap 3").toBe("600,599,598");
  expect(many.length, "argument unchanged").toBe(600);
});

test("Merge Feed ex4: the kept element wins on a repeated id", () => {
  const kept = H.fixtureEvents();
  const changed = { ...kept[0], label: "changed" };
  const r = M.mergeEvents(kept, [changed, ...H.syntheticEvents([9])]);
  expect(ids(r)).toBe("9,8,7,6,5,4,3,2,1");
  const e8 = r.find((e) => e.id === 8)!;
  expect(e8 === kept[0], "the kept object").toBe(true);
  expect(e8.label).toBe("LaunchToken family");
});

test("Merge Feed ex5: filterByKind", () => {
  const all = M.mergeEvents(H.fixtureEvents(), [H.UPGRADE_EVENT]);
  expect(ids(M.filterByKind(all, "ALL")), "ALL").toBe("9,8,7,6,5,4,3,2,1");
  expect(ids(M.filterByKind(all, "ALERT")), "ALERT").toBe("8,7,6,5,4,3,2,1");
  expect(ids(M.filterByKind(all, "UPGRADE")), "UPGRADE").toBe("9");
});
MORPH_PROBE_EOF
echo '== tsc'; node_modules/.bin/tsc --noEmit
echo '== guard'; node $P/guard.mjs src; node $P/guard.mjs tests tests/feed.test.ts 1 5
echo '== probe'; node_modules/.bin/vitest run --config $P/probe.config.mts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== own test'; node_modules/.bin/vitest run tests/feed.test.ts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== full'; node_modules/.bin/vitest run  --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
cd ..
git diff --quiet HEAD -- ethsc tests contour.yaml dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts dashboard/index.html dashboard/tests/setup.ts dashboard/tests/helpers.ts dashboard/package-lock.json || { echo "changed outside the targets: $(git diff --name-only HEAD -- ethsc tests contour.yaml dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts dashboard/index.html dashboard/tests/setup.ts dashboard/tests/helpers.ts dashboard/package-lock.json | tr "\n" " ")"; exit 1; }
X=$(git ls-files --others --exclude-standard | grep -vxF -e dashboard/src/feed.ts -e dashboard/tests/feed.test.ts || true); [ -z "$X" ] || { echo "tests left files: $X"; exit 1; }
) > $L 2>&1; rc=$?; cat $L; exit $rc