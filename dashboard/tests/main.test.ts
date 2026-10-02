import { expect, test } from "vitest";
import { start } from "../src/main";
import {
  fakeClock,
  fixtureFetch,
  flush,
  UPGRADE_EVENT
} from "./helpers";

function freshApp(): void {
  document.body.replaceChildren();
  const app = document.createElement("div");
  app.id = "app";
  document.body.appendChild(app);
}

test("start builds the panels and requests the four endpoints in order", async () => {
  freshApp();
  const f = fixtureFetch();
  const clock = fakeClock();
  const stop = start(document, (url) => f.fetch(url), clock);
  await flush();
  expect(f.calls.length).toBe(4);
  expect(f.calls[0]).toBe("/api/health");
  expect(f.calls[1]).toBe("/api/events?after=0&limit=500");
  expect(f.calls[2]).toBe("/api/summary");
  expect(f.calls[3]).toBe("/api/clusters?level=impl&n=20");
  expect(clock.timers.length).toBe(4);
  expect(document.querySelector("#health") === null).toBe(false);
  expect(document.querySelector("select#kind-filter") === null).toBe(false);
  expect(document.querySelectorAll("#events [data-id]").length).toBe(8);
  expect(document.querySelectorAll("#clusters [data-key]").length).toBe(20);
  stop();
  expect(clock.cleared.length).toBe(4);
});

test("the events poll continues with after = last_id", async () => {
  freshApp();
  const f = fixtureFetch();
  f.set("/api/events?after=8&limit=500", {
    body: { events: [UPGRADE_EVENT], last_id: 9 }
  });
  const clock = fakeClock();
  const stop = start(document, (url) => f.fetch(url), clock);
  await flush();
  clock.fire(5000);
  await flush();
  expect(f.calls.includes("/api/events?after=8&limit=500")).toBe(true);
  expect(document.querySelectorAll("#events [data-id]").length).toBe(9);
  stop();
});

test("a failed fetch shows backend unreachable and keeps the data", async () => {
  freshApp();
  const f = fixtureFetch();
  const clock = fakeClock();
  const stop = start(document, (url) => f.fetch(url), clock);
  await flush();
  expect(document.querySelector("#health .unreachable") === null).toBe(true);
  f.failAll(new TypeError("Failed to fetch"));
  clock.fire(5000);
  clock.fire(30000);
  await flush();
  expect(document.querySelector("#health .unreachable") === null).toBe(false);
  expect(document.querySelector("#summary .unreachable") === null).toBe(false);
  expect(document.querySelectorAll("#events [data-id]").length).toBe(8);
  expect(document.querySelectorAll("#clusters [data-key]").length).toBe(20);
  stop();
});
