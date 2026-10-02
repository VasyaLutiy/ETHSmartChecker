import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { setImmediate } from "node:timers/promises";

export type FixtureName = "health" | "events" | "summary" | "clusters_impl";

export interface FixtureEvent {
  id: number;
  kind: string;
  block: number;
  at: string;
  address: string;
  seed_address: string | null;
  label: string | null;
  score: number | null;
  origin: string | null;
  old_impl: string | null;
  new_impl: string | null;
}

export function loadFixture(name: FixtureName): unknown {
  const here = dirname(fileURLToPath(import.meta.url));
  const path = resolve(here, "../../tests/fixtures/dashboard_" + name + ".json");
  return JSON.parse(readFileSync(path, "utf8")) as unknown;
}

export function fixtureEvents(): FixtureEvent[] {
  const data = loadFixture("events") as { events: FixtureEvent[] };
  return data.events.map((e) => ({ ...e }));
}

export function syntheticEvents(ids: readonly number[]): FixtureEvent[] {
  const base = fixtureEvents().find((e) => e.id === 8);
  if (base === undefined) {
    throw new Error("fixture event 8 not found");
  }
  return ids.map((i) => ({ ...base, id: i, block: i }));
}

export const UPGRADE_EVENT: FixtureEvent = {
  id: 9,
  kind: "UPGRADE",
  block: 26077729,
  at: "2026-10-02T08:00:00Z",
  address: "0x0c0105334a50db16b51b2911c9956539753a2cf8",
  seed_address: null,
  label: null,
  score: null,
  origin: null,
  old_impl: "0x72b971717e088b59f26d4236be222adb6acd393b",
  new_impl: "0xe440cc08a71694c8229323803f59024e3144630e"
};

export type FakeReply =
  | { status?: number; body?: unknown; jsonError?: boolean }
  | Error;

export interface FakeResponse {
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}

export interface FakeFetch {
  fetch(url: string): Promise<FakeResponse>;
  calls: string[];
  set(url: string, reply: FakeReply): void;
  failAll(e: Error | null): void;
}

export function fakeFetch(routes: Record<string, FakeReply> = {}): FakeFetch {
  const calls: string[] = [];
  const table = new Map<string, FakeReply>(Object.entries(routes));
  let fail: Error | null = null;

  return {
    calls,
    fetch(url: string): Promise<FakeResponse> {
      calls.push(url);
      if (fail !== null) {
        return Promise.reject(fail);
      }
      const reply = table.get(url);
      if (reply === undefined) {
        return Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ error: "not found" })
        });
      }
      if (reply instanceof Error) {
        return Promise.reject(reply);
      }
      const status = reply.status === undefined ? 200 : reply.status;
      const json = reply.jsonError
        ? () => Promise.reject(new SyntaxError("bad json"))
        : () => Promise.resolve(reply.body);
      return Promise.resolve({
        ok: status >= 200 && status <= 299,
        status,
        json
      });
    },
    set(url: string, reply: FakeReply): void {
      table.set(url, reply);
    },
    failAll(e: Error | null): void {
      fail = e;
    }
  };
}

export function fixtureFetch(): FakeFetch {
  return fakeFetch({
    "/api/health": { body: loadFixture("health") },
    "/api/events?after=0&limit=500": { body: loadFixture("events") },
    "/api/summary": { body: loadFixture("summary") },
    "/api/clusters?level=impl&n=20": { body: loadFixture("clusters_impl") }
  });
}

export interface FakeTimer {
  id: number;
  fn: () => void;
  ms: number;
}

export interface FakeClock {
  setInterval(fn: () => void, ms: number): number;
  clearInterval(id: number): void;
  timers: FakeTimer[];
  cleared: number[];
  fire(ms?: number): void;
}

export function fakeClock(): FakeClock {
  const timers: FakeTimer[] = [];
  const cleared: number[] = [];
  let next = 1;

  return {
    timers,
    cleared,
    setInterval(fn: () => void, ms: number): number {
      const id = next;
      next += 1;
      timers.push({ id, fn, ms });
      return id;
    },
    clearInterval(id: number): void {
      cleared.push(id);
    },
    fire(ms?: number): void {
      for (const t of [...timers]) {
        if (cleared.includes(t.id)) {
          continue;
        }
        if (ms !== undefined && t.ms !== ms) {
          continue;
        }
        t.fn();
      }
    }
  };
}

export async function flush(): Promise<void> {
  for (let i = 0; i < 5; i += 1) {
    await setImmediate();
  }
}
