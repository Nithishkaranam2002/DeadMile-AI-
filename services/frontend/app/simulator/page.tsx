"use client";

import { SimulatorMap } from "@/components/simulator/SimulatorMap";

export default function SimulatorPage() {
  return (
    <div className="space-y-4 p-4 lg:p-6">
      <div>
        <h1 className="text-2xl font-bold">What-If Simulator</h1>
        <p className="text-text-secondary">
          Explore projected earnings from any location — drag the map or set your driver location in the dashboard
        </p>
      </div>
      <SimulatorMap />
    </div>
  );
}
