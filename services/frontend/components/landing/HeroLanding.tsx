"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSession, signIn } from "next-auth/react";
import { animate, motion } from "framer-motion";
import { ClipboardPaste, Rocket, Scale, Truck, TrendingUp } from "lucide-react";
import { getDashboardStats, getDriverCount } from "@/lib/api";
import { searchCities } from "@/lib/cities";
import { MOCK_STATS } from "@/lib/mock-data";
import { useAppStore } from "@/lib/store";
import type { DashboardStats } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DeadheadControl } from "@/components/DeadheadControl";

function AnimatedNumber({
  value,
  format,
}: {
  value: number;
  format?: (n: number) => string;
}) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const controls = animate(0, value, {
      duration: 1.4,
      ease: "easeOut",
      onUpdate: (v) => setDisplay(v),
    });
    return () => controls.stop();
  }, [value]);

  const text = format ? format(display) : Math.round(display).toLocaleString();
  return <span className="font-mono-num">{text}</span>;
}

export function HeroLanding() {
  const [stats, setStats] = useState<DashboardStats>(MOCK_STATS);
  const [cityQuery, setCityQuery] = useState("Dallas, TX");
  const [localEquipment, setLocalEquipment] = useState("Dry Van");
  const [localDeadhead, setLocalDeadhead] = useState(250);
  const [suggestions, setSuggestions] = useState<ReturnType<typeof searchCities>>([]);
  const [submitting, setSubmitting] = useState(false);
  const [motionReady, setMotionReady] = useState(false);
  const [driverCount, setDriverCount] = useState(0);
  const { status } = useSession();

  const { setDriverLocation, setEquipment, setMaxDeadhead, dismissHero, triggerSearch } = useAppStore();

  useEffect(() => {
    setMotionReady(true);
  }, []);

  useEffect(() => {
    getDashboardStats()
      .then(setStats)
      .catch(() => setStats(MOCK_STATS));
    getDriverCount().then(setDriverCount).catch(() => {});
  }, []);

  const handleFindLoads = () => {
    if (status === "unauthenticated") {
      signIn(undefined, { callbackUrl: "/" });
      return;
    }
    const match =
      searchCities(cityQuery).find(
        (c) => `${c.city}, ${c.state}`.toLowerCase() === cityQuery.toLowerCase()
      ) ?? searchCities("Dallas")[0];

    if (!match) return;

    setSubmitting(true);
    setDriverLocation(match.lat, match.lng, match.city, match.state);
    setEquipment(localEquipment);
    setMaxDeadhead(localDeadhead);
    dismissHero();
    triggerSearch(
      `Find the best ${localEquipment} loads near ${match.city}, ${match.state} within ${localDeadhead} miles. Rank by net profit.`,
      `Best ${localEquipment} near ${match.city}, ${match.state} · ${localDeadhead} mi deadhead`
    );
  };

  const statCards = [
    { label: "Loads", value: stats.total_loads, format: (n: number) => Math.round(n).toLocaleString() },
    { label: "Avg Net", value: stats.avg_net_profit, format: (n: number) => `$${Math.round(n).toLocaleString()}` },
    { label: "#1 Mkt", text: stats.best_market.split(",")[0] },
    { label: "Avg $/mi", value: stats.avg_rate_per_mile, format: (n: number) => `$${n.toFixed(2)}` },
  ];

  return (
    <div className="relative min-h-[calc(100vh-5.5rem)] overflow-hidden bg-background">
      {/* Animated route lines */}
      <div className="pointer-events-none absolute inset-0 opacity-30">
        <svg className="h-full w-full" xmlns="http://www.w3.org/2000/svg">
          <motion.path
            d="M-100,400 Q200,200 500,350 T1100,280"
            fill="none"
            stroke="url(#routeGrad)"
            strokeWidth="2"
            strokeDasharray="8 12"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 3, repeat: Infinity, repeatType: "reverse", ease: "easeInOut" }}
          />
          <motion.path
            d="M-50,600 Q300,450 600,500 T1200,420"
            fill="none"
            stroke="#10B981"
            strokeWidth="1.5"
            strokeDasharray="6 10"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 4, delay: 0.5, repeat: Infinity, repeatType: "reverse" }}
          />
          <defs>
            <linearGradient id="routeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#22D3EE" />
              <stop offset="100%" stopColor="#10B981" />
            </linearGradient>
          </defs>
        </svg>
      </div>

      <div className="relative z-10 mx-auto flex max-w-4xl flex-col items-center px-4 py-12 text-center">
        <motion.div
          initial={motionReady ? { opacity: 0, y: 20 } : false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mb-6 flex items-center gap-3"
        >
          <Truck className="h-10 w-10 text-primary" />
          <h1 className="bg-gradient-to-r from-primary to-accent bg-clip-text text-4xl font-bold tracking-[0.2em] text-transparent md:text-5xl">
            D E A D M I L E &nbsp; A I
          </h1>
        </motion.div>

        <motion.h2
          initial={motionReady ? { opacity: 0 } : false}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="mb-2 text-2xl font-bold text-text-primary md:text-3xl"
        >
          Stop Losing Money on Empty Miles
        </motion.h2>

        <motion.p
          initial={motionReady ? { opacity: 0 } : false}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.35 }}
          className="mb-4 max-w-xl text-text-secondary"
        >
          AI-powered load optimization that maximizes your{" "}
          <span className="font-semibold text-accent">NET profit</span> — not just gross revenue.
        </motion.p>

        <motion.span
          initial={motionReady ? { opacity: 0 } : false}
          animate={{ opacity: 1 }}
          className="mb-8 inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-4 py-1.5 text-sm font-semibold text-accent"
        >
          100% Free — No credit card · No limits
        </motion.span>

        <motion.div
          initial={motionReady ? { opacity: 0, scale: 0.96 } : false}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.45 }}
          className="w-full max-w-lg rounded-xl border border-border bg-surface/90 p-6 shadow-2xl backdrop-blur"
        >
          <div className="space-y-4 text-left">
            <div className="relative">
              <label className="mb-1 block text-xs text-text-secondary">📍 Where are you?</label>
              <Input
                value={cityQuery}
                onChange={(e) => {
                  setCityQuery(e.target.value);
                  setSuggestions(searchCities(e.target.value));
                }}
                placeholder="Dallas, TX"
              />
              {suggestions.length > 0 && (
                <div className="absolute z-20 mt-1 w-full rounded-md border border-border bg-surface shadow-lg">
                  {suggestions.slice(0, 6).map((s) => (
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

            <div>
              <label className="mb-1 block text-xs text-text-secondary">🚛 Equipment?</label>
              <Select value={localEquipment} onValueChange={setLocalEquipment}>
                <SelectTrigger>
                  <SelectValue placeholder="Dry Van" />
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

            <DeadheadControl value={localDeadhead} onChange={setLocalDeadhead} />

            <Button
              className="w-full gap-2 bg-gradient-to-r from-primary to-accent text-background hover:opacity-90"
              size="lg"
              onClick={handleFindLoads}
              disabled={submitting}
            >
              <Rocket className="h-5 w-5" />
              Find My Best Loads
            </Button>
          </div>
        </motion.div>

        <motion.div
          initial={motionReady ? { opacity: 0, y: 16 } : false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
          className="mt-10 grid w-full max-w-2xl grid-cols-2 gap-4 md:grid-cols-4"
        >
          {statCards.map((card, i) => (
            <motion.div
              key={card.label}
              initial={motionReady ? { opacity: 0, y: 12 } : false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.7 + i * 0.1 }}
              className="rounded-lg border border-border bg-surface/80 p-4 backdrop-blur"
            >
              <div className="text-2xl font-bold text-primary">
                {"text" in card ? (
                  <span className="font-mono-num">{card.text}</span>
                ) : (
                  <AnimatedNumber value={card.value!} format={card.format} />
                )}
              </div>
              <div className="mt-1 text-xs text-text-secondary">{card.label}</div>
            </motion.div>
          ))}
        </motion.div>
      </div>

      {/* How it works + social proof */}
      <div className="relative z-10 mx-auto max-w-5xl px-4 pb-16">
        <h3 className="mb-8 text-center text-xl font-bold md:text-2xl">How It Works</h3>
        <div className="mb-12 grid gap-6 md:grid-cols-3">
          {[
            {
              icon: ClipboardPaste,
              title: "Paste your loads",
              desc: "Copy listings from DAT, Truckstop, or any load board.",
            },
            {
              icon: Scale,
              title: "True net profit",
              desc: "We calculate fuel, deadhead, fees, and destination market score.",
            },
            {
              icon: TrendingUp,
              title: "Pick the winner",
              desc: "See which load actually puts the most money in your pocket.",
            },
          ].map((step, i) => (
            <div
              key={step.title}
              className="rounded-xl border border-border bg-surface/80 p-6 text-center backdrop-blur"
            >
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                <step.icon className="h-6 w-6 text-primary" />
              </div>
              <div className="mb-1 text-sm font-bold text-primary">Step {i + 1}</div>
              <h4 className="mb-2 font-semibold">{step.title}</h4>
              <p className="text-sm text-text-secondary">{step.desc}</p>
            </div>
          ))}
        </div>

        <div className="mb-12 rounded-xl border border-border bg-surface/80 p-6 md:p-8">
          <h3 className="mb-4 text-lg font-bold">Why Gross Rate Lies to You</h3>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-danger/30 bg-danger/5 p-4">
              <div className="text-sm text-text-secondary">Load paying $3,100 gross</div>
              <div className="font-mono-num text-2xl font-bold text-danger">$412 net</div>
              <div className="mt-1 text-xs text-text-secondary">Dead market · 180mi deadhead next</div>
            </div>
            <div className="rounded-lg border border-accent/30 bg-accent/5 p-4">
              <div className="text-sm text-text-secondary">Load paying $2,275 gross</div>
              <div className="font-mono-num text-2xl font-bold text-accent">$892 net</div>
              <div className="mt-1 text-xs text-text-secondary">Hot market · 22mi deadhead next</div>
            </div>
          </div>
          <p className="mt-4 text-center text-sm text-text-secondary">
            Lower gross can mean higher NET when destination markets and deadhead differ.
          </p>
        </div>

        <div className="flex flex-col items-center gap-4 text-center">
          <Link
            href="/compare"
            className="inline-flex items-center gap-2 rounded-lg border border-primary bg-primary/10 px-6 py-3 font-semibold text-primary hover:bg-primary/20"
          >
            🥊 Try the Load Showdown
          </Link>
          <p className="text-sm text-text-secondary">
            Used by{" "}
            <span className="font-mono-num font-bold text-primary">{driverCount}</span> drivers
          </p>
        </div>
      </div>
    </div>
  );
}
