// Wiring and timers only: it calls api, feed and render. The DOM, the
// global fetch and the timer functions are named here and nowhere else in
// src/.

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

function divWithId(doc: Document, id: string): HTMLElement {
  const el = doc.createElement("div");
  el.id = id;
  return el;
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

export function start(
  doc: Document,
  fetchFn: FetchLike,
  clock: Clock = defaultClock
): () => void {
  const host = doc.getElementById("app") ?? doc.body;

  const healthEl = divWithId(doc, "health");
  const eventsEl = divWithId(doc, "events");
  const summaryEl = divWithId(doc, "summary");
  const clustersEl = divWithId(doc, "clusters");
  const select = buildKindFilter(doc);

  host.appendChild(healthEl);
  host.appendChild(eventsEl);
  host.appendChild(summaryEl);
  host.appendChild(clustersEl);
  host.appendChild(select);

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
    renderEvents(eventsEl, eventsKept, kind, eventsError);
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
    } else {
      healthPanel.error = result.error;
    }
    renderHealth(healthEl, healthPanel);
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
    renderSummary(summaryEl, summaryPanel);
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
    renderClusters(clustersEl, clustersPanel);
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
