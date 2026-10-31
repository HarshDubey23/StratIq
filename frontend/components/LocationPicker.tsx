"use client";

import { MapPin, Search } from "lucide-react";
import { useState } from "react";
import { Map as MarketMap } from "@/components/Map";
import { Button, ErrorState, Input, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { circlePolygon } from "@/lib/geo";
import type { GeoResult } from "@/lib/types";

export interface PickedPlace {
  lat: number;
  lng: number;
  address: string;
}

export function LocationPicker({
  value,
  onChange,
  radiusKm,
  initialQuery = "",
  height = "h-80",
}: {
  value: PickedPlace | null;
  onChange: (p: PickedPlace) => void;
  radiusKm: number;
  initialQuery?: string;
  height?: string;
}) {
  const [q, setQ] = useState(initialQuery);
  const [results, setResults] = useState<GeoResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<[number, number]>(value ? [value.lng, value.lat] : [78.9629, 22.5937]);
  const [fitKey, setFitKey] = useState("init");

  async function search(e?: React.FormEvent) {
    e?.preventDefault();
    if (q.trim().length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const r = await api<{ results: GeoResult[] }>(`/market/search?q=${encodeURIComponent(q.trim())}`);
      setResults(r.results);
      if (!r.results.length) setError("No places found. Try a nearby landmark, locality and city, or click the map to drop a pin.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  function pick(lat: number, lng: number, address: string) {
    onChange({ lat, lng, address });
    setView([lng, lat]);
    setFitKey(`${lat},${lng},${radiusKm}`);
  }

  async function dropPin(lat: number, lng: number) {
    pick(lat, lng, `Pinned location (${lat.toFixed(5)}, ${lng.toFixed(5)})`);
    try {
      const r = await api<{ display_name: string }>(`/market/reverse?lat=${lat}&lng=${lng}`);
      if (r.display_name) onChange({ lat, lng, address: r.display_name });
    } catch {
      /* address is optional */
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={search} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a locality, street or landmark, e.g. ‘HSR Layout Sector 2, Bengaluru’" className="pl-9" aria-label="Search place" />
        </div>
        <Button type="submit" loading={loading}>Search</Button>
      </form>
      {error && <ErrorState message={error} />}
      {results && results.length > 0 && (
        <ul className="max-h-40 divide-y divide-black/[0.06] overflow-auto rounded-xl border border-black/[0.07] bg-black/[0.02]">
          {results.map((r, i) => (
            <li key={i}>
              <button type="button" onClick={() => pick(r.lat, r.lng, r.display_name)} className="flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-ink-800">
                <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                <span>
                  <span className="block text-ink-100">{r.name}</span>
                  <span className="block text-xs text-ink-400">{r.display_name}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className={`overflow-hidden rounded-md border border-black/[0.07] ${height}`}>
        <MarketMap
          className="h-full w-full"
          center={view}
          zoom={value ? 13 : 4}
          pitch={value ? 40 : 0}
          catchment={value ? circlePolygon(value.lat, value.lng, radiusKm) : null}
          candidates={value ? [{ id: "pick", label: "Candidate", lat: value.lat, lng: value.lng, active: true }] : []}
          onMapClick={dropPin}
          crosshair
          fitKey={fitKey}
        />
      </div>
      <div className="text-xs text-ink-400">
        {loading ? <Spinner label="Searching OpenStreetMap…" /> : value ? <>Selected: <span className="text-ink-200">{value.address}</span></> : "Search, then pick a result, or click anywhere on the map to drop a pin. An approximate area is fine for an early study."}
      </div>
    </div>
  );
}
