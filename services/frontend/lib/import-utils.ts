import type { ImportAnalyzeResult } from "./api";
import type { ProfitBreakdown } from "./types";
import { formatCurrency } from "./utils";

export type SortKey = "score" | "net" | "margin" | "deadhead" | "rate_per_mile";

export function sortLoads(loads: ProfitBreakdown[], key: SortKey): ProfitBreakdown[] {
  const copy = [...loads];
  switch (key) {
    case "net":
      return copy.sort((a, b) => (b.net_profit ?? 0) - (a.net_profit ?? 0));
    case "margin":
      return copy.sort((a, b) => (b.profit_margin_percent ?? 0) - (a.profit_margin_percent ?? 0));
    case "deadhead":
      return copy.sort((a, b) => (a.deadhead_to_pickup ?? 0) - (b.deadhead_to_pickup ?? 0));
    case "rate_per_mile":
      return copy.sort((a, b) => {
        const ar = (a.gross_rate ?? 0) / (a.loaded_miles || 1);
        const br = (b.gross_rate ?? 0) / (b.loaded_miles || 1);
        return br - ar;
      });
    default:
      return copy.sort((a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0));
  }
}

export function buildImportSummary(result: ImportAnalyzeResult, location: string): string {
  const lines = [
    "DeadMile AI — Load Analysis",
    `Location: ${location}`,
    `Parsed ${result.parsed_count} loads`,
    "",
    ...result.loads.map((load, i) => {
      const rpm = load.loaded_miles
        ? ((load.gross_rate ?? 0) / load.loaded_miles).toFixed(2)
        : "?";
      return (
        `#${i + 1} ${load.origin} → ${load.destination}\n` +
        `   Gross ${formatCurrency(load.gross_rate ?? 0)} · ` +
        `Net ${formatCurrency(load.net_profit ?? 0)} (${(load.profit_margin_percent ?? 0).toFixed(1)}%) · ` +
        `$${rpm}/mi · ${load.destination_market_label}`
      );
    }),
    "",
    `Insight: ${result.insight}`,
    "",
    "100% free — deadmile.ai",
  ];
  return lines.join("\n");
}

export function encodeImportShare(result: ImportAnalyzeResult): string {
  return btoa(JSON.stringify(result));
}

export function decodeImportShare(encoded: string): ImportAnalyzeResult | null {
  try {
    return JSON.parse(atob(encoded)) as ImportAnalyzeResult;
  } catch {
    return null;
  }
}

export function importShareUrl(result: ImportAnalyzeResult): string {
  if (typeof window === "undefined") return "";
  const params = new URLSearchParams({ r: encodeImportShare(result) });
  return `${window.location.origin}/import?${params.toString()}`;
}

export const DEFAULT_COSTS = {
  fuel: 3.9,
  driverCpm: 0.55,
  insurance: 0.08,
};

export function isDefaultFleetCosts(profile: {
  fuel_price_per_gallon?: number;
  driver_cpm?: number;
  insurance_per_mile?: number;
}): boolean {
  return (
    Math.abs((profile.fuel_price_per_gallon ?? 0) - DEFAULT_COSTS.fuel) < 0.01 &&
    Math.abs((profile.driver_cpm ?? 0) - DEFAULT_COSTS.driverCpm) < 0.01 &&
    Math.abs((profile.insurance_per_mile ?? 0) - DEFAULT_COSTS.insurance) < 0.01
  );
}
