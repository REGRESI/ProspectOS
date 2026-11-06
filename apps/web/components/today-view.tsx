"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
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
import { StyleNotice } from "./style-notice";

type Item = {
  id: string;
  kind: "connect" | "message" | "followup" | "followup2";
  state: "pending" | "approved" | "sent" | "skipped";
  contact: { id: string; name: string; job_title: string; linkedin_url: string | null; stage: Stage; stage_label: string };
  company: { id: string; name: string; location: string } | null;
  profile_url: string;
  profile_confirmed: boolean;
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
  notice: string;
};

const kindLabel = {
  connect: "Kontaktanfrage",
  message: "Nachricht nach Annahme",
  followup: "Follow-up (Tag 3)",
  followup2: "Letztes Follow-up (Tag 7)",
};
const STAGE_LABELS: Record<Stage, string> = {
  new: "neu",
  sent: "gesendet",
  connected: "verbunden",
  replied: "geantwortet",
  meeting: "Termin",
  not_interested: "kein Interesse",
};
const STAGE_TONE: Record<Stage, string> = {
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

export function TodayView({ base, write }: { base: string; write: Write }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [profileFor, setProfileFor] = useState<Item | null>(null);
  const [replyFor, setReplyFor] = useState<Check | null>(null);
  const started = useRef<Record<string, number>>({});
  const data = useData<Today>(`${base}/today`, revision);
  const pipeline = useData<{ counts: Record<Stage, number>; items: { id: string; name: string; company: string; linkedin_url: string | null; stage: Stage; stage_label: string }[] }>(
    `${base}/today/pipeline`,
    revision,
  );
  const refresh = () => setRevision((v) => v + 1);
  const form = settings || data.data?.settings || null;

  const open = data.data?.items.filter((i) => i.state === "pending" || i.state === "approved") || [];
  const active = open.find((i) => i.state === "approved");

  const act = useCallback(
    async (key: string, fn: () => Promise<unknown>) => {
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
    },
    [],
  );

  const setStage = (contactId: string, stage: Stage) =>
    act("stage-" + contactId, () => write(`/contacts/${contactId}/outreach-stage`, { stage }, "PUT"));

  const copyAndOpen = useCallback(async (item: Item) => {
    started.current[item.id] = started.current[item.id] || Date.now();
    const text = item.kind === "connect" ? item.note : item.kind === "message" ? item.message : item.followup;
    // Copy first, then open the profile (or the people search if no profile is confirmed).
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
  return (
    <>
      <Heading
        eyebrow={d ? new Date(d.day).toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" }) : "HEUTE"}
        title="Heute"
        description="Vorbereitete LinkedIn-Schritte: prüfen, freigeben, in LinkedIn selbst senden, hier abhaken."
      />
      <ErrorNote message={error || data.error} />
      <StyleNotice base={base} write={write} compact />
      <section className="panel pad today-toolbar">
        {form && (
          <>
            <label>
              Absender
              <input
                value={form.sender_name}
                placeholder="Dein Name"
                onChange={(e) => setSettings({ ...form, sender_name: e.target.value })}
              />
            </label>
            <label>
              Firma
              <input
                value={form.sender_company}
                placeholder="z. B. CleanStar"
                onChange={(e) => setSettings({ ...form, sender_company: e.target.value })}
              />
            </label>
            <label>
              Tageslimit
              <select
                aria-label="Tageslimit"
                value={form.daily_limit}
                onChange={(e) => setSettings({ ...form, daily_limit: Number(e.target.value) })}
              >
                {[5, 6, 7, 8, 9, 10].map((n) => (
                  <option key={n} value={n}>
                    {n} Anfragen/Tag
                  </option>
                ))}
              </select>
            </label>
            <label>
              Anrede
              <select
                aria-label="Anrede"
                value={form.address_form}
                onChange={(e) => setSettings({ ...form, address_form: e.target.value as "sie" | "du" })}
              >
                <option value="sie">Sie</option>
                <option value="du">Du</option>
              </select>
            </label>
            {settings && (
              <button
                className="button secondary"
                disabled={!!busy}
                onClick={() =>
                  act("settings", async () => {
                    await write("/today/settings", settings, "PUT");
                    setSettings(null);
                  })
                }
              >
                Einstellungen speichern
              </button>
            )}
          </>
        )}
        <button
          className="button primary"
          disabled={!!busy || !!settings}
          title={settings ? "Erst Einstellungen speichern" : undefined}
          onClick={() => act("build", () => write("/today/build", {}))}
        >
          {busy === "build" ? <Spinner /> : <><RefreshCw size={15} /> Tagesliste erstellen</>}
        </button>
        {d && (
          <span className="today-stats">
            <Badge>{d.stats.pending} zu prüfen</Badge>
            <Badge tone="amber">{d.stats.approved} freigegeben</Badge>
            <Badge tone="green">{d.stats.sent} gesendet</Badge>
            {d.stats.avg_seconds_per_contact !== null && (
              <small className="muted">Ø {d.stats.avg_seconds_per_contact} s pro Kontakt</small>
            )}
          </span>
        )}
      </section>
      {d && (
        <p className="today-daily" data-testid="daily-limit">
          <strong>Tageslimit:</strong> {d.daily.sent_last_24h} von {d.daily.limit} Anfragen gesendet (24 h)
          <meter min={0} max={d.daily.limit} value={d.daily.sent_last_24h} />
          <span className="muted">
            {d.daily.remaining > 0 ? `noch ${d.daily.remaining} möglich, ${d.daily.queued} vorbereitet` : "Limit erreicht, morgen geht es weiter"}
          </span>
        </p>
      )}
      {d && d.stats.pending > 0 && (
        <div className="today-approve">
          <button
            className="button secondary"
            disabled={!!busy}
            onClick={() => act("approve", () => write("/today/approve", { all_pending: true }))}
          >
            <CheckCircle2 size={15} /> Alle {d.stats.pending} von heute freigeben
          </button>
          <small className="muted">Nach Durchsicht. Bearbeitete Einträge müssen erneut freigegeben werden.</small>
        </div>
      )}
      {data.loading && !d ? (
        <Spinner />
      ) : open.length === 0 ? (
        <Empty
          title="Nichts offen für heute"
          description="„Tagesliste erstellen“ füllt die Liste aus Top-Kandidaten, fälligen Nachrichten und Follow-ups – im Rahmen der Tageslimits."
        />
      ) : (
        <ol className="today-list" data-testid="today-list">
          {open.map((item) => (
            <TodayCard
              key={`${item.id}:${item.state}:${item.note.length}:${item.message.length}:${item.followup.length}`}
              item={item}
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
      )}
      {active && (
        <p className="muted small today-keys">
          Tastatur: <kbd>C</kbd> kopieren & Profil öffnen · <kbd>G</kbd> als gesendet markieren
        </p>
      )}
      {d && d.checks.length > 0 && (
        <section className="panel pad">
          <h2>Rückmeldungen abfragen</h2>
          <ul className="today-checks">
            {d.checks.map((c) => (
              <li key={c.action_id}>
                <span>
                  <strong>{c.contact}</strong> – {c.question}{" "}
                  <small className="muted">seit {c.days_open} Tag(en)</small>
                </span>
                {c.action === "connection_request" ? (
                  <span className="form-actions">
                    <button className="button secondary small" onClick={() => act("o", () => write(`/linkedin/actions/${c.action_id}/outcome`, { outcome: "accepted" }))}>
                      Ja, angenommen
                    </button>
                    <button className="button ghost small" onClick={() => act("o", () => write(`/linkedin/actions/${c.action_id}/outcome`, { outcome: "declined" }))}>
                      Abgelehnt
                    </button>
                  </span>
                ) : (
                  <span className="form-actions">
                    <button className="button secondary small" onClick={() => setReplyFor(c)}>
                      Ja, Antwort einfügen
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {pipeline.data && pipeline.data.items.length > 0 && (
        <section className="panel pad" data-testid="pipeline">
          <h2>Kontakte im Ablauf</h2>
          <div className="pipeline-counts">
            {(Object.keys(STAGE_LABELS) as Stage[]).map((k) => (
              <Badge key={k} tone={STAGE_TONE[k]}>
                {STAGE_LABELS[k]}: {pipeline.data?.counts[k] ?? 0}
              </Badge>
            ))}
          </div>
          <ul className="pipeline-list">
            {pipeline.data.items.map((c) => (
              <li key={c.id}>
                <strong>{c.name}</strong>
                <span className="muted">{c.company}</span>
                {c.linkedin_url && (
                  <a href={c.linkedin_url} target="_blank" rel="noreferrer noopener">
                    Profil <ExternalLink size={11} />
                  </a>
                )}
                <StageSelect value={c.stage} disabled={!!busy} onChange={(stage) => setStage(c.id, stage)} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {d && <p className="muted small">{d.notice}</p>}
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
    </>
  );
}

function TodayCard({
  item,
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
  return (
    <li className={`today-card ${active ? "active" : ""}`} data-testid={`today-item-${item.kind}`}>
      <header>
        <Badge tone={item.kind === "connect" ? "neutral" : "amber"}>{kindLabel[item.kind]}</Badge>
        <strong>{item.company ? item.company.name : item.contact.name}</strong>
        <span className="muted">
          {item.company ? `Ansprechperson: ${item.contact.name}` : ""}
          {item.contact.job_title ? ` · ${item.contact.job_title}` : ""}
          {item.company?.location ? ` · ${item.company.location}` : ""}
        </span>
        <Badge tone={item.state === "approved" ? "green" : "neutral"}>
          {item.state === "approved" ? "freigegeben" : "zu prüfen"}
        </Badge>
        <StageSelect value={item.contact.stage} disabled={!!busy} onChange={onStage} />
      </header>
      <p className="today-profile">
        <a href={item.profile_url} target="_blank" rel="noreferrer noopener" data-testid="profile-link">
          {item.profile_confirmed ? "LinkedIn-Profil" : "LinkedIn-Suche (Profil noch nicht bestätigt)"} <ExternalLink size={11} />
        </a>
      </p>
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
          {field === "note" ? "Verbindungsnotiz" : field === "message" ? "Nachricht" : kindLabel[item.kind]}
          <small className={text.length > limit ? "over" : "muted"}>
            {" "}
            {text.length}/{limit}
          </small>
        </span>
        <textarea rows={field === "note" ? 3 : 6} value={text} maxLength={limit} onChange={(e) => setText(e.target.value)} />
      </label>
      {item.kind === "connect" && (
        <details>
          <summary>Nachricht nach Annahme und Follow-up an Tag 3 (Tag 7 folgt automatisch)</summary>
          <pre className="today-preview">{item.message}</pre>
          <pre className="today-preview">{item.followup}</pre>
        </details>
      )}
      <div className="form-actions">
        {changed && (
          <button className="button secondary small" onClick={() => onEdit({ [field]: text })}>
            Text speichern
          </button>
        )}
        {!item.profile_confirmed && (
          <button className="button ghost small" onClick={onProfile} title="Profil-Kandidaten suchen und bestätigen">
            <UserSearch size={14} /> Profil zuordnen
          </button>
        )}
        {item.state === "pending" ? (
          <button className="button secondary small" disabled={!!busy || changed} onClick={onApprove}>
            Freigeben
          </button>
        ) : (
          <>
            <button className="button primary small" disabled={changed} onClick={onCopy}>
              <Copy size={14} /> Kopieren & LinkedIn öffnen <ExternalLink size={12} />
            </button>
            <button className="button secondary small" disabled={!!busy || changed} onClick={onSent}>
              {busy === "sent-" + item.id ? <Spinner /> : <><CheckCircle2 size={14} /> Gesendet</>}
            </button>
          </>
        )}
        <button className="button ghost small" disabled={!!busy} onClick={onSkip}>
          <SkipForward size={14} /> Überspringen
        </button>
      </div>
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
          <a href={candidates.data?.fallback_search_url || item.profile_url} target="_blank" rel="noreferrer noopener">
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
