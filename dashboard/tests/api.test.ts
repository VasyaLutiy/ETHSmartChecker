import { expect, test } from "vitest";
import {
  getEvents,
  getHealth,
  parseHealth,
  parseClusters
} from "../src/api";
import {
  fakeFetch,
  fixtureFetch,
  loadFixture
} from "./helpers";

test("parseHealth ex1", () => {
  const h = parseHealth(loadFixture("health"));
  expect(h === null).toBe(false);
  expect(h !== null && h.progress).toBe(26103569);
  expect(h !== null && h.seconds_since_progress).toBe(24);
  expect(h !== null && h.now).toBe("2026-10-02T08:53:39Z");
});

test("parseClusters ex4", () => {
  const c = parseClusters(loadFixture("clusters_impl"));
  expect(c === null).toBe(false);
  expect(c !== null && c.clusters.length).toBe(20);
  expect(c !== null && c.clusters[0] !== undefined && c.clusters[0].key).toBe(
    "0x985462c9aa4d6c3ad59ae6e1e9c0c11347ed1598"
  );
  expect(c !== null && c.clusters[0] !== undefined && c.clusters[0].members.length).toBe(14);
});

test("getHealth fixture", async () => {
  const f = fixtureFetch();
  const r = await getHealth(f.fetch);
  expect(r.ok).toBe(true);
  expect(r.ok && r.data.progress).toBe(26103569);
  expect(f.calls).toEqual(["/api/health"]);
});

test("getEvents url and data", async () => {
  const f = fixtureFetch();
  const r = await getEvents(0, f.fetch);
  expect(r.ok).toBe(true);
  expect(r.ok && r.data.last_id).toBe(8);
  expect(f.calls[0]).toBe("/api/events?after=0&limit=500");
  const r2 = await getEvents(8, f.fetch);
  expect(r2.ok).toBe(false);
  expect(f.calls[1]).toBe("/api/events?after=8&limit=500");
});

test("getHealth failure naming status", async () => {
  const f = fakeFetch({ "/api/health": { status: 500, body: { error: "boom" } } });
  const r = await getHealth(f.fetch);
  expect(r.ok).toBe(false);
  expect(r.ok === false && r.error.includes("500")).toBe(true);
});
