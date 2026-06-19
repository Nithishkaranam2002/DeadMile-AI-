"use client";

import { motion } from "framer-motion";
import { TrendingDown, TrendingUp } from "lucide-react";
import { cn, formatCurrency } from "@/lib/utils";

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  trend?: number;
  className?: string;
}

export function StatCard({ icon, label, value, trend, className }: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("rounded-lg border border-border bg-surface p-4", className)}
    >
      <div className="mb-2 flex items-center gap-2 text-text-secondary">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <div className="font-mono-num text-2xl font-bold text-text-primary">
        {typeof value === "number" && label.toLowerCase().includes("profit")
          ? formatCurrency(value)
          : value}
      </div>
      {trend !== undefined && (
        <div className={cn("mt-1 flex items-center gap-1 text-xs", trend >= 0 ? "text-accent" : "text-danger")}>
          {trend >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
          {Math.abs(trend)}%
        </div>
      )}
    </motion.div>
  );
}
