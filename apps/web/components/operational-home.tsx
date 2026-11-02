"use client";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  FileText,
  Plus,
  Search,
  Users,
  Workflow,
} from "lucide-react";
import { useData } from "@/lib/use-data";
import { dateTime, money, number } from "@/lib/api";
import { Badge, Empty, ErrorNote, Heading, Spinner } from "./ui";

type Home = {
  counts: {
    contacts: number;
    companies: number;
    qualified: number;
    deals: number;
    pipeline_value: number;
    pending_approvals: number;
    scheduled_posts: number;
    open_tasks: number;
    active_campaigns: number;
  };
  recent_leads: {
    id: string;
    first_name: string;
    last_name: string;
    company: string;
    job_title: string;
    source: string;
    score: { value: number };
  }[];
  qualified_leads: { id: string; name: string; job_title: string }[];
  pending_outreach: {
    id: string;
    contact_id: string;
    subject: string;
    revision: number;
  }[];
  scheduled_posts: {
    id: string;
    caption: string;
    scheduled_at: string;
    publish_enabled: boolean;
  }[];
  tasks: {
    id: string;
    title: string;
    due_at: string | null;
    contact_id: string | null;
  }[];
  campaigns: {
    id: string;
    name: string;
    status: string;
    audience_count: number;
  }[];
  pipeline_changes: { id: string; description: string; created_at: string }[];
};
export function OperationalHome({
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
  const { data, error, loading } = useData<Home>(`${base}/home`, revision);
  const integrations = useData<{
    items: { name: string; status: string; reason: string }[];
  }>(`${base}/integrations`, revision);
  const c = data?.counts;
  const cards = [
    {
      label: "Kontakte",
      value: c?.contacts,
      icon: Users,
      path: "/contacts",
      color: "purple",
      sub: `${c?.qualified ?? 0} qualifiziert`,
    },
    {
      label: "Offene Aufgaben",
      value: c?.open_tasks,
      icon: CheckCircle2,
      path: "/tasks",
      color: "blue",
      sub: "Mit nächstem Schritt",
    },
    {
      label: "Ausstehende Freigaben",
      value: c?.pending_approvals,
      icon: FileText,
      path: "/outreach",
      color: "amber",
      sub: "Vorbereitet, noch nicht versendet",
    },
    {
      label: "Pipeline-Wert",
      value: c?.pipeline_value,
      icon: Workflow,
      path: "/pipeline",
      color: "green",
      sub: `${c?.deals ?? 0} offene Verkaufschancen`,
      currency: true,
    },
  ];
  const unavailable =
    integrations.data?.items.filter(
      (p) => !["connected", "configured"].includes(p.status),
    ) || [];
  return (
    <>
      <Heading
        eyebrow="ARBEITSÜBERSICHT"
        title={`Hallo ${name?.split(" ")[0] || "zusammen"}, auf gute Verbindungen.`}
        description="Kontakte, Freigaben und nächste Schritte in deinem Workspace."
      >
        <button className="button secondary" onClick={() => go("/discover")}>
          <Search size={16} /> Unternehmen finden
        </button>
        <button className="button primary" onClick={openImport}>
          <Plus size={16} /> Kontakte importieren
        </button>
      </Heading>
      <ErrorNote message={error} />
      <div className="stats-grid operational-kpis">
        {cards.map((card) => (
          <button
            className="stat-card"
            key={card.label}
            onClick={() => go(card.path)}
          >
            <div className="stat-top">
              <span>{card.label}</span>
              <span className={`stat-icon ${card.color}`}>
                <card.icon size={18} />
              </span>
            </div>
            <strong>
              {card.value === undefined
                ? "—"
                : card.currency
                  ? money(card.value)
                  : number(card.value)}
            </strong>
            <small>{card.sub}</small>
          </button>
        ))}
      </div>
      <div className="home-work-grid">
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Neue Kontakte</h2>
              <p>Zuletzt in diesem Workspace angelegt</p>
            </div>
            <button className="text-link" onClick={() => go("/contacts")}>
              Alle Kontakte <ArrowRight size={14} />
            </button>
          </div>
          {loading ? (
            <div className="loading-block">
              <Spinner />
            </div>
          ) : data?.recent_leads.length ? (
            <div className="home-rows">
              {data.recent_leads.map((lead) => (
                <button
                  className="home-row"
                  key={lead.id}
                  onClick={() =>
                    go(`/contacts?contact=${encodeURIComponent(lead.id)}`)
                  }
                >
                  <span className="contact-avatar avatar-1">
                    {lead.first_name[0]}
                    {lead.last_name[0]}
                  </span>
                  <span>
                    <strong>
                      {lead.first_name} {lead.last_name}
                    </strong>
                    <small>
                      {lead.company || "Unternehmen unbekannt"} ·{" "}
                      {lead.job_title || "Position unbekannt"}
                    </small>
                  </span>
                  <Badge tone="purple">{lead.score.value} Fit</Badge>
                </button>
              ))}
            </div>
          ) : (
            <Empty
              title="Noch keine Kontakte"
              description="Importiere eine CSV oder recherchiere deine erste Zielgruppe."
            >
              <button className="button secondary" onClick={openImport}>
                CSV importieren
              </button>
            </Empty>
          )}
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Anstehende Aufgaben</h2>
              <p>Offene Aufgaben, nach Fälligkeit sortiert</p>
            </div>
            <button className="text-link" onClick={() => go("/tasks")}>
              Aufgaben <ArrowRight size={14} />
            </button>
          </div>
          {data?.tasks.length ? (
            <div className="home-rows">
              {data.tasks.map((task) => (
                <button
                  className="home-row"
                  key={task.id}
                  onClick={() => go("/tasks")}
                >
                  <CheckCircle2 size={18} />
                  <span>
                    <strong>{task.title}</strong>
                    <small>
                      {task.due_at
                        ? dateTime(task.due_at)
                        : "Ohne Fälligkeitsdatum"}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="compact-empty">
              <CheckCircle2 size={24} />
              <p>Keine offenen Aufgaben.</p>
              <button className="text-link" onClick={() => go("/tasks")}>
                Nächsten Schritt anlegen
              </button>
            </div>
          )}
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Zur Freigabe vorbereitet</h2>
              <p>Nachrichten mit Betreff, noch ohne Versand</p>
            </div>
            <Badge>{c?.pending_approvals ?? 0}</Badge>
          </div>
          {data?.pending_outreach.length ? (
            <div className="home-rows">
              {data.pending_outreach.map((draft) => (
                <button
                  className="home-row"
                  key={draft.id}
                  onClick={() =>
                    go(`/outreach?draft=${encodeURIComponent(draft.id)}`)
                  }
                >
                  <FileText size={18} />
                  <span>
                    <strong>{draft.subject}</strong>
                    <small>
                      Revision {draft.revision} · Prüfung erforderlich
                    </small>
                  </span>
                  <ArrowRight size={15} />
                </button>
              ))}
            </div>
          ) : (
            <div className="compact-empty">
              <p>Keine vorbereiteten Nachrichten zur Prüfung.</p>
              <button className="text-link" onClick={() => go("/outreach")}>
                Outreach öffnen
              </button>
            </div>
          )}
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Geplante Beiträge</h2>
              <p>Termine und Veröffentlichungsfreigabe getrennt</p>
            </div>
            <button
              className="text-link"
              onClick={() => go("/social/calendar")}
            >
              Kalender <ArrowRight size={14} />
            </button>
          </div>
          {data?.scheduled_posts.length ? (
            <div className="home-rows">
              {data.scheduled_posts.map((post) => (
                <button
                  className="home-row"
                  key={post.id}
                  onClick={() =>
                    go(`/social/calendar?post=${encodeURIComponent(post.id)}`)
                  }
                >
                  <CalendarDays size={18} />
                  <span>
                    <strong>{post.caption.slice(0, 100)}</strong>
                    <small>
                      {dateTime(post.scheduled_at)} ·{" "}
                      {post.publish_enabled
                        ? "Veröffentlichung autorisiert"
                        : "Nur redaktionell geplant"}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="compact-empty">
              <p>Es sind noch keine Beiträge eingeplant.</p>
              <button
                className="text-link"
                onClick={() => go("/social/studio")}
              >
                Beitrag erstellen
              </button>
            </div>
          )}
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Aktive Kampagnen</h2>
              <p>Persistierte Zielgruppen und Status</p>
            </div>
            <Badge>{c?.active_campaigns ?? 0} aktiv</Badge>
          </div>
          {data?.campaigns.length ? (
            <div className="home-rows">
              {data.campaigns.map((campaign) => (
                <button
                  className="home-row"
                  key={campaign.id}
                  onClick={() =>
                    go(`/outreach?campaign=${encodeURIComponent(campaign.id)}`)
                  }
                >
                  <Users size={18} />
                  <span>
                    <strong>{campaign.name}</strong>
                    <small>{campaign.audience_count} Kontakte · aktiv</small>
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="compact-empty">
              <p>Noch keine aktive Kampagne.</p>
              <button className="text-link" onClick={() => go("/campaigns")}>
                Zielgruppe und Kampagne anlegen
              </button>
            </div>
          )}
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Pipeline-Verlauf</h2>
              <p>Tatsächlich protokollierte Änderungen</p>
            </div>
            <button className="text-link" onClick={() => go("/pipeline")}>
              Pipeline <ArrowRight size={14} />
            </button>
          </div>
          {data?.pipeline_changes.length ? (
            <div className="home-rows">
              {data.pipeline_changes.map((event) => (
                <div className="home-row" key={event.id}>
                  <Workflow size={17} />
                  <span>
                    <strong>{event.description}</strong>
                    <small>{dateTime(event.created_at)}</small>
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="compact-empty">
              <p>Noch keine Pipeline-Aktivität.</p>
            </div>
          )}
        </section>
      </div>
      {data?.qualified_leads.length ? (
        <section className="panel home-qualified">
          <div className="panel-head">
            <div>
              <h2>Qualifizierte Kontakte</h2>
              <p>Status von deinem Team vergeben, keine Kaufprognose</p>
            </div>
            <button className="text-link" onClick={() => go("/contacts")}>
              Kontakte öffnen
            </button>
          </div>
          <div className="qualified-strip">
            {data.qualified_leads.map((lead) => (
              <button
                className="qualified-item"
                key={lead.id}
                onClick={() =>
                  go(`/contacts?contact=${encodeURIComponent(lead.id)}`)
                }
              >
                <strong>{lead.name}</strong>
                <small>{lead.job_title || "Position unbekannt"}</small>
                <Badge tone="green">Qualifiziert</Badge>
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {unavailable.length > 0 && (
        <section className="panel home-provider-notice">
          <div>
            <h2>Anbieter einrichten</h2>
            <p>
              {unavailable.map((p) => p.name).join(", ")} sind noch nicht
              verbunden. Lokale Datenverwaltung und manuelle Entwürfe bleiben
              verfügbar.
            </p>
          </div>
          <button
            className="button secondary"
            onClick={() => go("/settings/integrations")}
          >
            Einrichtung prüfen <ArrowRight size={14} />
          </button>
        </section>
      )}
      <p className="data-note">
        <span className="status-dot" /> Alle Kennzahlen stammen aus diesem
        Workspace. Synthetische Quellen bleiben gekennzeichnet.
      </p>
    </>
  );
}
