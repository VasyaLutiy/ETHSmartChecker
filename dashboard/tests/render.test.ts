import { test, expect } from "vitest";
import { loadFixture, UPGRADE_EVENT } from "./helpers";
import { parseHealth, parseEvents, parseSummary, parseClusters, type DashEvent } from "../src/api";
import { renderHealth } from "../src/render/health";
import { renderEvents } from "../src/render/events";
import { renderSummary } from "../src/render/summary";
import { renderClusters } from "../src/render/clusters";

test("RenderHealth ex1", () => {
  const data = parseHealth(loadFixture("health"));
  expect(data === null).toBe(false);
  if (data === null) return;
  const root = document.createElement("div");
  renderHealth(root, { data, error: null });
  expect(root.querySelector('[data-field="progress"]')?.textContent).toBe("26103569");
  expect(root.querySelector('[data-field="age"]')?.textContent).toBe("24 s");
  expect(root.querySelector('[data-field="status"]')?.getAttribute("data-status")).toBe("live");
  expect(root.querySelectorAll(".unreachable").length).toBe(0);
});

test("RenderPanels unreachable keeps data", () => {
  const data = parseHealth(loadFixture("health"));
  if (data === null) throw new Error("bad fixture");
  const root = document.createElement("div");
  renderHealth(root, { data, error: "HTTP 500" });
  expect(root.querySelectorAll(".unreachable").length).toBe(1);
  expect(root.querySelector(".unreachable")?.textContent).toBe("backend unreachable");
  expect(root.querySelector('[data-field="progress"]')?.textContent).toBe("26103569");
  renderHealth(root, { data, error: null });
  expect(root.querySelectorAll(".unreachable").length).toBe(0);
});

test("RenderEvents rows and links", () => {
  const page = parseEvents(loadFixture("events"));
  if (page === null) throw new Error("bad fixture");
  const root = document.createElement("div");
  renderEvents(root, page.events, "ALL", null);
  expect(root.querySelectorAll("[data-id]").length).toBe(8);
  const row8 = root.querySelector('[data-id="8"]');
  expect(row8?.getAttribute("data-kind")).toBe("ALERT");
  const a = row8?.querySelector("a");
  expect(a?.getAttribute("href")).toBe(
    "https://etherscan.io/address/0x0be5cfbcbb8a82c8d44af544dd40261b967ab832"
  );
  expect(a?.textContent).toBe("0x0be5\u2026b832");
  const upgrade = UPGRADE_EVENT as unknown as DashEvent;
  renderEvents(root, [upgrade], "ALL", null);
  expect(root.querySelectorAll("[data-id]").length).toBe(1);
  expect(root.querySelectorAll("a").length).toBe(3);
});

test("RenderSummary counters and bars", () => {
  const data = parseSummary(loadFixture("summary"));
  if (data === null) throw new Error("bad fixture");
  const root = document.createElement("div");
  renderSummary(root, { data, error: null });
  expect(root.querySelector('[data-field="addresses"]')?.textContent).toBe("217009");
  const seen = root.querySelector('[data-bar="origins"] [data-origin="seen"]');
  expect(seen?.getAttribute("data-count")).toBe("19256");
  expect(seen?.getAttribute("style")).toBe("width: 8.9%");
  const recentImpl = root.querySelector('[data-bar="recent"] [data-origin="impl"]');
  expect(recentImpl?.getAttribute("style")).toBe("width: 13.5%");
});

test("RenderClusters rows", () => {
  const data = parseClusters(loadFixture("clusters_impl"));
  if (data === null) throw new Error("bad fixture");
  const root = document.createElement("div");
  renderClusters(root, { data, error: null });
  expect(root.querySelectorAll("[data-key]").length).toBe(20);
  const first = root.querySelector("[data-key]");
  expect(first?.getAttribute("data-key")).toBe("0x985462c9aa4d6c3ad59ae6e1e9c0c11347ed1598");
  expect(first?.querySelector('[data-field="members"]')?.textContent).toBe("14");
});
