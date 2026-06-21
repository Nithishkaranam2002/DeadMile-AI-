"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Search, Send } from "lucide-react";
import { streamChat } from "@/lib/api";
import { searchCities } from "@/lib/cities";
import { buildLoadSearchMessages, EQUIPMENT_OPTIONS, resolveCityQuery } from "@/lib/search-query";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/lib/store";
import type { AgentEvent } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { DeadheadControl } from "@/components/DeadheadControl";
import { Separator } from "@/components/ui/separator";
import { AgentStream, ChatMessageList } from "./AgentStream";
import { VoiceInput } from "./VoiceInput";

export function ChatPanel() {
  const [input, setInput] = useState("");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [cityQuery, setCityQuery] = useState("");
  const [suggestions, setSuggestions] = useState<ReturnType<typeof searchCities>>([]);
  const abortRef = useRef<AbortController | null>(null);

  const {
    driverLat,
    driverLng,
    driverCity,
    driverState,
    equipment,
    maxDeadhead,
    isStreaming,
    searchRequest,
    setDriverLocation,
    setEquipment,
    setMaxDeadhead,
    addMessage,
    setIsStreaming,
    setAgentStatus,
    setRecommendedLoads,
    setLoadChain,
    setConnected,
    clearSearchRequest,
    setMapViewState,
    setMessages,
    setAgentActivity,
    recommendedLoads,
  } = useAppStore();

  const handleCityChange = (value: string) => {
    setCityQuery(value);
    setSuggestions(searchCities(value));
  };

  const selectCity = (city: string, state: string, lat: number, lng: number) => {
    setDriverLocation(lat, lng, city, state);
    setCityQuery(`${city}, ${state}`);
    setSuggestions([]);
  };

  const sendMessage = useCallback(
    async (
      overrideMessage?: string,
      displayMessage?: string,
      coords?: { lat: number; lng: number }
    ) => {
      const message = (overrideMessage ?? input).trim();
      if (!message || isStreaming) return;
      if (!overrideMessage) setInput("");

      setMessages([]);
      setRecommendedLoads([]);
      setLoadChain(null);
      addMessage({
        id: Date.now().toString(),
        type: "user",
        content: displayMessage ?? message,
        timestamp: Date.now(),
      });
      setIsStreaming(true);
      setAgentStatus("thinking");
      setAgentActivity("Finding your best loads…");
      setEvents([]);

      const lat = coords?.lat ?? driverLat ?? 32.7767;
      const lng = coords?.lng ?? driverLng ?? -96.797;

      setMapViewState({ latitude: lat, longitude: lng, zoom: 6, pitch: 20, bearing: 0 });

      abortRef.current?.abort();
      abortRef.current = streamChat(
        message,
        lat,
        lng,
        (event) => setEvents((prev) => [...prev, event]),
        { equipment, maxDeadhead }
      );
      setConnected(true);
    },
    [
      input,
      isStreaming,
      driverLat,
      driverLng,
      equipment,
      maxDeadhead,
      addMessage,
      setIsStreaming,
      setAgentStatus,
      setAgentActivity,
      setRecommendedLoads,
      setLoadChain,
      setMessages,
      setConnected,
      setMapViewState,
    ]
  );

  useEffect(() => {
    if (searchRequest?.message) {
      void sendMessage(searchRequest.message, searchRequest.displayMessage);
      clearSearchRequest();
    }
  }, [searchRequest, sendMessage, clearSearchRequest]);

  useEffect(() => {
    if (events.some((e) => e.type === "done" || e.type === "error")) {
      setIsStreaming(false);
      setAgentStatus(events.some((e) => e.type === "error") ? "error" : "ready");
    }
  }, [events, setIsStreaming, setAgentStatus]);

  const runLoadSearch = useCallback(() => {
    if (isStreaming) return;

    const match =
      resolveCityQuery(cityQuery) ??
      (driverCity && driverState
        ? resolveCityQuery(`${driverCity}, ${driverState}`)
        : null) ??
      searchCities("Dallas")[0];

    if (!match) return;

    setDriverLocation(match.lat, match.lng, match.city, match.state);
    setCityQuery(`${match.city}, ${match.state}`);

    const { agentMessage, displayMessage } = buildLoadSearchMessages(
      equipment,
      match.city,
      match.state,
      maxDeadhead
    );
    void sendMessage(agentMessage, displayMessage, { lat: match.lat, lng: match.lng });
  }, [
    isStreaming,
    cityQuery,
    driverCity,
    driverState,
    equipment,
    maxDeadhead,
    setDriverLocation,
    sendMessage,
  ]);

  const locationLabel =
    cityQuery ||
    (driverCity && driverState ? `${driverCity}, ${driverState}` : "Dallas, TX");
  const hasResults = recommendedLoads.length > 0;

  return (
    <div className="flex h-full flex-col border-r border-border bg-surface">
      <div className="border-b border-border p-4">
        <div className="mb-1 flex items-center gap-2">
          <Bot className="h-5 w-5 text-primary" />
          <h2 className="font-bold">DeadMile AI</h2>
        </div>
        <p className="text-xs text-text-secondary">
          Change equipment or miles, then tap Search Loads — no need to go back
        </p>
      </div>

      <div className="z-20 shrink-0 space-y-3 border-b border-border bg-surface p-4 shadow-sm">
        <div className="relative">
          <Input
            placeholder="📍 Location (city)"
            value={cityQuery || (driverCity ? `${driverCity}, ${driverState}` : "")}
            onChange={(e) => handleCityChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                runLoadSearch();
              }
            }}
          />
          {suggestions.length > 0 && (
            <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
              {suggestions.map((s) => (
                <button
                  key={`${s.city}-${s.state}`}
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-hover"
                  onClick={() => selectCity(s.city, s.state, s.lat, s.lng)}
                >
                  {s.city}, {s.state}
                </button>
              ))}
            </div>
          )}
        </div>
        <div>
          <p className="mb-2 text-xs text-text-secondary">🚛 Equipment type</p>
          <div className="grid grid-cols-2 gap-2">
            {EQUIPMENT_OPTIONS.map((eq) => (
              <button
                key={eq}
                type="button"
                onClick={() => setEquipment(eq)}
                disabled={isStreaming}
                className={cn(
                  "rounded-md border px-2 py-2 text-sm transition-colors",
                  equipment === eq
                    ? "border-primary bg-primary/15 font-semibold text-primary"
                    : "border-border bg-surface-hover text-text-secondary hover:border-primary/50"
                )}
              >
                {eq}
              </button>
            ))}
          </div>
        </div>
        <DeadheadControl
          value={maxDeadhead}
          onChange={setMaxDeadhead}
          label={`📏 Max deadhead? ${maxDeadhead} mi`}
        />
        <div className="rounded-md border border-border/60 bg-surface-hover px-3 py-2 text-xs text-text-secondary">
          Ready to search:{" "}
          <span className="font-medium text-text-primary">
            {equipment} · {locationLabel} · {maxDeadhead} mi
          </span>
        </div>
        <Button
          className="w-full gap-2 font-semibold"
          size="lg"
          onClick={runLoadSearch}
          disabled={isStreaming}
        >
          <Search className="h-4 w-4" />
          {isStreaming ? "Searching…" : hasResults ? "Update Search" : "Search Loads"}
        </Button>
        <p className="text-center text-[11px] text-text-secondary">
          Press Enter in the location field to search
        </p>
      </div>

      <ScrollArea className="flex-1 p-4">
        <ChatMessageList />
        <AgentStream events={events} />
      </ScrollArea>

      <Separator />
      <div className="flex gap-2 p-4">
        <Input
          placeholder="💬 Ask anything..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          disabled={isStreaming}
        />
        <VoiceInput onResult={(text) => setInput(text)} />
        <Button onClick={() => sendMessage()} disabled={isStreaming || !input.trim()} size="icon">
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
