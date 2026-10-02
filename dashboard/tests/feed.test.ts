import { expect, test } from "vitest";
import { filterByKind, mergeEvents } from "../src/feed";
import { fixtureEvents, syntheticEvents, UPGRADE_EVENT } from "./helpers";

test("mergeEvents ex1", () => {
  const events = fixtureEvents();
  const once = mergeEvents([], events);
  const twice = mergeEvents(once, events);
  expect(once.length).toBe(8);
  expect(once[0].id).toBe(8);
  expect(twice.length).toBe(8);
  expect(twice[7].id).toBe(1);
});

test("mergeEvents ex2 ex4", () => {
  const asc = syntheticEvents([1, 2, 3]);
  expect(mergeEvents([], asc).map((e) => e.id)).toEqual([3, 2, 1]);
  const kept = fixtureEvents();
  const incoming = [...kept];
  const changed = { ...incoming[0], id: 8, label: "changed" };
  incoming[0] = changed;
  incoming.push({ ...kept[0], id: 9 });
  const merged = mergeEvents(kept, incoming);
  expect(merged.length).toBe(9);
  expect(merged[0].id).toBe(9);
  expect(merged.find((e) => e.id === 8)?.label).toBe("LaunchToken family");
});

test("mergeEvents cap", () => {
  const events = syntheticEvents([...Array(600).keys()].map((i) => i + 1));
  const capped = mergeEvents([], events);
  expect(capped.length).toBe(500);
  expect(capped[0].id).toBe(600);
  expect(capped[499].id).toBe(101);
  expect(mergeEvents([], events, 3).map((e) => e.id)).toEqual([600, 599, 598]);
});

test("filterByKind", () => {
  const events = [...fixtureEvents(), UPGRADE_EVENT];
  expect(filterByKind(events, "ALL").length).toBe(9);
  expect(filterByKind(events, "ALERT").length).toBe(8);
  expect(filterByKind(events, "UPGRADE").length).toBe(1);
  expect(filterByKind(events, "UPGRADE")[0].id).toBe(9);
});
