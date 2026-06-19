"use client";

import { Maximize2 } from "lucide-react";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";

export function MapControls() {
  const showHeatmap = useAppStore((s) => s.showHeatmap);
  const showArcs = useAppStore((s) => s.showArcs);
  const showRoutes = useAppStore((s) => s.showRoutes);
  const toggleHeatmap = useAppStore((s) => s.toggleHeatmap);
  const toggleArcs = useAppStore((s) => s.toggleArcs);
  const toggleRoutes = useAppStore((s) => s.toggleRoutes);
  const recommendedLoads = useAppStore((s) => s.recommendedLoads);
  const driverLat = useAppStore((s) => s.driverLat);
  const driverLng = useAppStore((s) => s.driverLng);
  const setMapViewState = useAppStore((s) => s.setMapViewState);

  const zoomToFit = () => {
    if (recommendedLoads.length && recommendedLoads[0].origin_lat) {
      setMapViewState({
        latitude: recommendedLoads[0].origin_lat!,
        longitude: recommendedLoads[0].origin_lng!,
        zoom: 5,
        pitch: 30,
        bearing: 0,
      });
    } else if (driverLat && driverLng) {
      setMapViewState({ latitude: driverLat, longitude: driverLng, zoom: 6, pitch: 0, bearing: 0 });
    }
  };

  return (
    <div className="absolute left-3 top-3 z-10 flex flex-col gap-2">
      <Button variant={showHeatmap ? "default" : "outline"} size="sm" onClick={toggleHeatmap}>
        Heatmap
      </Button>
      <Button variant={showArcs ? "default" : "outline"} size="sm" onClick={toggleArcs}>
        Arcs
      </Button>
      <Button variant={showRoutes ? "default" : "outline"} size="sm" onClick={toggleRoutes}>
        Routes
      </Button>
      <Button variant="outline" size="icon" onClick={zoomToFit} title="Zoom to fit">
        <Maximize2 className="h-4 w-4" />
      </Button>
    </div>
  );
}
