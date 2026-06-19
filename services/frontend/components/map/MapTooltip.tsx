"use client";

import { formatCurrency } from "@/lib/utils";
import type { ProfitBreakdown } from "@/lib/types";
import type { MarketScore } from "@/lib/types";

interface LoadTooltipProps {
  load: ProfitBreakdown;
}

interface MarketTooltipProps {
  market: MarketScore & { load_count?: number };
}

export function LoadMapTooltip({ load }: LoadTooltipProps) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-xl">
      <div className="font-bold text-text-primary">{load.load_id}</div>
      <div className="text-text-secondary">
        {load.origin} → {load.destination}
      </div>
      <div className="mt-1 font-mono-num text-accent">{formatCurrency(load.net_profit)} net</div>
      <div className="text-text-secondary">{load.loaded_miles} mi · {load.equipment}</div>
    </div>
  );
}

export function MarketMapTooltip({ market }: MarketTooltipProps) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-xl">
      <div className="font-bold text-text-primary">
        {market.city}, {market.state}
      </div>
      <div className="font-mono-num text-primary">Score: {market.market_score.toFixed(0)}</div>
      <div className="text-text-secondary">
        Loads: {market.load_count ?? market.outbound_load_count} · ${market.avg_outbound_rate.toFixed(2)}/mi
      </div>
    </div>
  );
}
