// Live check of the phase-16 page through the Chrome DevTools Protocol (Node 23 global WebSocket).
// node cdp.mjs <phase> ; phases: watch <seconds>, shot <name>, sample
import fs from "node:fs";
const [phase, arg] = process.argv.slice(2);
const list = await (await fetch("http://127.0.0.1:9333/json/list")).json();
const page = list.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let n = 0;
const pending = new Map();
ws.addEventListener("message", (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
});
const send = (method, params = {}) => new Promise((r) => { const id = ++n; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const evaluate = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true })).result?.result?.value;

const SAMPLE = `(() => {
  const q = (s) => document.querySelector(s);
  const t = (s) => (q(s)?.textContent ?? "").trim();
  const rows = Array.from(document.querySelectorAll("#events [data-id]"));
  if (!window.__mark && rows.length) { window.__mark = rows[rows.length - 1]; window.__markId = window.__mark.getAttribute("data-id"); }
  return {
    progress: t('#health [data-field="progress"]'), age: t('#health [data-field="age"]'),
    status: t('#health [data-field="status"]'),
    rows: rows.length, kinds: rows.map((r) => r.getAttribute("data-kind")).join("").length,
    newest: rows[0]?.getAttribute("data-id") ?? null,
    markSame: window.__mark ? document.querySelector('#events [data-id="' + window.__markId + '"]') === window.__mark : null,
    reloads: performance.getEntriesByType("navigation").length,
    addresses: t('#summary [data-field="addresses"]'),
    clusters: document.querySelectorAll("#clusters [data-key]").length,
    unreachable: Array.from(document.querySelectorAll(".unreachable")).map((e) => e.closest("#health,#events,#summary,#clusters")?.id).join(","),
    errors: window.__errors ?? 0,
  };
})()`;

if (phase === "watch") {
  await send("Runtime.enable");
  const end = Date.now() + Number(arg) * 1000;
  while (Date.now() < end) {
    console.log(new Date().toISOString().slice(11, 19), JSON.stringify(await evaluate(SAMPLE)));
    await new Promise((r) => setTimeout(r, 30000));
  }
} else if (phase === "sample") {
  console.log(new Date().toISOString().slice(11, 19), JSON.stringify(await evaluate(SAMPLE)));
} else if (phase === "shot") {
  await send("Emulation.setDeviceMetricsOverride", { width: 1400, height: 1100, deviceScaleFactor: 1, mobile: false });
  const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  fs.writeFileSync(arg, Buffer.from(r.result.data, "base64"));
  console.log("shot", arg);
}
ws.close();
