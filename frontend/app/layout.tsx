import type { Metadata, Viewport } from "next";
import { Archivo, Instrument_Serif, Inter_Tight, JetBrains_Mono, Tiro_Devanagari_Hindi } from "next/font/google";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";
import VoiceDock from "@/components/voice/VoiceDockLoader";

const inter = Inter_Tight({ subsets: ["latin"], variable: "--font-inter-tight", display: "swap" });
const serif = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--font-instrument", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jbmono", display: "swap" });
// Archivo with its width axis: extra-wide for landing headlines, normal width for landing text
const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo", display: "swap" });
const tiro = Tiro_Devanagari_Hindi({ subsets: ["devanagari"], weight: "400", variable: "--font-tiro", display: "swap" });

export const metadata: Metadata = {
  title: "StrataIQ — Test your business on a live model of the street",
  description:
    "Pick any business and any place. StrataIQ loads the real competitors and population around it, adds ground data from a field researcher, simulates 10,000 customers on a 3D map, and shows profit, risk and break-even before you invest.",
};

export const viewport: Viewport = { themeColor: "#f3f4f7", colorScheme: "light" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${serif.variable} ${mono.variable} ${tiro.variable} ${archivo.variable}`}>
      <body className="grain min-h-screen font-sans">
        {children}
        <VoiceDock />
      </body>
    </html>
  );
}
