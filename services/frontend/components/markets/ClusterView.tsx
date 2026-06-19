"use client";

import { useEffect, useState } from "react";
import { getMarketClusters } from "@/lib/api";
import { MOCK_MARKETS } from "@/lib/mock-data";
import type { MarketCluster } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadMapDynamic } from "@/components/map/LoadMapDynamic";
import { useAppStore } from "@/lib/store";

const CLUSTER_COLORS: Record<string, string> = {
  "Mega Hub": "#22D3EE",
  "Origin Heavy": "#10B981",
  "Destination Heavy": "#F59E0B",
  Balanced: "#A78BFA",
  Underserved: "#EF4444",
};

const CLUSTER_DESCRIPTIONS: Record<string, string> = {
  "Mega Hub": "High volume both ways — ideal relay points",
  "Origin Heavy": "Strong outbound freight, fewer inbound loads",
  "Destination Heavy": "Inbound-heavy — plan deadhead carefully",
  Balanced: "Moderate volume with stable lane balance",
  Underserved: "Low volume markets — higher deadhead risk",
};

export function ClusterView() {
  const [clusters, setClusters] = useState<MarketCluster[]>([]);
  const setTopMarkets = useAppStore((s) => s.setTopMarkets);
  const toggleHeatmap = useAppStore((s) => s.toggleHeatmap);
  const showHeatmap = useAppStore((s) => s.showHeatmap);

  useEffect(() => {
    getMarketClusters()
      .then(setClusters)
      .catch(() => {
        setClusters(
          MOCK_MARKETS.map((m, i) => ({
            city: m.city,
            state: m.state,
            lat: m.lat,
            lng: m.lng,
            cluster_id: i % 5,
            cluster_label: m.cluster_label || "Balanced",
            features: {},
          }))
        );
      });
    if (!showHeatmap) toggleHeatmap();
    setTopMarkets(MOCK_MARKETS);
  }, [setTopMarkets, showHeatmap, toggleHeatmap]);

  const uniqueClusters = [...new Set(clusters.map((c) => c.cluster_label))];

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Market Clusters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {uniqueClusters.map((label) => (
            <div key={label} className="rounded-md border border-border p-3">
              <div className="flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 rounded-full"
                  style={{ background: CLUSTER_COLORS[label] || "#94A3B8" }}
                />
                <Badge variant="outline">{label}</Badge>
              </div>
              <p className="mt-2 text-xs text-text-secondary">
                {CLUSTER_DESCRIPTIONS[label] || "Cluster segment"}
              </p>
              <p className="mt-1 text-xs font-mono-num text-text-secondary">
                {clusters.filter((c) => c.cluster_label === label).length} markets
              </p>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="h-[480px] overflow-hidden rounded-lg border border-border">
        <LoadMapDynamic />
      </div>
    </div>
  );
}
