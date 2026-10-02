// Panel renderer for /api/health. The DOM is reached only through
// root.ownerDocument; data reaches it only through textContent and
// setAttribute.

import type { Health, Panel } from "../api";
import { formatAge, statusOf } from "../format";

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

export function renderHealth(root: HTMLElement, panel: Panel<Health>): void {
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

  const progress = doc.createElement("span");
  progress.setAttribute("data-field", "progress");
  progress.textContent = data.progress === null ? "" : String(data.progress);
  box.appendChild(progress);

  const progressAt = doc.createElement("span");
  progressAt.setAttribute("data-field", "progress_at");
  progressAt.textContent = data.progress_at === null ? "" : data.progress_at;
  box.appendChild(progressAt);

  const age = doc.createElement("span");
  age.setAttribute("data-field", "age");
  age.textContent = formatAge(data.seconds_since_progress);
  box.appendChild(age);

  const status = doc.createElement("span");
  status.setAttribute("data-field", "status");
  const state = statusOf(data.seconds_since_progress);
  status.textContent = state;
  status.setAttribute("data-status", state);
  box.appendChild(status);

  root.appendChild(box);
}
