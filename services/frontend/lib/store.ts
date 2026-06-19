import { create } from "zustand";
import { MOCK_CHAIN, MOCK_LOADS, MOCK_MARKETS, MOCK_STATS } from "./mock-data";
import type { ChatMessage, LoadChain, MarketScore, ProfitBreakdown, ViewState } from "./types";

interface AppStore {
  driverLat: number | null;
  driverLng: number | null;
  driverCity: string;
  driverState: string;
  equipment: string;
  maxDeadhead: number;
  messages: ChatMessage[];
  isStreaming: boolean;
  agentStatus: "ready" | "thinking" | "error";
  selectedLoad: ProfitBreakdown | null;
  recommendedLoads: ProfitBreakdown[];
  loadChain: LoadChain | null;
  showHeatmap: boolean;
  showArcs: boolean;
  showRoutes: boolean;
  mapViewState: ViewState;
  topMarkets: MarketScore[];
  connected: boolean;
  totalLoads: number;
  dashboardStats: typeof MOCK_STATS;

  setDriverLocation: (lat: number, lng: number, city: string, state: string) => void;
  setEquipment: (equipment: string) => void;
  setMaxDeadhead: (miles: number) => void;
  addMessage: (message: ChatMessage) => void;
  updateLastMessage: (content: string) => void;
  setMessages: (messages: ChatMessage[]) => void;
  setIsStreaming: (v: boolean) => void;
  setAgentStatus: (s: "ready" | "thinking" | "error") => void;
  setRecommendedLoads: (loads: ProfitBreakdown[]) => void;
  selectLoad: (load: ProfitBreakdown | null) => void;
  setLoadChain: (chain: LoadChain | null) => void;
  toggleHeatmap: () => void;
  toggleArcs: () => void;
  toggleRoutes: () => void;
  setMapViewState: (v: ViewState) => void;
  setTopMarkets: (markets: MarketScore[]) => void;
  setConnected: (v: boolean) => void;
}

export const useAppStore = create<AppStore>((set) => ({
  driverLat: 32.7767,
  driverLng: -96.797,
  driverCity: "Dallas",
  driverState: "TX",
  equipment: "Dry Van",
  maxDeadhead: 250,
  messages: [],
  isStreaming: false,
  agentStatus: "ready",
  selectedLoad: null,
  recommendedLoads: MOCK_LOADS,
  loadChain: MOCK_CHAIN,
  showHeatmap: false,
  showArcs: true,
  showRoutes: true,
  mapViewState: { latitude: 39.8, longitude: -98.5, zoom: 4, pitch: 0, bearing: 0 },
  topMarkets: MOCK_MARKETS,
  connected: true,
  totalLoads: MOCK_STATS.total_loads,
  dashboardStats: MOCK_STATS,

  setDriverLocation: (lat, lng, city, state) =>
    set({ driverLat: lat, driverLng: lng, driverCity: city, driverState: state }),
  setEquipment: (equipment) => set({ equipment }),
  setMaxDeadhead: (maxDeadhead) => set({ maxDeadhead }),
  addMessage: (message) => set((s) => ({ messages: [...s.messages, message] })),
  updateLastMessage: (content) =>
    set((s) => {
      const msgs = [...s.messages];
      if (msgs.length > 0) msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content };
      return { messages: msgs };
    }),
  setMessages: (messages) => set({ messages }),
  setIsStreaming: (isStreaming) => set({ isStreaming }),
  setAgentStatus: (agentStatus) => set({ agentStatus }),
  setRecommendedLoads: (recommendedLoads) => set({ recommendedLoads }),
  selectLoad: (selectedLoad) => set({ selectedLoad }),
  setLoadChain: (loadChain) => set({ loadChain }),
  toggleHeatmap: () => set((s) => ({ showHeatmap: !s.showHeatmap })),
  toggleArcs: () => set((s) => ({ showArcs: !s.showArcs })),
  toggleRoutes: () => set((s) => ({ showRoutes: !s.showRoutes })),
  setMapViewState: (mapViewState) => set({ mapViewState }),
  setTopMarkets: (topMarkets) => set({ topMarkets }),
  setConnected: (connected) => set({ connected }),
}));
