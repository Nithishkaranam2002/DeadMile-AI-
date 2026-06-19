import type {
  AgentEvent,
  DashboardStats,
  HeatmapData,
  Load,
  MarketDetail,
  MarketScore,
  ProfitBreakdown,
  WhatIfResult,
} from "./types";

/** Resolve API base URL at runtime so Docker port changes don't require a rebuild. */
export function getApiBase(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl && !envUrl.endsWith(":8000")) {
    return envUrl.replace(/\/$/, "");
  }

  if (typeof window !== "undefined") {
    const { protocol, hostname, port, origin } = window.location;
    if (port === "8888" || port === "80" || port === "443") {
      return `${origin}/api`;
    }
    if (port === "3000" || port === "") {
      return `${protocol}//${hostname}:8010`;
    }
    return `${origin}/api`;
  }

  return envUrl?.replace(/\/$/, "") || "http://localhost:8010";
}

/** Direct agent-core URL (debug/SSE); most calls go through getApiBase(). */
export function getAgentBase(): string {
  const envUrl = process.env.NEXT_PUBLIC_AGENT_URL;
  if (envUrl) {
    return envUrl.replace(/\/$/, "");
  }

  if (typeof window !== "undefined") {
    const { protocol, hostname, port, origin } = window.location;
    if (port === "8888" || port === "80" || port === "443") {
      return `${origin}/agent`;
    }
    return `${protocol}//${hostname}:8001`;
  }

  return "http://localhost:8001";
}

export function streamChat(
  message: string,
  driverLat: number,
  driverLng: number,
  onEvent: (event: AgentEvent) => void,
  options?: {
    equipment?: string;
    maxDeadhead?: number;
    driverId?: string;
    sessionId?: string;
  }
): AbortController {
  const controller = new AbortController();
  const apiBase = getApiBase();

  (async () => {
    try {
      const resp = await fetch(`${apiBase}/recommend/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({
          message,
          driver_lat: driverLat,
          driver_lng: driverLng,
          equipment: options?.equipment,
          max_deadhead: options?.maxDeadhead ?? 250,
          driver_id: options?.driverId,
          session_id: options?.sessionId,
        }),
        signal: controller.signal,
      });

      if (!resp.ok || !resp.body) {
        onEvent({ type: "error", data: { message: `Agent error: ${resp.status}` } });
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          let eventType = "message";
          let dataStr = "";
          for (const line of part.split("\n")) {
            if (line.startsWith("event:")) eventType = line.slice(6).trim();
            if (line.startsWith("data:")) dataStr = line.slice(5).trim();
          }
          if (dataStr) {
            try {
              const data = JSON.parse(dataStr);
              onEvent({ type: eventType as AgentEvent["type"], data });
            } catch {
              onEvent({ type: eventType as AgentEvent["type"], data: { raw: dataStr } });
            }
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onEvent({ type: "error", data: { message: String(err) } });
      }
    }
  })();

  return controller;
}

export async function chatSync(
  message: string,
  driverLat: number,
  driverLng: number,
  equipment?: string,
  maxDeadhead?: number
): Promise<{ response: string }> {
  const resp = await fetch(`${getApiBase()}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      driver_lat: driverLat,
      driver_lng: driverLng,
      equipment,
      max_deadhead: maxDeadhead ?? 250,
    }),
  });
  return resp.json();
}

export async function getTopMarkets(limit = 10): Promise<MarketScore[]> {
  const resp = await fetch(`${getApiBase()}/markets/top?limit=${limit}`);
  if (!resp.ok) throw new Error("Failed to fetch markets");
  return resp.json();
}

export async function getMarketHeatmap(): Promise<HeatmapData[]> {
  const resp = await fetch(`${getApiBase()}/markets/heatmap`);
  if (!resp.ok) throw new Error("Failed to fetch heatmap");
  return resp.json();
}

export async function getMarketDetails(city: string, state: string): Promise<MarketDetail> {
  const resp = await fetch(`${getApiBase()}/markets/${encodeURIComponent(city)}/${state}`);
  if (!resp.ok) throw new Error("Market not found");
  return resp.json();
}

export async function calculateWhatIf(
  lat: number,
  lng: number,
  equipment?: string
): Promise<WhatIfResult> {
  const resp = await fetch(`${getApiBase()}/simulate/what-if`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lat, lng, equipment }),
  });
  if (!resp.ok) throw new Error("What-if failed");
  return resp.json();
}

export async function searchLoads(
  lat: number,
  lng: number,
  radius: number,
  equipment?: string
): Promise<Load[]> {
  const params = new URLSearchParams({ lat: String(lat), lng: String(lng), radius: String(radius) });
  if (equipment) params.set("equipment", equipment);
  const resp = await fetch(`${getApiBase()}/loads/search?${params}`);
  if (!resp.ok) throw new Error("Search failed");
  const data = await resp.json();
  return data.loads || [];
}

export async function calculateBatch(
  lat: number,
  lng: number,
  equipment: string,
  limit = 10
): Promise<ProfitBreakdown[]> {
  const resp = await fetch(`${getApiBase()}/simulate/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ driver_lat: lat, driver_lng: lng, equipment, limit }),
  });
  if (!resp.ok) throw new Error("Batch calc failed");
  return resp.json();
}

export async function getDashboardStats(): Promise<DashboardStats> {
  try {
    const resp = await fetch(`${getApiBase()}/dashboard/stats`);
    if (!resp.ok) throw new Error("stats failed");
    const data = await resp.json();
    return {
      total_loads: data.total_loads,
      avg_net_profit: data.avg_net_profit,
      best_market: data.best_market,
      best_market_score: data.best_market_score,
      avg_rate_per_mile: data.avg_rate_per_mile,
    };
  } catch {
    return {
      total_loads: 2847,
      avg_net_profit: 687,
      best_market: "Atlanta, GA",
      best_market_score: 92,
      avg_rate_per_mile: 2.34,
    };
  }
}

export async function getHealthAll(): Promise<{ status: string; services: Record<string, { status: string }> }> {
  const resp = await fetch(`${getApiBase()}/health/all`);
  if (!resp.ok) throw new Error("Health check failed");
  return resp.json();
}

export async function getMarketClusters() {
  const resp = await fetch(`${getApiBase()}/markets/clusters`);
  if (!resp.ok) return [];
  return resp.json();
}

export async function predictRate(
  originCity: string,
  originState: string,
  destCity: string,
  destState: string,
  equipment = "Dry Van"
) {
  const resp = await fetch(`${getApiBase()}/rates/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      origin_city: originCity,
      origin_state: originState,
      dest_city: destCity,
      dest_state: destState,
      equipment,
    }),
  });
  if (!resp.ok) throw new Error("Rate predict failed");
  return resp.json();
}

export async function optimizeChain(params: {
  start_lat: number;
  start_lng: number;
  equipment?: string;
  num_hops?: number;
  days?: number;
  prefer_return_to_start?: boolean;
}) {
  const resp = await fetch(`${getApiBase()}/chain/optimize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!resp.ok) throw new Error("Chain optimization failed");
  return resp.json();
}

export async function getChainResult(workflowId: string) {
  const resp = await fetch(`${getApiBase()}/chain/result/${workflowId}`);
  if (!resp.ok) throw new Error("Chain result not ready");
  return resp.json();
}
