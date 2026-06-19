/** Map tile provider — Mapbox or MapTiler (both work with mapbox-gl / react-map-gl). */

export interface MapConfig {
  mapStyle: string;
  mapboxAccessToken: string;
  provider: "mapbox" | "maptiler";
}

export function getMapConfig(): MapConfig | null {
  const maptilerKey = process.env.NEXT_PUBLIC_MAPTILER_KEY;
  const mapboxToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  if (maptilerKey) {
    return {
      provider: "maptiler",
      mapStyle: `https://api.maptiler.com/maps/dataviz-dark/style.json?key=${maptilerKey}`,
      mapboxAccessToken: maptilerKey,
    };
  }

  if (mapboxToken) {
    return {
      provider: "mapbox",
      mapStyle: "mapbox://styles/mapbox/dark-v11",
      mapboxAccessToken: mapboxToken,
    };
  }

  return null;
}

export function mapConfigErrorMessage(): string {
  return "Set NEXT_PUBLIC_MAPBOX_TOKEN or NEXT_PUBLIC_MAPTILER_KEY to enable the map";
}
