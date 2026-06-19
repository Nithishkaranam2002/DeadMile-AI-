"use client";

import { useMemo } from "react";
import Map, { NavigationControl } from "react-map-gl";
import { DeckGL } from "@deck.gl/react";
import { ArcLayer, LineLayer, ScatterplotLayer } from "@deck.gl/layers";
import { HexagonLayer } from "@deck.gl/aggregation-layers";
import "mapbox-gl/dist/mapbox-gl.css";
import { useAppStore } from "@/lib/store";
import type { ProfitBreakdown } from "@/lib/types";
import { MapControls } from "./MapControls";
import { getMapConfig, mapConfigErrorMessage } from "@/lib/map-config";

function marketRgb(label: string): [number, number, number] {
  const l = label.toLowerCase();
  if (l.includes("hot")) return [16, 185, 129];
  if (l.includes("warm")) return [245, 158, 11];
  if (l.includes("neutral")) return [148, 163, 184];
  if (l.includes("cool")) return [249, 115, 22];
  return [239, 68, 68];
}

export function LoadMap() {
  const mapConfig = getMapConfig();
  const driverLat = useAppStore((s) => s.driverLat);
  const driverLng = useAppStore((s) => s.driverLng);
  const recommendedLoads = useAppStore((s) => s.recommendedLoads);
  const selectedLoad = useAppStore((s) => s.selectedLoad);
  const showHeatmap = useAppStore((s) => s.showHeatmap);
  const showArcs = useAppStore((s) => s.showArcs);
  const showRoutes = useAppStore((s) => s.showRoutes);
  const mapViewState = useAppStore((s) => s.mapViewState);
  const setMapViewState = useAppStore((s) => s.setMapViewState);
  const selectLoad = useAppStore((s) => s.selectLoad);
  const topMarkets = useAppStore((s) => s.topMarkets);

  const layers = useMemo(() => {
    const result = [];
    const dLat = driverLat ?? 32.7767;
    const dLng = driverLng ?? -96.797;

    result.push(
      new ScatterplotLayer({
        id: "driver",
        data: [{ position: [dLng, dLat] }],
        getPosition: (d: { position: [number, number] }) => d.position,
        getFillColor: [34, 211, 238],
        getRadius: 12000,
        radiusMinPixels: 10,
        radiusMaxPixels: 20,
        pickable: false,
      })
    );

    const loadPoints = recommendedLoads.filter((l) => l.origin_lat && l.origin_lng);
    if (loadPoints.length) {
      result.push(
        new ScatterplotLayer({
          id: "load-origins",
          data: loadPoints,
          getPosition: (l: ProfitBreakdown) => [l.origin_lng!, l.origin_lat!] as [number, number],
          getFillColor: [16, 185, 129],
          getRadius: 8000,
          radiusMinPixels: 6,
          radiusMaxPixels: 12,
          pickable: true,
          onClick: (info) => selectLoad(info.object as ProfitBreakdown),
        })
      );

      result.push(
        new ScatterplotLayer({
          id: "load-dests",
          data: loadPoints.filter((l) => l.dest_lat && l.dest_lng),
          getPosition: (l: ProfitBreakdown) => [l.dest_lng!, l.dest_lat!] as [number, number],
          getFillColor: (l: ProfitBreakdown): [number, number, number, number] => [...marketRgb(l.destination_market_label), 200],
          getRadius: 6000,
          radiusMinPixels: 5,
          radiusMaxPixels: 10,
          pickable: true,
        })
      );
    }

    if (showArcs && loadPoints.length) {
      result.push(
        new ArcLayer({
          id: "arcs",
          data: loadPoints.slice(0, 10),
          getSourcePosition: () => [dLng, dLat],
          getTargetPosition: (l: ProfitBreakdown) => [l.origin_lng!, l.origin_lat!] as [number, number],
          getSourceColor: [34, 211, 238, 180],
          getTargetColor: [16, 185, 129, 180],
          getWidth: 2,
        })
      );
    }

    if (showRoutes && selectedLoad?.origin_lat && selectedLoad.origin_lng) {
      const route = [
        { path: [[dLng, dLat], [selectedLoad.origin_lng!, selectedLoad.origin_lat!], [selectedLoad.dest_lng!, selectedLoad.dest_lat!]] },
      ];
      result.push(
        new LineLayer({
          id: "route",
          data: route,
          getPath: (d: { path: [number, number][] }) => d.path,
          getColor: [34, 211, 238, 220],
          getWidth: 3,
        })
      );
    }

    if (showHeatmap && topMarkets.length) {
      result.push(
        new HexagonLayer({
          id: "heatmap",
          data: topMarkets,
          getPosition: (m: { lng: number; lat: number }) => [m.lng, m.lat] as [number, number],
          getElevationWeight: (m: { outbound_load_count: number }) => m.outbound_load_count,
          elevationScale: 5000,
          extruded: true,
          radius: 60000,
          coverage: 0.8,
          colorRange: [
            [239, 68, 68],
            [245, 158, 11],
            [16, 185, 129],
          ],
          pickable: true,
        })
      );
    }

    return result;
  }, [driverLat, driverLng, recommendedLoads, selectedLoad, showArcs, showRoutes, showHeatmap, topMarkets, selectLoad]);

  if (!mapConfig) {
    return (
      <div className="flex h-full items-center justify-center bg-surface text-text-secondary">
        {mapConfigErrorMessage()}
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      <MapControls />
      <DeckGL
        viewState={mapViewState}
        onViewStateChange={({ viewState }) => setMapViewState(viewState as typeof mapViewState)}
        controller
        layers={layers}
      >
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
