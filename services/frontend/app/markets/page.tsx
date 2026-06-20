"use client";

import { useEffect, useState } from "react";
import { TopMarketsTable } from "@/components/markets/TopMarketsTable";
import { MarketHeatmap } from "@/components/markets/MarketHeatmap";
import { MarketDetailCard } from "@/components/markets/MarketDetailCard";
import { ClusterView } from "@/components/markets/ClusterView";
import { getMarketDetails } from "@/lib/api";
import type { MarketDetail, MarketScore } from "@/lib/types";
import { useAppStore } from "@/lib/store";

export default function MarketsPage() {
  const setMapViewState = useAppStore((s) => s.setMapViewState);
  const [selected, setSelected] = useState<MarketDetail | null>(null);

  const handleSelect = async (m: MarketScore) => {
    setMapViewState({ latitude: m.lat, longitude: m.lng, zoom: 7, pitch: 40, bearing: 0 });
    try {
      const detail = await getMarketDetails(m.city, m.state);
      setSelected({
        ...m,
        ...detail,
        top_lanes: detail.top_lanes ?? [],
        rate_history: detail.rate_history ?? [],
      });
    } catch {
      setSelected({ ...m, top_lanes: [], rate_history: [] });
    }
  };

  return (
    <div className="space-y-6 p-4 lg:p-6">
      <div>
        <h1 className="text-2xl font-bold">Top Markets</h1>
        <p className="text-text-secondary">Ranked by outbound volume, rates, and lane balance</p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <TopMarketsTable onSelect={handleSelect} />
        {selected ? (
          <MarketDetailCard market={selected} />
        ) : (
          <div className="flex items-center justify-center rounded-lg border border-dashed border-border p-8 text-sm text-text-secondary">
            Select a market from the table to view details
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-3 text-xl font-bold">Market Heatmap</h2>
        <MarketHeatmap />
      </div>

      <div>
        <h2 className="mb-3 text-xl font-bold">Cluster Analysis</h2>
        <ClusterView />
      </div>
    </div>
  );
}
