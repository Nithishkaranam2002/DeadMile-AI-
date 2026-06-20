"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import type { AgentEvent } from "@/lib/types";
import { friendlyToolLabel } from "@/lib/agent-response";
import { getLoadById } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { ProfitBreakdown, LoadChain } from "@/lib/types";
import { AgentSummary } from "./AgentSummary";
import { AgentStatusBar } from "./AgentStatusBar";

interface AgentStreamProps {
  events: AgentEvent[];
}

function mergeRecommendedLoad(load: ProfitBreakdown): ProfitBreakdown[] {
  const current = useAppStore.getState().recommendedLoads;
  const merged = [...current.filter((l) => l.load_id !== load.load_id), load];
  merged.sort((a, b) => (b.net_profit ?? 0) - (a.net_profit ?? 0));
  return merged.slice(0, 5);
}

async function enrichAndMergeLoad(load: ProfitBreakdown): Promise<ProfitBreakdown> {
  if (load.origin_lat && load.dest_lat && load.dest_city) return load;

  try {
    const detail = await getLoadById(load.load_id);
    const [destCity, destState] = (detail.destination || ",").split(",").map((s) => s.trim());
    return {
      ...load,
      origin_lat: load.origin_lat ?? detail.origin_lat,
      origin_lng: load.origin_lng ?? detail.origin_lng,
      dest_lat: load.dest_lat ?? detail.dest_lat,
      dest_lng: load.dest_lng ?? detail.dest_lng,
      dest_city: load.dest_city ?? destCity,
      dest_state: load.dest_state ?? destState,
    };
  } catch {
    return load;
  }
}

export function AgentStream({ events }: AgentStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const addMessage = useAppStore((s) => s.addMessage);
  const setRecommendedLoads = useAppStore((s) => s.setRecommendedLoads);
  const setLoadChain = useAppStore((s) => s.setLoadChain);
  const setAgentStatus = useAppStore((s) => s.setAgentStatus);
  const setAgentActivity = useAppStore((s) => s.setAgentActivity);
  const processedRef = useRef(0);

  useEffect(() => {
    const newEvents = events.slice(processedRef.current);
    processedRef.current = events.length;

    for (const event of newEvents) {
      switch (event.type) {
        case "thinking":
          setAgentStatus("thinking");
          setAgentActivity(String(event.data.message || "Finding your best loads…"));
          break;
        case "tool_call": {
          const tool = String(event.data.tool || "");
          setAgentActivity(friendlyToolLabel(tool));
          break;
        }
        case "tool_result":
          break;
        case "load_found": {
          const load = (event.data.load || event.data) as ProfitBreakdown;
          if (typeof load.net_profit === "number" && typeof load.composite_score === "number") {
            void enrichAndMergeLoad(load).then((enriched) => {
              setRecommendedLoads(mergeRecommendedLoad(enriched));
            });
          }
          break;
        }
        case "chain_found": {
          const chain = event.data.chain as LoadChain;
          if (chain?.hops) {
            setLoadChain(chain);
          }
          break;
        }
        case "response":
          break;
        case "done":
          setAgentStatus("ready");
          setAgentActivity(null);
          if (event.data.response) {
            addMessage({
              id: `agent-${Date.now()}`,
              type: "agent",
              content: String(event.data.response),
              timestamp: Date.now(),
            });
          }
          break;
        case "error":
          setAgentStatus("error");
          setAgentActivity(null);
          addMessage({
            id: `error-${Date.now()}`,
            type: "agent",
            content: `Something went wrong: ${event.data.message}. Try again or check your connection.`,
            timestamp: Date.now(),
          });
          break;
      }
    }
  }, [events, addMessage, setRecommendedLoads, setLoadChain, setAgentStatus, setAgentActivity]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  return <div ref={bottomRef} />;
}

export function ChatMessageList() {
  const messages = useAppStore((s) => s.messages);

  const visible = messages.filter(
    (msg) => msg.type === "user" || msg.type === "agent"
  );

  return (
    <div className="space-y-3">
      {visible.length === 0 && (
        <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-text-secondary">
          Set your location and equipment, then search. Your ranked loads appear on the map →
        </p>
      )}
      {visible.map((msg) => (
        <motion.div
          key={msg.id}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className={
            msg.type === "user"
              ? "ml-6 rounded-lg bg-primary/10 px-3 py-2.5 text-sm"
              : "rounded-lg border border-border/60 bg-surface-hover px-3 py-3 text-sm"
          }
        >
          {msg.type === "user" ? (
            <div>{msg.content}</div>
          ) : (
            <AgentSummary content={msg.content} />
          )}
        </motion.div>
      ))}
      <AgentStatusBar />
    </div>
  );
}
