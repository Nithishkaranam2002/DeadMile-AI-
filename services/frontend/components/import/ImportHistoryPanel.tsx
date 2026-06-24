"use client";

import { useEffect, useState } from "react";
import { Clock, ChevronRight } from "lucide-react";
import { getImportHistory, getImportHistoryItem, type ImportHistorySummary } from "@/lib/api";
import type { ImportAnalyzeResult } from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/utils";

interface ImportHistoryPanelProps {
  onSelect: (result: ImportAnalyzeResult, meta: { city: string; equipment: string }) => void;
  refreshKey?: number;
}

export function ImportHistoryPanel({ onSelect, refreshKey = 0 }: ImportHistoryPanelProps) {
  const [items, setItems] = useState<ImportHistorySummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getImportHistory()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const openItem = async (id: number) => {
    try {
      const item = await getImportHistoryItem(id);
      onSelect(
        {
          loads: item.loads,
          parsed_count: item.parsed_count,
          insight: item.insight,
        },
        {
          city: [item.driver_city, item.driver_state].filter(Boolean).join(", "),
          equipment: item.equipment || "Dry Van",
        }
      );
    } catch {
      /* ignore */
    }
  };

  if (loading) {
    return <p className="text-xs text-text-secondary">Loading history…</p>;
  }

  if (items.length === 0) {
    return (
      <p className="text-xs text-text-secondary">
        No saved analyses yet. Run an import and click Save.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            onClick={() => openItem(item.id)}
            className={cn(
              "flex w-full items-center justify-between rounded-lg border border-border bg-surface p-3 text-left",
              "hover:border-primary/40 hover:bg-surface-hover"
            )}
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1 text-xs text-text-secondary">
                <Clock className="h-3 w-3 shrink-0" />
                {item.created_at ? new Date(item.created_at).toLocaleString() : "—"}
              </div>
              <div className="truncate text-sm font-medium">{item.top_load || `${item.parsed_count} loads`}</div>
              {item.top_net_profit != null && (
                <div className="text-xs text-accent">
                  Top net {formatCurrency(item.top_net_profit)}
                </div>
              )}
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-text-secondary" />
          </button>
        </li>
      ))}
    </ul>
  );
}
