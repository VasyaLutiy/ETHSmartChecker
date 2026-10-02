// Panel renderer for /api/clusters: one table row per cluster, in order.

import type { ClustersPage, Panel } from "../api";
import { shortAddress, etherscanUrl } from "../format";

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

export function renderClusters(root: HTMLElement, panel: Panel<ClustersPage>): void {
  setUnreachable(root, panel.error);
  if (panel.data === null) {
    return;
  }
  const previous = root.querySelector('[data-role="data"]');
  if (previous !== null) {
    previous.remove();
  }
  const doc = root.ownerDocument;
  const table = doc.createElement("table");
  table.setAttribute("data-role", "data");
  for (const cluster of panel.data.clusters) {
    const row = doc.createElement("tr");
    row.setAttribute("data-key", cluster.key);
    const keyCell = doc.createElement("td");
    keyCell.appendChild(link(doc, cluster.key));
    row.appendChild(keyCell);
    const membersCell = doc.createElement("td");
    membersCell.setAttribute("data-field", "members");
    membersCell.textContent = String(cluster.members.length);
    row.appendChild(membersCell);
    table.appendChild(row);
  }
  root.appendChild(table);
}
