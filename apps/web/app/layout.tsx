import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "ProspectOS · Dein nächster guter Kontakt",
  description:
    "Dein Workspace für B2B-Kontakte, bessere Gespräche und LinkedIn-Content.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="de">
      <body>{children}</body>
    </html>
  );
}
