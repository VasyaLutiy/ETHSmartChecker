// Panel renderer for /api/summary: four counters and two origin bars.

import type { Panel, Summary } from "../api";
import type { OriginShare } from "../format";
import { originShares } from "../format";

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

function buildBar(doc: Document, name: string, shares: OriginShare[]): HTMLElement {
  const bar = doc.createElement("div");
  bar.setAttribute("data-bar", name);
  for (const share of shares) {
    const segment = doc.createElement("span");
    segment.setAttribute("data-origin", share.origin);
    segment.setAttribute("data-count", String(share.count));
    segment.setAttribute("style", "width: " + String(share.percent) + "%");
    bar.appendChild(segment);
  }
  return bar;
}

export function renderSummary(root: HTMLElement, panel: Panel<Summary>): void {
  setUnreachable(root, panel.error);
  if (panel.data === null) {
    return;
  }
  const previous = root.querySelector('[data-role="data"]');
  if (previous !== null) {
    previous.remove();
  }
  const doc = root.ownerDocument;
  const data = panel.data;
  const box = doc.createElement("div");
  box.setAttribute("data-role", "data");

  const fields: [string, number][] = [
    ["addresses", data.addresses],
    ["codes", data.codes],
    ["seeds", data.seeds],
    ["implementations_resolved", data.implementations_resolved]
  ];
  for (const [name, value] of fields) {
    const el = doc.createElement("span");
    el.setAttribute("data-field", name);
    el.textContent = String(value);
    box.appendChild(el);
  }

  box.appendChild(buildBar(doc, "origins", originShares(data.origins)));
  box.appendChild(buildBar(doc, "recent", originShares(data.recent.by_origin)));

  root.appendChild(box);
}
