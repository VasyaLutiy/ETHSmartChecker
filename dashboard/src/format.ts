export type OriginKey = "created" | "seen" | "impl" | "fetched" | "unknown";

export interface OriginShare {
  origin: string;
  count: number;
  percent: number;
}

export function formatScore(score: number | null): string {
  if (score === null) {
    return "";
  }
  return score.toFixed(4);
}

export function formatAge(seconds: number | null): string {
  if (seconds === null) {
    return "n/a";
  }
  if (seconds < 60) {
    return seconds + " s";
  }
  if (seconds < 3600) {
    return Math.floor(seconds / 60) + " min";
  }
  return Math.floor(seconds / 3600) + " h";
}

export function statusOf(seconds: number | null): "live" | "behind" | "stalled" | "unknown" {
  if (seconds === null) {
    return "unknown";
  }
  if (seconds < 60) {
    return "live";
  }
  if (seconds < 300) {
    return "behind";
  }
  return "stalled";
}

export function shortAddress(address: string): string {
  if (address.length <= 12) {
    return address;
  }
  return address.slice(0, 6) + "\u2026" + address.slice(-4);
}

export function etherscanUrl(address: string): string {
  return "https://etherscan.io/address/" + address.toLowerCase();
}

export function formatTime(at: string): string {
  const m = /^([0-9]{4}-[0-9]{2}-[0-9]{2})T([0-9]{2}:[0-9]{2}:[0-9]{2})Z$/.exec(at);
  if (m === null) {
    return at;
  }
  return m[2];
}

const ORIGIN_ORDER: readonly OriginKey[] = ["created", "seen", "impl", "fetched", "unknown"];

export function originShares(counts: Readonly<Record<OriginKey, number>>): OriginShare[] {
  const total = ORIGIN_ORDER.reduce((sum, k) => sum + counts[k], 0);
  return ORIGIN_ORDER.map((origin) => {
    const count = counts[origin];
    const percent = total === 0 ? 0 : Math.round((count * 1000) / total) / 10;
    return { origin, count, percent };
  });
}
