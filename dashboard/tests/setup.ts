import net from "node:net";

const BLOCKED = "network blocked in tests";

function throwBlocked(): never {
  throw new Error(BLOCKED);
}

const blockedFetch = (): Promise<never> => {
  throw new Error(BLOCKED);
};

function BlockedXMLHttpRequest(): never {
  throw new Error(BLOCKED);
}

function BlockedWebSocket(): never {
  throw new Error(BLOCKED);
}

const g = globalThis as unknown as Record<string, unknown>;
g.fetch = blockedFetch;
g.XMLHttpRequest = BlockedXMLHttpRequest;
g.WebSocket = BlockedWebSocket;
net.connect = throwBlocked as unknown as typeof net.connect;
net.createConnection = throwBlocked as unknown as typeof net.createConnection;
