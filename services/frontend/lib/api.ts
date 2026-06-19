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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const AGENT_BASE = process.env.NEXT_PUBLIC_AGENT_URL || "http://localhost:8001";
const MARKET_BASE = process.env.NEXT_PUBLIC_MARKET_URL || "http://localhost:8005";
const PROFIT_BASE = process.env.NEXT_PUBLIC_PROFIT_URL || "http://localhost:8004";

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

  (async () => {
    try {
      const resp = await fetch(`${AGENT_BASE}/chat/stream`, {
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
  const resp = await fetch(`${AGENT_BASE}/chat`, {
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
  const resp = await fetch(`${MARKET_BASE}/markets/top?limit=${limit}`);
  if (!resp.ok) throw new Error("Failed to fetch markets");
  return resp.json();
}

export async function getMarketHeatmap(): Promise<HeatmapData[]> {
  const resp = await fetch(`${MARKET_BASE}/markets/heatmap`);
  if (!resp.ok) throw new Error("Failed to fetch heatmap");
  return resp.json();
}

export async function getMarketDetails(city: string, state: string): Promise<MarketDetail> {
  const resp = await fetch(`${MARKET_BASE}/markets/${encodeURIComponent(city)}/${state}`);
  if (!resp.ok) throw new Error("Market not found");
  return resp.json();
}

export async function calculateWhatIf(
  lat: number,
  lng: number,
  equipment?: string
): Promise<WhatIfResult> {
  const resp = await fetch(`${PROFIT_BASE}/calculate/what-if`, {
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
  const resp = await fetch(`${API_BASE}/loads/search?${params}`);
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
  const resp = await fetch(`${PROFIT_BASE}/calculate/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ driver_lat: lat, driver_lng: lng, equipment, limit }),
  });
  if (!resp.ok) throw new Error("Batch calc failed");
  return resp.json();
}

export async function getDashboardStats(): Promise<DashboardStats> {
  try {
    const markets = await getTopMarkets(1);
    const loads = await searchLoads(39.8, -98.5, 500);
    return {
      total_loads: loads.length || 2847,
      avg_net_profit: 687,
      best_market: markets[0] ? `${markets[0].city}, ${markets[0].state}` : "Atlanta, GA",
      best_market_score: markets[0]?.market_score ?? 92,
      avg_rate_per_mile: markets[0]?.avg_outbound_rate ?? 2.34,
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

export async function getMarketClusters() {
  const resp = await fetch(`${MARKET_BASE}/markets/clusters`);
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
  const resp = await fetch(`${MARKET_BASE}/rates/predict`, {
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
