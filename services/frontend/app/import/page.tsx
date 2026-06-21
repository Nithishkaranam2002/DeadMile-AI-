"use client";

import { LoadImporter } from "@/components/import/LoadImporter";

export default function ImportPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold md:text-3xl">📋 Import Your Loads</h1>
        <p className="mt-2 text-text-secondary">
          Paste load board results and we&apos;ll tell you which ones actually make you the most money.
        </p>
      </div>
      <LoadImporter />
    </div>
  );
}
