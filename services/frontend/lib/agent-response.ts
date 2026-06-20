/** Turn verbose agent markdown into a short, driver-friendly summary. */

export interface DriverSummary {
  topLoadId?: string;
  topDestination?: string;
  topNetProfit?: string;
  headline: string;
  bullets: string[];
  insight?: string;
}

const TOOL_LABELS: Record<string, string> = {
  search_loads: "Searching nearby loads…",
  calculate_profitability: "Calculating net profit…",
  get_market_score: "Checking destination markets…",
  find_load_chain: "Finding multi-hop routes…",
  semantic_load_search: "Searching similar lanes…",
  predict_lane_rate: "Checking rate trends…",
  get_fuel_prices: "Updating fuel costs…",
  get_driver_preferences: "Loading your preferences…",
};

export function friendlyToolLabel(tool: string): string {
  return TOOL_LABELS[tool] || "Working on your search…";
}

export function parseDriverSummary(text: string): DriverSummary {
  const loadId = text.match(/\*\*Load ID:\*\*\s*(L-[\d]+)/i)?.[1];
  const destination = text.match(/\*\*Destination:\*\*\s*([^\n*]+)/i)?.[1]?.trim();
  const netProfit = text.match(/\*\*Net Profit:\*\*\s*\*\*\$([\d,.]+)\*\*/i)?.[1];

  const insight = text
    .match(/##\s*💡\s*Strategic Insight\s*\n+([\s\S]*?)(?=\n##|$)/i)?.[1]
    ?.trim()
    ?.replace(/\*\*/g, "");

  const marketLines = [...text.matchAll(/\*\*([^*]+)\*\*:\s*([^\n]+)/g)]
    .filter(([full]) => full.includes("market") || full.includes("Market"))
    .slice(0, 3)
    .map(([, city, detail]) => `${city.trim()}: ${detail.trim().replace(/\*\*/g, "")}`);

  let headline = "Here are your best loads — ranked by net profit on the right.";
  if (loadId && destination && netProfit) {
    headline = `Top pick: ${destination} (${loadId}) — $${netProfit} net profit`;
  } else if (loadId && netProfit) {
    headline = `Top pick: ${loadId} — $${netProfit} net profit`;
  }

  const bullets: string[] = [];
  if (marketLines.length) {
    bullets.push(...marketLines);
  } else {
    bullets.push("Compare gross, costs, and miles in the load cards below the map.");
  }

  return {
    topLoadId: loadId,
    topDestination: destination,
    topNetProfit: netProfit,
    headline,
    bullets,
    insight,
  };
}

export function stripMarkdownTables(text: string): string {
  return text
    .split("\n")
    .filter((line) => !/^\s*\|/.test(line))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
