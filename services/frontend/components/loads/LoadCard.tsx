"use client";

import { motion } from "framer-motion";
import { formatCurrency, marketColor, marketEmoji } from "@/lib/utils";
import type { ProfitBreakdown } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ProfitBreakdownView } from "./ProfitBreakdown";
import { useState } from "react";

interface LoadCardProps {
  load: ProfitBreakdown;
  rank?: number;
  compact?: boolean;
  onShowMap?: (load: ProfitBreakdown) => void;
}

export function LoadCard({ load, rank, compact = false, onShowMap }: LoadCardProps) {
  const [expanded, setExpanded] = useState(false);
  const netProfit = load.net_profit ?? 0;
  const profitPositive = netProfit >= 0;
  const compositeScore = load.composite_score ?? 0;
  const profitMargin = load.profit_margin_percent ?? 0;
  const deadhead = load.deadhead_to_pickup ?? 0;
  const marketLabel = load.destination_market_label || "Neutral";
  const destCity = load.dest_city?.trim() || load.destination?.split(",")[0]?.trim() || "Unknown";
  const destState = load.dest_state?.trim() || load.destination?.split(",")[1]?.trim() || "";
  const marketLocation = destState ? `${destCity}, ${destState}` : destCity;

  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        className="rounded-md border border-border bg-surface-hover p-2 text-xs"
      >
        <div className="font-medium">{load.load_id}</div>
        <div className="text-text-secondary">
          {load.origin} → {load.destination}
        </div>
        <div className={`font-mono-num font-bold ${profitPositive ? "text-accent" : "text-danger"}`}>
          {load.net_profit != null
            ? `${formatCurrency(netProfit)} net`
            : `${formatCurrency(load.gross_rate ?? load.rate ?? 0)} gross`}
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: (rank ?? 0) * 0.08 }}
    >
      <Card className="overflow-hidden hover:border-primary/40">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <div className="flex items-center gap-2">
            {rank !== undefined && (
              <Badge variant="default">#{rank} RECOMMENDED</Badge>
            )}
            <span className="text-sm text-text-secondary">{load.load_id}</span>
            <Badge variant="outline">{load.equipment}</Badge>
          </div>
          <div className="font-mono-num text-sm font-bold text-primary">
            Score: {compositeScore.toFixed(0)}/100
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <CardTitle className="text-base">
              {load.origin} → {load.destination}
            </CardTitle>
            <p className="text-sm text-text-secondary">{load.loaded_miles ?? load.miles ?? 0} mi · {load.commodity || "General freight"}</p>
          </div>

          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-md bg-surface-hover p-2">
              <div className="text-xs text-text-secondary">GROSS</div>
              <div className="font-mono-num font-bold">{formatCurrency(load.gross_rate ?? load.rate ?? 0)}</div>
            </div>
            <div className="rounded-md bg-surface-hover p-2">
              <div className="text-xs text-text-secondary">COSTS</div>
              <div className="font-mono-num font-bold text-danger">{formatCurrency(load.total_costs ?? 0)}</div>
            </div>
            <div className="rounded-md bg-surface-hover p-2">
              <div className="text-xs text-text-secondary">NET PROFIT</div>
              <div className={`font-mono-num text-lg font-bold ${profitPositive ? "text-accent" : "text-danger"}`}>
                {formatCurrency(netProfit)}
              </div>
              <div className="text-xs text-text-secondary">{profitMargin.toFixed(1)}%</div>
            </div>
          </div>

          <div className="flex flex-wrap gap-3 text-xs text-text-secondary">
            <span>Deadhead: {deadhead.toFixed(0)}mi</span>
            <span className={marketColor(marketLabel)}>
              {marketEmoji(marketLabel)} {marketLocation} · {marketLabel}
            </span>
            {load.pickup_window && <span>PU: {load.pickup_window}</span>}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => setExpanded(!expanded)}>
              {expanded ? "Hide Details" : "View Details"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => onShowMap?.(load)}>
              Show on Map
            </Button>
          </div>

          {expanded && <ProfitBreakdownView load={load} />}
        </CardContent>
      </Card>
    </motion.div>
  );
}
