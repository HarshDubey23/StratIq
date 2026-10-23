import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Geist, Geist_Mono, Tiro_Devanagari_Hindi } from "next/font/google";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";
import VoiceDock from "@/components/voice/VoiceDockLoader";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist", display: "swap" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });
const bricolage = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage", display: "swap", axes: ["opsz", "wdth"] });
const tiro = Tiro_Devanagari_Hindi({ subsets: ["devanagari"], weight: "400", variable: "--font-tiro", display: "swap" });

export const metadata: Metadata = {
  title: "StrataIQ — Test your business on a live model of the street",
  description:
    "Pick any business and any place. StrataIQ pulls real competitors from OpenStreetMap and real population from WorldPop, simulates 10,000 synthetic customers on a 3D map, and shows profit, risk and break-even before you invest.",
};

export const viewport: Viewport = { themeColor: "#04060b", colorScheme: "dark" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geist.variable} ${mono.variable} ${bricolage.variable} ${tiro.variable}`}>
      <body className="grain min-h-screen font-sans">
        {children}
        <VoiceDock />
      </body>
    </html>
  );
}
