import { test, expect } from "vitest";
import * as M from "../../src/feed";
import * as H from "../../tests/helpers";

const ids = (xs: readonly { id: number }[]) => xs.map((e) => e.id).join(",");

test("Merge Feed ex1: merging the same events twice", () => {
  const ev = H.fixtureEvents();
  const empty: H.FixtureEvent[] = [];
  const a = M.mergeEvents(empty, ev);
  expect(ids(a), "first").toBe("8,7,6,5,4,3,2,1");
  const b = M.mergeEvents(a, ev);
  expect(ids(b), "second").toBe("8,7,6,5,4,3,2,1");
  expect(b !== a, "a new array").toBe(true);
  expect(b.every((e, i) => e === a[i]), "same objects").toBe(true);
  expect(`${empty.length} ${ev.length} ${a.length}`, "arguments unchanged").toBe("0 8 8");
});

test("Merge Feed ex2: ascending input comes out newest first", () => {
  expect(ids(M.mergeEvents([], H.syntheticEvents([1, 2, 3])))).toBe("3,2,1");
});

test("Merge Feed ex3: the cap", () => {
  const many = H.syntheticEvents(Array.from({ length: 600 }, (_, i) => i + 1));
  const r = M.mergeEvents([], many);
  expect(`${r.length} ${r[0].id} ${r[r.length - 1].id}`, "default cap").toBe("500 600 101");
  expect(ids(M.mergeEvents([], many, 3)), "cap 3").toBe("600,599,598");
  expect(many.length, "argument unchanged").toBe(600);
});

test("Merge Feed ex4: the kept element wins on a repeated id", () => {
  const kept = H.fixtureEvents();
  const changed = { ...kept[0], label: "changed" };
  const r = M.mergeEvents(kept, [changed, ...H.syntheticEvents([9])]);
  expect(ids(r)).toBe("9,8,7,6,5,4,3,2,1");
  const e8 = r.find((e) => e.id === 8)!;
  expect(e8 === kept[0], "the kept object").toBe(true);
  expect(e8.label).toBe("LaunchToken family");
});

test("Merge Feed ex5: filterByKind", () => {
  const all = M.mergeEvents(H.fixtureEvents(), [H.UPGRADE_EVENT]);
  expect(ids(M.filterByKind(all, "ALL")), "ALL").toBe("9,8,7,6,5,4,3,2,1");
  expect(ids(M.filterByKind(all, "ALERT")), "ALERT").toBe("8,7,6,5,4,3,2,1");
  expect(ids(M.filterByKind(all, "UPGRADE")), "UPGRADE").toBe("9");
});
