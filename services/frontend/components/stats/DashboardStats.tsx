"use client";

import { DollarSign, MapPin, Package, TrendingUp } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { StatCard } from "./StatCard";

export function DashboardStats() {
  const stats = useAppStore((s) => s.dashboardStats);

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StatCard icon={<Package className="h-4 w-4" />} label="Total Loads" value={stats.total_loads.toLocaleString()} />
      <StatCard icon={<DollarSign className="h-4 w-4" />} label="Avg Net Profit" value={stats.avg_net_profit} trend={12} />
      <StatCard
        icon={<MapPin className="h-4 w-4" />}
        label="Best Market"
        value={`${stats.best_market} (${stats.best_market_score})`}
      />
      <StatCard icon={<TrendingUp className="h-4 w-4" />} label="Avg Rate/Mi" value={`$${(stats.avg_rate_per_mile ?? 0).toFixed(2)}`} />
    </div>
  );
}
