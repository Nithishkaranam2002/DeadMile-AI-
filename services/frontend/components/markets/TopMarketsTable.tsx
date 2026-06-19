"use client";

import { useEffect, useState } from "react";
import { getTopMarkets } from "@/lib/api";
import { MOCK_MARKETS } from "@/lib/mock-data";
import { marketColor, marketEmoji } from "@/lib/utils";
import type { MarketScore } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

const MEDALS = ["🥇", "🥈", "🥉"];

export function TopMarketsTable({ onSelect }: { onSelect?: (m: MarketScore) => void }) {
  const [markets, setMarkets] = useState<MarketScore[]>(MOCK_MARKETS);
  const [sortKey, setSortKey] = useState<keyof MarketScore>("market_score");
  const [desc, setDesc] = useState(true);

  useEffect(() => {
    getTopMarkets(25).then(setMarkets).catch(() => setMarkets(MOCK_MARKETS));
  }, []);

  const sorted = [...markets].sort((a, b) => {
    const av = a[sortKey] as number;
    const bv = b[sortKey] as number;
    return desc ? bv - av : av - bv;
  });

  const toggleSort = (key: keyof MarketScore) => {
    if (sortKey === key) setDesc(!desc);
    else {
      setSortKey(key);
      setDesc(true);
    }
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-surface-hover text-left text-xs uppercase text-text-secondary">
          <tr>
            <th className="p-3">Rank</th>
            <th className="p-3 cursor-pointer" onClick={() => toggleSort("city")}>City</th>
            <th className="p-3 cursor-pointer" onClick={() => toggleSort("market_score")}>Score</th>
            <th className="p-3">Label</th>
            <th className="p-3 cursor-pointer" onClick={() => toggleSort("outbound_load_count")}>Outbound</th>
            <th className="p-3 cursor-pointer" onClick={() => toggleSort("avg_outbound_rate")}>Avg $/mi</th>
            <th className="p-3">Balance</th>
            <th className="p-3">Cluster</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((m, i) => (
            <tr
              key={`${m.city}-${m.state}`}
              className="cursor-pointer border-t border-border hover:bg-surface-hover"
              onClick={() => onSelect?.(m)}
            >
              <td className="p-3">{i < 3 ? MEDALS[i] : i + 1}</td>
              <td className="p-3 font-medium">{m.city}, {m.state}</td>
              <td className="p-3 font-mono-num font-bold text-primary">{m.market_score.toFixed(0)}</td>
              <td className={`p-3 ${marketColor(m.label)}`}>{marketEmoji(m.label)} {m.label}</td>
              <td className="p-3 font-mono-num">{m.outbound_load_count}</td>
              <td className="p-3 font-mono-num">${m.avg_outbound_rate.toFixed(2)}</td>
              <td className="p-3 font-mono-num">{m.lane_balance_ratio.toFixed(1)}</td>
              <td className="p-3">
                {m.cluster_label && <Badge variant="outline">{m.cluster_label}</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
