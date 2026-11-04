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

type Item = {
  id: string;
  kind: "connect" | "message" | "followup";
  state: "pending" | "approved" | "sent" | "skipped";
  contact: { id: string; name: string; job_title: string; linkedin_url: string | null };
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
type Today = {
  day: string;
  items: Item[];
  checks: Check[];
  limits: { connection_requests_per_day: number; messages_per_day: number };
  usage: { connection_requests_last_24h: number; messages_last_24h: number };
  stats: { pending: number; approved: number; sent: number; avg_seconds_per_contact: number | null };
  notice: string;
};

const kindLabel = { connect: "Kontaktanfrage", message: "Nachricht nach Annahme", followup: "Follow-up" };
const SENDER_KEY = "prospectos.today.sender";

function loadSender() {
  try {
    return JSON.parse(localStorage.getItem(SENDER_KEY) || "{}");
  } catch {
    return {};
  }
}

export function TodayView({ base, write }: { base: string; write: Write }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [sender, setSender] = useState<{ sender_name?: string; sender_company?: string }>(() =>
    typeof window === "undefined" ? {} : loadSender(),
  );
  const [profileFor, setProfileFor] = useState<Item | null>(null);
  const [replyFor, setReplyFor] = useState<Check | null>(null);
  const started = useRef<Record<string, number>>({});
  const data = useData<Today>(`${base}/today`, revision);
  const refresh = () => setRevision((v) => v + 1);

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

  const copyAndOpen = useCallback(async (item: Item) => {
    started.current[item.id] = started.current[item.id] || Date.now();
    const text = item.kind === "connect" ? item.note : item.kind === "message" ? item.message : item.followup;
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
      <section className="panel today-toolbar">
        <label>
          Absender
          <input
            value={sender.sender_name || ""}
            placeholder="Dein Name"
            onChange={(e) => setSender((s) => ({ ...s, sender_name: e.target.value }))}
          />
        </label>
        <label>
          Firma
          <input
            value={sender.sender_company || ""}
            placeholder="z. B. CleanStar Dienstleistungen"
            onChange={(e) => setSender((s) => ({ ...s, sender_company: e.target.value }))}
          />
        </label>
        <button
          className="button primary"
          disabled={!!busy}
          onClick={() =>
            act("build", async () => {
              try {
                localStorage.setItem(SENDER_KEY, JSON.stringify(sender));
              } catch {
                /* per-browser convenience only */
              }
              await write("/today/build", sender);
            })
          }
        >
          {busy === "build" ? <Spinner /> : <><RefreshCw size={15} /> Tagesliste erstellen</>}
        </button>
        {d && (
          <span className="today-stats">
            <Badge>{d.stats.pending} zu prüfen</Badge>
            <Badge tone="amber">{d.stats.approved} freigegeben</Badge>
            <Badge tone="green">{d.stats.sent} gesendet</Badge>
            <small className="muted">
              Anfragen {d.usage.connection_requests_last_24h}/{d.limits.connection_requests_per_day} (24 h)
              {d.stats.avg_seconds_per_contact !== null && ` · Ø ${d.stats.avg_seconds_per_contact} s pro Kontakt`}
            </small>
          </span>
        )}
      </section>
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
        <section className="panel">
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
}) {
  const field = item.kind === "connect" ? "note" : item.kind === "message" ? "message" : "followup";
  const [text, setText] = useState(item[field]);
  const limit = field === "note" ? item.note_limit : 1500;
  const changed = text !== item[field];
  return (
    <li className={`today-card ${active ? "active" : ""}`} data-testid={`today-item-${item.kind}`}>
      <header>
        <Badge tone={item.kind === "connect" ? "neutral" : "amber"}>{kindLabel[item.kind]}</Badge>
        <strong>{item.contact.name}</strong>
        <span className="muted">
          {item.contact.job_title}
          {item.company ? ` · ${item.company.name}, ${item.company.location}` : ""}
        </span>
        <Badge tone={item.state === "approved" ? "green" : "neutral"}>
          {item.state === "approved" ? "freigegeben" : "zu prüfen"}
        </Badge>
      </header>
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
          {field === "note" ? "Kontaktnotiz" : field === "message" ? "Nachricht" : "Follow-up"}
          <small className={text.length > limit ? "over" : "muted"}>
            {" "}
            {text.length}/{limit}
          </small>
        </span>
        <textarea rows={field === "note" ? 3 : 6} value={text} maxLength={limit} onChange={(e) => setText(e.target.value)} />
      </label>
      {item.kind === "connect" && (
        <details>
          <summary>Nachricht nach Annahme und Follow-up nach {item.followup_days} Tagen</summary>
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
              <Copy size={14} /> Kopieren & {item.profile_confirmed ? "Profil" : "Suche"} öffnen <ExternalLink size={12} />
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
