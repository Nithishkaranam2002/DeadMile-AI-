"use client";

import { motion } from "framer-motion";
import { formatCurrency } from "@/lib/utils";
import type { LoadChain } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function LoadChainView({ chain }: { chain: LoadChain }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Optimal Load Chain</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="relative ml-4 border-l-2 border-primary/40 pl-6">
          <div className="mb-4 text-sm text-text-secondary">📍 Start</div>
          {chain.hops.map((hop, i) => (
            <motion.div
              key={hop.load_id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.15 }}
              className="relative mb-6"
            >
              <div className="absolute -left-[31px] top-1 h-3 w-3 rounded-full bg-primary" />
              {hop.deadhead_miles > 0 && (
                <p className="mb-1 text-xs text-text-secondary">{hop.deadhead_miles}mi deadhead</p>
              )}
              <div className="rounded-md border border-border bg-surface-hover p-3">
                <p className="font-medium">🚛 Load {i + 1}: {hop.origin} → {hop.destination}</p>
                <p className="font-mono-num text-accent">{formatCurrency(hop.net_profit)} net</p>
                <p className="text-xs text-text-secondary">{hop.load_id} · {hop.equipment}</p>
              </div>
            </motion.div>
          ))}
        </div>
        <div className="mt-4 rounded-md bg-surface-hover p-4 text-center">
          <p className="text-sm text-text-secondary">
            TOTAL: {chain.hops.length} loads · {chain.estimated_days} days
          </p>
          <p className="font-mono-num text-2xl font-bold text-accent">
            {formatCurrency(chain.cumulative_net_profit)} net
          </p>
          <p className="mt-2 text-sm text-text-secondary">
            Weekly: {formatCurrency(chain.weekly_projection)} · Monthly: {formatCurrency(chain.monthly_projection)}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
