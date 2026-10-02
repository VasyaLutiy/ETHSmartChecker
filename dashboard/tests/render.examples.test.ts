// Render Panels: the 11 Contour examples as one vitest test each, plus a
// few extra tests for rules of the behavior paragraph. Only the DOM
// contract of contour.yaml (group dashboard-ui, Function Render Panels)
// is asserted; values come from the fixtures verbatim.

import { describe, expect, test } from "vitest";

import {
  parseClusters,
  parseHealth,
  parseSummary,
  type ClustersPage,
  type DashEvent,
  type Health,
  type Panel,
  type Summary
} from "../src/api";
import { renderClusters } from "../src/render/clusters";
import { renderEvents } from "../src/render/events";
import { renderHealth } from "../src/render/health";
import { renderSummary } from "../src/render/summary";
import { UPGRADE_EVENT, fixtureEvents, loadFixture } from "./helpers";

// The helper's FixtureEvent types kind as string; the renderers take
// DashEvent[] (kind: Kind). Every fixture event is an ALERT, so the
// conversion holds.
function dashEvents(): DashEvent[] {
  return fixtureEvents() as unknown as DashEvent[];
}

function upgradeEvent(): DashEvent {
  return UPGRADE_EVENT as unknown as DashEvent;
}

function el(html: string): HTMLElement {
  const holder = document.createElement("div");
  holder.innerHTML = html;
  const root = holder.firstElementChild;
  if (root === null) {
    throw new Error("bad html fixture");
  }
  return root as HTMLElement;
}

function field(root: HTMLElement, name: string): Element {
  const found = root.querySelector('[data-field="' + name + '"]');
  if (found === null) {
    throw new Error("missing [data-field=" + name + "]");
  }
  return found;
}

function healthPanel(data: Health | null, error: string | null): Panel<Health> {
  return { data, error };
}

function summaryPanel(
  data: Summary | null,
  error: string | null
): Panel<Summary> {
  return { data, error };
}

function clustersPanel(
  data: ClustersPage | null,
  error: string | null
): Panel<ClustersPage> {
  return { data, error };
}

function healthFixture(): Health {
  const parsed = parseHealth(loadFixture("health"));
  if (parsed === null) {
    throw new Error("health fixture does not parse");
  }
  return parsed;
}

function summaryFixture(): Summary {
  const parsed = parseSummary(loadFixture("summary"));
  if (parsed === null) {
    throw new Error("summary fixture does not parse");
  }
  return parsed;
}

function clustersFixture(): ClustersPage {
  const parsed = parseClusters(loadFixture("clusters_impl"));
  if (parsed === null) {
    throw new Error("clusters fixture does not parse");
  }
  return parsed;
}

const EMPTY_SUMMARY: Summary = {
  addresses: 0,
  codes: 0,
  seeds: 0,
  implementations_resolved: 0,
  origins: { created: 0, seen: 0, impl: 0, fetched: 0, unknown: 0 },
  alerts_by_seed: [],
  recent: {
    blocks: 300,
    by_origin: { created: 0, seen: 0, impl: 0, fetched: 0, unknown: 0 }
  }
};

const FRESH_HEALTH: Health = {
  now: "2026-10-02T08:00:00Z",
  progress: null,
  progress_at: null,
  seconds_since_progress: null
};

describe("Render Panels", () => {
  // ex1
  test("Render Panels ex1: the health fixture renders its four fields", () => {
    const root = el('<div id="health"></div>');
    renderHealth(root, healthPanel(healthFixture(), null));
    expect(field(root, "progress").textContent).toBe("26103569");
    expect(field(root, "progress_at").textContent).toBe(
      "2026-10-02T08:53:15Z"
    );
    expect(field(root, "age").textContent).toBe("24 s");
    const status = field(root, "status");
    expect(status.textContent).toBe("live");
    expect(status.getAttribute("data-status")).toBe("live");
    expect(root.querySelectorAll(".unreachable").length).toBe(0);
  });

  // ex2
  test("Render Panels ex2: status behind, stalled and unknown", () => {
    const root = el('<div id="health"></div>');
    const withSeconds = (s: number | null): Health => ({
      ...healthFixture(),
      seconds_since_progress: s
    });
    renderHealth(root, healthPanel(withSeconds(75), null));
    expect(field(root, "status").textContent).toBe("behind");
    expect(field(root, "age").textContent).toBe("1 min");
    renderHealth(root, healthPanel(withSeconds(400), null));
    expect(field(root, "status").textContent).toBe("stalled");
    expect(field(root, "age").textContent).toBe("6 min");
    renderHealth(root, healthPanel(FRESH_HEALTH, null));
    expect(field(root, "status").textContent).toBe("unknown");
    expect(field(root, "age").textContent).toBe("n/a");
    expect(field(root, "progress").textContent).toBe("");
  });

  // ex3
  test("Render Panels ex3: an error shows unreachable and keeps the data", () => {
    const root = el('<div id="health"></div>');
    const data = healthFixture();
    renderHealth(root, healthPanel(data, "HTTP 500"));
    expect(root.querySelectorAll(".unreachable").length).toBe(1);
    const unreachable = root.querySelector(".unreachable");
    expect(unreachable?.textContent).toBe("backend unreachable");
    expect(field(root, "progress").textContent).toBe("26103569");
    renderHealth(root, healthPanel(data, null));
    expect(root.querySelectorAll(".unreachable").length).toBe(0);
    renderHealth(root, healthPanel(null, "Failed to fetch"));
    expect(root.querySelectorAll(".unreachable").length).toBe(1);
  });

  // ex4
  test("Render Panels ex4: the 8 fixture events render as rows, newest first", () => {
    const root = el('<div id="events"></div>');
    renderEvents(root, dashEvents(), "ALL", null);
    const rows = root.querySelectorAll("[data-id]");
    expect(rows.length).toBe(8);
    const ids: string[] = [];
    for (const row of rows) {
      ids.push(row.getAttribute("data-id") ?? "");
      expect(row.getAttribute("hidden")).toBeNull();
    }
    expect(ids).toEqual(["8", "7", "6", "5", "4", "3", "2", "1"]);
    const row8 = rows[0];
    expect(row8.getAttribute("data-kind")).toBe("ALERT");
    const badge = row8.querySelector('[data-badge="kind"]');
    expect(badge?.textContent).toBe("ALERT");
    expect(row8.querySelector('[data-badge="origin"]')?.textContent).toBe(
      "seen"
    );
    expect(row8.querySelector('[data-field="time"]')?.textContent).toBe(
      "08:47:50"
    );
    expect(row8.querySelector('[data-field="block"]')?.textContent).toBe(
      "26103541"
    );
    expect(row8.querySelector('[data-field="label"]')?.textContent).toBe(
      "LaunchToken family"
    );
    expect(row8.querySelector('[data-field="score"]')?.textContent).toBe(
      "1.0000"
    );
    const links = row8.querySelectorAll("a");
    expect(links.length).toBe(1);
    expect(links[0].getAttribute("href")).toBe(
      "https://etherscan.io/address/0x0be5cfbcbb8a82c8d44af544dd40261b967ab832"
    );
    expect(links[0].textContent).toBe("0x0be5…b832");
    expect(links[0].getAttribute("title")).toBe(
      "0x0be5cfbcbb8a82c8d44af544dd40261b967ab832"
    );
  });

  // ex5
  test("Render Panels ex5: the UPGRADE of id 9 renders three links and the arrow", () => {
    const root = el('<div id="events"></div>');
    renderEvents(root, [upgradeEvent()], "ALL", null);
    const rows = root.querySelectorAll("[data-id]");
    expect(rows.length).toBe(1);
    const row = rows[0];
    expect(row.getAttribute("data-kind")).toBe("UPGRADE");
    expect(row.querySelector('[data-badge="kind"]')?.textContent).toBe(
      "UPGRADE"
    );
    expect(row.querySelector('[data-badge="origin"]')).toBeNull();
    const links = row.querySelectorAll("a");
    expect(links.length).toBe(3);
    expect(links[0].getAttribute("href")).toBe(
      "https://etherscan.io/address/0x0c0105334a50db16b51b2911c9956539753a2cf8"
    );
    expect(links[1].getAttribute("href")).toBe(
      "https://etherscan.io/address/0x72b971717e088b59f26d4236be222adb6acd393b"
    );
    expect(links[2].getAttribute("href")).toBe(
      "https://etherscan.io/address/0xe440cc08a71694c8229323803f59024e3144630e"
    );
    expect(row.textContent).toContain("\u2192");
  });

  // ex6
  test("Render Panels ex6: rows are keyed by id and never rebuilt", () => {
    const root = el('<div id="events"></div>');
    renderEvents(root, dashEvents(), "ALL", null);
    const r8 = root.querySelector('[data-id="8"]');
    if (r8 === null) {
      throw new Error("row 8 missing");
    }
    const withNine = [upgradedTo9(), ...dashEvents()];
    renderEvents(root, withNine, "ALL", null);
    expect(root.querySelectorAll("[data-id]").length).toBe(9);
    expect(
      (root.querySelectorAll("[data-id]")[0] as Element).getAttribute("data-id")
    ).toBe("9");
    expect(root.querySelector('[data-id="8"]')).toBe(r8);
    const kept = withNine.slice(0, 7);
    renderEvents(root, kept, "ALL", null);
    expect(root.querySelectorAll("[data-id]").length).toBe(7);
    expect(root.querySelector('[data-id="8"]')).toBe(r8);
    expect(root.querySelector('[data-id="2"]')).toBeNull();
    expect(root.querySelector('[data-id="1"]')).toBeNull();
  });

  // ex7
  test("Render Panels ex7: the kind filter hides the other rows", () => {
    const root = el('<div id="events"></div>');
    const all = [upgradeEvent(), ...dashEvents()];
    renderEvents(root, all, "UPGRADE", null);
    expect(root.querySelectorAll("[data-id]").length).toBe(9);
    const visibleWhen = (kind: string): number => {
      let n = 0;
      for (const row of root.querySelectorAll("[data-id]")) {
        if (row.getAttribute("hidden") === null) {
          n += 1;
        } else {
          expect(row.getAttribute("data-kind")).not.toBe(kind);
        }
      }
      return n;
    };
    expect(visibleWhen("UPGRADE")).toBe(1);
    renderEvents(root, all, "ALERT", null);
    expect(visibleWhen("ALERT")).toBe(8);
    renderEvents(root, all, "ALL", null);
    expect(visibleWhen("ALL")).toBe(9);
  });

  // ex8
  test("Render Panels ex8: a hostile label stays text and the error shows", () => {
    const root = el('<div id="events"></div>');
    const hostile: DashEvent = {
      ...dashEvents()[0],
      label: '<img src=x onerror=alert(1)>'
    };
    renderEvents(root, [hostile], "ALL", "HTTP 503");
    expect(root.querySelectorAll(".unreachable").length).toBe(1);
    expect(root.querySelector(".unreachable")?.textContent).toBe(
      "backend unreachable"
    );
    expect(field(root as HTMLElement, "label").textContent).toBe(
      '<img src=x onerror=alert(1)>'
    );
    expect(root.querySelector("img")).toBeNull();
    expect(root.querySelectorAll("[data-id]").length).toBe(1);
  });

  // ex9
  test("Render Panels ex9: the summary fixture renders counters and bars", () => {
    const root = el('<div id="summary"></div>');
    renderSummary(root, summaryPanel(summaryFixture(), null));
    expect(field(root, "addresses").textContent).toBe("217009");
    expect(field(root, "codes").textContent).toBe("20374");
    expect(field(root, "seeds").textContent).toBe("8");
    expect(field(root, "implementations_resolved").textContent).toBe("454");
    const originsBar = root.querySelector('[data-bar="origins"]');
    if (originsBar === null) {
      throw new Error("no origins bar");
    }
    const origins = originsBar.querySelectorAll("[data-origin]");
    expect(origins.length).toBe(5);
    const order: string[] = [];
    for (const seg of origins) {
      order.push(seg.getAttribute("data-origin") ?? "");
    }
    expect(order).toEqual(["created", "seen", "impl", "fetched", "unknown"]);
    const seen = originsBar.querySelector('[data-origin="seen"]');
    expect(seen?.getAttribute("data-count")).toBe("19256");
    expect((seen as HTMLElement).style.width).toBe("8.9%");
    const recentBar = root.querySelector('[data-bar="recent"]');
    if (recentBar === null) {
      throw new Error("no recent bar");
    }
    const impl = recentBar.querySelector('[data-origin="impl"]');
    expect(impl?.getAttribute("data-count")).toBe("387");
    expect((impl as HTMLElement).style.width).toBe("13.5%");
    expect(
      (recentBar.querySelector('[data-origin="seen"]') as HTMLElement).style
        .width
    ).toBe("86%");
    expect(
      (recentBar.querySelector('[data-origin="unknown"]') as HTMLElement).style
        .width
    ).toBe("0%");
  });

  // ex10
  test("Render Panels ex10: the empty summary draws 0% bars and no NaN", () => {
    const root = el('<div id="summary"></div>');
    renderSummary(root, summaryPanel(EMPTY_SUMMARY, null));
    for (const bar of root.querySelectorAll("[data-bar]")) {
      for (const seg of bar.querySelectorAll("[data-origin]")) {
        expect((seg as HTMLElement).style.width).toBe("0%");
      }
    }
    expect(root.innerHTML).not.toContain("NaN");
    renderSummary(root, summaryPanel(EMPTY_SUMMARY, "HTTP 500"));
    expect(root.querySelectorAll(".unreachable").length).toBe(1);
    expect(field(root, "addresses").textContent).toBe("0");
  });

  // ex11
  test("Render Panels ex11: the clusters table, then an error keeps the rows", () => {
    const root = el('<div id="clusters"></div>');
    renderClusters(root, clustersPanel(clustersFixture(), null));
    const rows = root.querySelectorAll("[data-key]");
    expect(rows.length).toBe(20);
    const first = rows[0];
    expect(first.getAttribute("data-key")).toBe(
      "0x985462c9aa4d6c3ad59ae6e1e9c0c11347ed1598"
    );
    expect(field(first as HTMLElement, "members").textContent).toBe("14");
    const link = first.querySelector("a");
    expect(link?.getAttribute("href")).toBe(
      "https://etherscan.io/address/0x985462c9aa4d6c3ad59ae6e1e9c0c11347ed1598"
    );
    renderClusters(root, clustersPanel(clustersFixture(), "HTTP 500"));
    expect(root.querySelectorAll("[data-key]").length).toBe(20);
    expect(root.querySelectorAll(".unreachable").length).toBe(1);
  });

  // extra: behavior -- an unreachable error with no data draws no table
  test("Render Panels extra: clusters with error and null data shows only the unreachable line", () => {
    const root = el('<div id="clusters"></div>');
    renderClusters(root, clustersPanel(null, "Failed to fetch"));
    expect(root.querySelectorAll(".unreachable").length).toBe(1);
    expect(root.querySelector("[data-key]")).toBeNull();
  });

  // extra: behavior -- data is set through textContent/setAttribute only, no markup in fields
  test("Render Panels extra: events fields carry text, no element injection", () => {
    const root = el('<div id="events"></div>');
    const events = dashEvents();
    renderEvents(root, events, "ALL", null);
    for (const row of root.querySelectorAll("[data-id]")) {
      expect(row.querySelectorAll("img").length).toBe(0);
      expect(row.querySelectorAll("script").length).toBe(0);
    }
  });

  // extra: behavior -- every rendered row of an event has data-kind set
  test("Render Panels extra: every row carries data-kind matching its event", () => {
    const root = el('<div id="events"></div>');
    const events: DashEvent[] = dashEvents().concat([upgradeEvent()]);
    renderEvents(root, events, "ALL", null);
    for (const event of events) {
      const row = root.querySelector('[data-id="' + String(event.id) + '"]');
      expect(row?.getAttribute("data-kind")).toBe(event.kind);
    }
  });
});

// A copy of fixture event 8 with id 9 (Wire example 2 uses the same shape).
function upgradedTo9(): DashEvent {
  const base = dashEvents()[0];
  return { ...base, id: 9, block: 26103550 };
}
