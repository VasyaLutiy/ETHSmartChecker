import { describe, expect, test } from "vitest";
import {
  formatScore,
  formatAge,
  statusOf,
  shortAddress,
  etherscanUrl,
  formatTime,
  originShares
} from "../src/format";
import type { OriginKey } from "../src/format";
import { loadFixture } from "./helpers";

interface FixtureSummary {
  origins: Record<OriginKey, number>;
  recent: { blocks: number; by_origin: Record<OriginKey, number> };
}

function summaryFixture(): FixtureSummary {
  return loadFixture("summary") as FixtureSummary;
}

describe("Format Values", () => {
  test("Format Values ex1: formatScore four decimals, empty for null", () => {
    expect(formatScore(1)).toBe("1.0000");
    expect(formatScore(0.8666666666666667)).toBe("0.8667");
    expect(formatScore(0)).toBe("0.0000");
    expect(formatScore(null)).toBe("");
  });

  test("Format Values ex2: formatAge seconds, minutes, hours, n/a", () => {
    expect(formatAge(0)).toBe("0 s");
    expect(formatAge(8)).toBe("8 s");
    expect(formatAge(24)).toBe("24 s");
    expect(formatAge(59)).toBe("59 s");
    expect(formatAge(60)).toBe("1 min");
    expect(formatAge(150)).toBe("2 min");
    expect(formatAge(3599)).toBe("59 min");
    expect(formatAge(3600)).toBe("1 h");
    expect(formatAge(7300)).toBe("2 h");
    expect(formatAge(null)).toBe("n/a");
  });

  test("Format Values ex3: statusOf live, behind, stalled, unknown", () => {
    expect(statusOf(0)).toBe("live");
    expect(statusOf(24)).toBe("live");
    expect(statusOf(36)).toBe("live");
    expect(statusOf(59)).toBe("live");
    expect(statusOf(60)).toBe("behind");
    expect(statusOf(299)).toBe("behind");
    expect(statusOf(300)).toBe("stalled");
    expect(statusOf(86400)).toBe("stalled");
    expect(statusOf(null)).toBe("unknown");
  });

  test("Format Values ex4: shortAddress truncates, keeps short strings", () => {
    expect(shortAddress("0x0be5cfbcbb8a82c8d44af544dd40261b967ab832")).toBe("0x0be5\u2026b832");
    expect(shortAddress("0x1234")).toBe("0x1234");
    expect(shortAddress("0x1234567890")).toBe("0x1234567890");
  });

  test("Format Values ex5: etherscanUrl lowercases the address", () => {
    expect(etherscanUrl("0x0be5cfbcbb8a82c8d44af544dd40261b967ab832")).toBe(
      "https://etherscan.io/address/0x0be5cfbcbb8a82c8d44af544dd40261b967ab832"
    );
    expect(etherscanUrl("0x1807090DD15A6F58E00FD769E32EBF20EE610385")).toBe(
      "https://etherscan.io/address/0x1807090dd15a6f58e00fd769e32ebf20ee610385"
    );
  });

  test("Format Values ex6: formatTime extracts HH:MM:SS, passes garbage through", () => {
    expect(formatTime("2026-10-02T08:47:50Z")).toBe("08:47:50");
    expect(formatTime("2026-10-02T23:59:59Z")).toBe("23:59:59");
    expect(formatTime("garbage")).toBe("garbage");
  });

  test("Format Values ex7: originShares over the summary fixture and all zero", () => {
    const s = summaryFixture();
    const origins = originShares(s.origins);
    expect(origins.map((e) => e.origin)).toEqual(["created", "seen", "impl", "fetched", "unknown"]);
    expect(origins.map((e) => e.count)).toEqual([109, 19256, 387, 0, 197257]);
    expect(origins.map((e) => e.percent)).toEqual([0.1, 8.9, 0.2, 0, 90.9]);

    const recent = originShares(s.recent.by_origin);
    expect(recent.map((e) => e.count)).toEqual([16, 2474, 387, 0, 0]);
    expect(recent.map((e) => e.percent)).toEqual([0.6, 86, 13.5, 0, 0]);

    const zero: Record<OriginKey, number> = {
      created: 0,
      seen: 0,
      impl: 0,
      fetched: 0,
      unknown: 0
    };
    const zeros = originShares(zero);
    expect(zeros.length).toBe(5);
    for (const e of zeros) {
      expect(e.percent).toBe(0);
    }
  });

  test("Format Values rule: originShares entry shape has origin, count and percent", () => {
    const shares = originShares({ created: 1, seen: 1, impl: 1, fetched: 1, unknown: 1 });
    expect(shares).toEqual([
      { origin: "created", count: 1, percent: 20 },
      { origin: "seen", count: 1, percent: 20 },
      { origin: "impl", count: 1, percent: 20 },
      { origin: "fetched", count: 1, percent: 20 },
      { origin: "unknown", count: 1, percent: 20 }
    ]);
  });

  test("Format Values rule: formatScore rounds to four decimals, does not pad beyond", () => {
    expect(formatScore(0.12345)).toBe("0.1235");
    expect(formatScore(0.8125)).toBe("0.8125");
    expect(formatScore(0.2647058823529412)).toBe("0.2647");
  });

  test("Format Values rule: formatAge boundaries 59/60 and 3599/3600", () => {
    expect(formatAge(60)).toBe("1 min");
    expect(formatAge(61)).toBe("1 min");
    expect(formatAge(3600)).toBe("1 h");
    expect(formatAge(3601)).toBe("1 h");
    expect(formatAge(7200)).toBe("2 h");
  });

  test("Format Values rule: statusOf thresholds 59/60 and 299/300", () => {
    expect(statusOf(59)).toBe("live");
    expect(statusOf(60)).toBe("behind");
    expect(statusOf(299)).toBe("behind");
    expect(statusOf(300)).toBe("stalled");
  });

  test("Format Values rule: shortAddress keeps the first 6 and the last 4 above 12 characters", () => {
    expect(shortAddress("0x1234567890")).toBe("0x1234567890");
    expect(shortAddress("0x1234567890a")).toBe("0x1234\u2026890a");
  });

  test("Format Values rule: formatTime accepts only the exact backend shape", () => {
    expect(formatTime("2026-10-02T08:47:50.123Z")).toBe("2026-10-02T08:47:50.123Z");
    expect(formatTime("")).toBe("");
  });

  test("Format Values rule: formatAge null and statusOf null agree on n/a and unknown", () => {
    expect(formatAge(null)).toBe("n/a");
    expect(statusOf(null)).toBe("unknown");
  });
});
