export const US_CITIES = [
  { city: "Dallas", state: "TX", lat: 32.7767, lng: -96.797 },
  { city: "Atlanta", state: "GA", lat: 33.749, lng: -84.388 },
  { city: "Chicago", state: "IL", lat: 41.8781, lng: -87.6298 },
  { city: "Los Angeles", state: "CA", lat: 34.0522, lng: -118.2437 },
  { city: "Houston", state: "TX", lat: 29.7604, lng: -95.3698 },
  { city: "Phoenix", state: "AZ", lat: 33.4484, lng: -112.074 },
  { city: "Memphis", state: "TN", lat: 35.1495, lng: -90.049 },
  { city: "Charlotte", state: "NC", lat: 35.2271, lng: -80.8431 },
  { city: "Denver", state: "CO", lat: 39.7392, lng: -104.9903 },
  { city: "Indianapolis", state: "IN", lat: 39.7684, lng: -86.1581 },
  { city: "Grand Rapids", state: "MI", lat: 42.9634, lng: -85.6681 },
  { city: "Fort Worth", state: "TX", lat: 32.7555, lng: -97.3308 },
  { city: "Knoxville", state: "TN", lat: 35.9606, lng: -83.9207 },
  { city: "Salt Lake City", state: "UT", lat: 40.7608, lng: -111.891 },
  { city: "New York", state: "NY", lat: 40.7128, lng: -74.006 },
  { city: "Miami", state: "FL", lat: 25.7617, lng: -80.1918 },
  { city: "Seattle", state: "WA", lat: 47.6062, lng: -122.3321 },
  { city: "Nashville", state: "TN", lat: 36.1627, lng: -86.7816 },
  { city: "Kansas City", state: "MO", lat: 39.0997, lng: -94.5786 },
  { city: "Columbus", state: "OH", lat: 39.9612, lng: -82.9988 },
];

export function searchCities(query: string) {
  const q = query.toLowerCase();
  return US_CITIES.filter(
    (c) =>
      c.city.toLowerCase().includes(q) ||
      c.state.toLowerCase().includes(q) ||
      `${c.city}, ${c.state}`.toLowerCase().includes(q)
  ).slice(0, 8);
}
