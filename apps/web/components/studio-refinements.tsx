"use client";
import { useState } from "react";
import { useData } from "@/lib/use-data";
import type { Write } from "./growth-modules";
import { useGenerationJob } from "./social-tools";
import { ErrorNote, Spinner } from "./ui";

const actions = [
  "kürzer",
  "länger",
  "direkter",
  "persönlicher",
  "menschlicher",
  "professioneller",
  "meinungsstärker",
  "mehr Emojis",
  "weniger Emojis",
  "ohne Emojis",
  "stärkerer Hook",
  "weichere CTA",
  "provokanter",
  "sachlicher",
  "mehr wie ich",
  "weniger werblich",
];
type History = {
  id: string;
  status: string;
  original?: string;
  action?: string;
  voice_name?: string;
  result: { variants?: { text: string; angle?: string }[] };
};
export function StudioRefinements({
  base,
  write,
  caption,
  voiceId,
  parentJobId,
  brandId,
  onSelect,
  revision,
  onChange,
}: {
  base: string;
  write: Write;
  caption: string;
  voiceId: string;
  parentJobId?: string;
  brandId: string;
  onSelect: (text: string, jobId: string) => void;
  revision: number;
  onChange: () => void;
}) {
  const [action, setAction] = useState(actions[0]);
  const [facts, setFacts] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const history = useData<{ items: History[] }>(
    `${base}/social/generations`,
    revision,
  );
  const { job, setJob, pollError } = useGenerationJob(base, () => onChange());
  const pending = !!job && ["queued", "running", "retry"].includes(job.status);
  return (
    <section className="studio-refinements">
      <h3>Text gezielt verfeinern</h3>
      <p className="small muted">
        Der aktuelle Text bleibt erhalten. Überarbeitungen werden als Vorschläge
        gespeichert; die gewählte Fassung speicherst du als Entwurf.
      </p>
      <div className="form-grid">
        <label>
          Überarbeitung
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            {actions.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <button
          className="button secondary"
          disabled={caption.trim().length < 3 || busy || pending}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              setJob(
                await write("/social/refine", {
                  text: caption,
                  action,
                  voice_profile_id: voiceId || null,
                  brand_id: brandId || null,
                  parent_job_id: parentJobId || null,
                  ...(facts.trim() ? { factual_notes: facts } : {}),
                }),
              );
              onChange();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy || pending ? <Spinner /> : null} Überarbeitung anfordern
        </button>
      </div>
      <label>
        Faktenbasis für die Überarbeitung
        <textarea
          rows={2}
          value={facts}
          onChange={(e) => setFacts(e.target.value)}
          maxLength={2000}
          placeholder="Nur belegbare Angaben. Der Entwurf selbst ist kein Faktenbeleg."
        />
      </label>
      <ErrorNote
        message={
          error ||
          pollError ||
          history.error ||
          (job && ["failed", "ambiguous"].includes(job.status)
            ? `${job.last_error || job.status}. Bei unklarem Ausgang Anbieter und Kosten prüfen, bevor du neu anforderst.`
            : "")
        }
      />
      {pending && <p role="status">Überarbeitung läuft · {job?.status}</p>}
      {job?.status === "succeeded" &&
        job.result.variants?.map((variant, index) => (
          <article className="voice-example" key={index}>
            <strong>Überarbeiteter Vorschlag</strong>
            <p className="preserve-text">{variant.text}</p>
            <button
              className="button secondary small"
              onClick={() => onSelect(variant.text, job.id)}
            >
              Überarbeitung übernehmen
            </button>
          </article>
        ))}
      <details className="generation-history">
        <summary>
          Gespeicherte Varianten & Überarbeitungen (
          {history.data?.items.length || 0})
        </summary>
        {history.loading ? (
          <Spinner />
        ) : history.data?.items.length ? (
          history.data.items.map((entry) => (
            <details key={entry.id}>
              <summary>
                {entry.action || "Drei Ausgangsvarianten"} ·{" "}
                {entry.voice_name || "ohne Schreibprofil"} · {entry.status}
              </summary>
              {entry.original && (
                <div>
                  <strong>Ausgangstext</strong>
                  <p className="preserve-text">{entry.original}</p>
                </div>
              )}
              {entry.result.variants?.map((variant, index) => (
                <article className="voice-example" key={index}>
                  <strong>{variant.angle || `Variante ${index + 1}`}</strong>
                  <p className="preserve-text">{variant.text}</p>
                  <button
                    disabled={entry.status !== "succeeded"}
                    className="button secondary small"
                    onClick={() => onSelect(variant.text, entry.id)}
                  >
                    Diese Fassung übernehmen
                  </button>
                </article>
              ))}
            </details>
          ))
        ) : (
          <p className="small muted">
            Noch keine KI-Aufträge. Neue Varianten und Überarbeitungen bleiben
            hier nach dem Neuladen verfügbar.
          </p>
        )}
      </details>
    </section>
  );
}
