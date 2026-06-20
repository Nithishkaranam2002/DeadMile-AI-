"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Send } from "lucide-react";
import { streamChat } from "@/lib/api";
import { searchCities } from "@/lib/cities";
import { useAppStore } from "@/lib/store";
import type { AgentEvent } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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
    async (overrideMessage?: string, displayMessage?: string) => {
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

      const lat = driverLat ?? 32.7767;
      const lng = driverLng ?? -96.797;

      if (driverLat && driverLng) {
        setMapViewState({ latitude: lat, longitude: lng, zoom: 6, pitch: 20, bearing: 0 });
      }

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

  return (
    <div className="flex h-full flex-col border-r border-border bg-surface">
      <div className="border-b border-border p-4">
        <div className="mb-1 flex items-center gap-2">
          <Bot className="h-5 w-5 text-primary" />
          <h2 className="font-bold">DeadMile AI</h2>
        </div>
        <p className="text-xs text-text-secondary">
          Ask here — ranked loads show on the map →
        </p>
      </div>

      <div className="space-y-3 border-b border-border p-4">
        <div className="relative">
          <Input
            placeholder="📍 Location (city)"
            value={cityQuery || (driverCity ? `${driverCity}, ${driverState}` : "")}
            onChange={(e) => handleCityChange(e.target.value)}
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
        <Select value={equipment} onValueChange={setEquipment}>
          <SelectTrigger>
            <SelectValue placeholder="🚛 Equipment" />
          </SelectTrigger>
          <SelectContent>
            {["Dry Van", "Flatbed", "Reefer", "Step Deck"].map((e) => (
              <SelectItem key={e} value={e}>{e}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DeadheadControl
          value={maxDeadhead}
          onChange={setMaxDeadhead}
          label={`📏 Max deadhead? ${maxDeadhead} mi`}
        />
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
