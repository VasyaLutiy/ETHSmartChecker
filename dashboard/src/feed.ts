export function mergeEvents<T extends { id: number }>(
  kept: readonly T[],
  incoming: readonly T[],
  cap = 500
): T[] {
  const byId = new Map<number, T>();
  for (const e of kept) {
    byId.set(e.id, e);
  }
  for (const e of incoming) {
    if (!byId.has(e.id)) {
      byId.set(e.id, e);
    }
  }
  const all = [...byId.values()];
  all.sort((a, b) => b.id - a.id);
  return all.slice(0, cap);
}

export function filterByKind<T extends { kind: string }>(
  events: readonly T[],
  kind: "ALL" | "ALERT" | "UPGRADE"
): T[] {
  if (kind === "ALL") {
    return [...events];
  }
  return events.filter((e) => e.kind === kind);
}
