import { expect, test } from "vitest";
import {
  etherscanUrl,
  formatAge,
  formatScore,
  formatTime,
  originShares,
  shortAddress,
  statusOf
} from "../src/format";

test("formatScore ex1", () => {
  expect(formatScore(1)).toBe("1.0000");
  expect(formatScore(0.8666666666666667)).toBe("0.8667");
  expect(formatScore(0)).toBe("0.0000");
  expect(formatScore(null)).toBe("");
});

test("formatAge and statusOf ex2 ex3", () => {
  expect(formatAge(59)).toBe("59 s");
  expect(formatAge(60)).toBe("1 min");
  expect(formatAge(3600)).toBe("1 h");
  expect(formatAge(null)).toBe("n/a");
  expect(statusOf(59)).toBe("live");
  expect(statusOf(299)).toBe("behind");
  expect(statusOf(300)).toBe("stalled");
  expect(statusOf(null)).toBe("unknown");
});

test("shortAddress and etherscanUrl ex4 ex5", () => {
  expect(shortAddress("0x0be5cfbcbb8a82c8d44af544dd40261b967ab832")).toBe("0x0be5\u2026b832");
  expect(shortAddress("0x1234567890")).toBe("0x1234567890");
  expect(etherscanUrl("0x1807090DD15A6F58E00FD769E32EBF20EE610385")).toBe(
    "https://etherscan.io/address/0x1807090dd15a6f58e00fd769e32ebf20ee610385"
  );
});

test("formatTime ex6", () => {
  expect(formatTime("2026-10-02T08:47:50Z")).toBe("08:47:50");
  expect(formatTime("garbage")).toBe("garbage");
});

test("originShares ex7", () => {
  const shares = originShares({
    created: 0,
    seen: 0,
    impl: 0,
    fetched: 0,
    unknown: 0
  });
  expect(shares.length).toBe(5);
  expect(shares[0].percent).toBe(0);
  const one = originShares({
    created: 1,
    seen: 3,
    impl: 0,
    fetched: 0,
    unknown: 1
  });
  expect(one[1].percent).toBe(60);
});
