"use client";

import { useEffect, useState } from "react";
import { getMarketHeatmap } from "@/lib/api";
import { MOCK_MARKETS } from "@/lib/mock-data";
import { LoadMapDynamic } from "@/components/map/LoadMapDynamic";
import { useAppStore } from "@/lib/store";

export function MarketHeatmap() {
  const setTopMarkets = useAppStore((s) => s.setTopMarkets);
  const toggleHeatmap = useAppStore((s) => s.toggleHeatmap);
  const showHeatmap = useAppStore((s) => s.showHeatmap);

  useEffect(() => {
    if (!showHeatmap) toggleHeatmap();
    getMarketHeatmap()
      .then((data) => {
        const markets = data.map((d) => ({
          city: d.city,
          state: d.state,
          lat: d.lat,
          lng: d.lng,
          outbound_load_count: d.load_count,
          avg_outbound_rate: d.avg_rate,
          avg_inbound_rate: 0,
          lane_balance_ratio: 1,
          market_score: d.score,
          label: d.score >= 70 ? "Warm" : d.score >= 90 ? "Hot" : "Neutral",
        }));
        setTopMarkets(markets.length ? markets : MOCK_MARKETS);
      })
      .catch(() => setTopMarkets(MOCK_MARKETS));
  }, [setTopMarkets, showHeatmap, toggleHeatmap]);

  return (
    <div className="h-[600px] overflow-hidden rounded-lg border border-border">
      <LoadMapDynamic />
    </div>
  );
}
