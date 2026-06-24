"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  Copy,
  Loader2,
  Save,
  Search,
  Share2,
  Upload,
} from "lucide-react";
import { LoadCard } from "@/components/loads/LoadCard";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { searchCities } from "@/lib/cities";
import {
  getCarrierProfile,
  parseCsvImport,
  parseImportedLoads,
  parseScreenshotImport,
  saveImportHistory,
  type ImportAnalyzeResult,
} from "@/lib/api";
import type { ProfitBreakdown } from "@/lib/types";
import {
  buildImportSummary,
  decodeImportShare,
  importShareUrl,
  sortLoads,
  type SortKey,
} from "@/lib/import-utils";
import { cn } from "@/lib/utils";

const ImportMap = dynamic(() => import("./ImportMap").then((m) => m.ImportMap), {
  ssr: false,
  loading: () => <div className="h-[320px] animate-pulse rounded-lg bg-surface" />,
});

const EXAMPLE_TEXT = `Available Loads - DAT Load Board

Chicago, IL → Atlanta, GA | Dry Van | 716 mi | $2,275 | Jun 20
Chicago, IL → Reno, NV | Dry Van | 1,744 mi | $3,100 | Jun 20
Chicago, IL → Dallas, TX | Dry Van | 920 mi | $1,850 | Jun 21`;

interface LoadImporterProps {
  initialLocation?: string;
  initialEquipment?: string;
  initialResult?: ImportAnalyzeResult | null;
  onSaved?: () => void;
}

function LoadImporterInner({
  initialLocation = "Dallas, TX",
  initialEquipment = "Dry Van",
  initialResult = null,
  onSaved,
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
  const [result, setResult] = useState<ImportAnalyzeResult | null>(initialResult);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [dragOver, setDragOver] = useState(false);
  const [copied, setCopied] = useState(false);
  const [saved, setSaved] = useState(false);
  const [historyRefresh, setHistoryRefresh] = useState(0);

  useEffect(() => {
    getCarrierProfile()
      .then((p) => {
        if (p.home_city && p.home_state) {
          const loc = `${p.home_city}, ${p.home_state}`;
          setCityQuery(loc);
          const match = searchCities(loc)[0];
          if (match) {
            setDriverLat(match.lat);
            setDriverLng(match.lng);
          }
        }
        if (p.default_equipment) setEquipment(p.default_equipment);
      })
      .catch(() => {});
  }, []);

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

  const runAnalysis = async (runner: (loc: { lat: number; lng: number }) => Promise<ImportAnalyzeResult>) => {
    const loc = resolveLocation();
    if (!loc) {
      setError("Pick a valid city for your location.");
      return;
    }
    setLoading(true);
    setError("");
    setSaved(false);
    try {
      const data = await runner(loc);
      setResult(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Analysis failed";
      setError(
        msg.includes("OpenAI") || msg.includes("503")
          ? `${msg} — try Paste Text (works without vision) or check OPENAI_API_KEY.`
          : msg
      );
    } finally {
      setLoading(false);
    }
  };

  const analyzeText = () => {
    if (!rawText.trim()) {
      setError("Paste your load board results first.");
      return;
    }
    runAnalysis((loc) =>
      parseImportedLoads({ raw_text: rawText, driver_lat: loc.lat, driver_lng: loc.lng, equipment })
    );
  };

  const analyzeFile = (file: File) => {
    const isCsv = file.name.toLowerCase().endsWith(".csv") || file.type.includes("csv");
    if (isCsv) {
      const reader = new FileReader();
      reader.onload = () => {
        const text = String(reader.result || "");
        runAnalysis((loc) =>
          parseCsvImport({ csv_text: text, driver_lat: loc.lat, driver_lng: loc.lng, equipment })
        );
      };
      reader.readAsText(file);
      return;
    }
    runAnalysis((loc) => parseScreenshotImport(file, loc.lat, loc.lng, equipment));
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) analyzeFile(file);
  };

  const handleSave = async () => {
    if (!result) return;
    const parts = cityQuery.split(",").map((s) => s.trim());
    try {
      await saveImportHistory({
        driver_city: parts[0],
        driver_state: parts[1],
        equipment,
        parsed_count: result.parsed_count,
        insight: result.insight,
        loads: result.loads,
        raw_preview: rawText.slice(0, 500),
      });
      setSaved(true);
      setHistoryRefresh((k) => k + 1);
      onSaved?.();
    } catch {
      setError("Could not save — run make db-migrate-import if using Docker.");
    }
  };

  const handleCopy = async () => {
    if (!result) return;
    await navigator.clipboard.writeText(buildImportSummary(result, cityQuery));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleShare = async () => {
    if (!result) return;
    const url = importShareUrl(result);
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const rankLabel = (index: number, total: number) => {
    if (index === 0) return "BEST LOAD";
    if (index === total - 1 && total > 1) return "AVOID THIS ONE";
    return undefined;
  };

  const sortedLoads = result ? sortLoads(result.loads, sortKey) : [];

  return (
    <div className="space-y-6">
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
            <p className="mb-2 text-sm text-text-secondary">
              Screenshot (PNG/JPG) or CSV export
            </p>
            <label className="cursor-pointer">
              <span className="text-sm text-primary hover:underline">Browse files</span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/jpg,.csv,text/csv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) analyzeFile(f);
                }}
              />
            </label>
            <p className="mt-3 text-xs text-text-secondary">
              CSV columns: origin, destination, miles, rate
            </p>
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
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-lg font-semibold">Results</h3>
            <div className="flex flex-wrap gap-2">
              <Select value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Sort by" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="score">Best score</SelectItem>
                  <SelectItem value="net">Net profit</SelectItem>
                  <SelectItem value="margin">Margin %</SelectItem>
                  <SelectItem value="deadhead">Least deadhead</SelectItem>
                  <SelectItem value="rate_per_mile">Gross $/mi</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="sm" className="gap-1" onClick={handleCopy}>
                <Copy className="h-4 w-4" />
                {copied ? "Copied!" : "Copy"}
              </Button>
              <Button variant="outline" size="sm" className="gap-1" onClick={handleShare}>
                <Share2 className="h-4 w-4" />
                Share link
              </Button>
              <Button variant="outline" size="sm" className="gap-1" onClick={handleSave}>
                <Save className="h-4 w-4" />
                {saved ? "Saved!" : "Save"}
              </Button>
            </div>
          </div>

          {result.location_warning && (
            <div className="flex gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm">
              <AlertTriangle className="h-5 w-5 shrink-0 text-warning" />
              <div>
                <p className="font-medium text-warning">Location mismatch</p>
                <p className="mt-1 text-text-secondary">{result.location_warning}</p>
                {result.pickup_cities && result.pickup_cities.length > 0 && (
                  <p className="mt-2 text-xs text-text-secondary">
                    Pickups: {result.pickup_cities.join(" · ")}
                  </p>
                )}
              </div>
            </div>
          )}

          <p className="rounded-lg border border-primary/30 bg-primary/5 p-4 text-sm text-text-primary">
            💡 {result.insight}
          </p>

          <ImportMap loads={result.loads} driverLat={driverLat} driverLng={driverLng} />

          <div className="grid gap-4">
            {sortedLoads.map((load, i) => (
              <div key={load.load_id}>
                {rankLabel(i, sortedLoads.length) && sortKey === "score" && (
                  <div
                    className={cn(
                      "mb-2 text-xs font-bold tracking-wide",
                      i === 0 ? "text-accent" : "text-danger"
                    )}
                  >
                    #{i + 1} {rankLabel(i, sortedLoads.length)}
                  </div>
                )}
                <LoadCard load={load} rank={i + 1} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* history refresh trigger for parent */}
      <span className="hidden" data-history-refresh={historyRefresh} />
    </div>
  );
}

export function LoadImporter(props: LoadImporterProps) {
  return (
    <Suspense fallback={<div className="py-8 text-center text-text-secondary">Loading…</div>}>
      <LoadImporterWithShare {...props} />
    </Suspense>
  );
}

function LoadImporterWithShare(props: LoadImporterProps) {
  const searchParams = useSearchParams();
  const shared = searchParams.get("r");
  const initialResult = shared ? decodeImportShare(shared) : props.initialResult;

  return <LoadImporterInner {...props} initialResult={initialResult ?? props.initialResult} />;
}
