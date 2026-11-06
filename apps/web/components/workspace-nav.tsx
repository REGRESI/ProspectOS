"use client";
import { BookOpen, Building2, CalendarDays, CheckCircle2, FileText, LayoutDashboard, MessageSquare, Search, ShieldCheck, Sparkles, Target, Upload, Users, Workflow, Link2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export const navigation: {
  section: string;
  items: { path: string; label: string; icon: LucideIcon }[];
}[] = [
  {
    section: "HEUTE",
    items: [
      { path: "/today", label: "Heute", icon: CheckCircle2 },
      { path: "/agent", label: "Auftrags-Agent", icon: Sparkles },
      { path: "/overview", label: "Übersicht", icon: LayoutDashboard },
    ],
  },
  {
    section: "LEADS",
    items: [
      { path: "/leads/top", label: "Top-Kandidaten", icon: Target },
      { path: "/discover", label: "Lead Discovery", icon: Search },
      { path: "/companies", label: "Unternehmen", icon: Building2 },
      { path: "/contacts", label: "Kontakte", icon: Users },
      { path: "/audiences", label: "Zielgruppen & ICP", icon: Target },
      { path: "/intelligence", label: "Recherche & KI", icon: Sparkles },
      { path: "/imports", label: "Import-Verlauf", icon: Upload },
    ],
  },
  {
    section: "KAMPAGNEN",
    items: [
      { path: "/campaigns", label: "Kampagnen", icon: MessageSquare },
      { path: "/outreach", label: "Outreach-Entwürfe", icon: FileText },
    ],
  },
  {
    section: "CONTENT",
    items: [
      { path: "/content/plan", label: "LinkedIn-Strategie", icon: CalendarDays },
      { path: "/social/studio", label: "Social Studio", icon: Sparkles },
      { path: "/social/calendar", label: "Content-Kalender", icon: CalendarDays },
      { path: "/social/library", label: "Bildbibliothek", icon: FileText },
      { path: "/brands", label: "Markenprofile", icon: Target },
      { path: "/social/engagement", label: "Engagement", icon: MessageSquare },
    ],
  },
  {
    section: "CRM",
    items: [
      { path: "/pipeline", label: "CRM / Pipeline", icon: Workflow },
      { path: "/tasks", label: "Aufgaben & Notizen", icon: CheckCircle2 },
      { path: "/audit", label: "Aktivitäten", icon: ShieldCheck },
    ],
  },
  {
    section: "EINSTELLUNGEN",
    items: [
      { path: "/settings/setup", label: "Setup-Check", icon: ShieldCheck },
      { path: "/settings/workspace", label: "Workspace-Einrichtung", icon: Building2 },
      { path: "/settings/integrations", label: "Integrationen", icon: Link2 },
      { path: "/settings/team", label: "Team & Rollen", icon: Users },
      { path: "/settings/billing", label: "Abo & Ressourcen", icon: BookOpen },
      { path: "/operations", label: "Aufträge & Budget", icon: Workflow },
    ],
  },
];

export const titles: Record<string, string> = {
  "/settings/setup": "Setup-Check",
  "/settings/workspace": "Workspace-Einrichtung",
  "/settings/team": "Team & Rollen",
  "/settings/billing": "Abo & Ressourcen",
  "/social/engagement": "Engagement",
  "/imports": "Import-Verlauf",
  "/contacts/legacy": "Kontakte",
  "/companies/legacy": "Unternehmen",
  "/discover/legacy": "Discovery-Beispiele",
  "/outreach/legacy": "Outreach-Entwürfe",
  "/overview": "Übersicht",
  "/contacts": "Kontakte",
  "/discover": "Lead Discovery",
  "/intelligence": "Recherche & KI",
  "/companies": "Unternehmen",
  "/leads/top": "Top-Kandidaten",
  "/today": "Heute",
  "/agent": "Auftrags-Agent",
  "/content/plan": "LinkedIn-Strategie",
  "/audiences": "Zielgruppen & ICP",
  "/pipeline": "CRM / Pipeline",
  "/social/studio": "Social Studio",
  "/social/calendar": "Content-Kalender",
  "/settings/integrations": "Integrationen",
  "/audit": "Aktivitäten",
  "/tasks": "Aufgaben & Notizen",
  "/campaigns": "Kampagnen",
  "/outreach": "Outreach-Entwürfe",
  "/social/library": "Bildbibliothek",
  "/brands": "Markenprofile",
  "/operations": "Aufträge & Budget",
};

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
