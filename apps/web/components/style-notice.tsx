"use client";
import { useState } from "react";
import { PenLine } from "lucide-react";
import { useData } from "@/lib/use-data";
import { ErrorNote, Spinner } from "./ui";
import type { Write } from "./growth-modules";

export type StyleStatus = {
  state: "missing" | "empty" | "ok";
  path: string;
  samples: number;
  rules: string[];
  voice_profile_id: string | null;
  in_sync: boolean;
  hint: string | null;
  stats: { avg_words_per_sentence: number; formality: string } | null;
};

/** Writing-style status from data/private/meine-texte.md with a clear next step. */
export function StyleNotice({ base, write, compact = false }: { base: string; write: Write; compact?: boolean }) {
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const status = useData<StyleStatus>(`${base}/style`, revision);
  const s = status.data;
  if (!s) return null;
  async function sync() {
    setBusy(true);
    setError("");
    try {
      await write("/style/sync");
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (s.state === "ok" && s.in_sync && compact) return null;
  if (compact)
    return (
      <p className="style-line" data-testid="style-notice">
        <PenLine size={14} />
        <span>
          {s.state === "ok"
            ? "Deine Beispieltexte haben sich geändert."
            : "Die Texte klingen noch nicht nach dir: Es sind noch keine eigenen Beispieltexte hinterlegt."}
        </span>
        <button className="link-button" disabled={busy} onClick={sync}>
          {busy ? "Wird übernommen …" : "Aus Datei übernehmen"}
        </button>
        {error && <span className="error-inline">{error}</span>}
      </p>
    );
  return (
    <section className={`style-notice ${s.state === "ok" ? "ok" : "todo"}`} data-testid="style-notice">
      <PenLine size={16} />
      <div>
        {s.state === "ok" ? (
          <>
            <strong>
              Schreibstil aus {s.path}: {s.samples} Texte
              {s.stats ? `, Ø ${s.stats.avg_words_per_sentence} Wörter pro Satz, ${s.stats.formality}` : ""}
            </strong>
            {!s.in_sync && <p>Die Datei hat sich geändert. Bitte neu übernehmen, damit alle Texte den aktuellen Stil nutzen.</p>}
          </>
        ) : (
          <>
            <strong>{s.state === "missing" ? "Noch keine eigenen Texte hinterlegt" : "Die Datei mit deinen Texten ist leer"}</strong>
            <p>{s.hint}</p>
          </>
        )}
        {!compact && (
          <ul className="style-rules">
            {s.rules.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        )}
        <ErrorNote message={error} />
        {(s.state === "ok" && !s.in_sync) || s.state !== "ok" ? (
          <button className="button secondary small" disabled={busy} onClick={sync}>
            {busy ? <Spinner /> : "Aus Datei übernehmen"}
          </button>
        ) : null}
      </div>
    </section>
  );
}
