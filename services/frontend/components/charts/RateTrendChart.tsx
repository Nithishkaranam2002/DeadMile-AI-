"use client";

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

export interface RateHistoryPoint {
  date: string;
  rate: number;
}

interface RateTrendChartProps {
  data: RateHistoryPoint[];
  title?: string;
}

export function RateTrendChart({ data, title }: RateTrendChartProps) {
  return (
    <div className="w-full">
      {title && <p className="mb-2 text-sm font-medium text-text-secondary">{title}</p>}
      <div className="h-52 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#2A2A35" strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fill: "#94A3B8", fontSize: 11 }} />
            <YAxis
              tick={{ fill: "#94A3B8", fontSize: 11 }}
              domain={["auto", "auto"]}
              tickFormatter={(v) => `$${v.toFixed(2)}`}
            />
            <Tooltip
              contentStyle={{ background: "#12121A", border: "1px solid #2A2A35", borderRadius: 8 }}
              formatter={(v: number) => [`$${v.toFixed(2)}/mi`, "Rate"]}
            />
            <Line type="monotone" dataKey="rate" stroke="#22D3EE" strokeWidth={2} dot={{ fill: "#22D3EE", r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
