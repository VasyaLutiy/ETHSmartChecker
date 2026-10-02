import { describe, expect, test } from "vitest";

import { filterByKind, mergeEvents } from "../src/feed";

import {
  FixtureEvent,
  UPGRADE_EVENT,
  fixtureEvents,
  syntheticEvents,
} from "./helpers";

describe("Merge Feed", () => {
  test("Merge Feed ex1: union of the fixture events with itself keeps ids 8..1 and returns a new array of the same objects", () => {
    const events = fixtureEvents();
    expect(events).toHaveLength(8);
    const first = mergeEvents([], events);
    expect(first.map((e) => e.id)).toEqual([8, 7, 6, 5, 4, 3, 2, 1]);
    const second = mergeEvents(first, events);
    expect(second.map((e) => e.id)).toEqual([8, 7, 6, 5, 4, 3, 2, 1]);
    expect(second).not.toBe(first);
    for (let i = 0; i < 8; i += 1) {
      expect(second[i]).toBe(first[i]);
    }
    expect(events).toHaveLength(8);
    expect(first).toHaveLength(8);
  });

  test("Merge Feed ex2: three ascending ids 1, 2, 3 come back as [3, 2, 1]", () => {
    const merged = mergeEvents([], syntheticEvents([1, 2, 3]));
    expect(merged.map((e) => e.id)).toEqual([3, 2, 1]);
  });

  test("Merge Feed ex3: 600 events are cut to the 500 largest ids; an explicit cap of 3 keeps 3", () => {
    const ids: number[] = [];
    for (let i = 1; i <= 600; i += 1) {
      ids.push(i);
    }
    const events = syntheticEvents(ids);
    const capped = mergeEvents([], events);
    expect(capped).toHaveLength(500);
    expect(capped[0].id).toBe(600);
    expect(capped[499].id).toBe(101);
    const three = mergeEvents([], events, 3);
    expect(three.map((e) => e.id)).toEqual([600, 599, 598]);
  });

  test("Merge Feed ex4: an incoming copy of an existing id loses to the kept object, a new id 9 is merged in", () => {
    const kept = fixtureEvents();
    const changed: FixtureEvent = { ...kept.find((e) => e.id === 8)!, label: "changed" };
    const incoming = [changed, UPGRADE_EVENT];
    const merged = mergeEvents(kept, incoming);
    expect(merged.map((e) => e.id)).toEqual([9, 8, 7, 6, 5, 4, 3, 2, 1]);
    const row8 = merged.find((e) => e.id === 8)!;
    expect(row8).toBe(kept.find((e) => e.id === 8)!);
    expect(row8.label).toBe("LaunchToken family");
  });

  test("Merge Feed ex5: filterByKind ALL keeps every element, ALERT the 8 fixture alerts, UPGRADE only id 9", () => {
    const events: FixtureEvent[] = [...fixtureEvents(), UPGRADE_EVENT];
    const merged = mergeEvents([], events);
    expect(merged.map((e) => e.id)).toEqual([9, 8, 7, 6, 5, 4, 3, 2, 1]);
    const all = filterByKind(merged, "ALL");
    expect(all.map((e) => e.id)).toEqual([9, 8, 7, 6, 5, 4, 3, 2, 1]);
    const alerts = filterByKind(merged, "ALERT");
    expect(alerts.map((e) => e.id)).toEqual([8, 7, 6, 5, 4, 3, 2, 1]);
    const upgrades = filterByKind(merged, "UPGRADE");
    expect(upgrades.map((e) => e.id)).toEqual([9]);
  });

  test("rule: neither argument is mutated", () => {
    const kept = fixtureEvents();
    const incoming = syntheticEvents([9, 10, 11]);
    const keptCopy = [...kept];
    const incomingCopy = [...incoming];
    mergeEvents(kept, incoming);
    expect(kept).toEqual(keptCopy);
    expect(incoming).toEqual(incomingCopy);
    expect(kept).toHaveLength(8);
    expect(incoming).toHaveLength(3);
  });

  test("rule: empty inputs give an empty result", () => {
    expect(mergeEvents([], [])).toEqual([]);
    expect(mergeEvents(fixtureEvents(), [])).toHaveLength(8);
  });

  test("rule: the elements keep their object identity through a merge", () => {
    const kept = fixtureEvents();
    const merged = mergeEvents(kept, syntheticEvents([9]));
    for (const e of kept) {
      expect(merged.find((m) => m.id === e.id)).toBe(e);
    }
  });
});
