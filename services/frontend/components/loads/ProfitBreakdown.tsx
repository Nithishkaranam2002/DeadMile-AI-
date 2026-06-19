"use client";

import { formatCurrency } from "@/lib/utils";
import type { ProfitBreakdown } from "@/lib/types";
import { Separator } from "@/components/ui/separator";
import { ProfitChart } from "@/components/charts/ProfitChart";

export function ProfitBreakdownView({ load }: { load: ProfitBreakdown }) {
  const items = [
    { label: "Fuel", value: -load.fuel_cost },
    { label: "Driver Pay", value: -load.driver_cost },
    { label: "Insurance", value: -load.insurance_cost },
    { label: "Maintenance", value: -load.maintenance_cost },
    { label: "Tolls", value: -load.tolls_cost },
    { label: "Dispatch Fee", value: -load.dispatch_fee },
    { label: "Factoring Fee", value: -load.factoring_fee },
    { label: "Overhead", value: -load.overhead_cost },
  ];

  return (
    <div className="mt-2 rounded-md border border-border bg-background p-3 text-sm">
      <ProfitChart load={load} />
      <Separator className="my-3" />
      <div className="flex justify-between font-mono-num">
        <span>Revenue</span>
        <span className="text-accent">{formatCurrency(load.revenue)}</span>
      </div>
      <Separator className="my-2" />
      {items.map((item) => (
        <div key={item.label} className="flex justify-between font-mono-num text-text-secondary">
          <span>{item.label}</span>
          <span className="text-danger">{formatCurrency(item.value)}</span>
        </div>
      ))}
      <Separator className="my-2" />
      <div className="flex justify-between font-mono-num font-bold">
        <span>NET PROFIT</span>
        <span className={load.net_profit >= 0 ? "text-accent" : "text-danger"}>
          {formatCurrency(load.net_profit)} ({load.profit_margin_percent.toFixed(1)}%)
        </span>
      </div>
      <div className="mt-1 flex justify-between font-mono-num text-text-secondary">
        <span>Net $/mile</span>
        <span>${load.net_rate_per_mile.toFixed(2)}</span>
      </div>
    </div>
  );
}
