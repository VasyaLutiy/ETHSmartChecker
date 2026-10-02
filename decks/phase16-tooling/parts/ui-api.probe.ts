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
