"use client";

import { marketColor, marketEmoji } from "@/lib/utils";
import type { MarketDetail } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { RateTrendChart } from "@/components/charts/RateTrendChart";
import { MarketRadar } from "@/components/charts/MarketRadar";

interface MarketDetailCardProps {
  market: MarketDetail;
  onClose?: () => void;
}

export function MarketDetailCard({ market }: MarketDetailCardProps) {
  const radarData = [
    { dimension: "Volume", value: Math.min(100, market.outbound_load_count / 1.5) },
    { dimension: "Rate", value: Math.min(100, market.avg_outbound_rate * 35) },
    { dimension: "Balance", value: Math.min(100, market.lane_balance_ratio * 40) },
    { dimension: "Diversity", value: market.equipment_diversity ?? 65 },
    { dimension: "Score", value: market.market_score },
  ];

  const inboundRatio = market.inbound_load_count ?? Math.round(market.outbound_load_count / market.lane_balance_ratio);
  const total = market.outbound_load_count + inboundRatio;
  const outboundPct = (market.outbound_load_count / total) * 100;

  return (
    <Card className="h-full overflow-y-auto">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div>
            <CardTitle>
              {market.city}, {market.state}
            </CardTitle>
            <p className={`mt-1 text-lg font-bold ${marketColor(market.label)}`}>
              {marketEmoji(market.label)} {market.label} · {market.market_score.toFixed(0)}/100
            </p>
          </div>
          {market.cluster_label && <Badge variant="default">{market.cluster_label}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-md bg-surface-hover p-2">
            <div className="text-text-secondary">Outbound Loads</div>
            <div className="font-mono-num text-xl font-bold">{market.outbound_load_count}</div>
          </div>
          <div className="rounded-md bg-surface-hover p-2">
            <div className="text-text-secondary">Avg Rate/mi</div>
            <div className="font-mono-num text-xl font-bold text-primary">
              ${market.avg_outbound_rate.toFixed(2)}
            </div>
          </div>
        </div>

        <div>
          <p className="mb-2 text-sm font-medium">Inbound vs Outbound</p>
          <div className="flex h-4 overflow-hidden rounded-full">
            <div className="bg-accent" style={{ width: `${outboundPct}%` }} title="Outbound" />
            <div className="bg-primary/60" style={{ width: `${100 - outboundPct}%` }} title="Inbound" />
          </div>
          <div className="mt-1 flex justify-between text-xs text-text-secondary">
            <span>Outbound {outboundPct.toFixed(0)}%</span>
            <span>Inbound {(100 - outboundPct).toFixed(0)}%</span>
          </div>
        </div>

        {market.top_lanes && market.top_lanes.length > 0 && (
          <div>
            <p className="mb-2 text-sm font-medium">Top Outbound Lanes</p>
            <div className="space-y-1 text-sm">
              {market.top_lanes.map((lane) => (
                <div key={lane.destination} className="flex justify-between rounded bg-surface-hover px-2 py-1">
                  <span>{lane.destination}</span>
                  <span className="font-mono-num text-primary">${lane.avg_rate.toFixed(2)}/mi</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <Separator />

        {market.rate_history && market.rate_history.length > 0 && (
          <RateTrendChart data={market.rate_history} title="Rate Trend (90 days)" />
        )}

        <MarketRadar data={radarData} />
      </CardContent>
    </Card>
  );
}
