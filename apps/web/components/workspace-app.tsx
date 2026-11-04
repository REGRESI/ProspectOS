"use client";
import { IntegrationCredentials } from "./integration-credentials";
import { ICPBuilder } from "./icp-builder";
import { useEffect, useState, useCallback, FormEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  ArrowRight,
  PanelLeftClose,
  PanelLeftOpen,
  ArrowUpRight,
  BookOpen,
  Building2,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  CircleHelp,
  Copy,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  Upload,
  Users,
  Workflow,
  X,
  Link2,
  Sun,
  Moon,
  ExternalLink,
} from "lucide-react";
import { Badge, Empty, Modal, Spinner, Heading, ErrorNote } from "./ui";
import { Social } from "./social-studio";
import { OperationalHome } from "./operational-home";
import {
  WorkspaceOnboarding,
  TeamSettings,
  BillingSettings,
  ProviderChecks,
} from "./workspace-settings";
import {
  DiscoveryWorkbench,
  LeadDatabase,
  CompanyDirectory,
  CompanyProfile,
  ImportHistory,
  OutreachWorkbench,
} from "./journey-workspaces";
import { EngagementWorkspace } from "./social-tools";
import { IntelligenceConsole } from "./intelligence-console";
import {
  AssetLibrary,
  BrandProfiles,
  TaskNotes,
  Campaigns,
  Operations,
  OutreachDrafts,
} from "./growth-modules";
import { useData } from "@/lib/use-data";
import type { LucideIcon } from "lucide-react";
import {
  request,
  ApiError,
  number,
  money,
  dateTime,
  stageLabels,
} from "@/lib/api";
import type {
  Session,
  Workspace,
  Contact,
  Page,
  Deal,
  Icp,
  Preview,
  Activity,
} from "@/lib/api";

const navigation: {
  section: string;
  items: { path: string; label: string; icon: LucideIcon }[];
}[] = [
  {
    section: "START",
    items: [{ path: "/overview", label: "Übersicht", icon: LayoutDashboard }],
  },
  {
    section: "DISCOVER",
    items: [
      { path: "/discover", label: "Lead Discovery", icon: Search },
      { path: "/intelligence", label: "Recherche & KI", icon: Sparkles },
      { path: "/imports", label: "Import-Verlauf", icon: Upload },
    ],
  },
  {
    section: "LEADS",
    items: [
      { path: "/contacts", label: "Kontakte", icon: Users },
      { path: "/companies", label: "Unternehmen", icon: Building2 },
      { path: "/audiences", label: "Zielgruppen & ICP", icon: Target },
    ],
  },
  {
    section: "OUTREACH",
    items: [
      { path: "/campaigns", label: "Kampagnen", icon: MessageSquare },
      { path: "/outreach", label: "Outreach-Entwürfe", icon: FileText },
    ],
  },
  {
    section: "SOCIAL",
    items: [
      { path: "/social/studio", label: "Social Studio", icon: Sparkles },
      {
        path: "/social/calendar",
        label: "Content-Kalender",
        icon: CalendarDays,
      },
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
      {
        path: "/settings/workspace",
        label: "Workspace-Einrichtung",
        icon: Building2,
      },
      { path: "/settings/integrations", label: "Integrationen", icon: Link2 },
      { path: "/settings/team", label: "Team & Rollen", icon: Users },
      { path: "/settings/billing", label: "Abo & Ressourcen", icon: BookOpen },
      { path: "/operations", label: "Aufträge & Budget", icon: Workflow },
    ],
  },
];
const titles: Record<string, string> = {
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
function Logo() {
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
export default function WorkspaceApp() {
  const router = useRouter();
  const pathname = usePathname();
  const route = pathname === "/" ? "/overview" : pathname;
  const [authConfig, setAuthConfig] = useState<{
    mode: string;
    demo_enabled: boolean;
  } | null>(null);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [workspaceError, setWorkspaceError] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [boot, setBoot] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [mobile, setMobile] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [theme, setTheme] = useState("light");
  const [revision, setRevision] = useState(0);
  const [importOpen, setImportOpen] = useState(false);
  useEffect(() => {
    const nav = document.querySelector<HTMLElement>(".sidebar nav");
    const active = nav?.querySelector<HTMLElement>(".nav-item.active");
    if (nav && active) {
      const delta =
        active.getBoundingClientRect().top - nav.getBoundingClientRect().top;
      if (delta < 0 || delta + active.offsetHeight > nav.clientHeight)
        nav.scrollTop += delta - nav.clientHeight / 2 + active.offsetHeight / 2;
    }
  }, [route, session?.user.id]);
  const refresh = () => setRevision((v) => v + 1);
  const notify = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(""), 5000);
  };
  useEffect(() => {
    let active = true;
    Promise.allSettled([
      request<{ mode: string; demo_enabled: boolean }>("/v1/auth/config")
        .then((config) => {
          if (active) setAuthConfig(config);
        })
        .catch((e) => {
          if (active) setError(e.message);
        }),
      request<Session>("/v1/me")
        .then((s) => {
          if (active) {
            setSession(s);
            setWorkspace(
              s.workspaces.find(
                (w) => w.id === sessionStorage.getItem("prospectos.workspace"),
              ) ||
                s.workspaces[0] ||
                null,
            );
          }
        })
        .catch((e) => {
          if (active && !(e instanceof ApiError && e.status === 401))
            setError(e.message);
        }),
    ]).finally(() => {
      if (active) {
        try {
          setCollapsed(
            localStorage.getItem("prospectos.sidebar.collapsed") === "true",
          );
        } catch {}
        setBoot(false);
      }
    });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const go = (path: string) => {
    router.push(path);
    setMobile(false);
  };
  const write = async <T,>(
    path: string,
    body: unknown = {},
    method = "POST",
  ): Promise<T> =>
    request<T>(
      `/v1/workspaces/${workspace?.id}${path}`,
      { method, body: JSON.stringify(body) },
      session?.csrf_token,
    );
  const base = `/v1/workspaces/${workspace?.id}`;
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const s = await request<Session>(
        authConfig?.demo_enabled ? "/v1/auth/demo" : "/v1/auth/login",
        {
          method: "POST",
          body: JSON.stringify({
            email: form.get("email"),
            password: form.get("password"),
          }),
        },
      );
      setSession(s);
      setWorkspace(s.workspaces[0]);
      router.replace("/overview");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (boot)
    return (
      <div className="boot">
        <Logo />
        <Spinner />
        <p>Dein Workspace wird geladen …</p>
      </div>
    );
  if (!session)
    return (
      <main className="login-page">
        <section className="login-story">
          <Logo />
          <div>
            <Badge tone="light">DEIN WACHSTUM. EIN WORKSPACE.</Badge>
            <h1>
              Gute Geschäfte
              <br />
              beginnen mit guten
              <br />
              <span>Verbindungen.</span>
            </h1>
            <p>
              Finde passende Kontakte. Bereite bessere Gespräche vor.
              <br />
              Gib deiner Marke eine Stimme.
            </p>
            <div className="login-points">
              <span>
                <CheckCircle2 size={18} /> Nachvollziehbares Lead-Scoring
              </span>
              <span>
                <CheckCircle2 size={18} /> Kontakte und Content an einem Ort
              </span>
              <span>
                <CheckCircle2 size={18} /> Deine Daten. Dein Workspace.
              </span>
            </div>
          </div>
          <p className="login-foot">ProspectOS · Mit Klarheit wachsen.</p>
        </section>
        <section className="login-form-wrap">
          <div className="login-form">
            <Badge tone="purple">
              <Sparkles size={12} />{" "}
              {authConfig?.demo_enabled
                ? "LOKALE ENTWICKLUNGSUMGEBUNG"
                : "DEIN GESCHÜTZTER WORKSPACE"}
            </Badge>
            <h2>Willkommen zurück.</h2>
            <p>Öffne deinen Workspace und mach den nächsten Schritt.</p>
            <form onSubmit={login}>
              <label>
                E-Mail-Adresse
                <input
                  name="email"
                  type="email"
                  defaultValue={
                    authConfig?.demo_enabled ? "demo@prospectos.local" : ""
                  }
                  required
                  autoComplete="username"
                />
              </label>
              <label>
                Passwort
                <input
                  name="password"
                  type="password"
                  defaultValue={
                    authConfig?.demo_enabled ? "ProspectDemo!2026" : ""
                  }
                  required
                  autoComplete="current-password"
                />
              </label>
              {error && (
                <p role="alert" className="error-note">
                  {error}
                </p>
              )}
              <button
                className="button primary login-submit"
                disabled={busy || !authConfig}
              >
                {busy ? (
                  <Spinner />
                ) : (
                  <>
                    {authConfig?.demo_enabled
                      ? "Demo-Workspace öffnen"
                      : "Anmelden"}{" "}
                    <ArrowRight size={17} />
                  </>
                )}
              </button>
            </form>
            <div className="info-note">
              <ShieldCheck size={20} />
              <p>
                <strong>
                  {authConfig?.demo_enabled
                    ? "Transparent im Demo-Modus"
                    : "Sicher anmelden"}
                </strong>
                {authConfig?.demo_enabled
                  ? "Diese Zugangsdaten sind nur für die lokale Entwicklung. Beispieldaten sind synthetisch."
                  : "Die Anmeldung wird durch deinen konfigurierten Identitätsanbieter geprüft. Dein Browser erhält eine geschützte Sitzung."}
              </p>
            </div>
          </div>
          <span className="login-caption">
            Externe Aktionen benötigen explizite Freigaben und verifizierte
            Berechtigungen.
          </span>
        </section>
      </main>
    );
  return (
    <div className={`app ${collapsed ? "sidebar-collapsed" : ""}`}>
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <div className="sidebar-logo">
          <Logo />
          <button
            className="icon-button sidebar-toggle desktop-only"
            aria-label={
              collapsed ? "Navigation ausklappen" : "Navigation einklappen"
            }
            onClick={() => {
              setCollapsed(!collapsed);
              try {
                localStorage.setItem(
                  "prospectos.sidebar.collapsed",
                  String(!collapsed),
                );
              } catch {}
            }}
          >
            {collapsed ? (
              <PanelLeftOpen size={17} />
            ) : (
              <PanelLeftClose size={17} />
            )}
          </button>
          <button
            className="icon-button mobile-only"
            onClick={() => setMobile(false)}
            aria-label="Navigation schließen"
          >
            <X size={20} />
          </button>
        </div>
        <div className="workspace-picker">
          <span className="workspace-avatar">
            {workspace?.name.slice(0, 1) || "P"}
          </span>
          <label className="sr-only" htmlFor="workspace">
            Workspace
          </label>
          <select
            id="workspace"
            value={workspace?.id || ""}
            onChange={(e) => {
              if (e.target.value === "__new") {
                setWorkspaceOpen(true);
                return;
              }
              setImportOpen(false);
              sessionStorage.setItem("prospectos.workspace", e.target.value);
              setWorkspace(
                session.workspaces.find((w) => w.id === e.target.value) || null,
              );
              refresh();
            }}
          >
            {session.workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
            <option value="__new">+ Workspace erstellen</option>
          </select>
          <ChevronsUpDown size={14} />
        </div>
        <nav aria-label="Hauptnavigation">
          {navigation.map((group) => (
            <div className="nav-group" key={group.section}>
              <p>{group.section}</p>
              {group.items.map((item) => (
                <button
                  key={item.path}
                  aria-label={item.label}
                  title={collapsed ? item.label : undefined}
                  aria-current={
                    route === item.path || route.startsWith(item.path + "/")
                      ? "page"
                      : undefined
                  }
                  className={`nav-item ${route === item.path || route.startsWith(item.path + "/") ? "active" : ""}`}
                  onClick={() => go(item.path)}
                >
                  <item.icon size={18} />
                  <span>{item.label}</span>
                  {item.path === "/social/studio" && (
                    <span className="nav-new">NEU</span>
                  )}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-card">
            <span className="status-dot" />
            <strong>
              {authConfig?.demo_enabled
                ? "Lokaler Demo-Modus"
                : "Geschützter Workspace"}
            </strong>
            <p>
              {authConfig?.demo_enabled
                ? "Synthetische Daten. Echte Workflows."
                : "Sitzung mit geprüftem Kontozugriff."}
            </p>
          </div>
          <button
            className="user-menu"
            onClick={async () => {
              try {
                await request(
                  "/v1/auth/logout",
                  { method: "POST" },
                  session.csrf_token,
                );
                setSession(null);
                setWorkspace(null);
                sessionStorage.removeItem("prospectos.workspace");
              } catch (e) {
                notify((e as Error).message);
              }
            }}
          >
            <span className="user-avatar">
              {session.user.name?.slice(0, 1) || "D"}
            </span>
            <span>
              <strong>{session.user.name || "Demo-Nutzer"}</strong>
              <small>Abmelden</small>
            </span>
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      {mobile && (
        <div className="mobile-scrim" onClick={() => setMobile(false)} />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-only"
              aria-label="Navigation öffnen"
              onClick={() => setMobile(true)}
            >
              <Menu size={21} />
            </button>
            <span className="desktop-only">Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {titles[route] ||
                (route.startsWith("/campaigns/")
                  ? "Kampagnendetails"
                  : route.startsWith("/companies/")
                    ? "Unternehmensprofil"
                    : "Workspace")}
            </strong>
          </div>
          <div className="topbar-actions">
            <Badge tone="green">
              <span className="status-dot" />{" "}
              {workspace?.role === "owner" ? "Owner" : workspace?.role}
            </Badge>
            <button
              className="icon-button"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              aria-label={
                theme === "light"
                  ? "Dunkles Design aktivieren"
                  : "Helles Design aktivieren"
              }
            >
              {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
            </button>
            <button
              className="icon-button"
              title="Integrationsstatus"
              aria-label="Integrationsstatus öffnen"
              onClick={() => go("/settings/integrations")}
            >
              <CircleHelp size={18} />
            </button>
            <span className="top-avatar">
              {session.user.name?.slice(0, 1) || "D"}
            </span>
          </div>
        </header>
        <main className="main-content" key={workspace?.id}>
          {workspace ? (
            <>
              {route === "/discover" && (
                <DiscoveryWorkbench
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                  onNavigate={go}
                  onImport={() => setImportOpen(true)}
                />
              )}
              {route === "/contacts" && (
                <LeadDatabase
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                  onNavigate={go}
                  onImport={() => setImportOpen(true)}
                />
              )}
              {route === "/companies" && (
                <CompanyDirectory
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                  onNavigate={go}
                />
              )}
              {route.startsWith("/companies/") &&
                route !== "/companies/legacy" && (
                  <CompanyProfile
                    companyId={route.split("/")[2]}
                    base={base}
                    write={write}
                    csrf={session.csrf_token}
                    notify={notify}
                    revision={revision}
                    onChange={refresh}
                    onNavigate={go}
                  />
                )}
              {route === "/imports" && (
                <ImportHistory
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                  onNavigate={go}
                  onImport={() => setImportOpen(true)}
                />
              )}
              {(route === "/outreach" || route.startsWith("/campaigns/")) && (
                <OutreachWorkbench
                  key={route}
                  initialCampaignId={
                    route.startsWith("/campaigns/")
                      ? route.split("/")[2]
                      : undefined
                  }
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                  onNavigate={go}
                />
              )}
              {route === "/social/engagement" && (
                <EngagementWorkspace
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                />
              )}
              {route === "/settings/workspace" && (
                <WorkspaceOnboarding
                  role={workspace.role}
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                  onNavigate={go}
                  onImport={() => setImportOpen(true)}
                />
              )}
              {route === "/settings/team" && (
                <TeamSettings
                  role={workspace.role}
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                />
              )}
              {route === "/settings/billing" && (
                <BillingSettings
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                />
              )}
              {route === "/overview" && (
                <Overview
                  base={base}
                  revision={revision}
                  name={session.user.name}
                  go={go}
                  openImport={() => setImportOpen(true)}
                />
              )}
              {route === "/discover/legacy" && (
                <Discovery write={write} notify={notify} onChange={refresh} />
              )}
              {route === "/contacts/legacy" && (
                <Contacts
                  base={base}
                  revision={revision}
                  write={write}
                  notify={notify}
                  openImport={() => setImportOpen(true)}
                  onChange={refresh}
                />
              )}
              {route === "/companies/legacy" && (
                <Companies base={base} revision={revision} />
              )}
              {route === "/audiences" && (
                <ICPBuilder
                  base={base}
                  write={write}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                  csrf={session.csrf_token}
                  onNavigate={go}
                />
              )}
              {route === "/audiences/legacy" && (
                <Audiences
                  base={base}
                  write={write}
                  notify={notify}
                  onChange={refresh}
                />
              )}
              {route === "/pipeline" && (
                <Pipeline
                  base={base}
                  write={write}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                />
              )}
              {(route === "/social/studio" || route === "/social/calendar") && (
                <Social
                  base={base}
                  write={write}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                  calendar={route === "/social/calendar"}
                />
              )}
              {route === "/settings/integrations" && (
                <Integrations base={base} write={write} />
              )}
              {route === "/audit" && <Audit base={base} />}
              {route === "/outreach/legacy" && (
                <OutreachDrafts
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                />
              )}
              {route === "/tasks" && (
                <TaskNotes
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                />
              )}
              {route === "/campaigns" && (
                <Campaigns
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                />
              )}
              {route === "/social/library" && (
                <AssetLibrary
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                />
              )}
              {route === "/brands" && (
                <BrandProfiles
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                />
              )}
              {route === "/intelligence" && (
                <IntelligenceConsole
                  base={base}
                  write={write}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                  csrf={session.csrf_token}
                />
              )}
              {route === "/operations" && (
                <Operations
                  base={base}
                  write={write}
                  csrf={session.csrf_token}
                  notify={notify}
                  revision={revision}
                  onChange={refresh}
                />
              )}
              {!titles[route] &&
                !route.startsWith("/companies/") &&
                !route.startsWith("/campaigns/") && (
                  <Empty
                    title="Diese Seite gibt es noch nicht"
                    description="Die verfügbaren Bereiche findest du in der Navigation."
                  >
                    <button
                      className="button primary"
                      onClick={() => go("/overview")}
                    >
                      Zur Übersicht
                    </button>
                  </Empty>
                )}
            </>
          ) : (
            <Empty
              title="Dein Wachstum beginnt hier."
              description="Erstelle einen Workspace für dein Unternehmen oder dein Team."
            >
              <button
                className="button primary"
                onClick={() => setWorkspaceOpen(true)}
              >
                Workspace erstellen
              </button>
            </Empty>
          )}
        </main>
        <footer className="app-footer">
          <span>
            ProspectOS <span className="muted">/</span> Dein nächster guter
            Kontakt.
          </span>
          <span>
            <ShieldCheck size={12} /> Daten bleiben in deinem Workspace
          </span>
        </footer>
      </div>
      {toast && (
        <div role="status" className="toast">
          <CheckCircle2 size={18} />
          {toast}
          <button aria-label="Meldung schließen" onClick={() => setToast("")}>
            <X size={15} />
          </button>
        </div>
      )}
      {workspaceOpen && (
        <Modal
          title="Deinen Workspace einrichten"
          onClose={() => setWorkspaceOpen(false)}
        >
          <form
            className="modal-body"
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              setWorkspaceError("");
              const form = new FormData(event.currentTarget);
              try {
                const created = await request<Workspace>(
                  "/v1/workspaces",
                  {
                    method: "POST",
                    body: JSON.stringify({ name: form.get("name") }),
                  },
                  session.csrf_token,
                );
                setSession({
                  ...session,
                  workspaces: [...session.workspaces, created],
                });
                setWorkspace(created);
                sessionStorage.setItem("prospectos.workspace", created.id);
                setWorkspaceOpen(false);
                go("/settings/workspace");
                notify(
                  "Workspace erstellt. Starte mit deinem Kundenprofil oder dem ersten Kontakt.",
                );
              } catch (e) {
                setWorkspaceError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <p className="muted">
              Ein eigener Bereich für Kontakte, Inhalte und Zusammenarbeit. Die
              Daten bleiben von anderen Workspaces getrennt.
            </p>
            <label>
              Wie heißt dein Unternehmen oder Team?
              <input
                name="name"
                minLength={2}
                maxLength={120}
                required
                placeholder="z. B. Mein Unternehmen"
              />
            </label>
            <ErrorNote message={workspaceError} />
            <div className="form-actions">
              <button
                type="button"
                className="button secondary"
                onClick={() => setWorkspaceOpen(false)}
              >
                Abbrechen
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? <Spinner /> : <Plus size={16} />} Workspace erstellen
              </button>
            </div>
          </form>
        </Modal>
      )}
      {importOpen && workspace && (
        <ImportModal
          base={base}
          csrf={session.csrf_token}
          onClose={() => setImportOpen(false)}
          onDone={() => {
            refresh();
            notify("Import abgeschlossen. Kontakte wurden gespeichert.");
            setImportOpen(false);
            go("/contacts");
          }}
        />
      )}
    </div>
  );
}
type Write = <T>(path: string, body?: unknown, method?: string) => Promise<T>;

function Overview({
  base,
  revision,
  name,
  go,
  openImport,
}: {
  base: string;
  revision: number;
  name: string;
  go: (path: string) => void;
  openImport: () => void;
}) {
  return (
    <OperationalHome
      base={base}
      revision={revision}
      name={name}
      go={go}
      openImport={openImport}
    />
  );
}

function Contacts({
  base,
  revision,
  write,
  notify,
  openImport,
  onChange,
}: {
  base: string;
  revision: number;
  write: Write;
  notify: (s: string) => void;
  openImport: () => void;
  onChange: () => void;
}) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [add, setAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [draft, setDraft] = useState("");
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(search);
      setPage(1);
    }, 250);
    return () => clearTimeout(t);
  }, [search]);
  const { data, error, loading } = useData<Page<Contact>>(
    `${base}/contacts?search=${encodeURIComponent(query)}&page=${page}&limit=25`,
    revision,
  );
  const close = useCallback(() => {
    setSelected(null);
    setAdd(false);
    setDraft("");
    setFormError("");
  }, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    const f = new FormData(event.currentTarget);
    const fields = Object.fromEntries(f.entries());
    try {
      await write(
        selected ? `/contacts/${selected.id}` : "/contacts",
        { ...fields, ...(selected ? { version: selected.version } : {}) },
        selected ? "PATCH" : "POST",
      );
      onChange();
      close();
      notify(selected ? "Kontakt aktualisiert." : "Kontakt angelegt.");
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="DEINE KONTAKTBASIS"
        title="Aus Kontakten werden Verbindungen."
        description="Alle relevanten Menschen, ihr Kontext und dein nächster Schritt."
      >
        <button className="button secondary" onClick={openImport}>
          <Upload size={16} /> CSV importieren
        </button>
        <button className="button primary" onClick={() => setAdd(true)}>
          <Plus size={17} /> Kontakt hinzufügen
        </button>
      </Heading>
      <div className="panel contacts-panel">
        <div className="table-toolbar">
          <div className="tabs">
            <span className="tab active">
              Alle Kontakte <span>{data?.total ?? "—"}</span>
            </span>
          </div>
          <div className="search-box">
            <Search size={16} />
            <input
              aria-label="Kontakte suchen"
              placeholder="Name, Unternehmen, Ort suchen …"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button
                className="icon-button"
                aria-label="Suche löschen"
                onClick={() => setSearch("")}
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>
        <ErrorNote message={error} />
        {loading ? (
          <div className="loading-block">
            <Spinner /> Kontakte laden …
          </div>
        ) : data?.items.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Kontakt</th>
                    <th>Unternehmen</th>
                    <th>Position</th>
                    <th>Standort</th>
                    <th>
                      ICP-Fit <CircleHelp size={12} />
                    </th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((contact, i) => (
                    <tr key={contact.id} onClick={() => setSelected(contact)}>
                      <td>
                        <button
                          className="person-cell"
                          onClick={() => setSelected(contact)}
                        >
                          <span className={`contact-avatar avatar-${i % 5}`}>
                            {contact.first_name?.[0]}
                            {contact.last_name?.[0]}
                          </span>
                          <span>
                            <strong>
                              {contact.first_name} {contact.last_name}
                            </strong>
                            <small>
                              {contact.email || "Keine E-Mail hinterlegt"}
                            </small>
                          </span>
                        </button>
                      </td>
                      <td>
                        <span className="company-cell">
                          {contact.company || "—"}
                        </span>
                      </td>
                      <td>{contact.job_title || "—"}</td>
                      <td>{contact.location || "Unbekannt"}</td>
                      <td>
                        <span
                          className={`score ${contact.score.value >= 65 ? "high" : contact.score.value >= 35 ? "medium" : "low"}`}
                          title="Deterministischer ICP-Fit, keine Kaufwahrscheinlichkeit"
                        >
                          <span />
                          {contact.score.value} <small>/100</small>
                        </span>
                      </td>
                      <td>
                        <Badge
                          tone={
                            contact.status === "qualified" ? "green" : "neutral"
                          }
                        >
                          {contact.status === "archived"
                            ? "Archiviert"
                            : stageLabels[contact.status] || contact.status}
                        </Badge>
                      </td>
                      <td>
                        <ArrowUpRight size={15} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <span>
                {number(data.total)} Kontakte · Seite {page} von{" "}
                {Math.max(1, Math.ceil(data.total / 25))}
              </span>
              <div>
                <button
                  className="icon-button"
                  disabled={page === 1}
                  aria-label="Vorherige Seite"
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  className="icon-button"
                  disabled={page * 25 >= data.total}
                  aria-label="Nächste Seite"
                  onClick={() => setPage(page + 1)}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          </>
        ) : (
          <Empty
            title={
              query
                ? "Keine passenden Kontakte"
                : "Dein nächster guter Kontakt wartet."
            }
            description={
              query
                ? "Versuche einen anderen Namen, Ort oder Unternehmensnamen."
                : "Importiere deine erste CSV-Datei oder lege einen Kontakt manuell an."
            }
          >
            <button
              className="button primary"
              onClick={query ? () => setSearch("") : openImport}
            >
              {query ? (
                "Suche zurücksetzen"
              ) : (
                <>
                  <Upload size={16} /> Kontakte importieren
                </>
              )}
            </button>
          </Empty>
        )}
      </div>
      <p className="data-caption">
        <ShieldCheck size={13} /> Fehlende Daten bleiben unbekannt. Ein
        ICP-Score ist keine Kaufwahrscheinlichkeit.
      </p>
      {(selected || add) && (
        <Modal
          title={selected ? "Kontakt im Detail" : "Neuen Kontakt anlegen"}
          onClose={close}
          wide
        >
          <div className="modal-body">
            <form onSubmit={save}>
              <div className="form-grid">
                <label>
                  Vorname
                  <input
                    name="first_name"
                    defaultValue={selected?.first_name}
                    required
                    maxLength={120}
                  />
                </label>
                <label>
                  Nachname
                  <input
                    name="last_name"
                    defaultValue={selected?.last_name}
                    required
                    maxLength={120}
                  />
                </label>
                <label>
                  Unternehmen
                  <input
                    name="company"
                    defaultValue={selected?.company}
                    maxLength={240}
                  />
                </label>
                <label>
                  Position
                  <input
                    name="job_title"
                    defaultValue={selected?.job_title}
                    maxLength={240}
                  />
                </label>
                <label>
                  Standort
                  <input
                    name="location"
                    defaultValue={selected?.location}
                    maxLength={240}
                  />
                </label>
                <label>
                  Status
                  <select
                    name="status"
                    defaultValue={selected?.status || "new"}
                  >
                    {Object.entries({
                      new: "Neu",
                      qualified: "Qualifiziert",
                      contacted: "Kontaktiert",
                      archived: "Archiviert",
                    }).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  E-Mail (optional)
                  <input
                    name="email"
                    type="email"
                    defaultValue={selected?.email || ""}
                  />
                </label>
                <label>
                  Telefon (optional)
                  <input name="phone" defaultValue={selected?.phone || ""} />
                </label>
                <label className="full-width">
                  LinkedIn-Profil (optional)
                  <input
                    name="linkedin_url"
                    type="url"
                    defaultValue={selected?.linkedin_url || ""}
                    placeholder="https://www.linkedin.com/in/…"
                  />
                </label>
              </div>
              <ErrorNote message={formError} />
              <div className="form-actions">
                <button
                  className="button secondary"
                  type="button"
                  onClick={close}
                >
                  Schließen
                </button>
                <button className="button primary" disabled={saving}>
                  {saving ? <Spinner /> : <Check size={16} />} Speichern
                </button>
              </div>
            </form>
            {selected && (
              <>
                <section className="detail-section">
                  <div className="section-title">
                    <h3>ICP-Fit verstehen</h3>
                    <Badge tone="purple">{selected.score.value} / 100</Badge>
                  </div>
                  <div className="score-factors">
                    {selected.score.factors.map((f) => (
                      <div key={f.name}>
                        <span>
                          <strong>{f.name}</strong>
                          <b>
                            {f.points}/{f.max_points}
                          </b>
                        </span>
                        <div className="factor-track">
                          <span
                            style={{
                              width: `${f.max_points ? (f.points / f.max_points) * 100 : 0}%`,
                            }}
                          />
                        </div>
                        <small>{f.reason}</small>
                      </div>
                    ))}
                  </div>
                  {selected.score.missing_data.length > 0 && (
                    <p className="muted">
                      Unbekannt: {selected.score.missing_data.join(", ")}
                    </p>
                  )}
                  <small className="muted">
                    Quelle: {selected.source} · Fit-Score, keine Kaufabsicht.
                  </small>
                </section>
                <section className="detail-section">
                  <h3>Gespräch vorbereiten</h3>
                  <p className="muted">
                    Offline-Entwurf aus vorhandenen Kontaktdaten. Es wird keine
                    Nachricht versendet.
                  </p>
                  <button
                    className="button secondary"
                    onClick={async () => {
                      try {
                        const result = await write<{ content: string }>(
                          "/outreach/drafts",
                          { contact_id: selected.id },
                        );
                        setDraft(result.content);
                        notify("Offline-Entwurf erstellt. Kein Versand.");
                      } catch (e) {
                        setFormError((e as Error).message);
                      }
                    }}
                  >
                    <Sparkles size={16} /> Gesprächsentwurf erstellen
                  </button>
                  {draft && (
                    <>
                      <textarea
                        aria-label="Nachrichtenentwurf"
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        rows={5}
                      />
                      <div className="form-actions">
                        <button
                          className="button secondary"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(draft);
                              notify("Entwurf kopiert.");
                            } catch {
                              notify(
                                "Kopieren nicht verfügbar. Text bitte markieren und kopieren.",
                              );
                            }
                          }}
                        >
                          <Copy size={14} /> Kopieren
                        </button>
                        {selected.linkedin_url && (
                          <a
                            className="button secondary"
                            target="_blank"
                            rel="noopener noreferrer"
                            href={selected.linkedin_url}
                          >
                            Profil manuell öffnen <ExternalLink size={14} />
                          </a>
                        )}
                      </div>
                    </>
                  )}
                </section>
              </>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
function ImportModal({
  base,
  csrf,
  onClose,
  onDone,
}: {
  base: string;
  csrf: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function inspect() {
    if (!file) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("file", file);
    if (Object.keys(mapping).length)
      form.append("mapping", JSON.stringify(mapping));
    try {
      const result = await request<Preview>(
        `${base}/imports/preview`,
        { method: "POST", body: form },
        csrf,
      );
      setPreview(result);
      setMapping(result.mapping);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function commit() {
    if (!preview) return;
    setBusy(true);
    try {
      await request(
        `${base}/imports/${preview.id}/commit`,
        { method: "POST", body: "{}" },
        csrf,
      );
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Kontakte aus CSV importieren" onClose={onClose} wide>
      <div className="modal-body">
        <div className="import-progress">
          <span className="done">
            1 <b>Datei auswählen</b>
          </span>
          <i />
          <span className={preview ? "done" : ""}>
            2 <b>Prüfen & zuordnen</b>
          </span>
          <i />
          <span>
            3 <b>Importieren</b>
          </span>
        </div>
        <p className="muted">
          UTF-8, auch mit BOM. Komma, Semikolon und Tab werden erkannt. Fehlende
          E-Mails und Domains sind erlaubt.
        </p>
        <label className="upload-zone">
          <Upload size={30} />
          <strong>{file?.name || "Deine CSV-Datei auswählen"}</strong>
          <span>Nur rechtmäßig erhobene Daten importieren · maximal 3 MB</span>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              setPreview(null);
              setMapping({});
            }}
          />
        </label>
        <ErrorNote message={error} />
        {preview && (
          <>
            <div className="import-totals">
              <div>
                <strong>{preview.total}</strong>
                <small>Zeilen insgesamt</small>
              </div>
              <div>
                <strong>{preview.valid}</strong>
                <small>Gültige Zeilen</small>
              </div>
              <div>
                <strong>{preview.duplicates}</strong>
                <small>Dubletten</small>
              </div>
              <div>
                <strong>{preview.invalid}</strong>
                <small>Mit Fehlern</small>
              </div>
            </div>
            <details className="mapping">
              <summary>Spaltenzuordnung bearbeiten</summary>
              <div className="form-grid">
                {Object.entries(mapping).map(([key, value]) => (
                  <label key={key}>
                    {key}
                    <select
                      value={value}
                      onChange={(e) =>
                        setMapping({ ...mapping, [key]: e.target.value })
                      }
                    >
                      <option value="">Nicht importieren</option>
                      {preview.headers.map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <button
                className="button secondary"
                onClick={inspect}
                disabled={busy}
              >
                Zuordnung neu prüfen
              </button>
            </details>
            <div className="table-scroll preview-table">
              <table>
                <thead>
                  <tr>
                    <th>Zeile</th>
                    <th>Kontakt</th>
                    <th>Unternehmen</th>
                    <th>Prüfung</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.slice(0, 8).map((row) => (
                    <tr key={row.row}>
                      <td>{row.row}</td>
                      <td>
                        {row.first_name} {row.last_name}
                      </td>
                      <td>{row.company || "—"}</td>
                      <td>
                        {row.errors.length ? (
                          <Badge tone="red">{row.errors.join(", ")}</Badge>
                        ) : row.duplicate ? (
                          <Badge>Dubletten-Kandidat</Badge>
                        ) : (
                          <Badge tone="green">Gültig</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small">
              Vorschau der ersten {Math.min(preview.rows.length, 8)} Zeilen.
              Erkannte Dubletten werden nicht erneut angelegt; fehlerhafte
              Zeilen werden übersprungen.
            </p>
          </>
        )}
        <div className="form-actions">
          <button className="button secondary" onClick={onClose}>
            Abbrechen
          </button>
          {preview ? (
            <button
              className="button primary"
              onClick={commit}
              disabled={busy || preview.valid === 0}
            >
              {busy ? <Spinner /> : <Check size={16} />} Gültige Kontakte
              importieren
            </button>
          ) : (
            <button
              className="button primary"
              onClick={inspect}
              disabled={!file || busy}
            >
              {busy ? <Spinner /> : <ArrowRight size={16} />} Datei prüfen
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
function Companies({ base, revision }: { base: string; revision: number }) {
  const [page, setPage] = useState(1);
  const { data, error, loading } = useData<
    Page<{
      id: string;
      name: string;
      location?: string;
      city?: string;
      domain?: string;
      contact_count?: number;
    }>
  >(`${base}/companies?page=${page}&limit=25`, revision);
  return (
    <>
      <Heading
        eyebrow="UNTERNEHMENSKONTEXT"
        title="Die Unternehmen hinter deinen Kontakten."
        description="Aus importierten und manuell angelegten Kontakten – ohne erfundene Firmendaten."
      />
      <ErrorNote message={error} />
      <section className="panel">
        {loading ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : data?.items.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Unternehmen</th>
                    <th>Standort</th>
                    <th>Domain</th>
                    <th>Kontakte</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((company) => (
                    <tr key={company.id}>
                      <td>
                        <div className="person-cell">
                          <span className="contact-avatar avatar-1">
                            <Building2 size={18} />
                          </span>
                          <strong>{company.name}</strong>
                        </div>
                      </td>
                      <td>{company.location || company.city || "Unbekannt"}</td>
                      <td>{company.domain || "Nicht hinterlegt"}</td>
                      <td>{company.contact_count ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <span>
                {data.total} Unternehmen · Seite {page}
              </span>
              <div>
                <button
                  className="icon-button"
                  aria-label="Vorherige Seite"
                  disabled={page === 1}
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  className="icon-button"
                  aria-label="Nächste Seite"
                  disabled={page * 25 >= data.total}
                  onClick={() => setPage(page + 1)}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          </>
        ) : (
          <Empty
            icon={Building2}
            title="Noch keine Unternehmen"
            description="Unternehmen werden zusammen mit deinen Kontakten angelegt."
          />
        )}
      </section>
    </>
  );
}
function Audiences({
  base,
  write,
  notify,
  onChange,
}: {
  base: string;
  write: Write;
  notify: (s: string) => void;
  onChange: () => void;
}) {
  const { data, error, loading } = useData<Icp>(`${base}/icp`);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const split = (key: string) =>
      String(form.get(key) || "")
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);
    const weights = {
      location: Number(form.get("location_weight")),
      role: Number(form.get("role_weight")),
      industry: Number(form.get("industry_weight")),
    };
    if (Object.values(weights).reduce((a, b) => a + b, 0) !== 100) {
      setSaveError("Die Gewichtungen müssen zusammen genau 100 ergeben.");
      return;
    }
    setBusy(true);
    setSaveError("");
    try {
      await write(
        "/icp",
        {
          name: form.get("name"),
          locations: split("locations"),
          roles: split("roles"),
          industries: split("industries"),
          weights,
        },
        "PUT",
      );
      onChange();
      notify(
        "ICP gespeichert. Scores werden mit den neuen Kriterien berechnet.",
      );
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="KLARHEIT VOR REICHWEITE"
        title="Wer passt wirklich zu dir?"
        description="Definiere dein ideales Kundenprofil. Jeder Fit-Score bleibt nachvollziehbar."
      />
      <div className="icp-layout">
        <section className="panel padded">
          <div className="panel-head">
            <div>
              <h2>Dein ideales Kundenprofil</h2>
              <p>Kriterien als kommagetrennte Begriffe eingeben.</p>
            </div>
            <span className="step-icon purple">
              <Target size={22} />
            </span>
          </div>
          <ErrorNote message={error || saveError} />
          {loading ? (
            <Spinner />
          ) : (
            data && (
              <form onSubmit={save}>
                <label>
                  Profilname
                  <input name="name" defaultValue={data.name} required />
                </label>
                <label>
                  Standorte
                  <input
                    name="locations"
                    defaultValue={data.locations.join(", ")}
                    placeholder="Offenburg, Freiburg, Karlsruhe"
                  />
                </label>
                <label>
                  Relevante Positionen
                  <input
                    name="roles"
                    defaultValue={data.roles.join(", ")}
                    placeholder="Geschäftsführer, Office, Facility"
                  />
                </label>
                <label>
                  Branchen
                  <input
                    name="industries"
                    defaultValue={data.industries.join(", ")}
                    placeholder="Optional – nur belegte Branchendaten werden gewertet"
                  />
                </label>
                <h3 className="weight-heading">
                  Gewichtung · insgesamt 100 Punkte
                </h3>
                <div className="form-grid weights">
                  <label>
                    Standort
                    <input
                      type="number"
                      name="location_weight"
                      min={0}
                      max={100}
                      defaultValue={data.weights.location}
                      required
                    />
                  </label>
                  <label>
                    Position
                    <input
                      type="number"
                      name="role_weight"
                      min={0}
                      max={100}
                      defaultValue={data.weights.role}
                      required
                    />
                  </label>
                  <label>
                    Branche
                    <input
                      type="number"
                      name="industry_weight"
                      min={0}
                      max={100}
                      defaultValue={data.weights.industry}
                      required
                    />
                  </label>
                </div>
                <div className="form-actions">
                  <button className="button primary" disabled={busy}>
                    {busy ? <Spinner /> : <Check size={16} />} Kundenprofil
                    speichern
                  </button>
                </div>
              </form>
            )
          )}
        </section>
        <aside className="panel icp-explainer">
          <span className="large-icon">
            <ShieldCheck size={30} />
          </span>
          <h2>
            Fit erklären.
            <br />
            Nichts erfinden.
          </h2>
          <p>
            Der Score zeigt, wie gut bekannte Kontaktdaten zu deinen Kriterien
            passen.
          </p>
          <ul>
            <li>Jeder Faktor hat eine sichtbare Begründung.</li>
            <li>Fehlende Informationen bleiben unbekannt.</li>
            <li>Keine erfundene Firmengröße oder Kaufabsicht.</li>
            <li>Ein hoher Score ist keine Versandfreigabe.</li>
          </ul>
          <Badge tone="purple">Deterministisches Scoring · v1</Badge>
        </aside>
      </div>
    </>
  );
}
function Pipeline({
  base,
  write,
  notify,
  revision,
  onChange,
}: {
  base: string;
  write: Write;
  notify: (s: string) => void;
  revision: number;
  onChange: () => void;
}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("created");
  const [view, setView] = useState("board");
  const [detail, setDetail] = useState<{
    id: string;
    title: string;
    amount: number;
    stage: string;
    contact: { id: string; name: string } | null;
    company: { id: string; name: string } | null;
    tasks: {
      id: string;
      title: string;
      state: string;
      due_at: string | null;
    }[];
    notes: { id: string; body: string; created_at: string }[];
    notice: string;
  } | null>(null);
  const { data, error, loading } = useData<
    Page<Deal> & { open_value: number; won_value: number }
  >(
    `${base}/deals?limit=100&page=${page}&search=${encodeURIComponent(search)}&sort=${sort}`,
    revision,
  );
  async function moveDeal(id: string, stage: string) {
    try {
      await write(`/deals/${id}`, { stage }, "PATCH");
      onChange();
      notify("Phase aktualisiert.");
    } catch (e) {
      notify((e as Error).message);
    }
  }
  async function inspectDeal(id: string) {
    try {
      setDetail(await request(`${base}/deals/${id}/context`));
    } catch (e) {
      notify((e as Error).message);
    }
  }
  const [open, setOpen] = useState(false);
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [stageFilter, setStageFilter] = useState("all");
  const contacts = useData<Page<Contact>>(
    `${base}/contacts?limit=100`,
    revision,
  );
  const stages = Object.keys(stageLabels).filter((s) => s !== "lost");
  const close = useCallback(() => setOpen(false), []);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    setBusy(true);
    try {
      const contact = String(f.get("contact_id") || "");
      await write("/deals", {
        title: f.get("title"),
        amount: Math.round(Number(f.get("value")) * 100),
        stage: "new",
        ...(contact ? { contact_id: contact } : {}),
      });
      setOpen(false);
      onChange();
      notify("Verkaufschance angelegt.");
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="CRM / PIPELINE"
        title="Verkaufschancen"
        description="Phasen, Werte und nächste Schritte. Verschiebe Karten per Drag-and-drop oder nutze die tastaturbedienbare Phasenauswahl."
      >
        <button className="button primary" onClick={() => setOpen(true)}>
          <Plus size={17} /> Verkaufschance
        </button>
      </Heading>
      <div className="pipeline-summary">
        <div>
          <span>Offener Pipeline-Wert</span>
          <strong>{money(data?.open_value || 0)}</strong>
        </div>
        <div>
          <span>Verkaufschancen</span>
          <strong>{data?.total ?? "—"}</strong>
        </div>
        <div>
          <span>Gewonnen</span>
          <strong>{money(data?.won_value || 0)}</strong>
        </div>
        <label className="pipeline-filter">
          Ansicht
          <select
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
          >
            <option value="all">Alle aktiven Phasen</option>
            {Object.entries(stageLabels).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="pipeline-toolbar">
        <label>
          Verkaufschancen suchen
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            maxLength={200}
          />
        </label>
        <label>
          Sortierung
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="created">Zuletzt angelegt</option>
            <option value="amount">Höchster Wert</option>
            <option value="title">Titel A–Z</option>
          </select>
        </label>
        <div className="calendar-views">
          <button
            className={view === "board" ? "active" : ""}
            onClick={() => setView("board")}
          >
            Kanban
          </button>
          <button
            className={view === "list" ? "active" : ""}
            onClick={() => setView("list")}
          >
            Listenansicht
          </button>
        </div>
      </div>
      <ErrorNote message={error} />
      {loading ? (
        <div className="loading-block">
          <Spinner />
        </div>
      ) : view === "list" ? (
        <section className="panel">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Verkaufschance</th>
                  <th>Wert</th>
                  <th>Phase</th>
                </tr>
              </thead>
              <tbody>
                {data?.items
                  .filter(
                    (d) => stageFilter === "all" || d.stage === stageFilter,
                  )
                  .map((deal) => (
                    <tr key={deal.id}>
                      <td>
                        <button
                          className="journey-link"
                          onClick={() => inspectDeal(deal.id)}
                        >
                          {deal.title}
                        </button>
                      </td>
                      <td>{money(deal.amount)}</td>
                      <td>
                        <select
                          aria-label={`Phase ändern ${deal.title}`}
                          value={deal.stage}
                          onChange={(e) => moveDeal(deal.id, e.target.value)}
                        >
                          {Object.entries(stageLabels).map(([key, value]) => (
                            <option key={key} value={key}>
                              {value}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <div className="kanban">
          {(stageFilter === "all" ? stages : [stageFilter]).map((stage, i) => {
            const items = data?.items.filter((d) => d.stage === stage) || [];
            return (
              <section
                className="kanban-column"
                key={stage}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const id = e.dataTransfer.getData(
                    "application/prospectos-deal",
                  );
                  if (id) void moveDeal(id, stage);
                }}
              >
                <div className="kanban-head">
                  <span className={`stage-dot stage-${i % 4}`} />
                  <h2>{stageLabels[stage]}</h2>
                  <span>{items.length}</span>
                </div>
                <div className="kanban-total">
                  {money(items.reduce((sum, d) => sum + d.amount, 0))}
                </div>
                {items.map((deal) => (
                  <article
                    className="deal-card"
                    key={deal.id}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData(
                        "application/prospectos-deal",
                        deal.id,
                      );
                      e.dataTransfer.effectAllowed = "move";
                    }}
                  >
                    <span className="deal-icon">
                      <Building2 size={15} />
                    </span>
                    <h3>
                      <button
                        className="journey-link"
                        onClick={() => inspectDeal(deal.id)}
                      >
                        {deal.title}
                      </button>
                    </h3>
                    <strong>{money(deal.amount)}</strong>
                    <label>
                      Phase ändern
                      <select
                        value={deal.stage}
                        onChange={async (e) => {
                          try {
                            await write(
                              `/deals/${deal.id}`,
                              { stage: e.target.value },
                              "PATCH",
                            );
                            onChange();
                            notify("Phase aktualisiert.");
                          } catch (error) {
                            notify((error as Error).message);
                          }
                        }}
                      >
                        {Object.entries(stageLabels).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </label>
                  </article>
                ))}
                {!items.length && (
                  <p className="kanban-empty">
                    Hier ist Platz für deine
                    <br />
                    nächste Chance.
                  </p>
                )}
              </section>
            );
          })}
        </div>
      )}
      {data && data.total > 100 && (
        <div className="pagination">
          <span>
            Seite {page} · {data.total} Verkaufschancen. Summen über alle
            Suchtreffer.
          </span>
          <div>
            <button
              className="button secondary small"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              Zurück
            </button>
            <button
              className="button secondary small"
              disabled={page * 100 >= data.total}
              onClick={() => setPage(page + 1)}
            >
              Weiter
            </button>
          </div>
        </div>
      )}
      {detail && (
        <Modal title={detail.title} onClose={() => setDetail(null)} wide>
          <div className="modal-body">
            <div className="section-title">
              <strong>{money(detail.amount)}</strong>
              <Badge>{stageLabels[detail.stage]}</Badge>
            </div>
            <div className="journey-company-actions">
              {detail.contact && (
                <a
                  className="button secondary"
                  href={`/contacts?contact=${encodeURIComponent(detail.contact.id)}`}
                >
                  {detail.contact.name} · Kontakt öffnen
                </a>
              )}
              {detail.company && (
                <a
                  className="button secondary"
                  href={`/companies/${encodeURIComponent(detail.company.id)}`}
                >
                  {detail.company.name} · Unternehmen öffnen
                </a>
              )}
            </div>
            <div className="journey-profile-grid">
              <section>
                <h3>Nächste Aufgaben</h3>
                {detail.tasks.length ? (
                  detail.tasks.map((task) => (
                    <div className="journey-task" key={task.id}>
                      <span>
                        <strong>{task.title}</strong>
                        <small>
                          {task.state} ·{" "}
                          {task.due_at ? dateTime(task.due_at) : "Ohne Termin"}
                        </small>
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="muted small">Keine verknüpften Aufgaben.</p>
                )}
              </section>
              <section>
                <h3>Kontaktnotizen</h3>
                {detail.notes.length ? (
                  detail.notes.map((note) => (
                    <div className="journey-evidence" key={note.id}>
                      {note.body}
                      <small>{dateTime(note.created_at)}</small>
                    </div>
                  ))
                ) : (
                  <p className="muted small">Keine verknüpften Notizen.</p>
                )}
              </section>
            </div>
            <p className="small muted">{detail.notice}</p>
          </div>
        </Modal>
      )}
      {open && (
        <Modal title="Neue Verkaufschance" onClose={close}>
          <form className="modal-body" onSubmit={create}>
            <label>
              Titel
              <input
                name="title"
                required
                maxLength={240}
                placeholder="z. B. Büroreinigung · Musterfirma"
              />
            </label>
            <label>
              Kontakt (optional)
              <select name="contact_id">
                <option value="">Kein Kontakt zugeordnet</option>
                {contacts.data?.items.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.first_name} {c.last_name} · {c.company}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Wert in Euro
              <input
                name="value"
                type="number"
                min={0}
                max={100000000}
                step="0.01"
                defaultValue={0}
                required
              />
            </label>
            <ErrorNote message={formError} />
            <div className="form-actions">
              <button
                className="button secondary"
                type="button"
                onClick={close}
              >
                Abbrechen
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? <Spinner /> : <Plus size={16} />} Anlegen
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
function Integrations({ base, write }: { base: string; write: Write }) {
  const [localError, setLocalError] = useState("");
  const [revision, setRevision] = useState(0);
  const { data, error, loading } = useData<{
    items: {
      name: string;
      status: string;
      reason: string;
      connect_available?: boolean;
      scopes?: string[];
    }[];
  }>(`${base}/integrations`, revision);
  return (
    <>
      <Heading
        eyebrow="BEWUSST VERBUNDEN"
        title="Deine Werkzeuge. Klare Berechtigungen."
        description="Hier siehst du, welche Anbieter tatsächlich verbunden sind und was noch fehlt."
      />
      <div className="info-note integration-intro">
        <ShieldCheck size={22} />
        <p>
          <strong>Keine Verbindung wird simuliert.</strong>Die lokale Anwendung
          funktioniert ohne API-Schlüssel. Offline-Vorschläge sind
          gekennzeichnet. Verbindungsstatus und verfügbare Anbieter werden vom
          Backend gemeldet.
        </p>
      </div>
      <ErrorNote message={localError || error} />
      {loading ? (
        <Spinner />
      ) : (
        <div className="integration-grid">
          {data?.items.map((integration, i) => (
            <section className="panel provider-card" key={integration.name}>
              <span className={`provider-logo provider-${i % 4}`}>
                {integration.name.toLowerCase().includes("linkedin") ? (
                  "in"
                ) : (
                  <Link2 size={25} />
                )}
              </span>
              <div className="section-title">
                <h2>{integration.name}</h2>
                <Badge
                  tone={
                    integration.status === "connected" ? "green" : "neutral"
                  }
                >
                  {(
                    {
                      connected: "Verbunden",
                      configured: "Konfiguriert",
                      available: "Verfügbar",
                      offline: "Offline-Modus",
                      not_configured: "Nicht konfiguriert",
                      missing_credentials: "Zugangsdaten fehlen",
                      disabled: "Deaktiviert",
                      expired: "Abgelaufen",
                    } as Record<string, string>
                  )[integration.status] || `Status: ${integration.status}`}
                </Badge>
              </div>
              <p>{integration.reason}</p>
              {integration.name === "LinkedIn" && (
                <div className="form-actions">
                  {integration.status === "connected" ? (
                    <button
                      className="button secondary"
                      onClick={async () => {
                        try {
                          await write("/integrations/linkedin/disconnect");
                          setRevision((v) => v + 1);
                        } catch (e) {
                          setLocalError((e as Error).message);
                        }
                      }}
                    >
                      Verbindung entfernen
                    </button>
                  ) : (
                    <button
                      className="button secondary"
                      disabled={!integration.connect_available}
                      title={
                        integration.connect_available
                          ? "Offiziellen OAuth-Dialog öffnen"
                          : "Operator muss OAuth-Zugang und Token-Verschlüsselung konfigurieren."
                      }
                      onClick={async () => {
                        try {
                          const result = await write<{
                            authorization_url: string;
                          }>("/integrations/linkedin/start");
                          window.location.assign(result.authorization_url);
                        } catch (e) {
                          setLocalError((e as Error).message);
                        }
                      }}
                    >
                      Offiziell mit LinkedIn verbinden
                    </button>
                  )}
                </div>
              )}

              <div className="provider-footer">
                <ShieldCheck size={14} /> Berechtigungen und Anbieterstatus
                werden serverseitig geprüft
              </div>
            </section>
          ))}
        </div>
      )}
      <IntegrationCredentials base={base} write={write} />
      <ProviderChecks write={write} />
      <section className="panel integration-doc">
        <h2>Bereit für den nächsten Schritt?</h2>
        <p>
          Die Voraussetzungen für echte Anbieter stehen in der
          Repository-Dokumentation. LinkedIn benötigt eine offizielle App und
          gewährte Publishing-Berechtigungen. Zugangsdaten gehören in sichere
          Umgebungseinstellungen.
        </p>
        <span className="doc-path">
          docs/LINKEDIN_INTEGRATION.md · docs/OPERATIONS.md
        </span>
      </section>
    </>
  );
}
function Audit({ base }: { base: string }) {
  const [page, setPage] = useState(1);
  const { data, error, loading } = useData<Page<Activity>>(
    `${base}/audit?page=${page}&limit=25`,
  );
  return (
    <>
      <Heading
        eyebrow="NACHVOLLZIEHBARKEIT"
        title="Ein Workspace mit Gedächtnis."
        description="Importe, Änderungen und Statuswechsel – mit Zeitpunkt und Kontext."
      />
      <ErrorNote message={error} />
      <section className="panel">
        {loading ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : data?.items.length ? (
          <>
            <div className="activity-list audit-list">
              {data.items.map((activity) => (
                <div className="activity-row" key={activity.id}>
                  <span className="activity-icon">
                    <ShieldCheck size={17} />
                  </span>
                  <div>
                    <p>{activity.description}</p>
                    <small>
                      {activity.kind} · {dateTime(activity.created_at)}
                    </small>
                  </div>
                  <Badge>Protokolliert</Badge>
                </div>
              ))}
            </div>
            <div className="pagination">
              <span>
                {data.total} Aktivitäten · Seite {page}
              </span>
              <div>
                <button
                  className="icon-button"
                  aria-label="Vorherige Seite"
                  disabled={page === 1}
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  className="icon-button"
                  aria-label="Nächste Seite"
                  disabled={page * 25 >= data.total}
                  onClick={() => setPage(page + 1)}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          </>
        ) : (
          <Empty
            icon={ShieldCheck}
            title="Noch keine Aktivitäten"
            description="Sobald du Kontakte importierst oder Inhalte bearbeitest, wird es hier sichtbar."
          />
        )}
      </section>
    </>
  );
}
function Discovery({
  write,
  notify,
  onChange,
}: {
  write: Write;
  notify: (s: string) => void;
  onChange: () => void;
}) {
  const [topic, setTopic] = useState(
    "Büros und Dienstleistungsunternehmen in Offenburg",
  );
  const [result, setResult] = useState<{
    id: string;
    status: string;
    results: {
      external_key: string;
      company: string;
      first_name: string;
      last_name: string;
      job_title: string;
      location: string;
      source: string;
      license: string;
      confidence: string;
      observed_at: string;
    }[];
    notice: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [imported, setImported] = useState(false);
  async function search(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResult(await write("/discovery/runs", { topic }));
      setImported(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function importResults() {
    if (!result) return;
    setBusy(true);
    try {
      const imported = await write<{ created: number }>(
        `/discovery/runs/${result.id}/import`,
      );
      setImported(true);
      onChange();
      notify(`${imported.created} synthetische Kontakte importiert.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="PASSENDE UNTERNEHMEN ENTDECKEN"
        title="Neue Möglichkeiten beginnen hier."
        description="Erprobe den Discovery-Ablauf mit transparenten Beispieldaten."
      />
      <div className="provider-notice">
        <Sparkles size={23} />
        <div>
          <strong>Synthetischer Beispielanbieter.</strong>
          <span>
            {" "}
            Kein Datenanbieter verbunden. Die Ergebnisse sind feste, fiktive
            Datensätze und keine recherchierten Treffer zu deiner Anfrage.
          </span>
        </div>
        <Badge tone="purple">Demo-Daten</Badge>
      </div>
      <section className="panel padded">
        <div className="panel-head">
          <div>
            <h2>Dein Recherche-Ziel</h2>
            <p>
              Ein echter Anbieter benötigt separat geprüfte Zugangsdaten und
              Nutzungsrechte.
            </p>
          </div>
          <Target size={22} />
        </div>
        <form onSubmit={search}>
          <label>
            Welche Unternehmen interessieren dich?
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              required
              maxLength={300}
              rows={3}
            />
          </label>
          <div className="form-actions">
            <button className="button primary" disabled={busy || !topic.trim()}>
              {busy ? <Spinner /> : <Search size={16} />} Beispielsuche starten
            </button>
          </div>
        </form>
        <ErrorNote message={error} />
      </section>
      {result && (
        <section className="panel post-list">
          <div className="panel-head">
            <div>
              <h2>{result.results.length} synthetische Beispiele</h2>
              <p>{result.notice}</p>
            </div>
            <button
              className="button primary"
              disabled={busy || imported}
              onClick={importResults}
            >
              {imported ? (
                <>
                  <Check size={16} /> Importiert
                </>
              ) : (
                <>
                  <Plus size={16} /> Beispiele importieren
                </>
              )}
            </button>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Fiktives Unternehmen</th>
                  <th>Fiktiver Kontakt</th>
                  <th>Standort</th>
                  <th>Herkunft</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((row) => (
                  <tr key={row.external_key}>
                    <td>
                      <strong>{row.company}</strong>
                    </td>
                    <td>
                      {row.first_name} {row.last_name}
                      <br />
                      <small>{row.job_title}</small>
                    </td>
                    <td>{row.location}</td>
                    <td>
                      <Badge tone="purple">Synthetisch</Badge>
                      <br />
                      <small>
                        {row.source} · {row.license}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
