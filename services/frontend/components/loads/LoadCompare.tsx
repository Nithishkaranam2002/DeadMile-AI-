"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { formatCurrency } from "@/lib/utils";
import type { ProfitBreakdown } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const COLORS = ["#22D3EE", "#10B981", "#F59E0B"];

interface LoadCompareProps {
  loads: ProfitBreakdown[];
}

function normalize(value: number, min: number, max: number): number {
  if (max === min) return 50;
  return ((value - min) / (max - min)) * 100;
}

export function LoadCompare({ loads }: LoadCompareProps) {
  const compareLoads = loads.slice(0, 3);
  if (compareLoads.length < 2) return null;

  const radarData = useMemo(() => {
    const profits = compareLoads.map((l) => l.net_profit);
    const rates = compareLoads.map((l) => l.net_rate_per_mile);
    const scores = compareLoads.map((l) => l.composite_score);
    const deadheads = compareLoads.map((l) => l.deadhead_to_pickup);
    const timeEff = compareLoads.map((l) => l.loaded_miles);

    const dims = ["Net Profit", "$/Mile", "Market Score", "Time Eff.", "Deadhead"];
    return dims.map((dimension, i) => {
      const values = [
        [profits, Math.min(...profits), Math.max(...profits)],
        [rates, Math.min(...rates), Math.max(...rates)],
        [scores, Math.min(...scores), Math.max(...scores)],
        [timeEff.map((m) => -m), -Math.max(...timeEff), -Math.min(...timeEff)],
        [deadheads.map((d) => -d), -Math.max(...deadheads), -Math.min(...deadheads)],
      ][i];

      const [arr, min, max] = values as [number[], number, number];
      const row: Record<string, string | number> = { dimension };
      compareLoads.forEach((l, idx) => {
        row[l.load_id] = normalize(arr[idx], min, max);
      });
      return row;
    });
  }, [compareLoads]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Load Comparison</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="#2A2A35" />
                <PolarAngleAxis dataKey="dimension" tick={{ fill: "#94A3B8", fontSize: 11 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                {compareLoads.map((l, i) => (
                  <Radar
                    key={l.load_id}
                    name={l.load_id}
                    dataKey={l.load_id}
                    stroke={COLORS[i]}
                    fill={COLORS[i]}
                    fillOpacity={0.2}
                  />
                ))}
                <Legend />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          <div className="space-y-3">
            {compareLoads.map((l, i) => (
              <motion.div
                key={l.load_id}
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.1 }}
                className="rounded-md border border-border p-3"
                style={{ borderLeftColor: COLORS[i], borderLeftWidth: 3 }}
              >
                <div className="font-medium">{l.load_id}</div>
                <div className="text-sm text-text-secondary">
                  {l.origin} → {l.destination}
                </div>
                <div className="mt-1 grid grid-cols-3 gap-2 text-xs font-mono-num">
                  <span className="text-accent">{formatCurrency(l.net_profit)}</span>
                  <span>${l.net_rate_per_mile.toFixed(2)}/mi</span>
                  <span>Score {l.composite_score.toFixed(0)}</span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
