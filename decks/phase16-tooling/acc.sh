D=/tmp/morph/ui-format-p16; mkdir -p $D; S=$(date +%s)-$$; L=$D/acc-$S.log
cp dashboard/src/format.ts $D/0-$S.ts 2>/dev/null
cp dashboard/tests/format.test.ts $D/1-$S.ts 2>/dev/null
(
 set -e
 export NO_COLOR=1 CI=1
cd dashboard
[ -d node_modules ] || npm ci --no-audit --no-fund --prefer-offline > /dev/null 2>&1 || { echo 'npm ci failed'; exit 1; }
P=$PWD/probe/ui-format; rm -rf $P; mkdir -p $P; trap 'rm -rf $P' EXIT
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
  test: { environment: "happy-dom", include: ["probe/ui-format/**/*.probe.ts"],
    setupFiles: ["tests/setup.ts"], chaiConfig: { truncateThreshold: 200 } },
});
MORPH_CONF_EOF
cat > $P/ui-format.probe.ts <<'MORPH_PROBE_EOF'
import { test, expect } from "vitest";
import * as F from "../../src/format";
import * as H from "../../tests/helpers";

const each = <T,>(f: (x: T) => unknown, xs: T[]) => xs.map((x) => String(f(x)));

test("Format Values ex1: formatScore", () => {
  expect(each(F.formatScore, [1, 0.8666666666666667, 0, null])).toStrictEqual(["1.0000", "0.8667", "0.0000", ""]);
});

test("Format Values ex2: formatAge", () => {
  expect(each(F.formatAge, [0, 8, 24, 59, 60, 150, 3599, 3600, 7300, null])).toStrictEqual(
    ["0 s", "8 s", "24 s", "59 s", "1 min", "2 min", "59 min", "1 h", "2 h", "n/a"]);
});

test("Format Values ex3: statusOf", () => {
  expect(each(F.statusOf, [0, 24, 36, 59, 60, 299, 300, 86400, null])).toStrictEqual(
    ["live", "live", "live", "live", "behind", "behind", "stalled", "stalled", "unknown"]);
});

test("Format Values ex4: shortAddress", () => {
  expect(each(F.shortAddress, ["0x0be5cfbcbb8a82c8d44af544dd40261b967ab832", "0x1234", "0x1234567890"]))
    .toStrictEqual(["0x0be5…b832", "0x1234", "0x1234567890"]);
});

test("Format Values ex5: etherscanUrl", () => {
  expect(each(F.etherscanUrl, ["0x0be5cfbcbb8a82c8d44af544dd40261b967ab832",
    "0x1807090DD15A6F58E00FD769E32EBF20EE610385"])).toStrictEqual([
    "https://etherscan.io/address/0x0be5cfbcbb8a82c8d44af544dd40261b967ab832",
    "https://etherscan.io/address/0x1807090dd15a6f58e00fd769e32ebf20ee610385"]);
});

test("Format Values ex6: formatTime", () => {
  expect(each(F.formatTime, ["2026-10-02T08:47:50Z", "2026-10-02T23:59:59Z", "garbage"]))
    .toStrictEqual(["08:47:50", "23:59:59", "garbage"]);
});

test("Format Values ex7: originShares", () => {
  const s = H.loadFixture("summary") as { origins: Record<string, number>; recent: { by_origin: Record<string, number> } };
  const show = (c: Record<string, number>) => F.originShares(c as Parameters<typeof F.originShares>[0])
    .map((e) => `${e.origin}:${e.count}:${e.percent}`).join(" ");
  expect(show(s.origins), "origins").toBe("created:109:0.1 seen:19256:8.9 impl:387:0.2 fetched:0:0 unknown:197257:90.9");
  expect(show(s.recent.by_origin), "recent").toBe("created:16:0.6 seen:2474:86 impl:387:13.5 fetched:0:0 unknown:0:0");
  expect(show({ created: 0, seen: 0, impl: 0, fetched: 0, unknown: 0 }), "all zero")
    .toBe("created:0:0 seen:0:0 impl:0:0 fetched:0:0 unknown:0:0");
});
MORPH_PROBE_EOF
echo '== tsc'; node_modules/.bin/tsc --noEmit
echo '== guard'; node $P/guard.mjs src; node $P/guard.mjs tests tests/format.test.ts 1 5
echo '== probe'; node_modules/.bin/vitest run --config $P/probe.config.mts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== own test'; node_modules/.bin/vitest run tests/format.test.ts --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
echo '== full'; node_modules/.bin/vitest run  --reporter=dot > $P/vt.log 2>&1 || { grep -E '^ FAIL |Error|^ +Tests |^ +Test Files ' $P/vt.log | head -80; exit 1; }
cd ..
git diff --quiet HEAD -- ethsc tests contour.yaml dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts dashboard/index.html dashboard/tests/setup.ts dashboard/tests/helpers.ts dashboard/package-lock.json || { echo "changed outside the targets: $(git diff --name-only HEAD -- ethsc tests contour.yaml dashboard/package.json dashboard/tsconfig.json dashboard/vite.config.ts dashboard/index.html dashboard/tests/setup.ts dashboard/tests/helpers.ts dashboard/package-lock.json | tr "\n" " ")"; exit 1; }
X=$(git ls-files --others --exclude-standard | grep -vxF -e dashboard/src/format.ts -e dashboard/tests/format.test.ts || true); [ -z "$X" ] || { echo "tests left files: $X"; exit 1; }
) > $L 2>&1; rc=$?; cat $L; exit $rc