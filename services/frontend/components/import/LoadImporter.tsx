"use client";

import { useCallback, useState } from "react";
import { Loader2, Search, Upload } from "lucide-react";
import { LoadCard } from "@/components/loads/LoadCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { searchCities } from "@/lib/cities";
import { parseImportedLoads, parseScreenshotImport, type ImportAnalyzeResult } from "@/lib/api";
import type { ProfitBreakdown } from "@/lib/types";
import { cn } from "@/lib/utils";

const EXAMPLE_TEXT = `Available Loads - DAT Load Board

Chicago, IL → Atlanta, GA | Dry Van | 716 mi | $2,275 | Jun 20
Chicago, IL → Reno, NV | Dry Van | 1,744 mi | $3,100 | Jun 20
Chicago, IL → Dallas, TX | Dry Van | 920 mi | $1,850 | Jun 21`;

interface LoadImporterProps {
  initialLocation?: string;
  initialEquipment?: string;
  compact?: boolean;
}

export function LoadImporter({
  initialLocation = "Dallas, TX",
  initialEquipment = "Dry Van",
  compact = false,
}: LoadImporterProps) {
  const [tab, setTab] = useState("paste");
  const [rawText, setRawText] = useState("");
  const [cityQuery, setCityQuery] = useState(initialLocation);
  const [suggestions, setSuggestions] = useState<ReturnType<typeof searchCities>>([]);
  const [driverLat, setDriverLat] = useState(32.7767);
  const [driverLng, setDriverLng] = useState(-96.797);
  const [equipment, setEquipment] = useState(initialEquipment);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportAnalyzeResult | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const resolveLocation = useCallback(() => {
    const match =
      searchCities(cityQuery).find(
        (c) => `${c.city}, ${c.state}`.toLowerCase() === cityQuery.toLowerCase()
      ) ?? searchCities(cityQuery)[0];
    if (match) {
      setDriverLat(match.lat);
      setDriverLng(match.lng);
      setCityQuery(`${match.city}, ${match.state}`);
      return match;
    }
    return null;
  }, [cityQuery]);

  const analyzeText = async () => {
    if (!rawText.trim()) {
      setError("Paste your load board results first.");
      return;
    }
    const loc = resolveLocation();
    if (!loc) {
      setError("Pick a valid city for your location.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await parseImportedLoads({
        raw_text: rawText,
        driver_lat: loc.lat,
        driver_lng: loc.lng,
        equipment,
      });
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  const analyzeFile = async (file: File) => {
    const loc = resolveLocation();
    if (!loc) {
      setError("Pick a valid city for your location.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const data = await parseScreenshotImport(file, loc.lat, loc.lng, equipment);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) analyzeFile(file);
  };

  const rankLabel = (load: ProfitBreakdown, index: number, total: number) => {
    if (index === 0) return "BEST LOAD";
    if (index === total - 1 && total > 1) return "AVOID THIS ONE";
    return undefined;
  };

  return (
    <div className={cn("space-y-6", compact && "space-y-4")}>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="paste">Paste Text</TabsTrigger>
          <TabsTrigger value="upload">Upload File</TabsTrigger>
        </TabsList>

        <TabsContent value="paste" className="mt-4">
          <textarea
            className="min-h-[200px] w-full rounded-lg border border-border bg-surface px-4 py-3 text-sm text-text-primary placeholder:text-text-secondary focus:border-primary focus:outline-none"
            placeholder={EXAMPLE_TEXT}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
          />
        </TabsContent>

        <TabsContent value="upload" className="mt-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={cn(
              "flex min-h-[200px] flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors",
              dragOver ? "border-primary bg-primary/5" : "border-border bg-surface"
            )}
          >
            <Upload className="mb-3 h-10 w-10 text-text-secondary" />
            <p className="mb-2 text-sm text-text-secondary">Drag & drop a screenshot (PNG/JPG)</p>
            <label className="cursor-pointer">
              <span className="text-sm text-primary hover:underline">Browse files</span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/jpg"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) analyzeFile(f);
                }}
              />
            </label>
          </div>
        </TabsContent>
      </Tabs>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="relative">
          <label className="mb-1 block text-xs text-text-secondary">📍 Your location</label>
          <Input
            value={cityQuery}
            onChange={(e) => {
              setCityQuery(e.target.value);
              setSuggestions(searchCities(e.target.value));
            }}
            onBlur={resolveLocation}
          />
          {suggestions.length > 0 && (
            <div className="absolute z-10 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
              {suggestions.slice(0, 6).map((s) => (
                <button
                  key={`${s.city}-${s.state}`}
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-hover"
                  onClick={() => {
                    setCityQuery(`${s.city}, ${s.state}`);
                    setDriverLat(s.lat);
                    setDriverLng(s.lng);
                    setSuggestions([]);
                  }}
                >
                  {s.city}, {s.state}
                </button>
              ))}
            </div>
          )}
        </div>
        <div>
          <label className="mb-1 block text-xs text-text-secondary">🚛 Equipment</label>
          <Select value={equipment} onValueChange={setEquipment}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {["Dry Van", "Flatbed", "Reefer", "Step Deck"].map((e) => (
                <SelectItem key={e} value={e}>
                  {e}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {tab === "paste" && (
        <Button size="lg" className="w-full gap-2 sm:w-auto" onClick={analyzeText} disabled={loading}>
          {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Search className="h-5 w-5" />}
          {loading ? "Parsing your loads… Calculating profitability…" : "Analyze My Loads"}
        </Button>
      )}

      {error && <p className="text-sm text-danger">{error}</p>}

      {result && (
        <div className="space-y-4 border-t border-border pt-6">
          <h3 className="text-lg font-semibold">Results</h3>
          <p className="rounded-lg border border-primary/30 bg-primary/5 p-4 text-sm text-text-primary">
            💡 {result.insight}
          </p>
          <div className="grid gap-4">
            {result.loads.map((load, i) => (
              <div key={load.load_id} className="relative">
                {rankLabel(load, i, result.loads.length) && (
                  <div
                    className={cn(
                      "mb-2 text-xs font-bold tracking-wide",
                      i === 0 ? "text-accent" : "text-danger"
                    )}
                  >
                    #{i + 1} {rankLabel(load, i, result.loads.length)}
                  </div>
                )}
                <LoadCard load={load} rank={i + 1} />
                {i === result.loads.length - 1 && result.loads.length > 1 && i > 0 && (
                  <p className="mt-2 text-xs text-warning">
                    ⚠️ Looks high-paying but check the destination market!
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
