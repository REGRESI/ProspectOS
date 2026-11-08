"use client";
import { StartBanner } from "./start-page";
import { FlowTasksSection } from "./flow-builder";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Copy,
  ExternalLink,
  RefreshCw,
  SkipForward,
  UserSearch,
} from "lucide-react";
import { request } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Modal, Spinner } from "./ui";
import type { Write } from "./growth-modules";
import { MetricsForm, day as shortDay, type Due } from "./content-strategy";
import { useProfileCheck } from "./profile-quality";
import { StyleNotice } from "./style-notice";

type Item = {
  id: string;
  kind: "connect" | "message" | "followup" | "followup2";
  state: "pending" | "approved" | "sent" | "skipped";
  contact: { id: string; name: string; job_title: string; linkedin_url: string | null; stage: Stage; stage_label: string };
  company: { id: string; name: string; location: string } | null;
  profile_url: string | null;
  profile_confirmed: boolean;
  profile_status: string;
  profile_reason: string;
  reason: string;
  sources: string[];
  note: string;
  note_limit: number;
  message: string;
  followup: string;
  followup_days: number;
  action_id: string | null;
};
type Check = {
  action_id: string;
  question: string;
  action: string;
  contact: string;
  profile_url: string | null;
  days_open: number;
};
type Stage = "new" | "sent" | "connected" | "replied" | "meeting" | "not_interested";
type Settings = {
  daily_limit: number;
  address_form: "sie" | "du";
  sender_name: string;
  sender_company: string;
  offer: string;
  region: string;
};
type Today = {
  day: string;
  daily: { limit: number; sent_last_24h: number; queued: number; remaining: number };
  settings: Settings;
  stages: Record<Stage, string>;
  items: Item[];
  checks: Check[];
  limits: { connection_requests_per_day: number; messages_per_day: number };
  usage: { connection_requests_last_24h: number; messages_last_24h: number };
  stats: { pending: number; approved: number; sent: number; avg_seconds_per_contact: number | null };
  profile_check: { unchecked: number; available: boolean };
  metrics_due: Due[];
  notice: string;
};

const kindLabel = {
  connect: "Kontaktanfrage",
  message: "Nachricht nach Annahme",
  followup: "Follow-up (Tag 3)",
  followup2: "Letztes Follow-up (Tag 7)",
};
export const STAGE_LABELS: Record<Stage, string> = {
  new: "neu",
  sent: "gesendet",
  connected: "verbunden",
  replied: "geantwortet",
  meeting: "Termin",
  not_interested: "kein Interesse",
};
export const STAGE_TONE: Record<Stage, string> = {
  new: "neutral",
  sent: "amber",
  connected: "green",
  replied: "green",
  meeting: "green",
  not_interested: "red",
};

function StageSelect({ value, onChange, disabled }: { value: Stage; onChange: (s: Stage) => void; disabled?: boolean }) {
  return (
    <select
      className="stage-select"
      aria-label="Status"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as Stage)}
    >
      {(Object.keys(STAGE_LABELS) as Stage[]).map((k) => (
        <option key={k} value={k}>
          {STAGE_LABELS[k]}
        </option>
      ))}
    </select>
  );
}

function useMonthCost(base: string, revision: number) {
  const usage = useData<{ spent_usd: number; budget_usd: number; spent_estimated_usd: number }>(
    `${base}/usage`,
    revision,
  );
  return usage.data;
}

const money = (v: number) =>
  v.toLocaleString("de-DE", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: v > 0 && v < 1 ? 3 : 2,
  });

function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="table-wrap" aria-busy="true" aria-label="Lädt">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i}>
          <span className="skeleton" style={{ width: 160 }} />
          <span className="skeleton" style={{ width: 220 }} />
          <span className="skeleton" style={{ width: 80, marginLeft: "auto" }} />
        </div>
      ))}
    </div>
  );
}

export function TodayView({
  base,
  write,
  onNavigate,
}: {
  base: string;
  write: Write;
  onNavigate?: (path: string) => void;
}) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [profileFor, setProfileFor] = useState<Item | null>(null);
  const [replyFor, setReplyFor] = useState<Check | null>(null);
  const started = useRef<Record<string, number>>({});
  // Team mode: own contacts plus unassigned ones.
  const data = useData<Today>(`${base}/today?mine=true`, revision);
  const pipeline = useData<{ counts: Record<Stage, number>; items: unknown[] }>(
    `${base}/today/pipeline`,
    revision,
  );
  const cost = useMonthCost(base, revision);
  const refresh = () => setRevision((v) => v + 1);
  const [info, setInfo] = useState("");
  const check = useProfileCheck(base, write, setInfo, refresh);

  const open = data.data?.items.filter((i) => i.state === "pending" || i.state === "approved") || [];
  const requests = open.filter((i) => i.kind === "connect" || i.kind === "message");
  const followups = open.filter((i) => i.kind === "followup" || i.kind === "followup2");
  const active = open.find((i) => i.state === "approved");

  const act = useCallback(async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    setError("");
    try {
      await fn();
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }, []);

  const setStage = (contactId: string, stage: Stage) =>
    act("stage-" + contactId, () => write(`/contacts/${contactId}/outreach-stage`, { stage }, "PUT"));

  const copyAndOpen = useCallback(async (item: Item) => {
    started.current[item.id] = started.current[item.id] || Date.now();
    const text = item.kind === "connect" ? item.note : item.kind === "message" ? item.message : item.followup;
    // Copy first, then open the verified profile directly. Without one, assign it first.
    if (!item.profile_url) {
      setProfileFor(item);
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* clipboard may be unavailable; the text stays visible for manual copy */
    }
    window.open(item.profile_url, "_blank", "noopener,noreferrer");
  }, []);

  const markSent = useCallback(
    (item: Item) =>
      act("sent-" + item.id, () =>
        write(`/today/items/${item.id}/sent`, {
          elapsed_ms: started.current[item.id] ? Date.now() - started.current[item.id] : undefined,
        }),
      ),
    [act, write],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (!active || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || e.metaKey || e.ctrlKey) return;
      if (e.key === "c") {
        e.preventDefault();
        copyAndOpen(active);
      }
      if (e.key === "g") {
        e.preventDefault();
        markSent(active);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, copyAndOpen, markSent]);

  const d = data.data;
  const sent = d?.daily.sent_last_24h ?? 0;
  const limit = d?.daily.limit ?? 0;
  const date = d
    ? new Date(d.day).toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" })
    : "";

  const mainAction =
    d && d.stats.pending > 0 ? (
      <button
        className="button secondary today-bulk"
        disabled={!!busy}
        onClick={() => act("approve", () => write("/today/approve", { all_pending: true }))}
      >
        Alle {d.stats.pending} von heute freigeben
      </button>
    ) : (
      <button
        className={`button ${open.length ? "secondary" : "primary"}`}
        disabled={!!busy}
        onClick={() => act("build", () => write("/today/build", {}))}
      >
        {busy === "build" ? <Spinner /> : <RefreshCw size={14} />}
        {open.length ? "Liste aktualisieren" : "Tagesliste erstellen"}
      </button>
    );

  return (
    <div className="today">
      <Heading title="Heute" description={date ? `${date}. Prüfen, freigeben, in LinkedIn senden, hier abhaken.` : "Prüfen, freigeben, in LinkedIn senden, hier abhaken."}>
        {mainAction}
      </Heading>
      <ErrorNote message={error || data.error} />

      <div className="today-summary">
        <section className="metric today-progress" data-testid="daily-limit">
          <span>Fortschritt heute</span>
          <strong>
            {sent} von {limit}
          </strong>
          <div className="progress" aria-hidden="true">
            <span style={{ width: `${limit ? Math.min(100, (sent / limit) * 100) : 0}%` }} />
          </div>
          <small>
            {sent} von {limit} Anfragen gesendet ·{" "}
            {d && d.daily.remaining > 0 ? `noch ${d.daily.remaining} möglich` : "Limit erreicht, morgen geht es weiter"} ·{" "}
            <button className="link-button" onClick={() => onNavigate?.("/settings/outreach")}>
              Tageslimit ändern
            </button>
          </small>
        </section>
        <section className="metric">
          <span>Zu prüfen</span>
          <strong>{d?.stats.pending ?? "–"}</strong>
          <small>{d ? `${d.stats.approved} bereit zum Senden` : " "}</small>
        </section>
        <section className="metric">
          <span>Follow-ups fällig</span>
          <strong>{d ? followups.length : "–"}</strong>
          <small>Tag 3 und Tag 7</small>
        </section>
      </div>

      <FlowTasksSection base={base} write={write} />

      {d && d.profile_check.unchecked > 0 && (
        <p className="notice-line" data-testid="profile-check-notice">
          {d.profile_check.unchecked} Ansprechpartner haben noch kein geprüftes LinkedIn-Profil. In der Liste stehen nur
          Kontakte mit geprüftem Profil.{" "}
          {d.profile_check.available ? (
            <button className="link-button" disabled={check.busy} onClick={() => check.start({ limit: 200 })}>
              {check.busy ? "Prüfe Profile …" : "Jetzt prüfen"}
            </button>
          ) : (
            <button className="link-button" onClick={() => onNavigate?.("/settings/integrations")}>
              Brave Search verbinden
            </button>
          )}{" "}
          ·{" "}
          <button className="link-button" onClick={() => onNavigate?.("/contacts/email")}>
            Ohne LinkedIn: E-Mail-Kampagne
          </button>
        </p>
      )}
      <ErrorNote message={check.error} />
      {info && (
        <p className="muted small-print" role="status">
          {info}
        </p>
      )}

      {data.loading && !d ? (
        <SkeletonRows />
      ) : requests.length === 0 && followups.length === 0 ? (
        <Empty
          title="Nichts offen für heute"
          description="Erstelle die Tagesliste, dann stehen hier die nächsten Anfragen im Rahmen deines Tageslimits."
        />
      ) : (
        <>
          {requests.length > 0 && (
            <section className="today-section">
              <h2>Anfragen und Nachrichten</h2>
              <ol className="today-list" data-testid="today-list">
                {requests.map((item, index) => (
                  <TodayCard
                    key={`${item.id}:${item.state}:${item.note.length}:${item.message.length}:${item.followup.length}`}
                    item={item}
                    open={index === 0}
                    active={item.id === active?.id}
                    busy={busy}
                    onCopy={() => copyAndOpen(item)}
                    onSent={() => markSent(item)}
                    onSkip={() => act("skip-" + item.id, () => write(`/today/items/${item.id}/skip`))}
                    onApprove={() => act("ap-" + item.id, () => write("/today/approve", { item_ids: [item.id] }))}
                    onEdit={(patch) => act("edit-" + item.id, () => write(`/today/items/${item.id}`, patch, "PATCH"))}
                    onProfile={() => setProfileFor(item)}
                    onStage={(stage) => setStage(item.contact.id, stage)}
                  />
                ))}
              </ol>
            </section>
          )}
          {followups.length > 0 && (
            <section className="today-section">
              <h2>Follow-ups fällig</h2>
              <ol className="today-list" data-testid="followup-list">
                {followups.map((item) => (
                  <TodayCard
                    key={`${item.id}:${item.state}:${item.followup.length}`}
                    item={item}
                    open={false}
                    active={item.id === active?.id}
                    busy={busy}
                    onCopy={() => copyAndOpen(item)}
                    onSent={() => markSent(item)}
                    onSkip={() => act("skip-" + item.id, () => write(`/today/items/${item.id}/skip`))}
                    onApprove={() => act("ap-" + item.id, () => write("/today/approve", { item_ids: [item.id] }))}
                    onEdit={(patch) => act("edit-" + item.id, () => write(`/today/items/${item.id}`, patch, "PATCH"))}
                    onProfile={() => setProfileFor(item)}
                    onStage={(stage) => setStage(item.contact.id, stage)}
                  />
                ))}
              </ol>
            </section>
          )}
        </>
      )}
      {active && (
        <p className="muted small today-keys">
          Tastatur: <kbd>C</kbd> kopieren und Profil öffnen · <kbd>G</kbd> als gesendet markieren
        </p>
      )}

      {d && d.metrics_due.length > 0 && (
        <section className="today-section" data-testid="metrics-due">
          <h2>Zahlen zu deinen Beiträgen</h2>
          <p className="muted small-print">48 Stunden nach dem Posten. Die Zahlen stehen in LinkedIn unter „Statistik anzeigen“.</p>
          <ul className="row-list">
            {d.metrics_due.map((p) => (
              <li key={p.id} className="stack">
                <span className="row-main">
                  <span className="clamp-1">{p.caption}</span>
                  <small className="muted block">Veröffentlicht {shortDay(p.published_at)}</small>
                </span>
                <MetricsForm write={write} postId={p.id} onSaved={refresh} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {d && d.checks.length > 0 && (
        <section className="today-section">
          <h2>Rückmeldungen abfragen</h2>
          <ul className="row-list">
            {d.checks.map((c) => (
              <li key={c.action_id}>
                <span>
                  <strong>{c.contact}</strong> <span className="muted">· {c.question} · seit {c.days_open} {c.days_open === 1 ? "Tag" : "Tagen"}</span>
                </span>
                {c.action === "connection_request" ? (
                  <span className="row-actions">
                    <button className="button secondary small" onClick={() => act("o", () => write(`/linkedin/actions/${c.action_id}/outcome`, { outcome: "accepted" }))}>
                      Angenommen
                    </button>
                    <button className="button ghost small" onClick={() => act("o", () => write(`/linkedin/actions/${c.action_id}/outcome`, { outcome: "declined" }))}>
                      Abgelehnt
                    </button>
                  </span>
                ) : (
                  <span className="row-actions">
                    <button className="button secondary small" onClick={() => setReplyFor(c)}>
                      Antwort einfügen
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="today-foot">
        {pipeline.data && (
          <span data-testid="pipeline">
            {(Object.keys(STAGE_LABELS) as Stage[])
              .filter((k) => (pipeline.data?.counts[k] ?? 0) > 0)
              .map((k) => `${STAGE_LABELS[k]}: ${pipeline.data?.counts[k]}`)
              .join(" · ") || "Noch keine Kontakte im Ablauf"}{" "}
            ·{" "}
            <button className="link-button" onClick={() => onNavigate?.("/contacts")}>
              Alle Kontakte
            </button>
          </span>
        )}
        {cost && (
          <span data-testid="cost-line">
            KI-Kosten diesen Monat: {money(cost.spent_usd)} von {money(cost.budget_usd)}
          </span>
        )}
      </footer>

      {profileFor && (
        <ProfileMatch
          item={profileFor}
          base={base}
          write={write}
          onClose={() => {
            setProfileFor(null);
            refresh();
          }}
        />
      )}
      {replyFor && (
        <ReplyAnalysis
          check={replyFor}
          base={base}
          write={write}
          onClose={() => {
            setReplyFor(null);
            refresh();
          }}
        />
      )}
      <div className="today-hints">
        <StartBanner base={base} onNavigate={onNavigate} />
        <StyleNotice base={base} write={write} compact />
      </div>
    </div>
  );
}

/** Einstellungen → Anschreiben: sender, daily limit and form of address. */
export function OutreachSettingsPage({ base, write, notify }: { base: string; write: Write; notify: (m: string) => void }) {
  const [revision, setRevision] = useState(0);
  const data = useData<Settings>(`${base}/today/settings`, revision);
  const [form, setForm] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const value = form || data.data;
  async function save() {
    if (!form) return;
    setBusy(true);
    setError("");
    try {
      const { daily_limit, address_form, sender_name, sender_company, offer, region } = form;
      await write(
        "/today/settings",
        { daily_limit, address_form, sender_name, sender_company, offer, region },
        "PUT",
      );
      setForm(null);
      setRevision((v) => v + 1);
      notify("Gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading title="Anschreiben" description="Wer schreibt, wie viele Anfragen pro Tag und ob du duzt oder siezt.">
        <button className="button primary" disabled={!form || busy} onClick={save}>
          Einstellungen speichern
        </button>
      </Heading>
      <ErrorNote message={error || data.error} />
      {!value ? (
        <SkeletonRows rows={2} />
      ) : (
        <section className="card form-grid" data-testid="outreach-settings">
          <label>
            Absender
            <input value={value.sender_name} placeholder="Dein Vorname" onChange={(e) => setForm({ ...value, sender_name: e.target.value })} />
          </label>
          <label>
            Firma
            <input value={value.sender_company} placeholder="z. B. CleanStar" onChange={(e) => setForm({ ...value, sender_company: e.target.value })} />
          </label>
          <label>
            Tageslimit
            <select aria-label="Tageslimit" value={value.daily_limit} onChange={(e) => setForm({ ...value, daily_limit: Number(e.target.value) })}>
              {[5, 6, 7, 8, 9, 10].map((n) => (
                <option key={n} value={n}>
                  {n} Anfragen pro Tag
                </option>
              ))}
            </select>
          </label>
          <label>
            Anrede
            <select aria-label="Anrede" value={value.address_form} onChange={(e) => setForm({ ...value, address_form: e.target.value as "sie" | "du" })}>
              <option value="sie">Sie</option>
              <option value="du">Du</option>
            </select>
          </label>
          <p className="muted small form-hint">LinkedIn erlaubt ohne Premium etwa 100 Anfragen pro Woche. 5 bis 10 pro Tag bleiben sicher darunter.</p>
        </section>
      )}
      <StyleNotice base={base} write={write} />
    </>
  );
}

function TodayCard({
  item,
  open,
  active,
  busy,
  onCopy,
  onSent,
  onSkip,
  onApprove,
  onEdit,
  onProfile,
  onStage,
}: {
  item: Item;
  open: boolean;
  active: boolean;
  busy: string;
  onCopy: () => void;
  onSent: () => void;
  onSkip: () => void;
  onApprove: () => void;
  onEdit: (patch: Partial<Pick<Item, "note" | "message" | "followup">>) => void;
  onProfile: () => void;
  onStage: (stage: Stage) => void;
}) {
  const field = item.kind === "connect" ? "note" : item.kind === "message" ? "message" : "followup";
  const [text, setText] = useState(item[field]);
  const limit = field === "note" ? item.note_limit : 1500;
  const changed = text !== item[field];
  const person = [item.company ? item.contact.name : "", item.contact.job_title, item.company?.location]
    .filter(Boolean)
    .join(" · ");
  return (
    <li className={`today-row ${active ? "active" : ""}`} data-testid={`today-item-${item.kind}`}>
      <details open={open}>
        <summary>
          <span className="today-who">
            <strong>{item.company ? item.company.name : item.contact.name}</strong>
            <span className="muted">{person}</span>
          </span>
          <span className="today-tags">
            <Badge>{kindLabel[item.kind]}</Badge>
            <Badge tone={item.state === "approved" ? "green" : "amber"}>
              {item.state === "approved" ? "freigegeben" : "zu prüfen"}
            </Badge>
          </span>
          <span className="row-actions" onClick={(e) => e.preventDefault()}>
            {item.state === "pending" ? (
              <button className="button primary small" disabled={!!busy || changed} onClick={onApprove}>
                Freigeben
              </button>
            ) : (
              <>
                <button className="button primary small" disabled={changed} onClick={onCopy} data-testid="copy-open">
                  <Copy size={13} /> {item.kind === "connect" ? "Notiz kopieren & Profil öffnen" : "Text kopieren & Profil öffnen"}
                </button>
                <button className="button secondary small" disabled={!!busy || changed} onClick={onSent}>
                  {busy === "sent-" + item.id ? <Spinner /> : "Gesendet"}
                </button>
              </>
            )}
          </span>
        </summary>
        <div className="today-detail">
          <p className="today-reason">
            {item.reason}{" "}
            {item.sources.map((s, i) => (
              <a key={s} href={s} target="_blank" rel="noreferrer noopener">
                [{i + 1}]
              </a>
            ))}
          </p>
          <label className="today-text">
            <span>
              {field === "note" ? "Notiz zur Kontaktanfrage" : field === "message" ? "Nachricht" : kindLabel[item.kind]}
              <small className={text.length > limit ? "over" : "muted"}>
                {text.length} / {limit}
              </small>
            </span>
            <textarea rows={Math.max(field === "note" ? 3 : 6, Math.ceil(text.length / 80) + 1)} value={text} maxLength={limit} onChange={(e) => setText(e.target.value)} />
          </label>
          {item.kind === "connect" && (
            <details className="today-later">
              <summary>Nachricht nach Annahme und Follow-up an Tag 3</summary>
              <pre className="today-preview">{item.message}</pre>
              <pre className="today-preview">{item.followup}</pre>
            </details>
          )}
          <div className="today-detail-actions">
            {item.profile_url ? (
              <span className="profile-proof">
                <a href={item.profile_url} target="_blank" rel="noreferrer noopener" data-testid="profile-link" className="link-button">
                  LinkedIn-Profil <ExternalLink size={11} />
                </a>
                {item.profile_reason && <small className="muted"> {item.profile_reason}</small>}
              </span>
            ) : (
              <span className="muted">Kein geprüftes Profil</span>
            )}
            {!item.profile_confirmed && (
              <button className="button ghost small" onClick={onProfile}>
                <UserSearch size={13} /> Profil zuordnen
              </button>
            )}
            <StageSelect value={item.contact.stage} disabled={!!busy} onChange={onStage} />
            <span className="spacer" />
            {changed && (
              <button className="button secondary small" onClick={() => onEdit({ [field]: text })}>
                Text speichern
              </button>
            )}
            <button className="button ghost small" disabled={!!busy} onClick={onSkip}>
              <SkipForward size={13} /> Überspringen
            </button>
          </div>
        </div>
      </details>
    </li>
  );
}

function ProfileMatch({ item, base, write, onClose }: { item: Item; base: string; write: Write; onClose: () => void }) {
  const candidates = useData<{
    items: { url: string; title: string; snippet: string; confidence: number }[];
    fallback_search_url: string;
    error: string | null;
    notice: string;
  }>(`${base}/contacts/${item.contact.id}/linkedin-candidates`);
  const [manual, setManual] = useState("");
  const [error, setError] = useState("");
  async function confirm(url: string) {
    try {
      await write(`/contacts/${item.contact.id}/linkedin-profile`, { url }, "PUT");
      onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <Modal title={`Profil zuordnen: ${item.contact.name}`} onClose={onClose}>
      <div className="modal-body">
        <ErrorNote message={error || candidates.data?.error || ""} />
        {candidates.loading ? (
          <Spinner />
        ) : (
          <ul className="profile-candidates">
            {candidates.data?.items.map((c) => (
              <li key={c.url}>
                <div>
                  <a href={c.url} target="_blank" rel="noreferrer noopener">
                    {c.title || c.url}
                  </a>
                  <small className="muted"> Sicherheit {Math.round(c.confidence * 100)} %</small>
                  <p className="muted small">{c.snippet}</p>
                </div>
                <button className="button secondary small" onClick={() => confirm(c.url)}>
                  Das ist die Person
                </button>
              </li>
            ))}
            {candidates.data?.items.length === 0 && <li className="muted">Keine Kandidaten gefunden.</li>}
          </ul>
        )}
        <p className="small">
          Alternativ in LinkedIn suchen:{" "}
          <a href={candidates.data?.fallback_search_url || item.profile_url || undefined} target="_blank" rel="noreferrer noopener">
            vorbefüllte Suche öffnen
          </a>{" "}
          und die Profiladresse hier einfügen.
        </p>
        <div className="form-actions">
          <input value={manual} onChange={(e) => setManual(e.target.value)} placeholder="https://www.linkedin.com/in/…" />
          <button className="button primary small" disabled={!manual} onClick={() => confirm(manual)}>
            Bestätigen
          </button>
        </div>
        <p className="muted small">{candidates.data?.notice}</p>
      </div>
    </Modal>
  );
}

type Analysis = { classification: string; next_step: string; suggested_reply: string };

function ReplyAnalysis({ check, base, write, onClose }: { check: Check; base: string; write: Write; onClose: () => void }) {
  const [text, setText] = useState("");
  const [state, setState] = useState<"idle" | "running" | "done" | "failed">("idle");
  const [result, setResult] = useState<Analysis | null>(null);
  const [error, setError] = useState("");
  async function run() {
    setState("running");
    setError("");
    try {
      await write(`/linkedin/actions/${check.action_id}/outcome`, { outcome: "replied", note: text.slice(0, 1000) });
      const job = await write<{ id: string }>("/today/replies", { action_id: check.action_id, text });
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const current = await request<{ status: string; result?: Analysis }>(`${base}/jobs/${job.id}`);
        if (current.status === "succeeded" && current.result) {
          setResult(current.result);
          setState("done");
          return;
        }
        if (["failed", "dead", "ambiguous"].includes(current.status)) break;
      }
      setState("failed");
    } catch (e) {
      setError((e as Error).message);
      setState("failed");
    }
  }
  return (
    <Modal title={`Antwort von ${check.contact}`} onClose={onClose}>
      <div className="modal-body">
        <ErrorNote message={error} />
        <label>
          Antwort aus LinkedIn einfügen
          <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <div className="form-actions">
          <button className="button primary small" disabled={text.length < 2 || state !== "idle"} onClick={run}>
            Als beantwortet markieren & auswerten
          </button>
        </div>
        {state === "running" && <Spinner />}
        {state === "done" && result && (
          <div className="reply-result">
            <p>
              <strong>Einordnung:</strong> {result.classification}
            </p>
            <p>
              <strong>Nächster Schritt:</strong> {result.next_step}
            </p>
            <label>
              Antwortvorschlag (wird nicht gesendet)
              <textarea rows={4} defaultValue={result.suggested_reply} />
            </label>
          </div>
        )}
        {state === "failed" && !error && <ErrorNote message="Auswertung fehlgeschlagen." />}
      </div>
    </Modal>
  );
}
