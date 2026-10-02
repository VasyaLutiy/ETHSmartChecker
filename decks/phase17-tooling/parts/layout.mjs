// Phase 17 layout probe: Style Page examples 1-8 measured in headless Chrome over CDP.
// Run from dashboard/ after `npm run build`: node layout.mjs <screenshot.png>
// Serves dist/ and the four fixtures on 127.0.0.1 (loopback only), drives Chrome, prints one
// line per failed check ("Style Page exN: ..."), exits 1 on any failure.
import http from "node:http";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";

const shot = process.argv[2] || "";
const FIX = path.resolve("../tests/fixtures");
const fx = (n) => fs.readFileSync(path.join(FIX, `dashboard_${n}.json`), "utf8");
let failing = false;
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://x");
  const json = (code, body) => { res.writeHead(code, { "content-type": "application/json" }); res.end(body); };
  if (url.pathname.startsWith("/api/")) {
    if (failing) return json(500, '{"error": "down"}');
    if (url.pathname === "/api/health") return json(200, fx("health"));
    if (url.pathname === "/api/summary") return json(200, fx("summary"));
    if (url.pathname === "/api/clusters") return json(200, fx("clusters_impl"));
    if (url.pathname === "/api/events")
      return json(200, url.searchParams.get("after") === "0" ? fx("events") : '{"events": [], "last_id": 8}');
    return json(404, '{"error": "not found"}');
  }
  const rel = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
  const file = path.resolve("dist", rel);
  if (!file.startsWith(path.resolve("dist")) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  const type = file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html";
  res.writeHead(200, { "content-type": type });
  res.end(fs.readFileSync(file));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const port = server.address().port;

const profile = fs.mkdtempSync(path.join(os.tmpdir(), "p17-chrome-"));
const chrome = spawn("google-chrome", ["--headless=new", "--no-first-run", "--no-default-browser-check",
  "--disable-gpu", "--disable-extensions", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
  "--window-size=1400,900", "about:blank"], { stdio: "ignore" });
const bad = [];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function done(code) {
  try { chrome.kill("SIGKILL"); } catch {}
  server.close();
  fs.rmSync(profile, { recursive: true, force: true });
  for (const b of bad) console.log(b);
  process.exit(code);
}
let devPort = null;
for (let i = 0; i < 100 && !devPort; i++) {
  await sleep(100);
  try { devPort = fs.readFileSync(path.join(profile, "DevToolsActivePort"), "utf8").split("\n")[0]; } catch {}
}
if (!devPort) { bad.push("layout: Chrome did not start"); done(1); }
const targets = await (await fetch(`http://127.0.0.1:${devPort}/json/list`)).json();
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let seq = 0;
const waiting = new Map();
ws.addEventListener("message", (m) => {
  const d = JSON.parse(m.data);
  if (d.id && waiting.has(d.id)) { waiting.get(d.id)(d); waiting.delete(d.id); }
});
const send = (method, params = {}) => new Promise((r) => { const id = ++seq; waiting.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const evaluate = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) return { error: r.result.exceptionDetails.exception?.description ?? "exception" };
  return r.result?.result?.value;
};
const viewport = (w, h) => send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile: false });

// Shared helpers injected into the page.
const LIB = `
const cs = (el, p) => getComputedStyle(el, p || null);
const rgb = (s) => (s.match(/[\\d.]+/g) || []).slice(0, 3).map(Number);
const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
  const [r, g, b] = c.map(f); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const ratio = (a, b) => { const [x, y] = [lum(rgb(a)), lum(rgb(b))].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const bg = (el) => { for (let e = el; e; e = e.parentElement) { const c = cs(e).backgroundColor;
  if (c && c !== "rgba(0, 0, 0, 0)" && c !== "transparent") return c; } return "rgb(255, 255, 255)"; };
const box = (el) => el ? el.getBoundingClientRect() : null;
const content = (el, p) => el ? cs(el, p).content.replace(/^"|"$/g, "") : "<missing>";
const bad = [];
const chk = (ex, ok, msg) => { if (!ok) bad.push("Style Page ex" + ex + ": " + msg); };
const q = (s) => document.querySelector(s);
`;

await viewport(1400, 900);
await send("Page.navigate", { url: `http://127.0.0.1:${port}/` });
await sleep(3000);

const MAIN = `(() => { ${LIB}
  // ex1 theme
  chk(1, cs(document.body).backgroundColor === "rgb(13, 13, 13)", "body background " + cs(document.body).backgroundColor);
  const panels = Array.from(document.querySelectorAll("section.panel"));
  chk(1, panels.length === 4, "section.panel count " + panels.length);
  for (const p of panels) {
    chk(1, cs(p).backgroundColor === "rgb(26, 26, 25)", "#" + p.id + " background " + cs(p).backgroundColor);
    const r = ratio(cs(p).color, bg(p));
    chk(1, r >= 7, "#" + p.id + " text contrast " + r.toFixed(2));
  }
  chk(1, /system-ui/.test(cs(document.body).fontFamily), "font-family " + cs(document.body).fontFamily);
  for (const sheet of Array.from(document.styleSheets)) {
    let rules = [];
    try { rules = Array.from(sheet.cssRules); } catch (e) { chk(1, false, "unreadable stylesheet " + sheet.href); }
    const walk = (list) => { for (const rule of list) {
      if (rule instanceof CSSImportRule) chk(1, false, "@import " + rule.href);
      if (rule.style) for (const prop of Array.from(rule.style)) {
        const v = rule.style.getPropertyValue(prop);
        if (/url\\(/i.test(v)) chk(1, false, "url() in " + rule.selectorText + " " + prop);
      }
      if (rule.cssRules) walk(Array.from(rule.cssRules));
    } };
    walk(rules);
  }
  // ex2 layout at 1400
  const h = box(q("#health")), e = box(q("#events")), s = box(q("#summary")), c = box(q("#clusters")), app = box(q("#app"));
  if (!h || !e || !s || !c || !app) { chk(2, false, "a panel is missing"); return bad; }
  chk(2, h.bottom <= Math.min(e.top, s.top, c.top) + 1, "#health is not above the other panels");
  chk(2, h.width >= 0.95 * app.width, "#health width " + Math.round(h.width) + " of #app " + Math.round(app.width));
  chk(2, e.width >= 0.55 * innerWidth, "#events width " + Math.round(e.width) + " of viewport " + innerWidth);
  chk(2, s.left >= e.right - 1 && c.left >= e.right - 1, "#summary/#clusters not right of #events");
  chk(2, s.bottom <= c.top + 1, "#summary not above #clusters");
  chk(2, document.documentElement.scrollWidth <= innerWidth, "horizontal scroll at 1400: " + document.documentElement.scrollWidth);
  // ex3 status
  const st = q('#health [data-field="status"]');
  if (!st) { chk(3, false, "no status"); } else {
    chk(3, parseFloat(cs(st).fontSize) >= 24, "status font-size " + cs(st).fontSize);
    const want = { live: "rgb(12, 163, 12)", behind: "rgb(250, 178, 25)", stalled: "rgb(208, 59, 59)", unknown: "rgb(137, 135, 129)" };
    const orig = st.getAttribute("data-status");
    chk(3, orig === "live", "fixture status " + orig);
    for (const [k, v] of Object.entries(want)) {
      st.setAttribute("data-status", k);
      chk(3, cs(st).backgroundColor === v, k + " background " + cs(st).backgroundColor);
      const r = ratio(cs(st).color, cs(st).backgroundColor);
      chk(3, r >= 4.5, k + " text contrast " + r.toFixed(2));
    }
    st.setAttribute("data-status", orig);
  }
  const pr = q('#health [data-field="progress"]');
  chk(3, pr && parseFloat(cs(pr).fontSize) >= 20, "progress font-size " + (pr && cs(pr).fontSize));
  const labels = ["progress", "progress_at", "age"].map((f) => content(q('#health [data-field="' + f + '"]'), "::before"));
  chk(3, labels.join("|") === "block|at|age", "health labels " + labels.join("|"));
  const hf = ["progress", "progress_at", "age", "status"].map((f) => box(q('#health [data-field="' + f + '"]')));
  for (let i = 0; i + 1 < hf.length; i++)
    if (hf[i] && hf[i + 1]) chk(3, hf[i + 1].left - hf[i].right >= 12,
      "health fields " + i + "/" + (i + 1) + " gap " + Math.round(hf[i + 1].left - hf[i].right) + " px");
  // ex4 feed columns
  const rows = Array.from(document.querySelectorAll('#events [data-id][data-kind="ALERT"]'));
  chk(4, rows.length === 8, "ALERT rows " + rows.length);
  const r8 = q('#events [data-id="8"]'), head = q("#events .feed-head");
  if (r8 && head) {
    const hc = Array.from(head.children).map(box), rc = Array.from(r8.children).map(box);
    hc.forEach((b, i) => chk(4, rc[i] && Math.abs(b.left - rc[i].left) <= 1,
      "head cell " + i + " at " + Math.round(b.left) + ", row cell at " + (rc[i] ? Math.round(rc[i].left) : "none")));
    for (let i = 0; i + 1 < rc.length; i++)
      chk(4, rc[i].right <= rc[i + 1].left + 0.5, "row 8 cells " + i + " and " + (i + 1) + " overlap");
  } else chk(4, false, "no row 8 or no .feed-head");
  const tx = rows.map((r) => box(r.querySelector('[data-field="time"]'))?.left ?? -1);
  chk(4, tx.length > 0 && Math.max(...tx) - Math.min(...tx) <= 1, "time column x " + tx.map(Math.round).join(","));
  for (const r of rows) chk(4, box(r).height <= 28, "row " + r.getAttribute("data-id") + " height " + box(r).height);
  for (const f of ["time", "block", "score"]) {
    const el = r8 && r8.querySelector('[data-field="' + f + '"]');
    chk(4, el && /tabular-nums/.test(cs(el).fontVariantNumeric), f + " numerals " + (el && cs(el).fontVariantNumeric));
  }
  // ex6 bars
  const colours = { created: "rgb(57, 135, 229)", seen: "rgb(217, 89, 38)", impl: "rgb(25, 158, 112)",
    fetched: "rgb(201, 133, 0)", unknown: "rgb(107, 106, 101)" };
  const barLabels = [];
  for (const bar of Array.from(document.querySelectorAll("#summary [data-bar]"))) {
    const bb = box(bar);
    chk(6, bb.height >= 8, bar.getAttribute("data-bar") + " bar height " + bb.height);
    barLabels.push(content(bar, "::before"));
    for (const seg of Array.from(bar.querySelectorAll("[data-origin]"))) {
      const o = seg.getAttribute("data-origin"), pct = parseFloat(seg.style.width) || 0;
      if (pct > 0) chk(6, cs(seg).backgroundColor === colours[o], o + " segment background " + cs(seg).backgroundColor);
      chk(6, Math.abs(box(seg).width - pct / 100 * bb.width) <= 3,
        bar.getAttribute("data-bar") + " " + o + " width " + box(seg).width.toFixed(1) + " for " + pct + "%");
    }
  }
  chk(6, barLabels.join("|") === "all addresses|last 300 blocks", "bar labels " + barLabels.join("|"));
  for (const li of Array.from(document.querySelectorAll("#summary ul.legend li[data-legend]"))) {
    const o = li.getAttribute("data-legend");
    chk(6, cs(li, "::before").backgroundColor === colours[o], "legend " + o + " swatch " + cs(li, "::before").backgroundColor);
  }
  const lg = q("#summary ul.legend");
  if (lg) {
    chk(6, box(lg).height <= 24, "legend height " + box(lg).height);
    const li0 = lg.querySelector("li");
    chk(6, li0 && cs(li0).listStyleType === "none", "legend bullet " + (li0 && cs(li0).listStyleType));
  } else chk(6, false, "no legend");
  const cb = ["addresses", "codes", "seeds", "implementations_resolved"].map((f) => box(q('#summary [data-field="' + f + '"]')));
  for (let i = 0; i < cb.length; i++) for (let j = i + 1; j < cb.length; j++) {
    const a = cb[i], b = cb[j];
    if (!a || !b) continue;
    const gapX = Math.max(b.left - a.right, a.left - b.right), gapY = Math.max(b.top - a.bottom, a.top - b.bottom);
    chk(6, gapX >= 12 || gapY >= 4, "counters " + i + "/" + j + " gap x " + Math.round(gapX) + " y " + Math.round(gapY));
  }
  const counters = ["addresses", "codes", "seeds", "implementations_resolved"].map((f) => content(q('#summary [data-field="' + f + '"]'), "::before"));
  chk(6, counters.join("|") === "addresses|codes|seeds|proxies resolved", "counter labels " + counters.join("|"));
  // ex7 clusters
  const tr = q("#clusters [data-key]");
  if (tr) {
    const m = tr.querySelector('[data-field="members"]'), a = tr.querySelector("a");
    chk(7, cs(m).textAlign === "right" || cs(m).textAlign === "end", "members text-align " + cs(m).textAlign);
    chk(7, /tabular-nums/.test(cs(m).fontVariantNumeric), "members numerals " + cs(m).fontVariantNumeric);
    const range = document.createRange(); range.selectNodeContents(m);
    const textLeft = range.getBoundingClientRect().left;
    chk(7, textLeft - box(a).right >= 12, "members text " + Math.round(textLeft - box(a).right) + " px after the key");
  } else chk(7, false, "no cluster row");
  for (const a of Array.from(document.querySelectorAll("#app a")))
    if (cs(a).color !== "rgb(110, 168, 236)") { chk(7, false, "link colour " + cs(a).color); break; }
  return bad;
})()`;

const FILTER = `(async () => { ${LIB}
  const sel = q("#kind-filter");
  sel.value = "UPGRADE"; sel.dispatchEvent(new Event("change"));
  await new Promise((r) => setTimeout(r, 100));
  for (const r of Array.from(document.querySelectorAll('#events [data-kind="ALERT"]')))
    chk(5, r.offsetHeight === 0, "hidden row " + r.getAttribute("data-id") + " is " + r.offsetHeight + " px high");
  sel.value = "ALL"; sel.dispatchEvent(new Event("change"));
  await new Promise((r) => setTimeout(r, 100));
  for (const r of Array.from(document.querySelectorAll("#events [data-id]")))
    chk(5, r.offsetHeight >= 14, "row " + r.getAttribute("data-id") + " is " + r.offsetHeight + " px high under ALL");
  return bad;
})()`;

const NARROW = `(() => { ${LIB}
  chk(2, document.documentElement.scrollWidth <= innerWidth, "horizontal scroll at 1024: " + document.documentElement.scrollWidth);
  return bad;
})()`;

const DOWN = `(() => { ${LIB}
  const u = q("#health .unreachable");
  if (!u) { chk(8, false, "no #health .unreachable"); return bad; }
  chk(8, box(u).height >= 14, ".unreachable height " + box(u).height);
  chk(8, cs(u).backgroundColor === "rgb(208, 59, 59)", ".unreachable background " + cs(u).backgroundColor);
  chk(8, cs(u).color === "rgb(255, 255, 255)", ".unreachable colour " + cs(u).color);
  const p = q('#health [data-field="progress"]');
  chk(8, p && p.textContent.trim() === "26103569", "progress kept: " + (p && p.textContent));
  return bad;
})()`;

const collect = (r, where) => {
  if (Array.isArray(r)) bad.push(...r);
  else bad.push(`layout: ${where} threw ${r?.error ?? JSON.stringify(r)}`);
};
collect(await evaluate(MAIN), "main checks");
collect(await evaluate(FILTER), "filter checks");
if (shot) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  if (r.result?.data) fs.writeFileSync(shot, Buffer.from(r.result.data, "base64"));
}
await viewport(1024, 768);
await sleep(300);
collect(await evaluate(NARROW), "narrow checks");
await viewport(1400, 900);
failing = true;
await sleep(7000);
collect(await evaluate(DOWN), "unreachable checks");
ws.close();
done(bad.length ? 1 : 0);
