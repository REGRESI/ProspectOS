"use client";
import { useState } from "react";
import { CheckCircle2, FlaskConical, XCircle } from "lucide-react";
import { useData } from "@/lib/use-data";
import { ErrorNote, Spinner } from "./ui";
import type { Write } from "./growth-modules";

type Readiness = {
  ready: boolean;
  rule: string;
  checks: { key: string; label: string; ok: boolean; next: string }[];
};

/** Probe-Post: prepares a short test draft. Publishing stays a separate, explicit click
 * on the approved post ("Auf LinkedIn veröffentlichen"); this card never publishes. */
export function ProbePost({ base, write, onChange }: { base: string; write: Write; onChange: () => void }) {
  const [revision, setRevision] = useState(0);
  const readiness = useData<Readiness>(`${base}/social/publish-readiness`, revision);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const r = readiness.data;
  async function prepare() {
    setBusy(true);
    setError("");
    try {
      const post = await write<{ existing: boolean }>("/social/probe-post");
      setNote(
        post.existing
          ? "Es gibt schon einen offenen Probe-Post. Er steht unten in der Liste."
          : "Probe-Post als Entwurf angelegt. Unten in der Liste: „Zur Prüfung“, „Freigeben“, dann „Auf LinkedIn veröffentlichen“. Erst dieser letzte Klick postet.",
      );
      onChange();
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel pad probe-post" data-testid="probe-post">
      <h2>
        <FlaskConical size={16} /> Probe-Post
      </h2>
      <p className="muted small">{r?.rule}</p>
      {r && (
        <ul className="probe-checks">
          {r.checks.map((c) => (
            <li key={c.key} className={c.ok ? "ok" : "bad"}>
              {c.ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />} {c.label}
              {!c.ok && <small className="muted"> · {c.next}</small>}
            </li>
          ))}
        </ul>
      )}
      <ErrorNote message={error || readiness.error} />
      <div className="form-actions">
        <button className="button secondary small" disabled={busy} onClick={prepare} data-testid="probe-prepare">
          {busy ? <Spinner /> : "Probe-Post vorbereiten"}
        </button>
        <small className="muted">
          {r?.ready ? "Alle Bedingungen erfüllt. Veröffentlicht wird erst nach Freigabe und deinem Klick." : "Veröffentlichen ist erst möglich, wenn alle Punkte grün sind."}
        </small>
      </div>
      {note && <p className="credential-result connected" role="status">{note}</p>}
    </section>
  );
}
