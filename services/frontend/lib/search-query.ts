import { searchCities } from "./cities";

export const EQUIPMENT_OPTIONS = ["Dry Van", "Flatbed", "Reefer", "Step Deck"] as const;

export type EquipmentType = (typeof EQUIPMENT_OPTIONS)[number];

export function resolveCityQuery(query: string) {
  const trimmed = query.trim();
  if (!trimmed) return null;

  const cities = searchCities(trimmed);
  const exact = cities.find((c) => `${c.city}, ${c.state}`.toLowerCase() === trimmed.toLowerCase());
  if (exact) return exact;

  return cities[0] ?? null;
}

export function buildLoadSearchMessages(
  equipment: string,
  city: string,
  state: string,
  maxDeadhead: number
) {
  return {
    agentMessage: `Find the best ${equipment} loads near ${city}, ${state} within ${maxDeadhead} miles. Rank by net profit.`,
    displayMessage: `Best ${equipment} near ${city}, ${state} · ${maxDeadhead} mi deadhead`,
  };
}
