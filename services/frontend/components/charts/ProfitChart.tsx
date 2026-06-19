"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { ProfitBreakdown } from "@/lib/types";

interface ProfitChartProps {
  load: ProfitBreakdown;
}

export function ProfitChart({ load }: ProfitChartProps) {
  const data = [
    { name: "Revenue", value: load.revenue, color: "#10B981" },
    { name: "Fuel", value: -load.fuel_cost, color: "#EF4444" },
    { name: "Driver", value: -load.driver_cost, color: "#F87171" },
    { name: "Insurance", value: -load.insurance_cost, color: "#FB923C" },
    { name: "Maint.", value: -load.maintenance_cost, color: "#F97316" },
    { name: "Tolls", value: -load.tolls_cost, color: "#F59E0B" },
    { name: "Dispatch", value: -load.dispatch_fee, color: "#EAB308" },
    { name: "Factoring", value: -load.factoring_fee, color: "#DC2626" },
    { name: "Overhead", value: -load.overhead_cost, color: "#B91C1C" },
  ];

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 8 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="name" width={72} tick={{ fill: "#94A3B8", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ background: "#12121A", border: "1px solid #2A2A35", borderRadius: 8 }}
            labelStyle={{ color: "#F8FAFC" }}
            formatter={(v: number) => [`$${Math.abs(v).toLocaleString()}`, ""]}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
