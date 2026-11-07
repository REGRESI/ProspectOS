"use client";
import { Building2, CheckCircle2, FlaskConical, PenLine, Settings, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/*
 * Five areas only. Each area has tabs for its sub-pages; everything else lives under
 * Einstellungen. Developer pages (synthetic examples, raw data) appear only in the
 * Demo workspace.
 */
export type Tab = { path: string; label: string };
export type Section = {
  key: string;
  label: string;
  icon: LucideIcon;
  tabs: Tab[];
  /** Extra route prefixes that belong to this area (detail pages). */
  prefixes?: string[];
};

export const sections: Section[] = [
  { key: "today", label: "Heute", icon: CheckCircle2, tabs: [{ path: "/today", label: "Heute" }] },
  {
    key: "companies",
    label: "Firmen",
    icon: Building2,
    tabs: [
      { path: "/leads/top", label: "Beste Treffer" },
      { path: "/companies", label: "Alle Firmen" },
      { path: "/discover", label: "Firmen finden" },
    ],
    prefixes: ["/companies/"],
  },
  {
    key: "contacts",
    label: "Kontakte",
    icon: Users,
    tabs: [
      { path: "/contacts", label: "Alle Kontakte" },
      { path: "/contacts/advanced", label: "Auswahl und Listen" },
      { path: "/imports", label: "Importe" },
    ],
  },
  {
    key: "content",
    label: "Content",
    icon: PenLine,
    tabs: [
      { path: "/content/plan", label: "Plan" },
      { path: "/social/studio", label: "Beitrag schreiben" },
      { path: "/social/calendar", label: "Kalender" },
      { path: "/social/library", label: "Bilder" },
    ],
  },
  {
    key: "settings",
    label: "Einstellungen",
    icon: Settings,
    tabs: [
      { path: "/settings/setup", label: "Status" },
      { path: "/settings/outreach", label: "Anschreiben" },
      { path: "/agent", label: "Autopilot" },
      { path: "/audiences", label: "Zielgruppe" },
      { path: "/settings/workspace", label: "Mein Angebot" },
      { path: "/settings/integrations", label: "Verbindungen" },
      { path: "/operations", label: "Kosten" },
      { path: "/settings/workspaces", label: "Workspaces" },
      { path: "/settings/team", label: "Team" },
      { path: "/audit", label: "Verlauf" },
    ],
  },
];

/** Only in the Demo workspace: examples and developer views. */
export const demoSection: Section = {
  key: "demo",
  label: "Mehr (Demo)",
  icon: FlaskConical,
  tabs: [
    { path: "/overview", label: "Übersicht" },
    { path: "/intelligence", label: "Recherche" },
    { path: "/campaigns", label: "Kampagnen" },
    { path: "/outreach", label: "Entwürfe" },
    { path: "/pipeline", label: "Pipeline" },
    { path: "/tasks", label: "Aufgaben" },
    { path: "/brands", label: "Markenprofile" },
    { path: "/social/engagement", label: "Kommentare" },
    { path: "/settings/billing", label: "Abo" },
    { path: "/discover/legacy", label: "Entwicklungsbeispiele" },
    { path: "/contacts/legacy", label: "Rohdaten Kontakte" },
    { path: "/companies/legacy", label: "Rohdaten Firmen" },
  ],
  prefixes: ["/campaigns/"],
};

/** Developer pages: refused outside the Demo workspace. */
export const DEV_ONLY = [
  "/discover/legacy",
  "/contacts/legacy",
  "/companies/legacy",
  "/audiences/legacy",
  "/outreach/legacy",
];

export function sectionFor(route: string, demo: boolean): Section | undefined {
  const all = demo ? [...sections, demoSection] : sections;
  return (
    all.find((s) => s.tabs.some((t) => t.path === route)) ||
    all.find((s) => s.prefixes?.some((p) => route.startsWith(p) && !route.endsWith("/legacy")))
  );
}

export function titleFor(route: string, demo: boolean): string {
  const section = sectionFor(route, demo);
  if (!section) return "";
  if (route.startsWith("/companies/") && route !== "/companies/legacy") return "Firmenprofil";
  if (route.startsWith("/campaigns/")) return "Kampagne";
  return section.tabs.find((t) => t.path === route)?.label || section.label;
}

export function Logo() {
  return (
    <span className="brand">
      <span className="brand-mark">
        <span />
        <span />
        <span />
      </span>
      <span className="brand-wordmark">
        Prospect<span className="brand-os">OS</span>
      </span>
    </span>
  );
}
