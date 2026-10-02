// Types and parsing for the four JSON endpoints of the phase-15 backend.
// The shapes are the dataObject Dashboard JSON of contour.yaml, group
// dashboard; the recorded fixtures tests/fixtures/dashboard_*.json are the
// source of truth. A parser never throws and never logs; a fetcher never
// throws and never names the global fetch -- it calls only the fetchFn it
// is given.

export interface Health {
  progress: number | null;
  progress_at: string | null;
  seconds_since_progress: number | null;
  now: string;
}

export type Kind = "ALERT" | "UPGRADE";

export interface DashEvent {
  id: number;
  kind: Kind;
  block: number;
  at: string;
  address: string;
  seed_address: string | null;
  label: string | null;
  origin: string | null;
  old_impl: string | null;
  new_impl: string | null;
  score: number | null;
}

export interface EventsPage {
  events: DashEvent[];
  last_id: number;
}

export type OriginKey = "created" | "seen" | "impl" | "fetched" | "unknown";

export type OriginCounts = Record<OriginKey, number>;

export interface Summary {
  addresses: number;
  codes: number;
  seeds: number;
  implementations_resolved: number;
  origins: OriginCounts;
  alerts_by_seed: { label: string; seed_address: string; count: number }[];
  recent: { blocks: number; by_origin: OriginCounts };
}

export interface Cluster {
  level: string;
  key: string;
  members: string[];
}

export interface ClustersPage {
  level: string;
  n: number;
  clusters: Cluster[];
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };

export interface Panel<T> {
  data: T | null;
  error: string | null;
}

export type FetchLike = (url: string) => Promise<{
  ok: boolean;
  status: number;
  json(): Promise<unknown>;
}>;

// ---- narrowing helpers -------------------------------------------------

function isObj(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function isNum(x: unknown): x is number {
  return typeof x === "number";
}

function isStr(x: unknown): x is string {
  return typeof x === "string";
}

function isStrOrNull(x: unknown): x is string | null {
  return x === null || typeof x === "string";
}

function isNumOrNull(x: unknown): x is number | null {
  return x === null || typeof x === "number";
}

function isStrArr(x: unknown): x is string[] {
  return Array.isArray(x) && x.every((e) => isStr(e));
}

function isKind(x: unknown): x is Kind {
  return x === "ALERT" || x === "UPGRADE";
}

const ORIGIN_KEYS: readonly OriginKey[] = [
  "created",
  "seen",
  "impl",
  "fetched",
  "unknown"
];

function isOriginCounts(x: unknown): x is OriginCounts {
  if (!isObj(x)) {
    return false;
  }
  return ORIGIN_KEYS.every((k) => isNum(x[k]));
}

// ---- parsers -----------------------------------------------------------

export function parseHealth(x: unknown): Health | null {
  if (!isObj(x)) {
    return null;
  }
  if (!isNumOrNull(x.progress)) return null;
  if (!isStrOrNull(x.progress_at)) return null;
  if (!isNumOrNull(x.seconds_since_progress)) return null;
  if (!isStr(x.now)) return null;
  return {
    progress: x.progress,
    progress_at: x.progress_at,
    seconds_since_progress: x.seconds_since_progress,
    now: x.now
  };
}

function parseEvent(x: unknown): DashEvent | null {
  if (!isObj(x)) {
    return null;
  }
  if (!isNum(x.id)) return null;
  if (!isKind(x.kind)) return null;
  if (!isNum(x.block)) return null;
  if (!isStr(x.at)) return null;
  if (!isStr(x.address)) return null;
  if (!isStrOrNull(x.seed_address)) return null;
  if (!isStrOrNull(x.label)) return null;
  if (!isStrOrNull(x.origin)) return null;
  if (!isStrOrNull(x.old_impl)) return null;
  if (!isStrOrNull(x.new_impl)) return null;
  if (!isNumOrNull(x.score)) return null;
  return {
    id: x.id,
    kind: x.kind,
    block: x.block,
    at: x.at,
    address: x.address,
    seed_address: x.seed_address,
    label: x.label,
    origin: x.origin,
    old_impl: x.old_impl,
    new_impl: x.new_impl,
    score: x.score
  };
}

export function parseEvents(x: unknown): EventsPage | null {
  if (!isObj(x)) {
    return null;
  }
  if (!isNum(x.last_id)) return null;
  if (!Array.isArray(x.events)) return null;
  const events: DashEvent[] = [];
  for (const e of x.events) {
    const parsed = parseEvent(e);
    if (parsed === null) {
      return null;
    }
    events.push(parsed);
  }
  return { events, last_id: x.last_id };
}

function parseAlertsBySeed(x: unknown): { label: string; seed_address: string; count: number }[] | null {
  if (!Array.isArray(x)) {
    return null;
  }
  const out: { label: string; seed_address: string; count: number }[] = [];
  for (const e of x) {
    if (!isObj(e)) return null;
    if (!isStr(e.label)) return null;
    if (!isStr(e.seed_address)) return null;
    if (!isNum(e.count)) return null;
    out.push({ label: e.label, seed_address: e.seed_address, count: e.count });
  }
  return out;
}

export function parseSummary(x: unknown): Summary | null {
  if (!isObj(x)) {
    return null;
  }
  if (!isNum(x.addresses)) return null;
  if (!isNum(x.codes)) return null;
  if (!isNum(x.seeds)) return null;
  if (!isNum(x.implementations_resolved)) return null;
  if (!isOriginCounts(x.origins)) return null;
  const alerts_by_seed = parseAlertsBySeed(x.alerts_by_seed);
  if (alerts_by_seed === null) return null;
  if (!isObj(x.recent)) return null;
  if (!isNum(x.recent.blocks)) return null;
  if (!isOriginCounts(x.recent.by_origin)) return null;
  return {
    addresses: x.addresses,
    codes: x.codes,
    seeds: x.seeds,
    implementations_resolved: x.implementations_resolved,
    origins: x.origins,
    alerts_by_seed,
    recent: { blocks: x.recent.blocks, by_origin: x.recent.by_origin }
  };
}

function parseCluster(x: unknown): Cluster | null {
  if (!isObj(x)) {
    return null;
  }
  if (!isStr(x.level)) return null;
  if (!isStr(x.key)) return null;
  if (!isStrArr(x.members)) return null;
  return { level: x.level, key: x.key, members: x.members };
}

export function parseClusters(x: unknown): ClustersPage | null {
  if (!isObj(x)) {
    return null;
  }
  if (!isStr(x.level)) return null;
  if (!isNum(x.n)) return null;
  if (!Array.isArray(x.clusters)) return null;
  const clusters: Cluster[] = [];
  for (const c of x.clusters) {
    const parsed = parseCluster(c);
    if (parsed === null) {
      return null;
    }
    clusters.push(parsed);
  }
  return { level: x.level, n: x.n, clusters };
}

// ---- fetchers ----------------------------------------------------------

async function request<T>(
  fetchFn: FetchLike,
  url: string,
  parse: (x: unknown) => T | null
): Promise<ApiResult<T>> {
  let response: Awaited<ReturnType<FetchLike>>;
  try {
    response = await fetchFn(url);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: "request failed: " + message };
  }
  if (response.status < 200 || response.status > 299) {
    return { ok: false, error: "HTTP " + String(response.status) + " for " + url };
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, error: "bad json: " + message };
  }
  const data = parse(body);
  if (data === null) {
    return { ok: false, error: "unexpected response shape for " + url };
  }
  return { ok: true, data };
}

export function getHealth(fetchFn: FetchLike): Promise<ApiResult<Health>> {
  return request(fetchFn, "/api/health", parseHealth);
}

export function getEvents(after: number, fetchFn: FetchLike): Promise<ApiResult<EventsPage>> {
  return request(
    fetchFn,
    "/api/events?after=" + String(after) + "&limit=500",
    parseEvents
  );
}

export function getSummary(fetchFn: FetchLike): Promise<ApiResult<Summary>> {
  return request(fetchFn, "/api/summary", parseSummary);
}

export function getClusters(level: string, n: number, fetchFn: FetchLike): Promise<ApiResult<ClustersPage>> {
  return request(
    fetchFn,
    "/api/clusters?level=" + level + "&n=" + String(n),
    parseClusters
  );
}
