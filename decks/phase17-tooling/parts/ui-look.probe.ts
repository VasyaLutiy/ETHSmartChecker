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

// ---- phase 17: Wire Page ex6-9 (layout) ----
test("Wire Page ex6: sections, titles, head, legend", async () => {
  await page();
  const app = q("#app")!;
  expect(app.classList.contains("dash"), "#app.dash").toBe(true);
  const kids = Array.from(app.children);
  expect(kids.map((k) => `${k.tagName.toLowerCase()}#${k.id}.${k.className}`), "children of #app").toStrictEqual(
    ["section#health.panel", "section#events.panel", "section#summary.panel", "section#clusters.panel"]);
  expect(kids.map((k) => {
    const h = k.firstElementChild;
    return h ? `${h.tagName.toLowerCase()}.${h.className}:${(h.textContent ?? "").trim()}` : "none";
  }), "titles").toStrictEqual(["h2.panel-title:Listener", "h2.panel-title:Events", "h2.panel-title:Summary",
    "h2.panel-title:Impl clusters"]);
  const sel = q("#events select#kind-filter");
  const list = q('#events [data-role="list"]');
  expect(sel !== null && list !== null, "select and list inside #events").toBe(true);
  expect(!!(sel!.compareDocumentPosition(list!) & Node.DOCUMENT_POSITION_FOLLOWING), "select before the list").toBe(true);
  const heads = document.querySelectorAll("#events .feed-head");
  expect(heads.length, ".feed-head count").toBe(1);
  expect(Array.from(heads[0].children).map((c) => (c.textContent ?? "").trim()), ".feed-head texts")
    .toStrictEqual(["kind", "time UTC", "block", "label", "score", "origin", "address"]);
  const legend = document.querySelectorAll("#summary ul.legend");
  expect(legend.length, "ul.legend count").toBe(1);
  expect(Array.from(legend[0].querySelectorAll("li")).map((li) => `${li.getAttribute("data-legend")}=${(li.textContent ?? "").trim()}`),
    "legend").toStrictEqual(["created=created", "seen=seen", "impl=impl", "fetched=fetched", "unknown=unknown"]);
});

test("Wire Page ex7: feed meta", async () => {
  await page();
  expect(txt('#events [data-field="feed-meta"]'), "fixture page").toBe("8 events · newest 08:47:50 UTC");
  document.body.replaceChildren();
  const app = document.createElement("div"); app.id = "app"; document.body.appendChild(app);
  const f = H.fixtureFetch();
  f.set("/api/events?after=0&limit=500", { body: { events: [], last_id: 0 } });
  start(document, f.fetch, H.fakeClock());
  await H.flush();
  expect(txt('#events [data-field="feed-meta"]'), "empty page").toBe("no events yet");
});

test("Wire Page ex8: the tab title follows health", async () => {
  const err = vi.spyOn(console, "error").mockImplementation(() => {});
  const { f, k } = await page();
  const t1 = document.title;
  f.failAll(new TypeError("Failed to fetch"));
  k.fire(5000);
  await H.flush();
  const t2 = document.title;
  f.failAll(null);
  k.fire(5000);
  await H.flush();
  expect([t1, t2, document.title]).toStrictEqual(["live · 26103569 · ethsc", "unreachable · ethsc", "live · 26103569 · ethsc"]);
  expect(err.mock.calls.length, "console.error").toBe(0);
});

test("Wire Page ex9: stalled title, and ethsc before the first answer", async () => {
  document.title = "previous";
  const f = H.fixtureFetch();
  f.set("/api/health", { body: { ...(H.loadFixture("health") as Record<string, unknown>), seconds_since_progress: 400 } });
  start(document, f.fetch, H.fakeClock());
  const before = document.title;
  await H.flush();
  expect([before, document.title]).toStrictEqual(["ethsc", "stalled · 26103569 · ethsc"]);
});
