import { describe, expect, test, vi } from "vitest";

import { start } from "../src/main";
import type { Clock } from "../src/main";
import {
  UPGRADE_EVENT,
  fakeClock,
  fakeFetch,
  fixtureFetch,
  flush,
  loadFixture
} from "./helpers";
import type { FakeFetch } from "./helpers";

interface Setup {
  app: HTMLElement;
  ff: FakeFetch;
  clock: ReturnType<typeof fakeClock>;
  stop: () => void;
}

function freshApp(): HTMLElement {
  // a fresh page: drop any earlier #app so getElementById finds this one
  document.body.replaceChildren();
  const app = document.createElement("div");
  app.id = "app";
  document.body.appendChild(app);
  return app;
}

function setup(ff: FakeFetch): Setup {
  const app = freshApp();
  const clock = fakeClock();
  const stop = start(document, ff.fetch, clock as unknown as Clock);
  return { app, ff, clock, stop };
}

function healthWith(seconds: number): { body: unknown } {
  const base = loadFixture("health") as Record<string, unknown>;
  return { body: { ...base, seconds_since_progress: seconds } };
}

function precedes(a: Element, b: Element): boolean {
  return (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
}

const panelTitles: ReadonlyArray<[string, string]> = [
  ["health", "Listener"],
  ["events", "Events"],
  ["summary", "Summary"],
  ["clusters", "Impl clusters"]
];

const HEAD_TEXTS = ["kind", "time UTC", "block", "label", "score", "origin", "address"];
const LEGEND_ORDER = ["created", "seen", "impl", "fetched", "unknown"];

describe("Wire Page phase 17 (layout)", () => {
  test("Wire Page ex6: panel structure, titles, select place, feed head, legend", async () => {
    const { app, stop } = setup(fixtureFetch());
    await flush();

    expect(app.classList.contains("dash")).toBe(true);
    const sections = Array.from(app.children);
    expect(sections.length).toBe(4);
    expect(sections.map((s) => (s as HTMLElement).id)).toEqual([
      "health",
      "events",
      "summary",
      "clusters"
    ]);
    for (const section of sections) {
      expect(section.tagName).toBe("SECTION");
      expect(section.classList.contains("panel")).toBe(true);
    }
    for (const [id, title] of panelTitles) {
      const section = document.getElementById(id) as HTMLElement;
      const first = section.children[0] as HTMLElement;
      expect(first.tagName).toBe("H2");
      expect(first.classList.contains("panel-title")).toBe(true);
      expect(first.textContent).toBe(title);
    }

    const eventsPanel = document.getElementById("events") as HTMLElement;
    const select = eventsPanel.querySelector("select#kind-filter") as Element;
    expect(select).not.toBeNull();
    const list = eventsPanel.querySelector('[data-role="list"]') as Element;
    expect(list).not.toBeNull();
    expect(eventsPanel.contains(select)).toBe(true);
    expect(precedes(select, list)).toBe(true);

    const head = eventsPanel.querySelector(".feed-head") as Element;
    expect(head).not.toBeNull();
    const headTexts = Array.from(head.children).map((c) => c.textContent);
    expect(headTexts).toEqual(HEAD_TEXTS);

    const summaryPanel = document.getElementById("summary") as HTMLElement;
    const legend = summaryPanel.querySelector("ul.legend") as Element;
    expect(legend).not.toBeNull();
    const legends = Array.from(legend.querySelectorAll("li[data-legend]"));
    expect(legends.map((li) => li.getAttribute("data-legend"))).toEqual(LEGEND_ORDER);
    expect(legends.map((li) => li.textContent)).toEqual(LEGEND_ORDER);
    stop();
  });

  test("Wire Page ex7: feed-meta counts and newest time, or 'no events yet'", async () => {
    const first = setup(fixtureFetch());
    await flush();
    const meta = document.querySelector('[data-field="feed-meta"]') as Element;
    expect(meta.textContent).toBe("8 events \u00B7 newest 08:47:50 UTC");
    first.stop();

    const second = setup(
      fakeFetch({
        "/api/health": { body: loadFixture("health") },
        "/api/events?after=0&limit=500": { body: { events: [], last_id: 0 } },
        "/api/summary": { body: loadFixture("summary") },
        "/api/clusters?level=impl&n=20": { body: loadFixture("clusters_impl") }
      })
    );
    await flush();
    const meta2 = document.querySelector('[data-field="feed-meta"]') as Element;
    expect(meta2.textContent).toBe("no events yet");
    second.stop();
  });

  test("Wire Page ex8: title 'live · …' after good health, 'unreachable · …' after a failed one", async () => {
    const { ff, clock, stop } = setup(fixtureFetch());
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    await flush();
    expect(document.title).toBe("live \u00B7 26103569 \u00B7 ethsc");

    ff.failAll(new TypeError("Failed to fetch"));
    clock.fire(5000);
    await flush();
    expect(document.title).toBe("unreachable \u00B7 ethsc");

    ff.failAll(null);
    clock.fire(5000);
    await flush();
    expect(document.title).toBe("live \u00B7 26103569 \u00B7 ethsc");
    expect(errSpy).not.toHaveBeenCalled();
    errSpy.mockRestore();
    stop();
  });

  test("Wire Page ex9: title 'stalled · …' for 300 s or more since progress; 'ethsc' before the first answer", async () => {
    freshApp();
    const clock = fakeClock();
    const ff = fakeFetch({
      "/api/health": healthWith(400),
      "/api/events?after=0&limit=500": { body: loadFixture("events") },
      "/api/summary": { body: loadFixture("summary") },
      "/api/clusters?level=impl&n=20": { body: loadFixture("clusters_impl") }
    });
    const stop = start(document, ff.fetch, clock as unknown as Clock);
    expect(document.title).toBe("ethsc");
    await flush();
    expect(document.title).toBe("stalled \u00B7 26103569 \u00B7 ethsc");
    stop();
  });

  test("Wire Page ex10 (extra): feed-meta updates after an events poll appends an event", async () => {
    const { ff, clock, stop } = setup(fixtureFetch());
    await flush();
    const meta = document.querySelector('[data-field="feed-meta"]') as Element;
    expect(meta.textContent).toBe("8 events \u00B7 newest 08:47:50 UTC");

    ff.set("/api/events?after=8&limit=500", {
      body: { events: [{ ...UPGRADE_EVENT }], last_id: 9 }
    });
    clock.fire(5000);
    await flush();
    expect(meta.textContent).toBe("9 events \u00B7 newest 08:00:00 UTC");
    stop();
  });

  test("Wire Page ex11 (extra): feed-meta reads 'no events yet' before the first events answer", async () => {
    const { stop } = setup(fixtureFetch());
    const meta = document.querySelector('[data-field="feed-meta"]') as Element;
    expect(meta.textContent).toBe("no events yet");
    stop();
  });

  test("Wire Page ex12 (extra): each panel has exactly one caption after its title", async () => {
    const { stop } = setup(fixtureFetch());
    await flush();
    for (const [id] of panelTitles) {
      const section = document.getElementById(id) as HTMLElement;
      expect(section.children[0].tagName).toBe("H2");
      const captions = section.querySelectorAll("p.panel-caption");
      expect(captions.length).toBe(1);
      expect(section.children[1]).toBe(captions[0]);
      expect((captions[0] as HTMLElement).textContent?.length).toBeGreaterThan(0);
    }
    stop();
  });

  test("Wire Page ex13 (extra): title goes 'behind' for 60..299 s since progress", async () => {
    const ff = fakeFetch({
      "/api/health": healthWith(200),
      "/api/events?after=0&limit=500": { body: loadFixture("events") },
      "/api/summary": { body: loadFixture("summary") },
      "/api/clusters?level=impl&n=20": { body: loadFixture("clusters_impl") }
    });
    const { stop } = setup(ff);
    await flush();
    expect(document.title).toBe("behind \u00B7 26103569 \u00B7 ethsc");
    stop();
  });

  test("Wire Page ex14 (extra): feed-head precedes the renderer's list in #events", async () => {
    const { stop } = setup(fixtureFetch());
    await flush();
    const eventsPanel = document.getElementById("events") as HTMLElement;
    const head = eventsPanel.querySelector(".feed-head") as Element;
    const list = eventsPanel.querySelector('[data-role="list"]') as Element;
    expect(head).not.toBeNull();
    expect(list).not.toBeNull();
    expect(precedes(head, list)).toBe(true);
    stop();
  });

  test("Wire Page ex15 (extra): legend sits before the renderer's data in #summary", async () => {
    const { stop } = setup(fixtureFetch());
    await flush();
    const summaryPanel = document.getElementById("summary") as HTMLElement;
    const legend = summaryPanel.querySelector("ul.legend") as Element;
    const data = summaryPanel.querySelector('[data-role="data"]') as Element;
    expect(data).not.toBeNull();
    expect(precedes(legend, data)).toBe(true);
    stop();
  });

  test("Wire Page ex16 (extra): the four intervals are on the clock, stop clears them", async () => {
    const { clock, stop } = setup(fixtureFetch());
    await flush();
    expect(clock.timers.map((t) => t.ms).sort((a, b) => a - b)).toEqual([
      5000, 5000, 30000, 60000
    ]);
    stop();
    expect(clock.cleared.sort((a, b) => a - b)).toEqual([1, 2, 3, 4]);
  });
});
