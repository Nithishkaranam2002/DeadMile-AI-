"use client";

import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Legend,
} from "recharts";

export interface RadarDimension {
  dimension: string;
  value: number;
  fullMark?: number;
}

interface MarketRadarProps {
  data: RadarDimension[];
  color?: string;
}

export function MarketRadar({ data, color = "#22D3EE" }: MarketRadarProps) {
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data}>
          <PolarGrid stroke="#2A2A35" />
          <PolarAngleAxis dataKey="dimension" tick={{ fill: "#94A3B8", fontSize: 11 }} />
          <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fill: "#64748B", fontSize: 10 }} />
          <Radar name="Score" dataKey="value" stroke={color} fill={color} fillOpacity={0.35} />
          <Legend />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
