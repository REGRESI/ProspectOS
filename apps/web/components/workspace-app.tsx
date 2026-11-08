"use client";
import { TopCandidates } from "./top-candidates";
import { OutreachSettingsPage, TodayView } from "./today-view";
import { FlowBuilderPage } from "./flow-builder";
import { InboxPage } from "./inbox";
import { StartPage } from "./start-page";
import { LettersPage } from "./letters-page";
import { SetupCheck } from "./setup-check";
import { AgentConsole } from "./agent-console";
import { ContentPlanner } from "./content-planner";
import { ICPBuilder } from "./icp-builder";
import { useEffect, useState, FormEvent } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PanelLeftClose, PanelLeftOpen, CheckCircle2, ChevronRight, ChevronsUpDown, LogOut, Menu, Plus, X, Sun, Moon } from "lucide-react";
import { Empty, Modal, Spinner, ErrorNote } from "./ui";
import { Social } from "./social-studio";
import { WorkspaceOnboarding, BillingSettings } from "./workspace-settings";
import { DiscoveryWorkbench, LeadDatabase, CompanyDirectory, CompanyProfile, ImportHistory, OutreachWorkbench } from "./journey-workspaces";
import { EngagementWorkspace } from "./social-tools";
import { IntelligenceConsole } from "./intelligence-console";
import { AssetLibrary, BrandProfiles, TaskNotes, Campaigns, Operations, OutreachDrafts } from "./growth-modules";
import { request, ApiError } from "@/lib/api";
import type { Session, Workspace } from "@/lib/api";
import { DEV_ONLY, Logo, demoSection, sectionFor, sections, titleFor } from "./workspace-nav";
import { WorkspacesAdmin } from "./workspaces-admin";
import { ContactsTable } from "./contacts-table";
import { DataQualityPage, EmailCampaignPage } from "./profile-quality";
import { InvitePage, TeamPage } from "./team-page";
import { WritingProfilePage } from "./writing-profile";
import { CampaignsPage, ResultsPage } from "./content-strategy";
import { TemplatesPage } from "./brand-templates";
import { Audiences, Companies, Contacts, ImportModal, Overview } from "./workspace-contacts";
import { Audit, Discovery, Integrations, Pipeline } from "./workspace-modules";


export default function WorkspaceApp() {
  const router = useRouter();
  const pathname = usePathname();
  const route = pathname === "/" ? "/today" : pathname;
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
  const isDemo = workspace?.kind === "demo";
  // After login always the production workspace; demo only via the Demo switch.
  const defaultWorkspace = (s: Session) =>
    s.workspaces.find((w) => w.kind === "production" && !w.archived) ||
    s.workspaces.find((w) => w.kind !== "demo" && !w.archived) ||
    s.workspaces[0] ||
    null;
  const reloadSession = async () => {
    const s = await request<Session>("/v1/me");
    setSession(s);
    setWorkspace((current) => s.workspaces.find((w) => w.id === current?.id) || defaultWorkspace(s));
  };
  const switchTo = (w: Workspace | null) => {
    if (!w) return;
    setImportOpen(false);
    try {
      sessionStorage.setItem("prospectos.workspace", w.id);
    } catch {}
    setWorkspace(w);
    refresh();
  };
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
                (w) =>
                  w.id === sessionStorage.getItem("prospectos.workspace") && !w.archived,
              ) || defaultWorkspace(s),
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
      try {
        sessionStorage.removeItem("prospectos.workspace");
      } catch {}
      setWorkspace(defaultWorkspace(s));
      router.replace("/today");
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
  if (route === "/einladung")
    return (
      <InvitePage
        csrf={session?.csrf_token}
        onJoined={async (id) => {
          try {
            sessionStorage.setItem("prospectos.workspace", id);
          } catch {}
          await reloadSession();
          router.push("/today");
        }}
      />
    );
  if (!session)
    return (
      <main className="login-page">
        <section className="login-card">
          <Logo />
          <h1>Anmelden</h1>
          <p className="muted">Deine Firmen, Kontakte und Beiträge für heute.</p>
          <form onSubmit={login} className="login-form">
            <label>
              E-Mail-Adresse
              <input
                name="email"
                type="email"
                defaultValue={authConfig?.demo_enabled ? "demo@prospectos.local" : ""}
                required
                autoComplete="username"
              />
            </label>
            <label>
              Passwort
              <input
                name="password"
                type="password"
                defaultValue={authConfig?.demo_enabled ? "ProspectDemo!2026" : ""}
                required
                autoComplete="current-password"
              />
            </label>
            {error && (
              <p role="alert" className="error-note">
                {error}
              </p>
            )}
            <button className="button primary login-submit" disabled={busy || !authConfig}>
              {busy ? <Spinner /> : authConfig?.demo_enabled ? "Demo-Workspace öffnen" : "Anmelden"}
            </button>
          </form>
          {authConfig?.demo_enabled && (
            <p className="login-note">
              Lokale Entwicklungsumgebung. Die Zugangsdaten sind vorausgefüllt.
            </p>
          )}
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
              switchTo(session.workspaces.find((w) => w.id === e.target.value) || null);
            }}
          >
            {session.workspaces
              .filter((w) => !w.archived && (w.kind !== "demo" || w.id === workspace?.id))
              .map((w) => (
                <option key={w.id} value={w.id}>
                  {w.kind === "demo" ? `${w.name} (nur Beispiel)` : w.name}
                </option>
              ))}
            <option value="__new">+ Workspace erstellen</option>
          </select>
          <ChevronsUpDown size={14} />
        </div>
        <nav aria-label="Hauptnavigation">
          <div className="nav-group">
            {sections.map((section) => {
              const current = sectionFor(route, isDemo)?.key === section.key;
              return (
                <button
                  key={section.key}
                  aria-label={section.label}
                  title={collapsed ? section.label : undefined}
                  aria-current={current ? "page" : undefined}
                  className={`nav-item ${current ? "active" : ""}`}
                  onClick={() => go(section.tabs[0].path)}
                >
                  <section.icon size={16} />
                  <span>{section.label}</span>
                </button>
              );
            })}
          </div>
          {isDemo && (
            <div className="nav-group nav-more">
              <p>Nur im Demo</p>
              {demoSection.tabs.map((tab) => (
                <button
                  key={tab.path}
                  aria-label={tab.label}
                  aria-current={route === tab.path ? "page" : undefined}
                  className={`nav-item ${route === tab.path ? "active" : ""}`}
                  onClick={() => go(tab.path)}
                >
                  <demoSection.icon size={16} />
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>
          )}
        </nav>
        <div className="sidebar-bottom">
          {session.workspaces.some((w) => w.kind === "demo") && (
            <button
              className={`demo-switch ${workspace?.kind === "demo" ? "on" : ""}`}
              role="switch"
              aria-checked={workspace?.kind === "demo"}
              data-testid="demo-switch"
              onClick={() =>
                switchTo(
                  workspace?.kind === "demo"
                    ? defaultWorkspace(session)
                    : session.workspaces.find((w) => w.kind === "demo") || null,
                )
              }
            >
              <span className="demo-switch-track" aria-hidden="true">
                <span />
              </span>
              <span>
                <strong>Demo ansehen</strong>
                <small>Nur Beispieldaten</small>
              </span>
            </button>
          )}
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
            <span className="desktop-only">{sectionFor(route, isDemo)?.label || "ProspectOS"}</span>
            {titleFor(route, isDemo) && titleFor(route, isDemo) !== sectionFor(route, isDemo)?.label && (
              <>
                <ChevronRight size={14} />
                <strong>{titleFor(route, isDemo)}</strong>
              </>
            )}
          </div>
          <div className="topbar-actions">
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
            <span className="top-avatar">
              {session.user.name?.slice(0, 1) || "D"}
            </span>
          </div>
        </header>
        <main className="main-content" key={workspace?.id}>
          {workspace?.kind === "demo" && (
            <p className="demo-banner" role="note" data-testid="demo-banner">
              <strong>Demo-Workspace.</strong> Nur Beispieldaten, keine echten Zugangsdaten,
              nichts geht nach außen.{" "}
              <button className="link-button" onClick={() => switchTo(defaultWorkspace(session))}>
                Zurück zu {defaultWorkspace(session)?.name || "deinem Workspace"}
              </button>
            </p>
          )}
          {workspace && sectionFor(route, isDemo) && (sectionFor(route, isDemo)?.tabs.length || 0) > 1 && (sectionFor(route, isDemo)?.key !== "demo" || isDemo) && (
            <nav className="section-tabs" aria-label="Unterseiten">
              {sectionFor(route, isDemo)?.tabs.map((tab) => (
                <button
                  key={tab.path}
                  aria-current={route === tab.path ? "page" : undefined}
                  onClick={() => go(tab.path)}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          )}
          {workspace && !isDemo && DEV_ONLY.includes(route) ? (
            <Empty
              title="Nur im Demo-Workspace"
              description="Diese Ansicht zeigt Entwicklungsbeispiele. Schalte unten links „Demo ansehen“ ein, um sie zu öffnen."
            />
          ) : workspace ? (
            <>
              {route === "/discover" && (
                <DiscoveryWorkbench
                  demo={isDemo}
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
                <ContactsTable
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
              {route === "/contacts/advanced" && (
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
              {route === "/today" && <TodayView base={base} write={write} onNavigate={go} />}
              {route === "/flows" && <FlowBuilderPage base={base} write={write} notify={notify} />}
              {route === "/inbox" && <InboxPage base={base} write={write} notify={notify} onNavigate={go} />}
              {route === "/start" && <StartPage base={base} write={write} notify={notify} onNavigate={go} />}
              {route === "/letters" && (
                <LettersPage base={base} write={write} notify={notify} csrf={session.csrf_token} />
              )}
              {route === "/settings/outreach" && <OutreachSettingsPage base={base} write={write} notify={notify} />}
              {route === "/agent" && (
                <AgentConsole base={base} write={write} onNavigate={go} />
              )}
              {route === "/content/plan" && (
                <ContentPlanner base={base} write={write} onNavigate={go} />
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
                <TeamPage base={base} write={write} notify={notify} myRole={workspace.role} />
              )}
              {route === "/contacts/quality" && <DataQualityPage base={base} write={write} notify={notify} />}
              {route === "/contacts/email" && <EmailCampaignPage base={base} />}
              {route === "/content/campaigns" && (
                <CampaignsPage base={base} write={write} notify={notify} onNavigate={go} />
              )}
              {route === "/content/results" && <ResultsPage base={base} write={write} notify={notify} />}
              {route === "/content/voice" && <WritingProfilePage base={base} write={write} notify={notify} />}
              {route === "/content/templates" && (
                <TemplatesPage base={base} csrf={session.csrf_token} notify={notify} />
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
              {route === "/settings/setup" && <SetupCheck base={base} onNavigate={go} />}
              {route === "/settings/workspaces" && (
                <WorkspacesAdmin
                  session={session}
                  active={workspace}
                  notify={notify}
                  onSessionChange={reloadSession}
                />
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
              {!sectionFor(route, true) && (
                <Empty
                  title="Diese Seite gibt es nicht"
                  description="Über die Navigation links kommst du zu allen Bereichen."
                >
                  <button className="button primary" onClick={() => go("/today")}>
                    Zu Heute
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
