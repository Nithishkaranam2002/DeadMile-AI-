"use client";

import { useEffect, useState } from "react";
import { TopMarketsTable } from "@/components/markets/TopMarketsTable";
import { MarketHeatmap } from "@/components/markets/MarketHeatmap";
import { MarketDetailCard } from "@/components/markets/MarketDetailCard";
import { ClusterView } from "@/components/markets/ClusterView";
import { getMarketDetails } from "@/lib/api";
import { MOCK_MARKETS } from "@/lib/mock-data";
import type { MarketDetail, MarketScore } from "@/lib/types";
import { useAppStore } from "@/lib/store";

const MOCK_DETAIL: MarketDetail = {
  ...MOCK_MARKETS[0],
  top_lanes: [
    { destination: "Charlotte, NC", avg_rate: 2.52, load_count: 34 },
    { destination: "Miami, FL", avg_rate: 2.48, load_count: 28 },
    { destination: "Nashville, TN", avg_rate: 2.41, load_count: 22 },
    { destination: "Jacksonville, FL", avg_rate: 2.38, load_count: 19 },
    { destination: "Birmingham, AL", avg_rate: 2.35, load_count: 15 },
  ],
  rate_history: [
    { date: "Mar", rate: 2.28 },
    { date: "Apr", rate: 2.31 },
    { date: "May", rate: 2.38 },
    { date: "Jun", rate: 2.45 },
  ],
};

export default function MarketsPage() {
  const setMapViewState = useAppStore((s) => s.setMapViewState);
  const [selected, setSelected] = useState<MarketDetail | null>(MOCK_DETAIL);

  const handleSelect = async (m: MarketScore) => {
    setMapViewState({ latitude: m.lat, longitude: m.lng, zoom: 7, pitch: 40, bearing: 0 });
    try {
      const detail = await getMarketDetails(m.city, m.state);
      setSelected(detail);
    } catch {
      setSelected({ ...MOCK_DETAIL, ...m });
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
        {selected && <MarketDetailCard market={selected} />}
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
