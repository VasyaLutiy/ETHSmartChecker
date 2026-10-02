// Wiring and timers only: it calls api, feed and render. The DOM, the
// global fetch and the timer functions are named here and nowhere else in
// src/.

import "./style.css";

import type {
  ApiResult,
  ClustersPage,
  DashEvent,
  EventsPage,
  FetchLike,
  Health,
  Panel,
  Summary
} from "./api";
import { getClusters, getEvents, getHealth, getSummary } from "./api";
import { mergeEvents } from "./feed";
import { formatTime, originShares, statusOf } from "./format";
import type { OriginKey } from "./format";
import { renderClusters } from "./render/clusters";
import { renderEvents } from "./render/events";
import { renderHealth } from "./render/health";
import { renderSummary } from "./render/summary";

type KindFilter = "ALL" | "ALERT" | "UPGRADE";

export interface Clock {
  setInterval(fn: () => void, ms: number): number;
  clearInterval(id: number): void;
}

const defaultClock: Clock = {
  setInterval(fn: () => void, ms: number): number {
    // node's setInterval typing returns Timeout; the Clock contract is a number.
    return setInterval(fn, ms) as unknown as number;
  },
  clearInterval(id: number): void {
    clearInterval(id);
  }
};

const ZERO_ORIGINS: Record<OriginKey, number> = {
  created: 0,
  seen: 0,
  impl: 0,
  fetched: 0,
  unknown: 0
};

const LEGEND_ORDER: readonly string[] = originShares(ZERO_ORIGINS).map(
  (s) => s.origin
);

const FEED_HEAD: readonly string[] = [
  "kind",
  "time UTC",
  "block",
  "label",
  "score",
  "origin",
  "address"
];

interface PanelSpec {
  id: string;
  title: string;
  caption: string;
}

const PANELS: readonly PanelSpec[] = [
  { id: "health", title: "Listener", caption: "indexer progress, live or behind" },
  { id: "events", title: "Events", caption: "times UTC, newest first" },
  { id: "summary", title: "Summary", caption: "counters and origin shares" },
  { id: "clusters", title: "Impl clusters", caption: "addresses sharing an implementation" }
];

interface PanelRoots {
  health: HTMLElement;
  events: HTMLElement;
  summary: HTMLElement;
  clusters: HTMLElement;
}

function buildKindFilter(doc: Document): HTMLSelectElement {
  const select = doc.createElement("select");
  select.id = "kind-filter";
  const options: KindFilter[] = ["ALL", "ALERT", "UPGRADE"];
  for (const value of options) {
    const option = doc.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }
  select.value = "ALL";
  return select;
}

function buildPanels(doc: Document, host: HTMLElement): PanelRoots {
  const roots: PanelRoots = {
    health: doc.createElement("div"),
    events: doc.createElement("div"),
    summary: doc.createElement("div"),
    clusters: doc.createElement("div")
  };
  const byId = new Map<string, HTMLElement>([
    ["health", roots.health],
    ["events", roots.events],
    ["summary", roots.summary],
    ["clusters", roots.clusters]
  ]);
  for (const spec of PANELS) {
    const section = doc.createElement("section");
    section.className = "panel";
    section.id = spec.id;
    const title = doc.createElement("h2");
    title.className = "panel-title";
    title.textContent = spec.title;
    const caption = doc.createElement("p");
    caption.className = "panel-caption";
    caption.textContent = spec.caption;
    section.appendChild(title);
    section.appendChild(caption);
    section.appendChild(byId.get(spec.id) as HTMLElement);
    host.appendChild(section);
  }
  return roots;
}

export function start(
  doc: Document,
  fetchFn: FetchLike,
  clock: Clock = defaultClock
): () => void {
  const host = doc.getElementById("app") ?? doc.body;
  host.classList.add("dash");
  doc.title = "ethsc";

  const { health, events, summary, clusters } = buildPanels(doc, host);

  const select = buildKindFilter(doc);
  const feedMeta = doc.createElement("span");
  feedMeta.setAttribute("data-field", "feed-meta");
  feedMeta.textContent = "no events yet";
  const feedHead = doc.createElement("div");
  feedHead.className = "feed-head";
  for (const text of FEED_HEAD) {
    const cell = doc.createElement("span");
    cell.textContent = text;
    feedHead.appendChild(cell);
  }
  events.appendChild(select);
  events.appendChild(feedMeta);
  events.appendChild(feedHead);

  const legend = doc.createElement("ul");
  legend.className = "legend";
  for (const origin of LEGEND_ORDER) {
    const li = doc.createElement("li");
    li.setAttribute("data-legend", origin);
    li.textContent = origin;
    legend.appendChild(li);
  }
  summary.appendChild(legend);

  const healthPanel: Panel<Health> = { data: null, error: null };
  const summaryPanel: Panel<Summary> = { data: null, error: null };
  const clustersPanel: Panel<ClustersPage> = { data: null, error: null };
  let eventsError: string | null = null;

  let eventsKept: DashEvent[] = [];
  let after = 0;
  let kind: KindFilter = "ALL";

  let healthBusy = false;
  let eventsBusy = false;
  let summaryBusy = false;
  let clustersBusy = false;

  function applyEvents(): void {
    renderEvents(events, eventsKept, kind, eventsError);
    if (eventsKept.length === 0) {
      feedMeta.textContent = "no events yet";
    } else {
      feedMeta.textContent =
        String(eventsKept.length) +
        " events \u00B7 newest " +
        formatTime(eventsKept[0].at) +
        " UTC";
    }
  }

  async function pollHealth(): Promise<void> {
    if (healthBusy) {
      return;
    }
    healthBusy = true;
    const result: ApiResult<Health> = await getHealth(fetchFn);
    if (result.ok) {
      healthPanel.data = result.data;
      healthPanel.error = null;
      doc.title =
        statusOf(result.data.seconds_since_progress) +
        " \u00B7 " +
        String(result.data.progress) +
        " \u00B7 ethsc";
    } else {
      healthPanel.error = result.error;
      doc.title = "unreachable \u00B7 ethsc";
    }
    renderHealth(health, healthPanel);
    healthBusy = false;
  }

  async function pollEvents(): Promise<void> {
    if (eventsBusy) {
      return;
    }
    eventsBusy = true;
    const result: ApiResult<EventsPage> = await getEvents(after, fetchFn);
    if (result.ok) {
      after = result.data.last_id;
      eventsKept = mergeEvents(eventsKept, result.data.events, 500);
      eventsError = null;
    } else {
      eventsError = result.error;
    }
    applyEvents();
    eventsBusy = false;
  }

  async function pollSummary(): Promise<void> {
    if (summaryBusy) {
      return;
    }
    summaryBusy = true;
    const result: ApiResult<Summary> = await getSummary(fetchFn);
    if (result.ok) {
      summaryPanel.data = result.data;
      summaryPanel.error = null;
    } else {
      summaryPanel.error = result.error;
    }
    renderSummary(summary, summaryPanel);
    summaryBusy = false;
  }

  async function pollClusters(): Promise<void> {
    if (clustersBusy) {
      return;
    }
    clustersBusy = true;
    const result: ApiResult<ClustersPage> = await getClusters("impl", 20, fetchFn);
    if (result.ok) {
      clustersPanel.data = result.data;
      clustersPanel.error = null;
    } else {
      clustersPanel.error = result.error;
    }
    renderClusters(clusters, clustersPanel);
    clustersBusy = false;
  }

  function onFilterChange(): void {
    const value = select.value;
    if (value === "ALERT" || value === "UPGRADE") {
      kind = value;
    } else {
      kind = "ALL";
    }
    applyEvents();
  }

  select.addEventListener("change", onFilterChange);

  void (async () => {
    await pollHealth();
    await pollEvents();
    await pollSummary();
    await pollClusters();
  })();

  const idHealth = clock.setInterval(() => void pollHealth(), 5000);
  const idEvents = clock.setInterval(() => void pollEvents(), 5000);
  const idSummary = clock.setInterval(() => void pollSummary(), 30000);
  const idClusters = clock.setInterval(() => void pollClusters(), 60000);

  return function stop(): void {
    clock.clearInterval(idHealth);
    clock.clearInterval(idEvents);
    clock.clearInterval(idSummary);
    clock.clearInterval(idClusters);
  };
}

if (import.meta.env.MODE !== "test") {
  start(document, fetch);
}
