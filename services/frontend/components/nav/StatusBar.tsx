"use client";

import { useEffect, useState } from "react";
import { getHealthAll } from "@/lib/api";
import { useAppStore } from "@/lib/store";

export function StatusBar() {
  const connected = useAppStore((s) => s.connected);
  const totalLoads = useAppStore((s) => s.totalLoads);
  const agentStatus = useAppStore((s) => s.agentStatus);
  const setConnected = useAppStore((s) => s.setConnected);
  const [lastUpdated, setLastUpdated] = useState(new Date());

  useEffect(() => {
    const poll = async () => {
      try {
        const health = await getHealthAll();
        setConnected(health.status === "healthy" || health.status === "degraded");
        setLastUpdated(new Date());
      } catch {
        setConnected(false);
      }
    };
    poll();
    const interval = setInterval(poll, 30000);
    return () => clearInterval(interval);
  }, [setConnected]);

  return (
    <footer className="flex h-8 items-center justify-between border-t border-border bg-surface px-4 text-xs text-text-secondary">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${connected ? "bg-accent" : "bg-danger"}`} />
        {connected ? "Connected" : "Disconnected"}
      </div>
      <div>Loads: {totalLoads.toLocaleString()}</div>
      <div>
        Agent:{" "}
        <span
          className={
            agentStatus === "ready"
              ? "text-accent"
              : agentStatus === "thinking"
                ? "text-primary"
                : "text-danger"
          }
        >
          {agentStatus === "ready" ? "Ready" : agentStatus === "thinking" ? "Thinking..." : "Error"}
        </span>
      </div>
      <div>Updated: {lastUpdated.toLocaleTimeString()}</div>
    </footer>
  );
}
