// dashboard/tests/main.examples.test.ts -- Wire Page (group dashboard-ui):
// one vitest test per Contour example, named "Wire Page ex<N>", plus extra
// tests for rules of the behavior paragraph. start() is called with a fresh
// happy-dom document, a fetch from ./helpers and a fake clock; nothing here
// names the real timers, the real fetch or the network.

import { describe, expect, test, vi } from "vitest";

import { start } from "../src/main";

import {
  UPGRADE_EVENT,
  fakeClock,
  fixtureEvents,
  fixtureFetch,
  flush,
  loadFixture
} from "./helpers";

const EVENTS_URL_0 = "/api/events?after=0&limit=500";

function freshDoc(): Document {
  document.body.innerHTML = '<div id="app"></div>';
  return document;
}

function rows(root: Element, selector: string): Element[] {
  return Array.from(root.querySelectorAll(selector));
}

describe("Wire Page", () => {
  test("Wire Page ex1: initial requests, panels, filter and intervals", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    const stop = start(doc, f.fetch, clock);
    await flush();

    // the four panels and the select exist inside #app
    const app = doc.getElementById("app");
    expect(app).not.toBeNull();
    expect(app!.querySelector("#health")).not.toBeNull();
    expect(app!.querySelector("#events")).not.toBeNull();
    expect(app!.querySelector("#summary")).not.toBeNull();
    expect(app!.querySelector("#clusters")).not.toBeNull();
    const select = app!.querySelector("select#kind-filter") as HTMLSelectElement;
    expect(select).not.toBeNull();
    expect(Array.from(select.options).map((o) => o.value)).toEqual([
      "ALL",
      "ALERT",
      "UPGRADE"
    ]);
    expect(select.value).toBe("ALL");

    // the recorded URLs are exactly the four, in this order
    expect(f.calls).toEqual([
      "/api/health",
      EVENTS_URL_0,
      "/api/summary",
      "/api/clusters?level=impl&n=20"
    ]);

    // exactly four intervals, delays [5000, 5000, 30000, 60000]
    expect(clock.timers.map((t) => t.ms).sort((a, b) => a - b)).toEqual([
      5000, 5000, 30000, 60000
    ]);

    // the panels are rendered
    const health = app!.querySelector("#health")!;
    expect(
      health.querySelector('[data-field="progress"]')!.textContent
    ).toBe("26103569");
    expect(rows(app!.querySelector("#events")!, "[data-id]")).toHaveLength(8);
    expect(rows(app!.querySelector("#clusters")!, "[data-key]")).toHaveLength(20);

    stop();
  });

  test("Wire Page ex2: polled with after=<last_id>, appended without reloading", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    const e8 = fixtureEvents().find((e) => e.id === 8);
    expect(e8).toBeDefined();
    const next = { ...e8!, id: 9, block: 26103550 };
    f.set("/api/events?after=8&limit=500", {
      body: { events: [next], last_id: 9 }
    });

    start(doc, f.fetch, clock);
    await flush();

    const eventsEl = doc.getElementById("events")!;
    const r8 = eventsEl.querySelector('[data-id="8"]') as HTMLElement;
    expect(r8).not.toBeNull();

    clock.fire(5000);
    await flush();

    expect(f.calls).toContain("/api/events?after=8&limit=500");
    const ids = rows(eventsEl, "[data-id]").map((r) => r.getAttribute("data-id"));
    expect(ids).toEqual(["9", "8", "7", "6", "5", "4", "3", "2", "1"]);
    expect(eventsEl.querySelector('[data-id="8"]')).toBe(r8);

    clock.fire(5000);
    await flush();
    expect(f.calls).toContain("/api/events?after=9&limit=500");
  });

  test("Wire Page ex3: a failed poll shows backend unreachable and keeps the data", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();
    const errSpy = vi.spyOn(console, "error");
    const warnSpy = vi.spyOn(console, "warn");

    start(doc, f.fetch, clock);
    await flush();

    f.failAll(new TypeError("Failed to fetch"));
    clock.fire();
    await flush();

    for (const id of ["health", "events", "summary", "clusters"]) {
      const panel = doc.getElementById(id)!;
      const unreachable = panel.querySelectorAll(".unreachable");
      expect(unreachable).toHaveLength(1);
      expect(unreachable[0].textContent).toBe("backend unreachable");
    }
    // the last good data is kept
    expect(
      doc
        .getElementById("health")!
        .querySelector('[data-field="progress"]')!.textContent
    ).toBe("26103569");
    expect(rows(doc.getElementById("events")!, "[data-id]")).toHaveLength(8);
    expect(rows(doc.getElementById("clusters")!, "[data-key]")).toHaveLength(20);

    expect(errSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
    errSpy.mockRestore();
    warnSpy.mockRestore();
  });

  test("Wire Page ex4: the kind filter re-renders without fetching", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    f.set("/api/events?after=8&limit=500", {
      body: { events: [UPGRADE_EVENT], last_id: 9 }
    });

    start(doc, f.fetch, clock);
    await flush();

    clock.fire(5000);
    await flush();
    expect(rows(doc.getElementById("events")!, "[data-id]")).toHaveLength(9);

    const select = doc.querySelector("select#kind-filter") as HTMLSelectElement;
    const callsBefore = f.calls.length;
    select.value = "UPGRADE";
    select.dispatchEvent(new Event("change"));
    await flush();

    // no new URL is recorded
    expect(f.calls).toHaveLength(callsBefore);

    // only the UPGRADE row is visible
    const visible = rows(doc.getElementById("events")!, "[data-id]").filter(
      (r) => !(r as HTMLElement).hidden
    );
    expect(visible).toHaveLength(1);
    expect(visible[0].getAttribute("data-id")).toBe("9");
    expect(visible[0].getAttribute("data-kind")).toBe("UPGRADE");
  });

  test("Wire Page ex5: stop clears the four intervals", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    const stop = start(doc, f.fetch, clock);
    await flush();

    stop();
    expect(clock.cleared).toEqual([1, 2, 3, 4]);
  });

  test("Wire Page ex6 (extra): a poll whose predecessor is still pending is skipped", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    start(doc, f.fetch, clock);
    // two firings before any promise resolves: the second is skipped
    clock.fire(5000);
    clock.fire(5000);
    await flush();

    expect(f.calls.filter((u) => u === "/api/health")).toHaveLength(1);
    expect(f.calls.filter((u) => u === EVENTS_URL_0)).toHaveLength(1);
  });

  test("Wire Page ex7 (extra): an events poll with nothing new keeps the list and the cursor", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    f.set("/api/events?after=8&limit=500", { body: { events: [], last_id: 8 } });

    start(doc, f.fetch, clock);
    await flush();
    expect(rows(doc.getElementById("events")!, "[data-id]")).toHaveLength(8);

    clock.fire(5000);
    await flush();
    expect(f.calls).toContain("/api/events?after=8&limit=500");
    expect(rows(doc.getElementById("events")!, "[data-id]")).toHaveLength(8);

    // the next poll still asks after=8
    const lastEvents = f.calls.filter((u) => u.startsWith("/api/events?"));
    expect(lastEvents).toEqual([EVENTS_URL_0, "/api/events?after=8&limit=500"]);
  });

  test("Wire Page ex8 (extra): the ALERT filter hides the UPGRADE row", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    f.set("/api/events?after=8&limit=500", {
      body: { events: [UPGRADE_EVENT], last_id: 9 }
    });
    start(doc, f.fetch, clock);
    await flush();
    clock.fire(5000);
    await flush();

    const select = doc.querySelector("select#kind-filter") as HTMLSelectElement;
    const callsBefore = f.calls.length;
    select.value = "ALERT";
    select.dispatchEvent(new Event("change"));
    await flush();

    expect(f.calls).toHaveLength(callsBefore);
    const all = rows(doc.getElementById("events")!, "[data-id]");
    expect(all).toHaveLength(9);
    const visible = all.filter((r) => !(r as HTMLElement).hidden);
    expect(visible).toHaveLength(8);
    expect(visible.every((r) => r.getAttribute("data-kind") === "ALERT")).toBe(
      true
    );
  });

  test("Wire Page ex9 (extra): the filter choice persists across polls", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    start(doc, f.fetch, clock);
    await flush();

    const select = doc.querySelector("select#kind-filter") as HTMLSelectElement;
    select.value = "UPGRADE";
    select.dispatchEvent(new Event("change"));

    // a new ALERT arrives by poll; it must render hidden
    const e8 = fixtureEvents().find((e) => e.id === 8)!;
    const next = { ...e8, id: 10, block: 26103560 };
    f.set("/api/events?after=8&limit=500", {
      body: { events: [next], last_id: 10 }
    });
    clock.fire(5000);
    await flush();

    const row10 = doc.getElementById("events")!.querySelector(
      '[data-id="10"]'
    ) as HTMLElement;
    expect(row10).not.toBeNull();
    expect(row10.hidden).toBe(true);
  });

  test("Wire Page ex10 (extra): the panels are appended inside #app in order", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    start(doc, f.fetch, clock);
    await flush();

    const app = doc.getElementById("app")!;
    const ids = Array.from(app.children).map((c) => c.id);
    expect(ids).toEqual(["health", "events", "summary", "clusters"]);
  });

  test("Wire Page ex11 (extra): exactly four intervals are registered", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    start(doc, f.fetch, clock);
    await flush();
    expect(clock.timers).toHaveLength(4);
  });

  test("Wire Page ex12 (extra): the summary panel renders the fixture counters", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    start(doc, f.fetch, clock);
    await flush();

    const summary = doc.getElementById("summary")!;
    expect(summary.querySelector('[data-field="addresses"]')!.textContent).toBe(
      "217009"
    );
    expect(summary.querySelector('[data-field="codes"]')!.textContent).toBe(
      "20374"
    );
    expect(summary.querySelector('[data-field="seeds"]')!.textContent).toBe("8");
    const bar = summary.querySelector('[data-bar="origins"]')!;
    expect(rows(bar, "[data-origin]").map((s) => s.getAttribute("data-origin"))).toEqual(
      ["created", "seen", "impl", "fetched", "unknown"]
    );
  });

  test("Wire Page ex13 (extra): the health strip reads the fixture heartbeat", async () => {
    const doc = freshDoc();
    const f = fixtureFetch();
    const clock = fakeClock();

    start(doc, f.fetch, clock);
    await flush();

    const health = doc.getElementById("health")!;
    expect(
      health.querySelector('[data-field="progress_at"]')!.textContent
    ).toBe(loadHealth().progress_at);
    expect(health.querySelector('[data-field="status"]')!.textContent).toBe(
      "live"
    );
  });
});

function loadHealth(): { progress_at: string | null } {
  return loadFixture("health") as { progress_at: string | null };
}
