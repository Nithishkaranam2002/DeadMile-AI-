"use client";

import { useEffect, useMemo, useState } from "react";
import Map, { NavigationControl } from "react-map-gl";
import { DeckGL } from "@deck.gl/react";
import { ArcLayer, LineLayer, ScatterplotLayer } from "@deck.gl/layers";
import "mapbox-gl/dist/mapbox-gl.css";
import type { ProfitBreakdown, ViewState } from "@/lib/types";
import { viewStateForLoads } from "@/lib/map-bounds";
import { getMapConfig, mapConfigErrorMessage } from "@/lib/map-config";

function marketRgb(label: string): [number, number, number] {
  const l = label.toLowerCase();
  if (l.includes("hot")) return [16, 185, 129];
  if (l.includes("warm")) return [245, 158, 11];
  if (l.includes("neutral")) return [148, 163, 184];
  if (l.includes("cool")) return [249, 115, 22];
  return [239, 68, 68];
}

interface ImportMapProps {
  loads: ProfitBreakdown[];
  driverLat: number;
  driverLng: number;
  height?: number;
}

export function ImportMap({ loads, driverLat, driverLng, height = 320 }: ImportMapProps) {
  const mapConfig = getMapConfig();
  const [viewState, setViewState] = useState<ViewState>({
    latitude: driverLat,
    longitude: driverLng,
    zoom: 5,
    pitch: 25,
    bearing: 0,
  });

  const withCoords = useMemo(
    () => loads.filter((l) => l.origin_lat && l.origin_lng),
    [loads]
  );

  useEffect(() => {
    const next = viewStateForLoads(loads, driverLat, driverLng);
    if (next) setViewState(next);
  }, [loads, driverLat, driverLng]);

  const layers = useMemo(() => {
    const result = [];
    result.push(
      new ScatterplotLayer({
        id: "driver",
        data: [{ position: [driverLng, driverLat] }],
        getPosition: (d: { position: [number, number] }) => d.position,
        getFillColor: [34, 211, 238],
        getRadius: 12000,
        radiusMinPixels: 10,
        radiusMaxPixels: 18,
      })
    );
    if (withCoords.length) {
      result.push(
        new LineLayer({
          id: "routes",
          data: withCoords
            .filter((l) => l.dest_lat && l.dest_lng)
            .map((l) => ({
              path: [
                [driverLng, driverLat],
                [l.origin_lng!, l.origin_lat!],
                [l.dest_lng!, l.dest_lat!],
              ] as [number, number][],
            })),
          getPath: (d: { path: [number, number][] }) => d.path,
          getColor: [34, 211, 238, 180],
          getWidth: 2,
        })
      );
      result.push(
        new ArcLayer({
          id: "arcs",
          data: withCoords.filter((l) => l.dest_lat && l.dest_lng),
          getSourcePosition: (l: ProfitBreakdown) => [l.origin_lng!, l.origin_lat!],
          getTargetPosition: (l: ProfitBreakdown) => [l.dest_lng!, l.dest_lat!],
          getSourceColor: [16, 185, 129, 200],
          getTargetColor: (l: ProfitBreakdown): [number, number, number, number] => [
            ...marketRgb(l.destination_market_label),
            220,
          ],
          getWidth: 2,
        })
      );
    }
    return result;
  }, [withCoords, driverLat, driverLng]);

  if (!mapConfig) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-border bg-surface text-sm text-text-secondary"
        style={{ height }}
      >
        {mapConfigErrorMessage()}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border" style={{ height }}>
      <DeckGL viewState={viewState} onViewStateChange={({ viewState: vs }) => setViewState(vs as ViewState)} controller layers={layers}>
        <Map
          mapboxAccessToken={mapConfig.mapboxAccessToken}
          mapStyle={mapConfig.mapStyle}
          style={{ width: "100%", height: "100%" }}
        >
          <NavigationControl position="bottom-right" />
        </Map>
      </DeckGL>
    </div>
  );
}
