"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { HeroLanding } from "@/components/landing/HeroLanding";
import { LoadMapDynamic } from "@/components/map/LoadMapDynamic";
import { LoadCard } from "@/components/loads/LoadCard";
import { LoadChainView } from "@/components/loads/LoadChainView";
import { LoadCompare } from "@/components/loads/LoadCompare";
import { DashboardStats } from "@/components/stats/DashboardStats";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { getDashboardStats } from "@/lib/api";
import { useAppStore } from "@/lib/store";

export default function DashboardPage() {
  const showHero = useAppStore((s) => s.showHero);
  const recommendedLoads = useAppStore((s) => s.recommendedLoads);
  const loadChain = useAppStore((s) => s.loadChain);
  const isStreaming = useAppStore((s) => s.isStreaming);
  const selectLoad = useAppStore((s) => s.selectLoad);
  const setMapViewState = useAppStore((s) => s.setMapViewState);
  const updateStats = useAppStore.setState;

  useEffect(() => {
    getDashboardStats().then((stats) => updateStats({ dashboardStats: stats, totalLoads: stats.total_loads }));
  }, [updateStats]);

  const handleShowMap = (load: (typeof recommendedLoads)[0]) => {
    selectLoad(load);
    if (load.origin_lat && load.origin_lng) {
      setMapViewState({
        latitude: load.origin_lat,
        longitude: load.origin_lng,
        zoom: 6,
        pitch: 25,
        bearing: 0,
      });
    }
  };

  return (
    <AnimatePresence mode="wait">
      {showHero ? (
        <motion.div
          key="hero"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, y: -24 }}
          transition={{ duration: 0.4 }}
        >
          <HeroLanding />
        </motion.div>
      ) : (
        <motion.div
          key="dashboard"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
          className="flex h-[calc(100vh-5.5rem)] flex-col lg:flex-row"
        >
          <aside className="w-full shrink-0 lg:w-[400px] lg:border-r lg:border-border">
            <div className="h-[45vh] lg:h-full">
              <ChatPanel />
            </div>
          </aside>

          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="space-y-3 border-b border-border p-4">
              <DashboardStats />
            </div>

            <div className="relative min-h-[300px] flex-1">
              <ErrorBoundary fallbackTitle="Map failed to load">
                <LoadMapDynamic />
              </ErrorBoundary>
            </div>

            <div className="max-h-[40vh] overflow-y-auto border-t border-border p-4">
              {recommendedLoads.length === 0 ? (
                <p className="py-6 text-center text-sm text-text-secondary">
                  {isStreaming
                    ? "Calculating your best loads…"
                    : "Search from the left panel to see ranked loads here."}
                </p>
              ) : (
                <>
                  <h3 className="mb-3 text-sm font-semibold text-text-secondary">
                    Top loads by net profit
                  </h3>
                  {recommendedLoads.length >= 2 && (
                    <div className="mb-4">
                      <ErrorBoundary fallbackTitle="Comparison chart failed">
                        <LoadCompare loads={recommendedLoads} />
                      </ErrorBoundary>
                    </div>
                  )}
                  <div className="mb-4 grid gap-4 lg:grid-cols-2">
                    {recommendedLoads.map((load, i) => (
                      <LoadCard key={load.load_id} load={load} rank={i + 1} onShowMap={handleShowMap} />
                    ))}
                  </div>
                </>
              )}
              {loadChain && (
                <div className="mt-4">
                  <LoadChainView chain={loadChain} />
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
