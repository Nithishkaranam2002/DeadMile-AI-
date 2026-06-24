"use client";

import { Suspense, useState } from "react";
import { ImportHistoryPanel } from "@/components/import/ImportHistoryPanel";
import { LoadImporter } from "@/components/import/LoadImporter";
import type { ImportAnalyzeResult } from "@/lib/api";

export default function ImportPage() {
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [restored, setRestored] = useState<{
    result: ImportAnalyzeResult;
    city: string;
    equipment: string;
  } | null>(null);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold md:text-3xl">📋 Import Your Loads</h1>
        <p className="mt-2 text-text-secondary">
          Paste load board results and we&apos;ll tell you which ones actually make you the most money.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_280px]">
        <Suspense fallback={<div className="py-12 text-center text-text-secondary">Loading…</div>}>
          <LoadImporter
            key={restored ? `restored-${restored.result.loads[0]?.load_id}` : "default"}
            initialResult={restored?.result}
            initialLocation={restored?.city}
            initialEquipment={restored?.equipment}
            onSaved={() => setHistoryRefresh((k) => k + 1)}
          />
        </Suspense>

        <aside className="lg:sticky lg:top-20 lg:self-start">
          <h2 className="mb-3 text-sm font-semibold text-text-secondary">Recent analyses</h2>
          <ImportHistoryPanel
            refreshKey={historyRefresh}
            onSelect={(result, meta) => {
              setRestored({ result, city: meta.city, equipment: meta.equipment });
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        </aside>
      </div>
    </div>
  );
}
