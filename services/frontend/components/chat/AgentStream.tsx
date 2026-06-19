"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import type { AgentEvent } from "@/lib/types";
import { useAppStore } from "@/lib/store";
import type { ProfitBreakdown, LoadChain } from "@/lib/types";
import { LoadCard } from "@/components/loads/LoadCard";
import { LoadChainView } from "@/components/loads/LoadChainView";

interface AgentStreamProps {
  events: AgentEvent[];
}

export function AgentStream({ events }: AgentStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const addMessage = useAppStore((s) => s.addMessage);
  const setRecommendedLoads = useAppStore((s) => s.setRecommendedLoads);
  const setLoadChain = useAppStore((s) => s.setLoadChain);
  const setAgentStatus = useAppStore((s) => s.setAgentStatus);
  const processedRef = useRef(0);

  useEffect(() => {
    const newEvents = events.slice(processedRef.current);
    processedRef.current = events.length;

    for (const event of newEvents) {
      const id = `${Date.now()}-${Math.random()}`;

      switch (event.type) {
        case "thinking":
          addMessage({
            id,
            type: "thinking",
            content: String(event.data.message || "Thinking..."),
            timestamp: Date.now(),
          });
          setAgentStatus("thinking");
          break;
        case "tool_call":
          addMessage({
            id,
            type: "tool_call",
            content: `🔧 ${event.data.tool || "tool"}: ${JSON.stringify(event.data.params || event.data).slice(0, 120)}`,
            timestamp: Date.now(),
          });
          break;
        case "tool_result":
          addMessage({
            id,
            type: "tool_result",
            content: `✅ ${event.data.tool || "Done"}: ${event.data.count !== undefined ? `Found ${event.data.count}` : event.data.summary || "Complete"}`,
            timestamp: Date.now(),
          });
          break;
        case "load_found": {
          const load = (event.data.load || event.data) as ProfitBreakdown;
          addMessage({ id, type: "load_card", content: load.load_id, load, timestamp: Date.now() });
          const current = useAppStore.getState().recommendedLoads;
          if (!current.some((l) => l.load_id === load.load_id)) {
            setRecommendedLoads([...current, load]);
          }
          break;
        }
        case "chain_found": {
          const chain = event.data.chain as LoadChain;
          if (chain?.hops) {
            addMessage({ id, type: "chain_view", content: "Load chain found", chain, timestamp: Date.now() });
            setLoadChain(chain);
          }
          break;
        }
        case "response":
          addMessage({
            id,
            type: "agent",
            content: String(event.data.text || event.data.response || ""),
            timestamp: Date.now(),
          });
          break;
        case "done":
          setAgentStatus("ready");
          if (event.data.response) {
            addMessage({
              id,
              type: "agent",
              content: String(event.data.response),
              timestamp: Date.now(),
            });
          }
          break;
        case "error":
          setAgentStatus("error");
          addMessage({
            id,
            type: "agent",
            content: `Error: ${event.data.message}`,
            timestamp: Date.now(),
          });
          break;
      }
    }
  }, [events, addMessage, setRecommendedLoads, setLoadChain, setAgentStatus]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  return <div ref={bottomRef} />;
}

export function ChatMessageList() {
  const messages = useAppStore((s) => s.messages);

  return (
    <div className="space-y-3">
      {messages.map((msg) => (
        <motion.div
          key={msg.id}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className={
            msg.type === "user"
              ? "ml-4 rounded-lg bg-primary/10 p-3 text-sm"
              : msg.type === "thinking" || msg.type === "tool_call" || msg.type === "tool_result"
                ? "text-xs italic text-text-secondary"
                : "rounded-lg bg-surface-hover p-3 text-sm"
          }
        >
          {msg.type === "load_card" && msg.load ? (
            <LoadCard load={msg.load} compact />
          ) : msg.type === "chain_view" && msg.chain ? (
            <LoadChainView chain={msg.chain} />
          ) : (
            <div className="whitespace-pre-wrap">{msg.content}</div>
          )}
        </motion.div>
      ))}
    </div>
  );
}
