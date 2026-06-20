"use client";

import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";

const MIN = 50;
const MAX = 500;

function clampMiles(value: number): number {
  return Math.min(MAX, Math.max(MIN, Math.round(value)));
}

interface DeadheadControlProps {
  value: number;
  onChange: (miles: number) => void;
  label?: string;
}

export function DeadheadControl({ value, onChange, label = "📏 Max deadhead?" }: DeadheadControlProps) {
  const [draft, setDraft] = useState(String(value));

  useEffect(() => {
    setDraft(String(value));
  }, [value]);

  const commitDraft = () => {
    const parsed = parseInt(draft, 10);
    if (Number.isNaN(parsed)) {
      setDraft(String(value));
      return;
    }
    const miles = clampMiles(parsed);
    onChange(miles);
    setDraft(String(miles));
  };

  return (
    <div>
      <label className="mb-1 block text-xs text-text-secondary">{label}</label>
      <div className="flex items-center gap-3">
        <Input
          type="number"
          inputMode="numeric"
          min={MIN}
          max={MAX}
          step={1}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commitDraft}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitDraft();
          }}
          className="w-24 shrink-0 font-mono-num"
          aria-label="Max deadhead miles"
        />
        <span className="shrink-0 text-xs text-text-secondary">mi</span>
        <Slider
          className="flex-1"
          value={[value]}
          min={MIN}
          max={MAX}
          step={1}
          onValueChange={([miles]) => {
            onChange(clampMiles(miles));
            setDraft(String(clampMiles(miles)));
          }}
        />
      </div>
    </div>
  );
}
