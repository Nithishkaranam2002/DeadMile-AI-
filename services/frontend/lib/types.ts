export interface FuelBreakdown {
  loaded_fuel: number;
  deadhead_to_fuel: number;
  deadhead_from_fuel: number;
  total_fuel: number;
}

export interface ProfitBreakdown {
  load_id: string;
  gross_rate: number;
  revenue: number;
  loaded_miles: number;
  deadhead_to_pickup: number;
  deadhead_from_delivery: number;
  total_miles: number;
  fuel_cost: number;
  fuel_breakdown: FuelBreakdown;
  driver_cost: number;
  insurance_cost: number;
  maintenance_cost: number;
  tolls_cost: number;
  dispatch_fee: number;
  factoring_fee: number;
  overhead_cost: number;
  total_costs: number;
  net_profit: number;
  profit_margin_percent: number;
  net_rate_per_mile: number;
  cost_per_mile: number;
  composite_score: number;
  destination_market_score?: number;
  destination_market_label: string;
  dest_city?: string;
  dest_state?: string;
  equipment: string;
  commodity: string;
  origin: string;
  destination: string;
  pickup_window?: string;
  delivery_window?: string;
  requirements?: string;
  origin_lat?: number;
  origin_lng?: number;
  dest_lat?: number;
  dest_lng?: number;
  /** Present on partial search results before profitability calc */
  rate?: number;
  miles?: number;
}

export interface Load {
  load_id: string;
  origin: string;
  destination: string;
  equipment: string;
  commodity?: string;
  miles: number;
  rate: number;
  rate_per_mile: number;
  requirements?: string;
  origin_lat?: number;
  origin_lng?: number;
  dest_lat?: number;
  dest_lng?: number;
}

export interface MarketScore {
  city: string;
  state: string;
  lat: number;
  lng: number;
  outbound_load_count: number;
  inbound_load_count?: number;
  avg_outbound_rate: number;
  avg_inbound_rate: number;
  lane_balance_ratio: number;
  market_score: number;
  equipment_diversity?: number;
  label: string;
  cluster_label?: string;
}

export interface MarketDetail extends MarketScore {
  top_lanes?: { destination: string; avg_rate: number; load_count: number }[];
  rate_history?: { date: string; rate: number }[];
}

export interface HeatmapData {
  lat: number;
  lng: number;
  score: number;
  city: string;
  state: string;
  load_count: number;
  avg_rate: number;
}

export interface RatePrediction {
  origin: string;
  destination: string;
  equipment: string;
  current_avg_rate: number;
  predicted_rate: number;
  confidence_low: number;
  confidence_high: number;
  trend: string;
  trend_percent: number;
}

export interface MarketCluster {
  city: string;
  state: string;
  lat: number;
  lng: number;
  cluster_id: number;
  cluster_label: string;
  features: Record<string, number>;
}

export interface WhatIfResult {
  available_loads_count: number;
  avg_net_profit: number;
  best_load_net_profit: number;
  avg_market_score_of_destinations: number;
  estimated_weekly_earnings: number;
  top_loads?: ProfitBreakdown[];
  equipment_breakdown?: Record<string, number>;
}

export interface DashboardStats {
  total_loads: number;
  avg_net_profit: number;
  best_market: string;
  best_market_score: number;
  avg_rate_per_mile: number;
}

export interface LoadChainHop {
  load_id: string;
  origin: string;
  destination: string;
  net_profit: number;
  deadhead_miles: number;
  equipment: string;
}

export interface LoadChain {
  hops: LoadChainHop[];
  cumulative_net_profit: number;
  total_miles: number;
  estimated_days: number;
  weekly_projection: number;
  monthly_projection: number;
}

export type AgentEventType =
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "load_found"
  | "chain_found"
  | "market_data"
  | "response"
  | "done"
  | "error";

export interface AgentEvent {
  type: AgentEventType;
  data: Record<string, unknown>;
}

export type ChatMessageType =
  | "user"
  | "agent"
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "load_card"
  | "chain_view";

export interface ChatMessage {
  id: string;
  type: ChatMessageType;
  content: string;
  load?: ProfitBreakdown;
  chain?: LoadChain;
  timestamp: number;
}

export interface DriverProfile {
  lat: number;
  lng: number;
  city: string;
  state: string;
  equipment: string;
  maxDeadhead: number;
}

export interface ViewState {
  latitude: number;
  longitude: number;
  zoom: number;
  pitch?: number;
  bearing?: number;
}
