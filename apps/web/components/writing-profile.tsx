"use client";
import { FormEvent, useState } from "react";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Heading } from "./ui";
import { SkeletonTable } from "./table";

type Write = <T>(path: string, body?: unknown, method?: string) => Promise<T>;
type Rule = { id: string; key: string; text: string; evidence: string; source: string; active: boolean };
export type WritingProfile = {
  id: string;
  rules: Rule[];
  learned_at: string | null;
  counts: { edits: number; yes: number; no: number };
  recent_edits: { id: string; kind: string; original: string; edited: string; created_at: string }[];
  recent_feedback: { id: string; verdict: string; reason: string; text: string; created_at: string }[];
  inspirations: { id: string; author: string; text: string; note: string; created_at: string }[];
};

const SOURCE: Record<string, string> = {
  auto: "gelernt",
  edited: "von dir angepasst",
  manual: "von dir",
};

/* Content → Schreibprofil. Rules in plain language, derived from your edits and from
   "Klingt nach mir"; you can change, switch off or delete them. */
export function WritingProfilePage({ base, write, notify }: { base: string; write: Write; notify: (m: string) => void }) {
  const [revision, setRevision] = useState(0);
  const { data, error, loading } = useData<WritingProfile>(`${base}/writing-profile`, revision);
  const [editing, setEditing] = useState<string | null>(null);
  const [localError, setLocalError] = useState("");
  const [busy, setBusy] = useState(false);
  const reload = () => setRevision((v) => v + 1);
  async function call(path: string, body?: unknown, method = "POST", message = "") {
    setBusy(true);
    setLocalError("");
    try {
      await write(path, body, method);
      if (message) notify(message);
      reload();
      return true;
    } catch (e) {
      setLocalError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function addRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const text = String(new FormData(form).get("text") || "");
    if (await call("/writing-profile/rules", { text }, "POST", "Regel gespeichert.")) form.reset();
  }
  async function addInspiration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const f = new FormData(form);
    if (
      await call(
        "/writing-profile/inspirations",
        { author: f.get("author"), text: f.get("text"), note: f.get("note") },
        "POST",
        "Stil-Vorbild gespeichert.",
      )
    )
      form.reset();
  }
  const c = data?.counts;
  return (
    <>
      <Heading
        title="Mein Schreibprofil"
        description="Was die Vorschläge über deinen Stil wissen. Es lernt aus jeder Änderung an einem Entwurf und aus deinen Rückmeldungen."
      >
        <button
          className="button secondary"
          disabled={busy}
          onClick={() => call("/writing-profile/relearn", {}, "POST", "Regeln neu abgeleitet.")}
        >
          Neu ableiten
        </button>
      </Heading>
      <ErrorNote message={error || localError} />
      {c && (
        <p className="muted small-print" data-testid="profile-counts">
          Gelernt aus {c.edits} Änderungen, {c.yes}× „Klingt nach mir“ und {c.no}× „Klingt nicht nach mir“.
        </p>
      )}
      <section className="today-section">
        <h2>Regeln</h2>
        {loading && !data ? (
          <SkeletonTable rows={4} cols={2} />
        ) : data?.rules.length ? (
          <ul className="row-list" data-testid="profile-rules">
            {data.rules.map((r) => (
              <li key={r.id} className={r.active ? "" : "inactive"}>
                {editing === r.id ? (
                  <form
                    className="inline-form"
                    onSubmit={async (e) => {
                      e.preventDefault();
                      const text = String(new FormData(e.currentTarget).get("text") || "");
                      if (await call(`/writing-profile/rules/${r.id}`, { text }, "PATCH", "Regel geändert.")) setEditing(null);
                    }}
                  >
                    <input name="text" defaultValue={r.text} aria-label="Regel" minLength={3} maxLength={300} autoFocus />
                    <button className="button primary small">Speichern</button>
                    <button type="button" className="button ghost small" onClick={() => setEditing(null)}>
                      Abbrechen
                    </button>
                  </form>
                ) : (
                  <>
                    <span className="row-main">
                      {r.text}
                      <small className="muted block">
                        {SOURCE[r.source] || r.source}
                        {r.evidence && r.source !== "manual" ? `, ${r.evidence}` : ""}
                      </small>
                    </span>
                    <span className="row-actions">
                      <label className="inline-toggle">
                        <input
                          type="checkbox"
                          checked={r.active}
                          onChange={(e) => call(`/writing-profile/rules/${r.id}`, { active: e.target.checked }, "PATCH")}
                        />
                        aktiv
                      </label>
                      <button className="button ghost small" onClick={() => setEditing(r.id)}>
                        Bearbeiten
                      </button>
                      <button
                        className="button ghost small"
                        onClick={() => call(`/writing-profile/rules/${r.id}`, undefined, "DELETE", "Regel entfernt.")}
                      >
                        Entfernen
                      </button>
                    </span>
                  </>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty-line">Noch keine Regeln. Ändere ein paar Entwürfe oder sag „Klingt nicht nach mir“.</p>
        )}
        <form className="inline-form" onSubmit={addRule}>
          <input name="text" placeholder="Eigene Regel, z. B. Immer mit einem Beispiel aus der Ortenau" aria-label="Neue Regel" minLength={3} maxLength={300} required />
          <button className="button secondary" disabled={busy}>
            Regel hinzufügen
          </button>
        </form>
      </section>
      <section className="today-section">
        <h2>Stil-Vorbilder</h2>
        <p className="muted small-print">
          Posts anderer Leute, die dir gefallen. Sie zeigen nur Rhythmus und Aufbau. Inhalte und Formulierungen werden nie übernommen.
        </p>
        {data?.inspirations.length ? (
          <ul className="row-list" data-testid="inspirations">
            {data.inspirations.map((i) => (
              <li key={i.id}>
                <span className="row-main">
                  <strong>{i.author || "Ohne Namen"}</strong>
                  <span className="clamp-2 block">{i.text}</span>
                  {i.note && <small className="muted block">{i.note}</small>}
                </span>
                <span className="row-actions">
                  <button
                    className="button ghost small"
                    onClick={() => call(`/writing-profile/inspirations/${i.id}`, undefined, "DELETE", "Stil-Vorbild entfernt.")}
                  >
                    Entfernen
                  </button>
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        <details className="add-details">
          <summary>Stil-Vorbild ablegen</summary>
          <form className="form-grid" onSubmit={addInspiration}>
            <label>
              Von wem
              <input name="author" maxLength={120} placeholder="Name oder Profil" />
            </label>
            <label className="span-2">
              Text des Posts
              <textarea name="text" rows={6} required minLength={20} maxLength={3000} />
            </label>
            <label className="span-2">
              Was dir daran gefällt (optional)
              <input name="note" maxLength={500} />
            </label>
            <div className="form-actions span-2">
              <button className="button primary" disabled={busy}>
                Speichern
              </button>
            </div>
          </form>
        </details>
      </section>
      {!!data?.recent_edits.length && (
        <section className="today-section">
          <h2>Deine letzten Änderungen</h2>
          <ul className="row-list" data-testid="recent-edits">
            {data.recent_edits.map((e) => (
              <li key={e.id}>
                <span className="row-main diff-pair">
                  <span>
                    <small className="muted block">Vorschlag</small>
                    <span className="clamp-3">{e.original}</span>
                  </span>
                  <span>
                    <small className="muted block">Deine Version</small>
                    <span className="clamp-3">{e.edited}</span>
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {!!data?.recent_feedback.length && (
        <section className="today-section">
          <h2>Deine Rückmeldungen</h2>
          <ul className="row-list">
            {data.recent_feedback.map((f) => (
              <li key={f.id}>
                <span className="row-main">
                  <Badge tone={f.verdict === "yes" ? "green" : "amber"}>
                    {f.verdict === "yes" ? "Klingt nach mir" : "Klingt nicht nach mir"}
                  </Badge>{" "}
                  {f.reason || <span className="muted">ohne Grund</span>}
                  <small className="muted block clamp-1">{f.text}</small>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/** "Klingt nach mir" / "Klingt nicht nach mir" with an optional reason. */
export function VoiceFeedback({
  write,
  notify,
  postId,
  text,
}: {
  write: Write;
  notify: (m: string) => void;
  postId?: string;
  text: string;
}) {
  const [verdict, setVerdict] = useState<"yes" | "no" | null>(null);
  const [reason, setReason] = useState("");
  const [sent, setSent] = useState(false);
  async function send(v: "yes" | "no", why: string) {
    try {
      await write("/writing-profile/feedback", { verdict: v, reason: why, post_id: postId, text: text.slice(0, 3000) });
      setSent(true);
      notify("Danke. Dein Schreibprofil hat das gelernt.");
    } catch (e) {
      notify((e as Error).message);
    }
  }
  if (sent) return <small className="muted">Rückmeldung gespeichert.</small>;
  return (
    <span className="voice-feedback">
      <button type="button" className="button ghost small" onClick={() => setVerdict("yes")} aria-pressed={verdict === "yes"}>
        Klingt nach mir
      </button>
      <button type="button" className="button ghost small" onClick={() => setVerdict("no")} aria-pressed={verdict === "no"}>
        Klingt nicht nach mir
      </button>
      {verdict && (
        <span className="inline-form">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={verdict === "no" ? "Was passt nicht? (optional)" : "Was passt gut? (optional)"}
            aria-label="Grund"
            maxLength={500}
          />
          <button type="button" className="button secondary small" onClick={() => send(verdict, reason)}>
            Senden
          </button>
        </span>
      )}
    </span>
  );
}
