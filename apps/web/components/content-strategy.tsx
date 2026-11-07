"use client";
import { FormEvent, useState } from "react";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Heading, Modal } from "./ui";
import { SkeletonTable } from "./table";

type Write = <T>(path: string, body?: unknown, method?: string) => Promise<T>;
export type Option = { key: string; label: string; brief?: string };
export type Strategy = {
  goals: Option[];
  audiences: Option[];
  approaches: Option[];
  pillars: string[];
  insights: Insights;
  due_metrics: Due[];
};
type Group = { name: string; posts: number; impressions: number; comments: number; profile_visits: number; inquiries: number; score: number };
type Insights = { measured_posts: number; pillars: Group[]; approaches: Group[]; goals: Group[]; hint: string };
export type Due = { id: string; caption: string; published_at: string; pillar: string | null; approach: string | null };
type Metrics = { impressions: number; comments: number; profile_visits: number; inquiries: number } | null;
type CampaignPost = {
  id: string;
  caption: string;
  version: number;
  alt_text: string;
  asset_ids: string[];
  state: string;
  placeholder: boolean;
  slot: number | null;
  planned_for: string | null;
  pillar: string | null;
  approach_label: string;
  goal_label: string;
  topic: string | null;
  metrics: Metrics;
};
type Campaign = {
  id: string;
  name: string;
  goal: string;
  goal_label: string;
  audience: string;
  audience_label: string;
  description: string;
  start_date: string;
  end_date: string;
  posts: CampaignPost[];
};

export const POST_STATE: Record<string, string> = {
  draft: "Entwurf",
  needs_review: "Zur Prüfung",
  approved: "Freigegeben",
  scheduled: "Geplant",
  published: "Veröffentlicht",
  published_manually: "Veröffentlicht",
  archived: "Archiviert",
};

export function day(value: string | null) {
  if (!value) return "";
  const d = new Date(value.length === 10 ? value + "T12:00:00" : value);
  return d.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
}

export const GOALS: Option[] = [
  { key: "reach", label: "Reichweite" },
  { key: "trust", label: "Vertrauen aufbauen" },
  { key: "leads", label: "Anfragen gewinnen" },
  { key: "partners", label: "Partner gewinnen" },
  { key: "hiring", label: "Mitarbeiter gewinnen" },
];
export const AUDIENCES: Option[] = [
  { key: "ortenau_ceo", label: "Geschäftsführer Ortenau" },
  { key: "founders_cleaning", label: "Gründer und Reinigungsfirmen" },
  { key: "ai_entrepreneurs", label: "Unternehmer und KI-Interessierte" },
];
export const PILLARS = [
  "Transparenz in der Reinigungsbranche",
  "Bauen mit KI",
  "Unternehmeralltag",
  "CleanStar-Einblicke",
];

/** Goal, audience and pillar: chosen before every post and every plan. */
export function StrategyFields({
  strategy,
  defaults = {},
  pillarRequired = false,
}: {
  strategy: Strategy | null;
  defaults?: { goal?: string; audience?: string; pillar?: string };
  pillarRequired?: boolean;
}) {
  return (
    <>
      <label>
        Ziel
        <select name="goal" aria-label="Ziel" defaultValue={defaults.goal || "trust"} required>
          {(strategy?.goals || GOALS).map((g) => (
            <option key={g.key} value={g.key}>
              {g.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Zielgruppe
        <select name="audience_key" aria-label="Zielgruppe" defaultValue={defaults.audience || "ortenau_ceo"} required>
          {(strategy?.audiences || AUDIENCES).map((a) => (
            <option key={a.key} value={a.key}>
              {a.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Themensäule
        <input name="pillar" aria-label="Themensäule" list="pillar-options" defaultValue={defaults.pillar || ""} required={pillarRequired} maxLength={120} />
        <datalist id="pillar-options">
          {(strategy?.pillars || PILLARS).map((p) => (
            <option key={p} value={p} />
          ))}
        </datalist>
      </label>
    </>
  );
}

/** Numbers 48 hours after posting, entered by hand (LinkedIn is never read). */
export function MetricsForm({
  write,
  postId,
  initial,
  onSaved,
}: {
  write: Write;
  postId: string;
  initial?: Metrics;
  onSaved: () => void;
}) {
  const [error, setError] = useState("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    const n = (k: string) => Number(f.get(k) || 0);
    try {
      await write(`/social/posts/${postId}/metrics`, {
        impressions: n("impressions"),
        comments: n("comments"),
        profile_visits: n("profile_visits"),
        inquiries: n("inquiries"),
      }, "PUT");
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <form className="metrics-form" onSubmit={save} data-testid={`metrics-form-${postId}`}>
      {(
        [
          ["impressions", "Impressionen"],
          ["comments", "Kommentare"],
          ["profile_visits", "Profilbesuche"],
          ["inquiries", "Anfragen"],
        ] as const
      ).map(([key, label]) => (
        <label key={key}>
          {label}
          <input name={key} type="number" min={0} inputMode="numeric" defaultValue={initial?.[key] ?? ""} required />
        </label>
      ))}
      <button className="button primary small">Speichern</button>
      <ErrorNote message={error} />
    </form>
  );
}

export function CampaignsPage({
  base,
  write,
  notify,
  onNavigate,
}: {
  base: string;
  write: Write;
  notify: (m: string) => void;
  onNavigate: (path: string) => void;
}) {
  const [revision, setRevision] = useState(0);
  const { data, error, loading } = useData<{ items: Campaign[] }>(`${base}/content/campaigns`, revision);
  const strategy = useData<Strategy>(`${base}/content/strategy`).data;
  const [creating, setCreating] = useState(false);
  const [measuring, setMeasuring] = useState<string | null>(null);
  const [editing, setEditing] = useState<CampaignPost | null>(null);
  const [localError, setLocalError] = useState("");
  const reload = () => setRevision((v) => v + 1);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    try {
      const c = await write<Campaign>("/content/campaigns", {
        name: f.get("name"),
        goal: f.get("goal"),
        audience: f.get("audience_key"),
        description: f.get("description") || "",
        start_date: f.get("start_date"),
        end_date: f.get("end_date"),
      });
      const count = Number(f.get("count") || 0);
      if (count > 0) await write(`/content/campaigns/${c.id}/slots`, { count, pillar: f.get("pillar") || "" });
      setCreating(false);
      notify("Kampagne angelegt.");
      reload();
    } catch (e) {
      setLocalError((e as Error).message);
    }
  }
  return (
    <>
      <Heading title="Kampagnen" description="Beitragsserien mit Start, Ende und Ziel. Jeder Beitrag hat einen Termin.">
        <button className="button primary" onClick={() => setCreating(true)}>
          Neue Kampagne
        </button>
      </Heading>
      <ErrorNote message={error || localError} />
      {loading && !data ? (
        <SkeletonTable rows={4} cols={4} />
      ) : !data?.items.length ? (
        <p className="empty-line">Noch keine Kampagne. Leg eine Serie mit Start, Ende und Ziel an.</p>
      ) : (
        data.items.map((c) => (
          <section className="today-section" key={c.id} data-testid={`campaign-${c.id}`}>
            <div className="section-head">
              <div>
                <h2 className="title-lg">{c.name}</h2>
                <p className="muted">
                  {day(c.start_date)} bis {day(c.end_date)} · Ziel: {c.goal_label} · {c.audience_label} · {c.posts.length} Beiträge
                </p>
              </div>
              <button
                className="button secondary small"
                onClick={async () => {
                  await write(`/content/campaigns/${c.id}/slots`, { count: 1 });
                  reload();
                }}
              >
                Termin hinzufügen
              </button>
            </div>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Termin</th>
                    <th>Beitrag</th>
                    <th className="hide-sm">Säule</th>
                    <th>Status</th>
                    <th className="hide-sm">Ergebnis</th>
                  </tr>
                </thead>
                <tbody>
                  {c.posts.map((p) => (
                    <tr key={p.id}>
                      <td className="nowrap">{day(p.planned_for)}</td>
                      <td>
                        <button className="link-button clamp-1" onClick={() => setEditing(p)}>
                          {p.placeholder ? <span className="muted">Teil {p.slot}: Text folgt</span> : p.caption.slice(0, 90)}
                        </button>
                        {p.approach_label && <small className="muted block">{p.approach_label}</small>}
                      </td>
                      <td className="hide-sm">{p.pillar || <span className="muted">offen</span>}</td>
                      <td>
                        <Badge tone={p.state.startsWith("published") ? "green" : p.placeholder ? "neutral" : "amber"}>
                          {p.placeholder ? "Text fehlt" : POST_STATE[p.state] || p.state}
                        </Badge>
                      </td>
                      <td className="hide-sm">
                        {p.metrics ? (
                          <small>
                            {p.metrics.impressions} Impr. · {p.metrics.comments} Komm. · {p.metrics.inquiries} Anfr.
                          </small>
                        ) : p.state.startsWith("published") ? (
                          <button className="button ghost small" onClick={() => setMeasuring(p.id)}>
                            Zahlen eintragen
                          </button>
                        ) : (
                          <span className="muted">noch nicht</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ))
      )}
      {editing && (
        <Modal title={`Teil ${editing.slot ?? ""} bearbeiten`} onClose={() => setEditing(null)} wide>
          <form
            className="modal-form"
            onSubmit={async (e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              try {
                await write(
                  `/social/posts/${editing.id}`,
                  {
                    caption: f.get("caption"),
                    alt_text: editing.alt_text || "",
                    asset_ids: editing.asset_ids || [],
                    version: editing.version,
                    topic: f.get("topic") || null,
                    planned_for: f.get("planned_for") || null,
                  },
                  "PATCH",
                );
                setEditing(null);
                notify("Beitrag gespeichert.");
                reload();
              } catch (err) {
                setLocalError((err as Error).message);
              }
            }}
          >
            <label>
              Thema
              <input name="topic" defaultValue={editing.topic || ""} maxLength={300} />
            </label>
            <label>
              Termin
              <input name="planned_for" type="date" defaultValue={editing.planned_for || ""} />
            </label>
            <label>
              Text
              <textarea
                name="caption"
                rows={12}
                required
                maxLength={3000}
                defaultValue={editing.placeholder ? "" : editing.caption}
                placeholder="Text hier einfügen"
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="button ghost" onClick={() => onNavigate("/social/studio")}>
                Im Editor öffnen
              </button>
              <button type="button" className="button secondary" onClick={() => setEditing(null)}>
                Abbrechen
              </button>
              <button className="button primary">Speichern</button>
            </div>
          </form>
        </Modal>
      )}
      {measuring && (
        <Modal title="Zahlen nach 48 Stunden" onClose={() => setMeasuring(null)}>
          <div className="modal-body">
            <MetricsForm
              write={write}
              postId={measuring}
              onSaved={() => {
                setMeasuring(null);
                notify("Zahlen gespeichert.");
                reload();
              }}
            />
          </div>
        </Modal>
      )}
      {creating && (
        <Modal title="Neue Kampagne" onClose={() => setCreating(false)} wide>
          <form className="modal-form form-grid" onSubmit={create}>
            <label className="span-2">
              Name
              <input name="name" required minLength={3} maxLength={160} placeholder="z. B. Die neue CleanStar-Website" />
            </label>
            <StrategyFields strategy={strategy} defaults={{ goal: "leads" }} />
            <label>
              Start
              <input name="start_date" type="date" required />
            </label>
            <label>
              Ende
              <input name="end_date" type="date" required />
            </label>
            <label>
              Anzahl Beiträge (Termine)
              <input name="count" type="number" min={0} max={30} defaultValue={7} />
            </label>
            <label className="span-2">
              Worum geht es (optional)
              <textarea name="description" rows={2} maxLength={1000} />
            </label>
            <div className="modal-actions span-2">
              <button type="button" className="button secondary" onClick={() => setCreating(false)}>
                Abbrechen
              </button>
              <button className="button primary">Anlegen</button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

export function ResultsPage({ base, write, notify }: { base: string; write: Write; notify: (m: string) => void }) {
  const [revision, setRevision] = useState(0);
  const { data, error, loading } = useData<Insights & { due: Due[] }>(`${base}/content/insights`, revision);
  const reload = () => setRevision((v) => v + 1);
  const table = (title: string, rows: Group[]) => (
    <section className="today-section">
      <h2>{title}</h2>
      {rows.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th className="align-right">Beiträge</th>
                <th className="align-right">Ø Impressionen</th>
                <th className="align-right hide-sm">Ø Kommentare</th>
                <th className="align-right hide-sm">Ø Profilbesuche</th>
                <th className="align-right">Ø Anfragen</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.name}>
                  <td>
                    {r.name} {i === 0 && rows.length > 1 && <Badge tone="green">am besten</Badge>}
                  </td>
                  <td className="align-right num">{r.posts}</td>
                  <td className="align-right num">{r.impressions}</td>
                  <td className="align-right num hide-sm">{r.comments}</td>
                  <td className="align-right num hide-sm">{r.profile_visits}</td>
                  <td className="align-right num">{r.inquiries}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="empty-line">Noch keine Zahlen.</p>
      )}
    </section>
  );
  return (
    <>
      <Heading
        title="Ergebnisse"
        description="Welche Säulen und Ansätze funktionieren. Die Zahlen trägst du 48 Stunden nach dem Posten von Hand ein."
      />
      <ErrorNote message={error} />
      {data?.hint && <p className="notice-line" data-testid="insight-hint">{data.hint} Neue Vorschläge berücksichtigen das.</p>}
      {loading && !data ? (
        <SkeletonTable rows={4} cols={5} />
      ) : (
        <>
          {!!data?.due.length && (
            <section className="today-section" data-testid="metrics-due">
              <h2>Zahlen fällig</h2>
              <ul className="row-list">
                {data.due.map((d) => (
                  <li key={d.id} className="stack">
                    <span className="row-main">
                      <span className="clamp-1">{d.caption}</span>
                      <small className="muted block">Veröffentlicht {day(d.published_at)}</small>
                    </span>
                    <MetricsForm
                      write={write}
                      postId={d.id}
                      onSaved={() => {
                        notify("Zahlen gespeichert.");
                        reload();
                      }}
                    />
                  </li>
                ))}
              </ul>
            </section>
          )}
          {table("Nach Säule", data?.pillars || [])}
          {table("Nach Ansatz", data?.approaches || [])}
          {table("Nach Ziel", data?.goals || [])}
        </>
      )}
    </>
  );
}
