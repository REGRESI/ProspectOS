"use client";
import { TopCandidates } from "./top-candidates";
import { TodayView } from "./today-view";
import { AgentConsole } from "./agent-console";
import { ContentPlanner } from "./content-planner";
import { ICPBuilder } from "./icp-builder";
import { useEffect, useState, FormEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ArrowRight, PanelLeftClose, PanelLeftOpen, CheckCircle2, ChevronRight, ChevronsUpDown, CircleHelp, LogOut, Menu, Plus, ShieldCheck, Sparkles, X, Sun, Moon } from "lucide-react";
import { Badge, Empty, Modal, Spinner, ErrorNote } from "./ui";
import { Social } from "./social-studio";
import { WorkspaceOnboarding, TeamSettings, BillingSettings } from "./workspace-settings";
import { DiscoveryWorkbench, LeadDatabase, CompanyDirectory, CompanyProfile, ImportHistory, OutreachWorkbench } from "./journey-workspaces";
import { EngagementWorkspace } from "./social-tools";
import { IntelligenceConsole } from "./intelligence-console";
import { AssetLibrary, BrandProfiles, TaskNotes, Campaigns, Operations, OutreachDrafts } from "./growth-modules";
import { request, ApiError } from "@/lib/api";
import type { Session, Workspace } from "@/lib/api";
import { Logo, navigation, titles } from "./workspace-nav";
import { Audiences, Companies, Contacts, ImportModal, Overview } from "./workspace-contacts";
import { Audit, Discovery, Integrations, Pipeline } from "./workspace-modules";


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
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "light";
    try {
      const saved = localStorage.getItem("prospectos.theme");
      if (saved === "light" || saved === "dark") return saved;
    } catch {
      /* storage unavailable: fall back to the system preference */
    }
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
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
    try {
      localStorage.setItem("prospectos.theme", theme);
    } catch {
      /* per-browser convenience only */
    }
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
              {route === "/today" && <TodayView base={base} write={write} />}
              {route === "/agent" && (
                <AgentConsole base={base} write={write} onNavigate={go} />
              )}
              {route === "/content/plan" && (
                <ContentPlanner base={base} write={write} />
              )}
              {route === "/leads/top" && (
                <TopCandidates base={base} write={write} onNavigate={go} />
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
