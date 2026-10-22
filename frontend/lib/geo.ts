export function circlePolygon(lat: number, lng: number, radiusKm: number, n = 64): { type: "Polygon"; coordinates: number[][][] } {
  const ring: number[][] = [];
  for (let i = 0; i <= n; i++) {
    const t = (2 * Math.PI * i) / n;
    const dLat = (radiusKm * Math.sin(t)) / 110.574;
    const dLng = (radiusKm * Math.cos(t)) / (111.32 * Math.max(0.05, Math.cos((lat * Math.PI) / 180)));
    ring.push([lng + dLng, lat + dLat]);
  }
  return { type: "Polygon", coordinates: [ring] };
}
