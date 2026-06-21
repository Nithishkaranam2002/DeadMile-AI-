"use client";

import { useEffect, useState } from "react";
import { getMarketHeatmap } from "@/lib/api";
import { isProductionMode } from "@/lib/config";
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
          label: d.score >= 90 ? "Hot" : d.score >= 70 ? "Warm" : d.score >= 50 ? "Neutral" : "Cool",
        }));
        setTopMarkets(markets.length ? markets : isProductionMode() ? [] : MOCK_MARKETS);
      })
      .catch(() => {
        if (!isProductionMode()) setTopMarkets(MOCK_MARKETS);
      });
    // Enable heatmap once on mount for this view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setTopMarkets]);

  return (
    <div className="h-[600px] overflow-hidden rounded-lg border border-border">
      <LoadMapDynamic />
    </div>
  );
}
