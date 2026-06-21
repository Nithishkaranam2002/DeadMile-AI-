/** Runtime app configuration — production vs demo behavior. */

export function isProductionMode(): boolean {
  return (
    process.env.NEXT_PUBLIC_APP_MODE === "production" ||
    process.env.NODE_ENV === "production"
  );
}

const API_KEY_STORAGE = "deadmile_api_key";

export function getStoredApiKey(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(API_KEY_STORAGE) || "";
}

export function setStoredApiKey(key: string): void {
  if (typeof window === "undefined") return;
  if (key) localStorage.setItem(API_KEY_STORAGE, key);
  else localStorage.removeItem(API_KEY_STORAGE);
}

export function apiHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const key = getStoredApiKey();
  if (key) headers["X-API-Key"] = key;
  return headers;
}
