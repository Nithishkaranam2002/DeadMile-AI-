"use client";

import { Loader2 } from "lucide-react";
import { useAppStore } from "@/lib/store";

export function AgentStatusBar() {
  const isStreaming = useAppStore((s) => s.isStreaming);
  const activity = useAppStore((s) => s.agentActivity);

  if (!isStreaming) return null;

  return (
    <div className="flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-text-secondary">
      <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
      <span>{activity || "Finding your best loads…"}</span>
    </div>
  );
}
