"use client";

import Link from "next/link";
import { Settings, X } from "lucide-react";
import { useEffect, useState } from "react";
import { getCarrierProfile } from "@/lib/api";
import { isDefaultFleetCosts } from "@/lib/import-utils";
import { Button } from "@/components/ui/button";

const DISMISS_KEY = "deadmile_cost_banner_dismissed";

export function FleetCostBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(DISMISS_KEY)) return;
    getCarrierProfile()
      .then((p) => {
        if (isDefaultFleetCosts(p)) setShow(true);
      })
      .catch(() => {});
  }, []);

  if (!show) return null;

  return (
    <div className="border-b border-warning/30 bg-warning/10 px-4 py-3">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-text-primary">
          <span className="font-semibold text-warning">Tip:</span> You&apos;re using default fuel &amp; pay
          costs. Set your real numbers for accurate net profit.
        </p>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" className="gap-1" asChild>
            <Link href="/settings">
              <Settings className="h-4 w-4" />
              Fleet Settings
            </Link>
          </Button>
          <button
            type="button"
            className="text-text-secondary hover:text-text-primary"
            onClick={() => {
              localStorage.setItem(DISMISS_KEY, "1");
              setShow(false);
            }}
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
