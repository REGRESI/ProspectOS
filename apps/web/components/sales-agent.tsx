"use client";
import { FormEvent, useEffect, useState } from "react";
import {
  Bot,
  CheckCircle2,
  Clipboard,
  ExternalLink,
  FlaskConical,
  Hand,
  Link2,
  Quote,
  RefreshCw,
  Send,
  ShieldOff,
  Trash2,
  UserPlus,
} from "lucide-react";
import { dateTime, request } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Spinner } from "./ui";
import type { JourneyProps } from "./journey-types";

export type Fact = {
  id: string;
  field: string;
  value: string;
  source_url: string;
  source_kind: string;
  confidence: string;
  created_at: string;
};
type ResearchJob = {
  id: string;
  status: string;
  last_error: string | null;
  created_at: string;
  result: { url: string; title: string; text: string } | null;
};

const sourceLabels: Record<string, string> = {
  openstreetmap: "OpenStreetMap",
  website_research: "Website-Auszug",
  website_impressum: "Impressum (ausgelesen)",
  ai_profile: "KI-Profil (zitiert, ungeprüft)",
  northdata: "North Data",
  manual: "Manuell belegt",
  people_data_labs: "People Data Labs",
  linkedin_simulator: "Simulator",
};

export function CompanyEvidence(
  props: JourneyProps & { companyId: string; website: string | null },
) {
  const { base, write, notify, revision, companyId, website } = props;
  const [local, setLocal] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [excerpt, setExcerpt] = useState("");
  const facts = useData<{
    items: Fact[];
    research_jobs: ResearchJob[];
    notice: string;
  }>(`${base}/companies/${companyId}/facts`, revision + local);
  const research = facts.data?.research_jobs.find((j) => j.result);
  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    try {
      await action();
      setLocal((v) => v + 1);
      notify(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function addManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void run(async () => {
      await write(`/companies/${companyId}/facts`, {
        field: String(data.get("field")),
        value: String(data.get("value")),
        source_url: String(data.get("source_url")),
      });
      form.reset();
    }, "Belegte Angabe gespeichert.");
  }
  return (
    <section className="panel" data-testid="company-evidence">
      <div className="panel-head">
        <div>
          <h2>
            <Quote size={16} /> Belegte Unternehmensangaben
          </h2>
          <p>{facts.data?.notice}</p>
        </div>
        <Badge tone="purple">{facts.data?.items.length || 0}</Badge>
      </div>
      <div className="modal-body">
        <ErrorNote message={facts.error || error} />
        {facts.data?.items.length ? (
          <ul className="evidence-list">
            {facts.data.items.map((fact) => (
              <li key={fact.id}>
                <div>
                  <small>{fact.field}</small>
                  <p>{fact.value}</p>
                  <span className="evidence-meta">
                    <Badge tone={fact.source_kind === "website_research" ? "green" : "neutral"}>
                      {sourceLabels[fact.source_kind] || fact.source_kind}
                    </Badge>
                    <a href={fact.source_url} target="_blank" rel="noreferrer">
                      Quelle <ExternalLink size={12} />
                    </a>
                    <span className="muted">{dateTime(fact.created_at)}</span>
                  </span>
                </div>
                <button
                  className="icon-button"
                  aria-label={`Angabe ${fact.field} entfernen`}
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => write(`/companies/${companyId}/facts/${fact.id}`, undefined, "DELETE"),
                      "Angabe entfernt.",
                    )
                  }
                >
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            Noch keine belegten Angaben. Ohne Belege wird kein personalisierter Entwurf erstellt.
          </p>
        )}
        <details className="evidence-add">
          <summary>Angabe mit Quelle hinzufügen</summary>
          <form className="form-grid" onSubmit={addManual}>
            <label>
              Feld
              <input name="field" required maxLength={80} placeholder="z. B. Leistung" />
            </label>
            <label>
              Quelle (HTTPS)
              <input name="source_url" required type="url" pattern="https://.*" placeholder="https://…" />
            </label>
            <label className="span-2">
              Angabe
              <textarea name="value" required minLength={3} maxLength={1000} rows={2} />
            </label>
            <button className="button secondary small" disabled={busy}>
              Speichern
            </button>
          </form>
        </details>
        {website && (
          <div className="evidence-research">
            <button
              className="button secondary small"
              disabled={busy}
              onClick={() =>
                run(
                  () => write(`/companies/${companyId}/research`),
                  "Website-Recherche eingeplant.",
                )
              }
            >
              Website & Impressum recherchieren
            </button>
            <button
              className="button secondary small"
              disabled={busy || !research}
              title={
                research
                  ? "KI fasst die recherchierten Seiten mit Quellenangabe zusammen"
                  : "Zuerst die Website recherchieren"
              }
              onClick={() =>
                run(
                  () => write(`/companies/${companyId}/profile`),
                  "KI-Firmenprofil eingeplant. Nur zitierte Aussagen werden gespeichert.",
                )
              }
            >
              KI-Profil erstellen
            </button>
            {facts.data?.research_jobs.map((job) => (
              <small key={job.id} className="muted">
                Recherche {dateTime(job.created_at)}: {job.status}
                {job.last_error ? ` (${job.last_error})` : ""}
              </small>
            ))}
            {research?.result && (
              <div className="research-excerpt">
                <p className="small">
                  <strong>{research.result.title || research.result.url}</strong> – nicht
                  vertrauenswürdiger Quelltext. Einen wörtlichen Auszug als Beleg übernehmen:
                </p>
                <blockquote>{research.result.text.slice(0, 1200)}</blockquote>
                <textarea
                  aria-label="Wörtlicher Auszug"
                  value={excerpt}
                  onChange={(e) => setExcerpt(e.target.value)}
                  rows={2}
                  maxLength={1000}
                />
                <button
                  className="button secondary small"
                  disabled={busy || excerpt.trim().length < 3}
                  onClick={() =>
                    run(async () => {
                      await write(`/companies/${companyId}/facts`, {
                        field: "Website-Auszug",
                        value: excerpt,
                        research_job_id: research.id,
                      });
                      setExcerpt("");
                    }, "Auszug als Beleg übernommen.")
                  }
                >
                  Auszug übernehmen
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

type Action = {
  id: string;
  contact_id: string;
  channel: "simulator" | "manual";
  action: "connection_request" | "message";
  state: string;
  content: string;
  simulated: boolean;
  history: { at: string; state: string; by: string; note: string }[];
  created_at: string;
};
type ProgressRow = {
  contact_id: string;
  name: string;
  simulator_account: boolean;
  linkedin_url: string | null;
  suppressed: boolean;
  connection: string;
  replied: boolean;
  completed_steps: number[];
  next_step: number | null;
  next_due_at: string | null;
  next_draft: { draft_id: string; state: string; approved: boolean } | null;
  stopped: boolean;
  actions: Action[];
};
type Capabilities = {
  channels: Record<
    "simulator" | "manual" | "official",
    { available: boolean; reason: string | null; scope: string | null }
  >;
  limits: Record<string, number>;
  usage: Record<string, number>;
  rules: string[];
};
type Handoff = {
  profile_url: string | null;
  text: string;
  steps: string[];
  missing_profile_url: boolean;
};

const connectionLabels: Record<string, string> = {
  none: "Nicht verbunden",
  pending: "Anfrage offen",
  handed_off: "Übergeben",
  sent: "Gesendet (manuell)",
  accepted: "Verbunden",
  declined: "Abgelehnt",
  no_response: "Keine Reaktion",
};
const stateTone = (state: string) =>
  ["accepted", "replied", "delivered", "sent"].includes(state)
    ? "green"
    : ["declined", "no_response", "cancelled"].includes(state)
      ? "red"
      : "neutral";

export function CampaignAgent(
  props: JourneyProps & { campaignId: string; onRefresh: () => void },
) {
  const { base, write, notify, revision, campaignId, onRefresh } = props;
  const [local, setLocal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [step, setStep] = useState(0);
  const [handoff, setHandoff] = useState<(Handoff & { id: string }) | null>(null);
  const caps = useData<Capabilities>(`${base}/linkedin/capabilities`, revision + local);
  const progress = useData<{
    steps: { position: number; delay_days: number }[];
    contacts: ProgressRow[];
    notice: string;
  }>(`${base}/campaigns/${campaignId}/linkedin`, revision + local);
  const pending = progress.data?.contacts.some((c) =>
    c.actions.some((a) => a.simulated && ["pending", "delivered"].includes(a.state) && !a.history.some((h) => h.by === "simulator")),
  );
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => setLocal((v) => v + 1), 5000);
    return () => window.clearInterval(timer);
  }, [pending]);
  async function run<T>(
    action: () => Promise<T>,
    message: (r: T) => string,
    reloadCampaign = true,
  ) {
    setBusy(true);
    setError("");
    try {
      const result = await action();
      setLocal((v) => v + 1);
      // Reloading the parent remounts this panel; skip it when only local state changes.
      if (reloadCampaign) onRefresh();
      notify(message(result));
      return result;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const act = (row: ProgressRow, action: "connection_request" | "message", channel: "simulator" | "manual") =>
    run(
      () =>
        write<Action & { handoff: Handoff | null }>("/linkedin/actions", {
          contact_id: row.contact_id,
          campaign_id: campaignId,
          channel,
          action,
          draft_id: action === "message" ? row.next_draft?.draft_id : undefined,
        }),
      (r) => {
        if (r.handoff) setHandoff({ ...r.handoff, id: r.id });
        return r.simulated
          ? "Im Simulator ausgeführt – nichts wurde an LinkedIn gesendet."
          : "Manuelle Übergabe vorbereitet. Bitte in LinkedIn selbst handeln.";
      },
      channel === "simulator",
    );
  const showHandoff = (row: ProgressRow, open: Action) =>
    setHandoff({
      id: open.id,
      profile_url: row.linkedin_url,
      text: open.content,
      missing_profile_url: !row.linkedin_url,
      steps: [
        "LinkedIn selbst im Browser öffnen und das Profil prüfen.",
        open.content
          ? "Text kopieren und selbst senden (nicht automatisiert)."
          : "Kontaktanfrage ohne Notiz selbst senden.",
        "Ergebnis hier bestätigen.",
      ],
    });
  const outcome = (id: string, value: string) =>
    run(
      () => write(`/linkedin/actions/${id}/outcome`, { outcome: value }),
      () => "Ergebnis als Selbstauskunft gespeichert.",
    );
  const official = caps.data?.channels.official;
  return (
    <section className="panel campaign-agent" data-testid="campaign-agent">
      <div className="panel-head">
        <div>
          <h2>
            <Bot size={16} /> Sales Agent · Personalisierung & LinkedIn
          </h2>
          <p>{progress.data?.notice}</p>
        </div>
        <button className="button ghost small" onClick={() => setLocal((v) => v + 1)} aria-label="Aktualisieren">
          <RefreshCw size={14} />
        </button>
      </div>
      <div className="modal-body">
        <ErrorNote message={error || progress.error || caps.error} />
        <div className="agent-toolbar">
          <label>
            Sequenzschritt
            <select value={step} onChange={(e) => setStep(Number(e.target.value))}>
              {(progress.data?.steps.length ? progress.data.steps : [{ position: 0, delay_days: 0 }]).map((s) => (
                <option key={s.position} value={s.position}>
                  Schritt {s.position + 1}
                  {s.delay_days ? ` · +${s.delay_days} Tage` : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            className="button secondary small"
            disabled={busy}
            onClick={() =>
              run(
                () =>
                  write<{ created: number; no_evidence: number; duplicates: number }>(
                    `/campaigns/${campaignId}/personalize`,
                    { mode: "evidence", step_position: step },
                  ),
                (r) =>
                  `${r.created} belegte Entwürfe · ${r.no_evidence} ohne Belege übersprungen · ${r.duplicates} vorhanden`,
              )
            }
          >
            <Quote size={14} /> Mit Belegen personalisieren
          </button>
          <button
            className="button secondary small"
            disabled={busy}
            onClick={() =>
              run(
                () =>
                  write<{ queued: number; no_evidence: number }>(`/campaigns/${campaignId}/personalize`, {
                    mode: "ai",
                    step_position: step,
                  }),
                (r) => `${r.queued} KI-Entwürfe eingeplant · ${r.no_evidence} ohne Belege übersprungen`,
              )
            }
          >
            <Bot size={14} /> KI-Vorschläge (zitiert)
          </button>
          {caps.data?.channels.simulator.available && (
            <button
              className="button ghost small"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  await write("/linkedin/simulator/seed");
                  const accounts = await request<{ items: { contact_id: string }[] }>(
                    `${base}/linkedin/simulator/accounts`,
                  );
                  return write<{ enrolled: number }>("/leads/bulk", {
                    contact_ids: accounts.items.map((a) => a.contact_id),
                    campaign_id: campaignId,
                  });
                }, (r) => `${r.enrolled} synthetische Simulator-Konten hinzugefügt`)
              }
            >
              <FlaskConical size={14} /> Simulator-Konten hinzufügen
            </button>
          )}
        </div>
        {caps.data && (
          <div className="channel-strip">
            <span className={`channel ${caps.data.channels.simulator.available ? "on" : "off"}`}>
              <FlaskConical size={13} /> Simulator
            </span>
            <span className="channel on">
              <Hand size={13} /> Manuelle Übergabe
            </span>
            <span className="channel off" title={official?.reason || ""}>
              <ShieldOff size={13} /> Offizielle API: nicht verfügbar
            </span>
            <span className="muted small">
              Heute {caps.data.usage.connection_requests_last_24h}/
              {caps.data.limits.connection_requests_per_day} Anfragen ·{" "}
              {caps.data.usage.messages_last_24h}/{caps.data.limits.messages_per_day} Nachrichten
            </span>
          </div>
        )}
        {progress.loading && !progress.data ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : progress.data?.contacts.length ? (
          <div className="table-scroll">
            <table className="agent-table">
              <thead>
                <tr>
                  <th>Kontakt</th>
                  <th>Verbindung</th>
                  <th>Sequenz</th>
                  <th>Nächste Aktion</th>
                </tr>
              </thead>
              <tbody>
                {progress.data.contacts.map((row) => {
                  const channel = row.simulator_account ? "simulator" : "manual";
                  const open = row.actions.find((a) => a.channel === "manual" && ["handed_off", "sent"].includes(a.state));
                  return (
                    <tr key={row.contact_id} data-testid={`agent-row-${row.name}`}>
                      <td>
                        <strong>{row.name}</strong>
                        <small className="journey-cell-sub">
                          {row.simulator_account ? (
                            <Badge tone="purple">Simulator · synthetisch</Badge>
                          ) : (
                            "Echter Kontakt · nur manuell"
                          )}
                        </small>
                      </td>
                      <td>
                        <Badge tone={stateTone(row.connection)}>
                          {connectionLabels[row.connection] || row.connection}
                        </Badge>
                        {row.replied && (
                          <Badge tone="green">
                            <CheckCircle2 size={12} /> Antwort
                          </Badge>
                        )}
                      </td>
                      <td>
                        {row.completed_steps.length
                          ? `Erledigt: ${row.completed_steps.map((p) => p + 1).join(", ")}`
                          : "Noch keine Nachricht"}
                        {row.next_due_at && !row.stopped && (
                          <small className="journey-cell-sub">
                            Schritt {(row.next_step ?? 0) + 1} fällig {dateTime(row.next_due_at)}
                          </small>
                        )}
                      </td>
                      <td className="agent-actions">
                        {row.stopped ? (
                          <span className="muted small">
                            {row.suppressed ? "Gesperrt – gestoppt" : "Beantwortet – Sequenz gestoppt"}
                          </span>
                        ) : open ? (
                          <span className="outcome-buttons">
                            <button
                              className="button ghost small"
                              onClick={() => showHandoff(row, open)}
                            >
                              <Hand size={13} /> Übergabe anzeigen
                            </button>
                            {(open.state === "handed_off" ? ["sent", "not_sent"] : []).concat(
                              open.action === "connection_request" ? ["accepted", "declined"] : ["replied"],
                            ).map((value) => (
                              <button
                                key={value}
                                className="button ghost small"
                                disabled={busy}
                                onClick={() => outcome(open.id, value)}
                              >
                                {outcomeLabels[value]}
                              </button>
                            ))}
                          </span>
                        ) : row.connection === "none" ? (
                          <button
                            className="button secondary small"
                            disabled={busy}
                            onClick={() => act(row, "connection_request", channel)}
                          >
                            <UserPlus size={14} />{" "}
                            {channel === "simulator" ? "Anfrage simulieren" : "Anfrage manuell übergeben"}
                          </button>
                        ) : row.connection === "accepted" && row.next_step !== null ? (
                          row.next_draft?.approved ? (
                            <button
                              className="button primary small"
                              disabled={busy}
                              onClick={() => act(row, "message", channel)}
                            >
                              <Send size={14} />{" "}
                              {channel === "simulator" ? "Nachricht simulieren" : "Nachricht übergeben"}
                            </button>
                          ) : (
                            <span className="muted small">
                              {row.next_draft
                                ? "Entwurf für nächsten Schritt freigeben"
                                : "Entwurf für nächsten Schritt erstellen"}
                            </span>
                          )
                        ) : (
                          <span className="muted small">
                            {row.connection === "pending"
                              ? "Warte auf simulierte Reaktion…"
                              : row.connection === "accepted" && !progress.data?.steps.length
                                ? "Zuerst Sequenzschritte anlegen"
                                : row.connection === "accepted"
                                  ? "Alle Schritte erledigt"
                                  : "Keine weitere Anfrage (Empfänger respektieren)"}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">Noch keine Kontakte in dieser Kampagne.</p>
        )}
        {caps.data && (
          <ul className="agent-rules small muted">
            {caps.data.rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        )}
      </div>
      {handoff && (
        <div className="handoff-card" role="dialog" aria-label="Manuelle LinkedIn-Übergabe">
          <h3>
            <Hand size={15} /> Manuelle Übergabe
          </h3>
          <ol>
            {handoff.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          {handoff.profile_url ? (
            <a className="button secondary small" href={handoff.profile_url} target="_blank" rel="noreferrer">
              <Link2 size={14} /> Profil öffnen
            </a>
          ) : (
            <p className="info-note small">Keine Profil-URL gespeichert – Person in LinkedIn selbst suchen.</p>
          )}
          {handoff.text && (
            <>
              <blockquote>{handoff.text}</blockquote>
              <button
                className="button ghost small"
                onClick={() => {
                  void navigator.clipboard?.writeText(handoff.text);
                  notify("Text kopiert.");
                }}
              >
                <Clipboard size={14} /> Text kopieren
              </button>
            </>
          )}
          <button className="button primary small" onClick={() => setHandoff(null)}>
            Verstanden
          </button>
        </div>
      )}
    </section>
  );
}

const outcomeLabels: Record<string, string> = {
  sent: "Gesendet",
  not_sent: "Nicht gesendet",
  accepted: "Angenommen",
  declined: "Abgelehnt",
  replied: "Antwort erhalten",
};
