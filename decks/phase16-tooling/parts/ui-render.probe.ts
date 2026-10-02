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
