import { test, expect } from "vitest";
import * as F from "../../src/format";
import * as H from "../../tests/helpers";

const each = <T,>(f: (x: T) => unknown, xs: T[]) => xs.map((x) => String(f(x)));

test("Format Values ex1: formatScore", () => {
  expect(each(F.formatScore, [1, 0.8666666666666667, 0, null])).toStrictEqual(["1.0000", "0.8667", "0.0000", ""]);
});

test("Format Values ex2: formatAge", () => {
  expect(each(F.formatAge, [0, 8, 24, 59, 60, 150, 3599, 3600, 7300, null])).toStrictEqual(
    ["0 s", "8 s", "24 s", "59 s", "1 min", "2 min", "59 min", "1 h", "2 h", "n/a"]);
});

test("Format Values ex3: statusOf", () => {
  expect(each(F.statusOf, [0, 24, 36, 59, 60, 299, 300, 86400, null])).toStrictEqual(
    ["live", "live", "live", "live", "behind", "behind", "stalled", "stalled", "unknown"]);
});

test("Format Values ex4: shortAddress", () => {
  expect(each(F.shortAddress, ["0x0be5cfbcbb8a82c8d44af544dd40261b967ab832", "0x1234", "0x1234567890"]))
    .toStrictEqual(["0x0be5…b832", "0x1234", "0x1234567890"]);
});

test("Format Values ex5: etherscanUrl", () => {
  expect(each(F.etherscanUrl, ["0x0be5cfbcbb8a82c8d44af544dd40261b967ab832",
    "0x1807090DD15A6F58E00FD769E32EBF20EE610385"])).toStrictEqual([
    "https://etherscan.io/address/0x0be5cfbcbb8a82c8d44af544dd40261b967ab832",
    "https://etherscan.io/address/0x1807090dd15a6f58e00fd769e32ebf20ee610385"]);
});

test("Format Values ex6: formatTime", () => {
  expect(each(F.formatTime, ["2026-10-02T08:47:50Z", "2026-10-02T23:59:59Z", "garbage"]))
    .toStrictEqual(["08:47:50", "23:59:59", "garbage"]);
});

test("Format Values ex7: originShares", () => {
  const s = H.loadFixture("summary") as { origins: Record<string, number>; recent: { by_origin: Record<string, number> } };
  const show = (c: Record<string, number>) => F.originShares(c as Parameters<typeof F.originShares>[0])
    .map((e) => `${e.origin}:${e.count}:${e.percent}`).join(" ");
  expect(show(s.origins), "origins").toBe("created:109:0.1 seen:19256:8.9 impl:387:0.2 fetched:0:0 unknown:197257:90.9");
  expect(show(s.recent.by_origin), "recent").toBe("created:16:0.6 seen:2474:86 impl:387:13.5 fetched:0:0 unknown:0:0");
  expect(show({ created: 0, seen: 0, impl: 0, fetched: 0, unknown: 0 }), "all zero")
    .toBe("created:0:0 seen:0:0 impl:0:0 fetched:0:0 unknown:0:0");
});
