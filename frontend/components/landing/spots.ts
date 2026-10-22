export interface Spot {
  key: string;
  label: string;
  lat: number;
  lng: number;
}
export interface PreviewComp {
  name: string;
  lat: number;
  lng: number;
  ref: string;
}

export const SPOTS: Spot[] = [
  { key: "cp-delhi", label: "Connaught Place, New Delhi", lat: 28.6315, lng: 77.2167 },
  { key: "indiranagar", label: "Indiranagar, Bengaluru", lat: 12.9719, lng: 77.6412 },
  { key: "bandra", label: "Bandra West, Mumbai", lat: 19.0596, lng: 72.8295 },
];
