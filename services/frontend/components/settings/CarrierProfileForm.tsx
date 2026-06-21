"use client";

import { useEffect, useState } from "react";
import { Save, Truck } from "lucide-react";
import { getCarrierProfile, updateCarrierProfile } from "@/lib/api";
import { setStoredApiKey, getStoredApiKey, isProductionMode } from "@/lib/config";
import type { CarrierCostProfile } from "@/lib/types";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { DeadheadControl } from "@/components/DeadheadControl";
import { EQUIPMENT_OPTIONS } from "@/lib/search-query";
import { cn } from "@/lib/utils";

const EMPTY: CarrierCostProfile = {
  carrier_id: "default",
  company_name: "My Fleet",
  default_equipment: "Dry Van",
  max_deadhead_miles: 250,
  fuel_price_per_gallon: 3.9,
  avg_mpg_loaded: 6,
  avg_mpg_empty: 7,
  driver_cpm: 0.55,
  insurance_per_mile: 0.08,
  maintenance_per_mile: 0.15,
  tolls_per_mile: 0.04,
  dispatch_fee_percent: 0.05,
  factoring_fee_percent: 0.03,
  overhead_per_mile: 0.05,
};

export function CarrierProfileForm() {
  const [profile, setProfile] = useState<CarrierCostProfile>(EMPTY);
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const { setEquipment, setMaxDeadhead } = useAppStore();

  useEffect(() => {
    setApiKey(getStoredApiKey());
    getCarrierProfile()
      .then((p) => {
        setProfile(p);
        setEquipment(p.default_equipment);
        setMaxDeadhead(p.max_deadhead_miles);
      })
      .catch(() => setProfile(EMPTY))
      .finally(() => setLoading(false));
  }, [setEquipment, setMaxDeadhead]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    try {
      setStoredApiKey(apiKey.trim());
      const updated = await updateCarrierProfile(profile);
      setProfile(updated);
      setEquipment(updated.default_equipment);
      setMaxDeadhead(updated.max_deadhead_miles);
      setMessage("Fleet profile saved. New searches use your custom costs.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Failed to save profile");
    } finally {
      setSaving(false);
    }
  };

  const setNum = (key: keyof CarrierCostProfile, value: string) => {
    const parsed = parseFloat(value);
    if (!Number.isNaN(parsed)) setProfile((p) => ({ ...p, [key]: parsed }));
  };

  if (loading) return <p className="text-text-secondary">Loading fleet settings…</p>;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <Truck className="h-7 w-7 text-primary" />
          Fleet Settings
        </h1>
        <p className="mt-1 text-text-secondary">
          Your real costs drive net profit calculations — not generic industry averages.
        </p>
      </div>

      {isProductionMode() && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">API Access</CardTitle>
          </CardHeader>
          <CardContent>
            <Input
              type="password"
              placeholder="X-API-Key (required in production)"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Company</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-text-secondary">Company name</label>
            <Input
              value={profile.company_name}
              onChange={(e) => setProfile((p) => ({ ...p, company_name: e.target.value }))}
            />
          </div>
          <div>
            <p className="mb-2 text-xs text-text-secondary">Default equipment</p>
            <div className="grid grid-cols-2 gap-2">
              {EQUIPMENT_OPTIONS.map((eq) => (
                <button
                  key={eq}
                  type="button"
                  onClick={() => setProfile((p) => ({ ...p, default_equipment: eq }))}
                  className={cn(
                    "rounded-md border px-2 py-2 text-sm",
                    profile.default_equipment === eq
                      ? "border-primary bg-primary/15 font-semibold text-primary"
                      : "border-border bg-surface-hover text-text-secondary"
                  )}
                >
                  {eq}
                </button>
              ))}
            </div>
          </div>
          <DeadheadControl
            value={profile.max_deadhead_miles}
            onChange={(m) => setProfile((p) => ({ ...p, max_deadhead_miles: m }))}
            label={`Default max deadhead (${profile.max_deadhead_miles} mi)`}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Operating Costs</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Fuel ($/gal)" value={profile.fuel_price_per_gallon} onChange={(v) => setNum("fuel_price_per_gallon", v)} />
          <Field label="Driver pay ($/mi)" value={profile.driver_cpm} onChange={(v) => setNum("driver_cpm", v)} />
          <Field label="Insurance ($/mi)" value={profile.insurance_per_mile} onChange={(v) => setNum("insurance_per_mile", v)} />
          <Field label="Maintenance ($/mi)" value={profile.maintenance_per_mile} onChange={(v) => setNum("maintenance_per_mile", v)} />
          <Field label="Tolls ($/mi)" value={profile.tolls_per_mile} onChange={(v) => setNum("tolls_per_mile", v)} />
          <Field label="Overhead ($/mi)" value={profile.overhead_per_mile} onChange={(v) => setNum("overhead_per_mile", v)} />
          <Field label="Loaded MPG" value={profile.avg_mpg_loaded} onChange={(v) => setNum("avg_mpg_loaded", v)} />
          <Field label="Empty MPG" value={profile.avg_mpg_empty} onChange={(v) => setNum("avg_mpg_empty", v)} />
          <Field label="Dispatch fee (decimal)" value={profile.dispatch_fee_percent} onChange={(v) => setNum("dispatch_fee_percent", v)} />
          <Field label="Factoring fee (decimal)" value={profile.factoring_fee_percent} onChange={(v) => setNum("factoring_fee_percent", v)} />
        </CardContent>
      </Card>

      <Button className="w-full gap-2" size="lg" onClick={save} disabled={saving}>
        <Save className="h-4 w-4" />
        {saving ? "Saving…" : "Save Fleet Profile"}
      </Button>

      {message && (
        <p className={`text-center text-sm ${message.includes("Failed") ? "text-danger" : "text-accent"}`}>
          {message}
        </p>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-text-secondary">{label}</label>
      <Input type="number" step="0.01" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
