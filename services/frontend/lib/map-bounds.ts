import type { ProfitBreakdown, ViewState } from "./types";

function computeZoom(latSpan: number, lngSpan: number): number {
  const span = Math.max(latSpan, lngSpan, 0.75);
  if (span > 35) return 3.5;
  if (span > 20) return 4.5;
  if (span > 12) return 5;
  if (span > 6) return 5.5;
  if (span > 3) return 6;
  if (span > 1.5) return 7;
  return 8;
}

/** Fit map view to driver location and all recommended load endpoints. */
export function viewStateForLoads(
  loads: ProfitBreakdown[],
  driverLat?: number | null,
  driverLng?: number | null
): ViewState | null {
  const points: Array<[number, number]> = [];

  if (driverLat != null && driverLng != null) {
    points.push([driverLng, driverLat]);
  }

  for (const load of loads) {
    if (load.origin_lat != null && load.origin_lng != null) {
      points.push([load.origin_lng, load.origin_lat]);
    }
    if (load.dest_lat != null && load.dest_lng != null) {
      points.push([load.dest_lng, load.dest_lat]);
    }
  }

  if (points.length === 0) return null;

  const lngs = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);

  return {
    latitude: (minLat + maxLat) / 2,
    longitude: (minLng + maxLng) / 2,
    zoom: computeZoom(maxLat - minLat, maxLng - minLng),
    pitch: 25,
    bearing: 0,
  };
}
