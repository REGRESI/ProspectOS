import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

// One typeface for the whole app; self-hosted by Next at build time.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "ProspectOS",
  description: "Jeden Morgen die nächsten Schritte für neue Kunden: Firmen, Kontakte und LinkedIn-Beiträge.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="de" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
