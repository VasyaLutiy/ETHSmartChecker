import { expect, test } from "vitest";
import { fakeClock, fakeFetch, flush, loadFixture, UPGRADE_EVENT } from "./helpers";
import { start } from "../src/main";

function freshDoc(): Document {
  const doc = document.implementation.createHTMLDocument();
  const app = doc.createElement("div");
  app.id = "app";
  doc.body.appendChild(app);
  return doc;
}

function fixtureRoutes(): Record<string, { body: unknown }> {
  return {
    "/api/health": { body: loadFixture("health") },
    "/api/events?after=0&limit=500": { body: loadFixture("events") },
    "/api/summary": { body: loadFixture("summary") },
    "/api/clusters?level=impl&n=20": { body: loadFixture("clusters_impl") }
  };
}

test("layout: dash class, four titled panels, select and head in events, legend in summary", async () => {
  const doc = freshDoc();
  const clock = fakeClock();
  const f = fakeFetch(fixtureRoutes());
  const stop = start(doc, f.fetch, clock);
  await flush();

  const app = doc.getElementById("app");
  expect(app).not.toBeNull();
  expect((app as HTMLElement).className).toBe("dash");

  const sections = Array.from((app as HTMLElement).children);
  expect(sections.length).toBe(4);
  expect(sections.map((s) => s.id).join(",")).toBe("health,events,summary,clusters");
  expect(sections[0].tagName).toBe("SECTION");

  const titles = sections
    .map((s) => s.querySelector(".panel-title"))
    .map((t) => (t as HTMLElement | null)?.textContent ?? "none");
  expect(titles.join(",")).toBe("Listener,Events,Summary,Impl clusters");

  const events = doc.getElementById("events") as HTMLElement;
  expect(events.querySelector("select#kind-filter")).not.toBeNull();
  expect(events.querySelector('[data-field="feed-meta"]')).not.toBeNull();
  const head = events.querySelector(".feed-head");
  expect(head).not.toBeNull();
  const headTexts = Array.from((head as HTMLElement).children)
    .map((c) => c.textContent)
    .join(",");
  expect(headTexts).toBe("kind,time UTC,block,label,score,origin,address");

  const summary = doc.getElementById("summary") as HTMLElement;
  const legend = summary.querySelector("ul.legend");
  expect(legend).not.toBeNull();
  const legends = Array.from((legend as HTMLElement).children)
    .map((li) => li.getAttribute("data-legend"))
    .join(",");
  expect(legends).toBe("created,seen,impl,fetched,unknown");

  stop();
});

test("feed-meta shows the kept count and the newest time", async () => {
  const doc = freshDoc();
  const clock = fakeClock();
  const f = fakeFetch(fixtureRoutes());
  const stop = start(doc, f.fetch, clock);
  await flush();

  const meta = doc.querySelector('#events [data-field="feed-meta"]');
  expect(meta).not.toBeNull();
  expect((meta as HTMLElement).textContent).toBe("8 events \u00B7 newest 08:47:50 UTC");

  stop();
});

test("title: ethsc at once, live after a good poll, unreachable after a failure", async () => {
  const doc = freshDoc();
  const clock = fakeClock();
  const f = fakeFetch(fixtureRoutes());
  const stop = start(doc, f.fetch, clock);
  expect(doc.title).toBe("ethsc");

  await flush();
  expect(doc.title).toBe("live \u00B7 26103569 \u00B7 ethsc");

  f.failAll(new TypeError("Failed to fetch"));
  clock.fire(5000);
  await flush();
  expect(doc.title).toBe("unreachable \u00B7 ethsc");

  stop();
});

test("kind filter re-renders the kept list and fetches nothing", async () => {
  const doc = freshDoc();
  const clock = fakeClock();
  const f = fakeFetch({
    ...fixtureRoutes(),
    "/api/events?after=8&limit=500": { body: { events: [UPGRADE_EVENT], last_id: 9 } }
  });
  const stop = start(doc, f.fetch, clock);
  await flush();

  clock.fire(5000);
  await flush();
  const events = doc.getElementById("events") as HTMLElement;
  const rows = Array.from(events.querySelectorAll("[data-role=\"list\"] > [data-id]"));
  expect(rows.length).toBe(9);

  const callsBefore = f.calls.length;
  const select = events.querySelector("select#kind-filter") as HTMLSelectElement;
  select.value = "UPGRADE";
  select.dispatchEvent(new Event("change"));
  await flush();

  expect(f.calls.length).toBe(callsBefore);
  const visible = rows.filter((r) => !(r as HTMLElement).hidden);
  expect(visible.length).toBe(1);
  expect(visible[0].getAttribute("data-id")).toBe("9");

  stop();
});
