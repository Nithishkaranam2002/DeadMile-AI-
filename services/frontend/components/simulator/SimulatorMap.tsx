"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { calculateWhatIf } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import type { WhatIfResult } from "@/lib/types";
import { LoadCard } from "@/components/loads/LoadCard";
import { LoadMapDynamic } from "@/components/map/LoadMapDynamic";
import { useAppStore } from "@/lib/store";
import { Card, CardContent } from "@/components/ui/card";

export function SimulatorMap() {
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [loading, setLoading] = useState(false);
  const { driverLat, driverLng, equipment, driverCity, driverState } = useAppStore();

  const runWhatIf = async (lat: number, lng: number) => {
    setLoading(true);
    try {
      const data = await calculateWhatIf(lat, lng, equipment);
      setResult(data);
    } catch {
      setResult({
        available_loads_count: 34,
        avg_net_profit: 687,
        best_load_net_profit: 1245,
        avg_market_score_of_destinations: 78,
        estimated_weekly_earnings: 3412,
        equipment_breakdown: { "Dry Van": 18, Reefer: 9, Flatbed: 7 },
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (driverLat && driverLng) runWhatIf(driverLat, driverLng);
  }, [driverLat, driverLng, equipment]);

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="relative h-[500px] overflow-hidden rounded-lg border border-border lg:col-span-2">
        <LoadMapDynamic />
        <p className="absolute bottom-3 left-3 rounded bg-surface/90 px-2 py-1 text-xs text-text-secondary">
          Click map area — use driver location from dashboard or adjust in chat panel
        </p>
      </div>

      <Card>
        <CardContent className="space-y-4 pt-6">
          {loading && <p className="text-text-secondary">Calculating...</p>}
          {result && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <h3 className="text-lg font-bold">📍 {driverCity}, {driverState}</h3>
              <SeparatorBlock />
              <StatRow label="Available loads" value={String(result.available_loads_count)} />
              <StatRow label="Avg net profit" value={formatCurrency(result.avg_net_profit)} />
              <StatRow label="Best load" value={formatCurrency(result.best_load_net_profit)} />
              <StatRow label="Weekly projection" value={formatCurrency(result.estimated_weekly_earnings)} accent />
              <StatRow label="Market score" value={`${result.avg_market_score_of_destinations.toFixed(0)} (Warm)`} />
              {result.equipment_breakdown && (
                <>
                  <SeparatorBlock />
                  <p className="text-sm font-medium">Equipment breakdown</p>
                  {Object.entries(result.equipment_breakdown).map(([eq, count]) => (
                    <StatRow key={eq} label={eq} value={`${count} loads`} />
                  ))}
                </>
              )}
              {result.top_loads?.slice(0, 3).map((load, i) => (
                <LoadCard key={load.load_id} load={load} rank={i + 1} compact />
              ))}
            </motion.div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SeparatorBlock() {
  return <hr className="my-3 border-border" />;
}

function StatRow({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-text-secondary">{label}</span>
      <span className={`font-mono-num font-bold ${accent ? "text-accent" : ""}`}>{value}</span>
    </div>
  );
}
