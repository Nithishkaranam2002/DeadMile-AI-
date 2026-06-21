"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, ChevronDown, ChevronUp, Truck } from "lucide-react";
import { searchCities } from "@/lib/cities";
import { updateCarrierProfile } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const EQUIPMENT_OPTIONS = ["Dry Van", "Flatbed", "Reefer", "Step Deck"];

export default function OnboardingPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [companyName, setCompanyName] = useState("");
  const [equipment, setEquipment] = useState<string[]>(["Dry Van"]);
  const [cityQuery, setCityQuery] = useState("");
  const [suggestions, setSuggestions] = useState<ReturnType<typeof searchCities>>([]);
  const [homeCity, setHomeCity] = useState("");
  const [homeState, setHomeState] = useState("");
  const [showCosts, setShowCosts] = useState(false);
  const [fuelPrice, setFuelPrice] = useState("3.90");
  const [mpgLoaded, setMpgLoaded] = useState("6.0");
  const [driverCpm, setDriverCpm] = useState("0.55");
  const [insurance, setInsurance] = useState("0.08");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login?callbackUrl=/onboarding");
  }, [status, router]);

  const toggleEquipment = (eq: string) => {
    setEquipment((prev) =>
      prev.includes(eq) ? (prev.length > 1 ? prev.filter((e) => e !== eq) : prev) : [...prev, eq]
    );
  };

  const finish = async (skip = false) => {
    setSaving(true);
    try {
      if (!skip) {
        await updateCarrierProfile({
          company_name: companyName || session?.user?.name || "My Fleet",
          default_equipment: equipment[0],
          home_city: homeCity || undefined,
          home_state: homeState || undefined,
          fuel_price_per_gallon: parseFloat(fuelPrice) || 3.9,
          avg_mpg_loaded: parseFloat(mpgLoaded) || 6.0,
          driver_cpm: parseFloat(driverCpm) || 0.55,
          insurance_per_mile: parseFloat(insurance) || 0.08,
        });
      }
      router.push("/");
    } catch {
      router.push("/");
    } finally {
      setSaving(false);
    }
  };

  if (status === "loading") {
    return <div className="flex min-h-[50vh] items-center justify-center text-text-secondary">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-10">
      <div className="mb-8 flex items-center gap-3">
        <Truck className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">Welcome to DeadMile AI</h1>
          <p className="text-sm text-text-secondary">Step {step} of 4 — set up your fleet profile</p>
        </div>
      </div>

      <div className="mb-6 flex gap-2">
        {[1, 2, 3, 4].map((s) => (
          <div
            key={s}
            className={cn("h-1 flex-1 rounded-full", s <= step ? "bg-primary" : "bg-border")}
          />
        ))}
      </div>

      <motion.div
        key={step}
        initial={{ opacity: 0, x: 16 }}
        animate={{ opacity: 1, x: 0 }}
        className="rounded-xl border border-border bg-surface p-6"
      >
        {step === 1 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">What&apos;s your company name?</h2>
            <Input
              placeholder="Optional — e.g. Smith Trucking"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
            />
            <Button className="w-full" onClick={() => setStep(2)}>
              Continue
            </Button>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">What equipment do you run?</h2>
            <div className="grid grid-cols-2 gap-2">
              {EQUIPMENT_OPTIONS.map((eq) => (
                <button
                  key={eq}
                  type="button"
                  onClick={() => toggleEquipment(eq)}
                  className={cn(
                    "rounded-lg border px-3 py-3 text-sm font-medium transition-colors",
                    equipment.includes(eq)
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:border-primary/40"
                  )}
                >
                  {eq}
                </button>
              ))}
            </div>
            <Button className="w-full" onClick={() => setStep(3)}>
              Continue
            </Button>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Where&apos;s your home base?</h2>
            <div className="relative">
              <Input
                placeholder="Dallas, TX"
                value={cityQuery}
                onChange={(e) => {
                  setCityQuery(e.target.value);
                  setSuggestions(searchCities(e.target.value));
                }}
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
                        setHomeCity(s.city);
                        setHomeState(s.state);
                        setSuggestions([]);
                      }}
                    >
                      {s.city}, {s.state}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <Button className="w-full" onClick={() => setStep(4)}>
              Continue
            </Button>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Customize your costs</h2>
            <button
              type="button"
              className="flex w-full items-center justify-between text-sm text-text-secondary"
              onClick={() => setShowCosts(!showCosts)}
            >
              Optional cost settings
              {showCosts ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
            {showCosts && (
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-xs text-text-secondary">
                  Fuel $/gal
                  <Input value={fuelPrice} onChange={(e) => setFuelPrice(e.target.value)} className="mt-1" />
                </label>
                <label className="text-xs text-text-secondary">
                  MPG loaded
                  <Input value={mpgLoaded} onChange={(e) => setMpgLoaded(e.target.value)} className="mt-1" />
                </label>
                <label className="text-xs text-text-secondary">
                  Driver pay $/mi
                  <Input value={driverCpm} onChange={(e) => setDriverCpm(e.target.value)} className="mt-1" />
                </label>
                <label className="text-xs text-text-secondary">
                  Insurance $/mi
                  <Input value={insurance} onChange={(e) => setInsurance(e.target.value)} className="mt-1" />
                </label>
              </div>
            )}
            <Button className="w-full gap-2" onClick={() => finish(false)} disabled={saving}>
              Start Finding Loads
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </motion.div>

      <button
        type="button"
        className="mt-4 w-full text-center text-sm text-text-secondary hover:text-primary"
        onClick={() => finish(true)}
        disabled={saving}
      >
        Skip — use defaults
      </button>
    </div>
  );
}
