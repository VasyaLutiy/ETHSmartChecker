// Panel renderer for the event feed. Rows are keyed by event id: a row
// already in root for an id still in events is the same node after the
// call (moved if needed, never rebuilt); rows for ids no longer in events
// are removed.

import type { DashEvent } from "../api";
import { formatScore, formatTime, shortAddress, etherscanUrl } from "../format";

type KindFilter = "ALL" | "ALERT" | "UPGRADE";

function setUnreachable(root: HTMLElement, error: string | null): void {
  const existing = root.querySelector(".unreachable");
  if (error === null) {
    if (existing !== null) {
      existing.remove();
    }
    return;
  }
  if (existing === null) {
    const el = root.ownerDocument.createElement("div");
    el.className = "unreachable";
    el.textContent = "backend unreachable";
    root.appendChild(el);
  }
}

function link(doc: Document, address: string): HTMLAnchorElement {
  const a = doc.createElement("a");
  a.setAttribute("href", etherscanUrl(address));
  a.setAttribute("title", address);
  a.textContent = shortAddress(address);
  return a;
}

function span(doc: Document, attribute: string, value: string, name: string): HTMLElement {
  const el = doc.createElement("span");
  el.setAttribute(attribute, name);
  el.textContent = value;
  return el;
}

function fillRow(row: HTMLElement, event: DashEvent, kind: KindFilter): void {
  const doc = row.ownerDocument;
  row.textContent = "";
  row.setAttribute("data-id", String(event.id));
  row.setAttribute("data-kind", event.kind);

  row.appendChild(span(doc, "data-badge", event.kind, "kind"));
  row.appendChild(span(doc, "data-field", formatTime(event.at), "time"));
  row.appendChild(span(doc, "data-field", String(event.block), "block"));

  if (event.kind === "ALERT") {
    row.appendChild(span(doc, "data-field", event.label === null ? "" : event.label, "label"));
    row.appendChild(span(doc, "data-field", formatScore(event.score), "score"));
    row.appendChild(span(doc, "data-badge", event.origin === null ? "" : event.origin, "origin"));
    row.appendChild(link(doc, event.address));
  } else {
    row.appendChild(link(doc, event.address));
    const arrow = doc.createElement("span");
    arrow.textContent = "\u2192";
    row.appendChild(arrow);
    row.appendChild(link(doc, event.old_impl === null ? "" : event.old_impl));
    row.appendChild(link(doc, event.new_impl === null ? "" : event.new_impl));
  }

  row.hidden = kind !== "ALL" && event.kind !== kind;
}

export function renderEvents(
  root: HTMLElement,
  events: readonly DashEvent[],
  kind: KindFilter,
  error: string | null
): void {
  setUnreachable(root, error);
  const doc = root.ownerDocument;
  let list = root.querySelector('[data-role="list"]');
  if (list === null) {
    const created = doc.createElement("div");
    created.setAttribute("data-role", "list");
    root.appendChild(created);
    list = created;
  }
  const container = list;

  const byId = new Map<string, HTMLElement>();
  for (const child of Array.from(container.children)) {
    const id = child.getAttribute("data-id");
    if (id !== null) {
      byId.set(id, child as HTMLElement);
    }
  }

  const keep = new Set<string>();
  for (const event of events) {
    const key = String(event.id);
    keep.add(key);
    let row = byId.get(key);
    if (row === undefined) {
      row = doc.createElement("div");
    }
    fillRow(row, event, kind);
    container.appendChild(row);
  }

  for (const [key, row] of byId) {
    if (!keep.has(key)) {
      row.remove();
    }
  }
}
