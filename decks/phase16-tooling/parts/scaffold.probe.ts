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
