"use client";

import { useCallback, useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Loader2, Share2, Swords } from "lucide-react";
import { compareLoadsText, type ImportAnalyzeResult } from "@/lib/api";
import { searchCities } from "@/lib/cities";
import { formatCurrency, marketEmoji } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function CompareContent() {
  const searchParams = useSearchParams();
  const [loadA, setLoadA] = useState(searchParams.get("a") || "");
  const [loadB, setLoadB] = useState(searchParams.get("b") || "");
  const [cityQuery, setCityQuery] = useState("Dallas, TX");
  const [suggestions, setSuggestions] = useState<ReturnType<typeof searchCities>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportAnalyzeResult | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const shared = searchParams.get("r");
    if (shared) {
      try {
        const decoded = JSON.parse(atob(shared));
        if (decoded.loads) setResult(decoded);
      } catch {
        /* ignore */
      }
    }
  }, [searchParams]);

  const resolveLocation = useCallback(() => {
    const match =
      searchCities(cityQuery).find(
        (c) => `${c.city}, ${c.state}`.toLowerCase() === cityQuery.toLowerCase()
      ) ?? searchCities(cityQuery)[0];
    return match ?? searchCities("Dallas")[0];
  }, [cityQuery]);

  const compare = async () => {
    const loc = resolveLocation();
    if (!loadA.trim() || !loadB.trim()) {
      setError("Paste both loads to compare.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await compareLoadsText({
        load_a_text: loadA,
        load_b_text: loadB,
        driver_lat: loc.lat,
        driver_lng: loc.lng,
        equipment: "Dry Van",
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Compare failed");
    } finally {
      setLoading(false);
    }
  };

  const shareUrl = () => {
    if (!result) return "";
    const encoded = btoa(JSON.stringify(result));
    const params = new URLSearchParams({ r: encoded });
    return `${window.location.origin}/compare?${params.toString()}`;
  };

  const copyLink = async () => {
    const url = shareUrl();
    if (!url) return;
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const winner = result?.loads[0];
  const loser = result?.loads[1];

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-8 text-center">
        <div className="mb-2 flex items-center justify-center gap-2">
          <Swords className="h-8 w-8 text-primary" />
          <h1 className="text-2xl font-bold md:text-3xl">Load Showdown</h1>
        </div>
        <p className="text-text-secondary">Which load actually makes you more money?</p>
        <span className="mt-2 inline-block rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-xs text-accent">
          100% Free · No login required
        </span>
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <div>
          <label className="mb-1 block text-sm font-medium">LOAD A</label>
          <textarea
            className="min-h-[120px] w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
            placeholder="Chicago, IL → Atlanta, GA | 716 mi | $2,275"
            value={loadA}
            onChange={(e) => setLoadA(e.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">LOAD B</label>
          <textarea
            className="min-h-[120px] w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
            placeholder="Chicago, IL → Reno, NV | 1,744 mi | $3,100"
            value={loadB}
            onChange={(e) => setLoadB(e.target.value)}
          />
        </div>
      </div>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="relative flex-1">
          <label className="mb-1 block text-xs text-text-secondary">📍 Your location</label>
          <Input
            value={cityQuery}
            onChange={(e) => {
              setCityQuery(e.target.value);
              setSuggestions(searchCities(e.target.value));
            }}
          />
          {suggestions.length > 0 && (
            <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
              {suggestions.slice(0, 5).map((s) => (
                <button
                  key={`${s.city}-${s.state}`}
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-hover"
                  onClick={() => {
                    setCityQuery(`${s.city}, ${s.state}`);
                    setSuggestions([]);
                  }}
                >
                  {s.city}, {s.state}
                </button>
              ))}
            </div>
          )}
        </div>
        <Button size="lg" className="gap-2" onClick={compare} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Swords className="h-4 w-4" />}
          Compare Now
        </Button>
      </div>

      {error && <p className="mb-4 text-sm text-danger">{error}</p>}

      {result && winner && (
        <div className="space-y-6 rounded-xl border border-border bg-surface p-6">
          <h2 className="text-center text-xl font-bold text-accent">
            WINNER: {winner.origin} → {winner.destination}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {[winner, loser].filter(Boolean).map((load, i) => (
              <div
                key={load!.load_id}
                className={`rounded-lg border p-4 ${i === 0 ? "border-accent/50 bg-accent/5" : "border-border"}`}
              >
                <div className="mb-2 text-sm font-medium text-text-secondary">
                  {i === 0 ? "LOAD A" : "LOAD B"}
                </div>
                <div className="font-semibold">
                  {load!.origin} → {load!.destination}
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-center text-sm">
                  <div>
                    <div className="text-text-secondary">Net</div>
                    <div className="font-mono-num font-bold text-accent">
                      {formatCurrency(load!.net_profit)}
                    </div>
                  </div>
                  <div>
                    <div className="text-text-secondary">Margin</div>
                    <div className="font-mono-num font-bold">
                      {(load!.profit_margin_percent ?? 0).toFixed(0)}%
                    </div>
                  </div>
                </div>
                <div className="mt-2 text-xs text-text-secondary">
                  {marketEmoji(load!.destination_market_label)}{" "}
                  {load!.destination_market_label} · {load!.destination}
                </div>
              </div>
            ))}
          </div>

          <p className="text-center text-sm text-text-primary">💡 {result.insight}</p>

          <div className="flex flex-wrap justify-center gap-3">
            <Button variant="outline" className="gap-2" onClick={copyLink}>
              <Share2 className="h-4 w-4" />
              {copied ? "Copied!" : "Copy Link"}
            </Button>
            <Button asChild>
              <Link href="/login?callbackUrl=/import">Try DeadMile AI Free →</Link>
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="py-20 text-center">Loading…</div>}>
      <CompareContent />
    </Suspense>
  );
}
