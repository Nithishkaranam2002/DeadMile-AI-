import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

export function marketColor(label: string): string {
  const l = label.toLowerCase();
  if (l.includes("hot")) return "text-accent";
  if (l.includes("warm")) return "text-warning";
  if (l.includes("neutral")) return "text-text-secondary";
  if (l.includes("cool")) return "text-orange-400";
  return "text-danger";
}

export function marketEmoji(label: string): string {
  const l = label.toLowerCase();
  if (l.includes("hot")) return "🟢";
  if (l.includes("warm")) return "🟡";
  if (l.includes("neutral")) return "🟠";
  if (l.includes("cool")) return "🔴";
  return "⚫";
}
