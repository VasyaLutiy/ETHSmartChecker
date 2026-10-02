import { describe, expect, test, vi } from "vitest";

import {
  getClusters,
  getEvents,
  getHealth,
  getSummary,
  parseClusters,
  parseEvents,
  parseHealth,
  parseSummary
} from "../src/api";

import {
  fixtureEvents,
  fixtureFetch,
  fakeFetch,
  loadFixture
} from "./helpers";

function spyConsole() {
  return {
    error: vi.spyOn(console, "error").mockImplementation(() => {}),
    warn: vi.spyOn(console, "warn").mockImplementation(() => {})
  };
}

describe("Fetch Endpoints", () => {
  test("Fetch Endpoints ex1: parseHealth on the recorded health fixture", () => {
    const spies = spyConsole();
    const parsed = parseHealth(loadFixture("health"));
    expect(parsed).not.toBeNull();
    expect(parsed?.progress).toBe(26103569);
    expect(parsed?.progress_at).toBe("2026-10-02T08:53:15Z");
    expect(parsed?.seconds_since_progress).toBe(24);
    expect(parsed?.now).toBe("2026-10-02T08:53:39Z");
    expect(spies.error).not.toHaveBeenCalled();
    expect(spies.warn).not.toHaveBeenCalled();
  });

  test("Fetch Endpoints ex2: parseEvents on the recorded events fixture", () => {
    const spies = spyConsole();
    const parsed = parseEvents(loadFixture("events"));
    expect(parsed).not.toBeNull();
    expect(parsed?.last_id).toBe(8);
    expect(parsed?.events).toHaveLength(8);
    expect(parsed?.events.map((e) => e.id)).toEqual([8, 7, 6, 5, 4, 3, 2, 1]);
    const first = parsed?.events[0];
    expect(first?.kind).toBe("ALERT");
    expect(first?.block).toBe(26103541);
    expect(first?.at).toBe("2026-10-02T08:47:50Z");
    expect(first?.address).toBe("0x0be5cfbcbb8a82c8d44af544dd40261b967ab832");
    expect(first?.label).toBe("LaunchToken family");
    expect(first?.score).toBe(1);
    expect(first?.origin).toBe("seen");
    expect(first?.seed_address).toBe(
      "0x0312eaa7791b5b15a12157b2a6e01d8e30c8b1b6"
    );
    expect(first?.old_impl).toBeNull();
    expect(first?.new_impl).toBeNull();
    expect(spies.error).not.toHaveBeenCalled();
    expect(spies.warn).not.toHaveBeenCalled();
  });

  test("Fetch Endpoints ex3: parseSummary on the recorded summary fixture", () => {
    const spies = spyConsole();
    const parsed = parseSummary(loadFixture("summary"));
    expect(parsed).not.toBeNull();
    expect(parsed?.addresses).toBe(217009);
    expect(parsed?.codes).toBe(20374);
    expect(parsed?.seeds).toBe(8);
    expect(parsed?.implementations_resolved).toBe(454);
    expect(parsed?.origins).toEqual({
      created: 109,
      fetched: 0,
      impl: 387,
      seen: 19256,
      unknown: 197257
    });
    expect(parsed?.alerts_by_seed).toEqual([
      {
        count: 8,
        label: "LaunchToken family",
        seed_address: "0x0312eaa7791b5b15a12157b2a6e01d8e30c8b1b6"
      }
    ]);
    expect(parsed?.recent.blocks).toBe(300);
    expect(parsed?.recent.by_origin).toEqual({
      created: 16,
      fetched: 0,
      impl: 387,
      seen: 2474,
      unknown: 0
    });
    expect(spies.error).not.toHaveBeenCalled();
    expect(spies.warn).not.toHaveBeenCalled();
  });

  test("Fetch Endpoints ex4: parseClusters on the recorded impl-clusters fixture", () => {
    const spies = spyConsole();
    const parsed = parseClusters(loadFixture("clusters_impl"));
    expect(parsed).not.toBeNull();
    expect(parsed?.level).toBe("impl");
    expect(parsed?.n).toBe(20);
    expect(parsed?.clusters).toHaveLength(20);
    const first = parsed?.clusters[0];
    expect(first?.level).toBe("impl");
    expect(first?.key).toBe("0x985462c9aa4d6c3ad59ae6e1e9c0c11347ed1598");
    expect(first?.members).toHaveLength(14);
    expect(first?.members[0]).toBe(
      "0x0752163d221d3d5d4b6e98bd616b22bd2b453964"
    );
    expect(parsed?.clusters.map((c) => c.members.length)).toEqual([
      14, 8, 5, 4, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2, 2
    ]);
    expect(spies.error).not.toHaveBeenCalled();
    expect(spies.warn).not.toHaveBeenCalled();
  });

  test("Fetch Endpoints ex5: the parsers accept the fresh-db answers", () => {
    const spies = spyConsole();
    const health = parseHealth({
      now: "2026-10-02T08:00:00Z",
      progress: null,
      progress_at: null,
      seconds_since_progress: null
    });
    expect(health).not.toBeNull();
    expect(health?.progress).toBeNull();
    expect(health?.seconds_since_progress).toBeNull();

    const events = parseEvents({ events: [], last_id: 0 });
    expect(events).not.toBeNull();
    expect(events?.events).toEqual([]);
    expect(events?.last_id).toBe(0);

    const summary = parseSummary({
      addresses: 0,
      codes: 0,
      seeds: 0,
      implementations_resolved: 0,
      origins: { created: 0, fetched: 0, impl: 0, seen: 0, unknown: 0 },
      alerts_by_seed: [],
      recent: {
        blocks: 300,
        by_origin: { created: 0, fetched: 0, impl: 0, seen: 0, unknown: 0 }
      }
    });
    expect(summary).not.toBeNull();
    expect(summary?.addresses).toBe(0);
    expect(summary?.recent.by_origin.seen).toBe(0);
    expect(spies.error).not.toHaveBeenCalled();
    expect(spies.warn).not.toHaveBeenCalled();
  });

  test("Fetch Endpoints ex6: malformed values give null without throwing or logging", () => {
    const spies = spyConsole();

    const health = loadFixture("health") as Record<string, unknown>;
    expect(parseHealth({ ...health, progress: "x" })).toBeNull();
    const noNow = { ...health };
    delete noNow.now;
    expect(parseHealth(noNow)).toBeNull();

    const events = loadFixture("events") as {
      events: Record<string, unknown>[];
    };
    const withBadKind = {
      events: events.events.map((e, i) =>
        i === 3 ? { ...e, kind: "FOO" } : e
      ),
      last_id: 8
    };
    expect(parseEvents(withBadKind)).toBeNull();
    expect(parseEvents({ events: [] })).toBeNull();

    const summary = loadFixture("summary") as {
      origins: Record<string, unknown>;
    };
    const noUnknown = JSON.parse(JSON.stringify(summary)) as typeof summary;
    delete noUnknown.origins.unknown;
    expect(parseSummary(noUnknown)).toBeNull();

    const clusters = loadFixture("clusters_impl") as {
      clusters: { members: unknown }[];
    };
    const badMembers = JSON.parse(JSON.stringify(clusters)) as typeof clusters;
    badMembers.clusters[0].members = "x";
    expect(parseClusters(badMembers)).toBeNull();

    expect(parseHealth(null)).toBeNull();
    expect(parseHealth(42)).toBeNull();
    expect(parseHealth("x")).toBeNull();
    expect(parseHealth([])).toBeNull();
    expect(parseEvents(null)).toBeNull();
    expect(parseEvents(42)).toBeNull();
    expect(parseEvents("x")).toBeNull();
    expect(parseEvents([])).toBeNull();
    expect(parseSummary(null)).toBeNull();
    expect(parseSummary(42)).toBeNull();
    expect(parseSummary("x")).toBeNull();
    expect(parseSummary([])).toBeNull();
    expect(parseClusters(null)).toBeNull();
    expect(parseClusters(42)).toBeNull();
    expect(parseClusters("x")).toBeNull();
    expect(parseClusters([])).toBeNull();

    expect(spies.error).not.toHaveBeenCalled();
    expect(spies.warn).not.toHaveBeenCalled();
  });

  test("Fetch Endpoints ex7: the fetchers hit the four URLs and parse the fixtures", async () => {
    const f = fixtureFetch();
    const health = await getHealth(f.fetch);
    const events = await getEvents(0, f.fetch);
    const summary = await getSummary(f.fetch);
    const clusters = await getClusters("impl", 20, f.fetch);
    expect(health.ok).toBe(true);
    expect(events.ok).toBe(true);
    expect(summary.ok).toBe(true);
    expect(clusters.ok).toBe(true);
    if (health.ok) expect(health.data.progress).toBe(26103569);
    if (events.ok) {
      expect(events.data.last_id).toBe(8);
      expect(events.data.events).toHaveLength(8);
    }
    if (summary.ok) expect(summary.data.codes).toBe(20374);
    if (clusters.ok) expect(clusters.data.clusters).toHaveLength(20);
    expect(f.calls).toEqual([
      "/api/health",
      "/api/events?after=0&limit=500",
      "/api/summary",
      "/api/clusters?level=impl&n=20"
    ]);
  });

  test("Fetch Endpoints ex8: every failure path gives ok false, one line, no throw", async () => {
    const spies = spyConsole();

    const rejected = fakeFetch();
    rejected.failAll(new TypeError("Failed to fetch"));
    const a = await getHealth(rejected.fetch);
    const a2 = await getEvents(0, rejected.fetch);
    const a3 = await getSummary(rejected.fetch);
    const a4 = await getClusters("impl", 20, rejected.fetch);
    expect(a.ok).toBe(false);
    expect(a2.ok).toBe(false);
    expect(a3.ok).toBe(false);
    expect(a4.ok).toBe(false);

    const b = await getHealth(
      fakeFetch({ "/api/health": { status: 500, body: { error: "boom" } } })
        .fetch
    );
    expect(b.ok).toBe(false);
    expect(b.ok === false && b.error.includes("500")).toBe(true);

    const c = await getSummary(
      fakeFetch({ "/api/summary": { jsonError: true } }).fetch
    );
    expect(c.ok).toBe(false);

    const d = await getClusters(
      "impl",
      20,
      fakeFetch({ "/api/clusters?level=impl&n=20": { body: { x: 1 } } }).fetch
    );
    expect(d.ok).toBe(false);

    for (const r of [a, a2, a3, a4, b, c, d]) {
      expect(r.ok === false && r.error.length > 0).toBe(true);
      expect(r.ok === false && r.error.includes("\n")).toBe(false);
    }
    expect(spies.error).not.toHaveBeenCalled();
    expect(spies.warn).not.toHaveBeenCalled();
  });

  test("rule: getEvents(8) requests after=8", async () => {
    const f = fixtureFetch();
    await getEvents(8, f.fetch);
    expect(f.calls).toEqual(["/api/events?after=8&limit=500"]);
  });

  test("rule: a non-2xx status is refused, whatever its body", async () => {
    for (const status of [199, 300, 404, 502]) {
      const f = fakeFetch({ "/api/health": { status, body: {} } });
      const r = await getHealth(f.fetch);
      expect(r.ok).toBe(false);
    }
    const okish = fakeFetch({ "/api/health": { status: 201, body: {} } });
    const r = await getHealth(okish.fetch);
    expect(r.ok).toBe(false);
  });

  test("rule: a kind outside ALERT/UPGRADE is refused, a valid one accepted", () => {
    const base = fixtureEvents()[0];
    expect(
      parseEvents({ events: [{ ...base, kind: "FOO" }], last_id: 0 })
    ).toBeNull();
    expect(
      parseEvents({ events: [{ ...base, kind: "UPGRADE" }], last_id: 0 })
    ).not.toBeNull();
  });

  test("rule: an event with a missing key is refused", () => {
    const base = fixtureEvents()[0];
    const partial: Record<string, unknown> = { ...base };
    delete partial.block;
    expect(parseEvents({ events: [partial], last_id: 0 })).toBeNull();
  });

  test("rule: each fetcher makes exactly one call to the fetchFn it is given", async () => {
    const f = fixtureFetch();
    await getHealth(f.fetch);
    await getEvents(0, f.fetch);
    await getSummary(f.fetch);
    await getClusters("impl", 20, f.fetch);
    expect(f.calls).toHaveLength(4);
  });

  test("rule: a rejected json() and a refused body are the same {ok: false} shape", async () => {
    const c = fakeFetch({ "/api/health": { jsonError: true } });
    const rej = await getHealth(c.fetch);
    const d = fakeFetch({ "/api/health": { body: { x: 1 } } });
    const bad = await getHealth(d.fetch);
    expect(rej.ok).toBe(false);
    expect(bad.ok).toBe(false);
    if (!rej.ok && !bad.ok) {
      expect(typeof rej.error).toBe("string");
      expect(typeof bad.error).toBe("string");
      expect(rej.error).not.toBe("");
      expect(bad.error).not.toBe("");
    }
  });

  test("rule: the status error text names the status", async () => {
    for (const status of [404, 500, 503]) {
      const f = fakeFetch({ "/api/health": { status, body: { error: "x" } } });
      const r = await getHealth(f.fetch);
      expect(r.ok === false && r.error.includes(String(status))).toBe(true);
    }
  });

  test("rule: an events page whose middle event is bad is refused whole", () => {
    const events = fixtureEvents();
    const withNull = [...events];
    (withNull as unknown[])[3] = null;
    expect(parseEvents({ events: withNull, last_id: 8 })).toBeNull();
    expect(parseEvents({ events, last_id: "8" })).toBeNull();
  });

  test("rule: origin counts require all five keys with numbers", () => {
    const base = loadFixture("summary") as Record<string, unknown>;
    const partial = JSON.parse(JSON.stringify(base)) as {
      recent: { by_origin: Record<string, unknown> };
    };
    delete partial.recent.by_origin.created;
    expect(parseSummary(partial)).toBeNull();
    const nan = JSON.parse(JSON.stringify(base)) as {
      origins: Record<string, unknown>;
    };
    nan.origins.seen = "19256";
    expect(parseSummary(nan)).toBeNull();
  });

  test("rule: clusters pages with a bad level, n or cluster shape are refused", () => {
    const base = loadFixture("clusters_impl") as Record<string, unknown>;
    expect(parseClusters({ ...base, level: 7 })).toBeNull();
    expect(parseClusters({ ...base, n: "20" })).toBeNull();
    expect(parseClusters({ ...base, clusters: "x" })).toBeNull();
    expect(parseClusters({ ...base, clusters: [1, 2] })).toBeNull();
  });
});
