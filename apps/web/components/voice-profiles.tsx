"use client";
import { useState, type FormEvent } from "react";
import { useData } from "@/lib/use-data";
import type { Write } from "./growth-modules";
import { ErrorNote, Modal, Spinner } from "./ui";

const defaults = {
  name: "",
  description: "",
  perspective: "Ich",
  tone: "direkt, persönlich",
  formality: "Du",
  emoji: "wenig",
  sentence_style: "gemischt",
  cta: "Frage",
  preferences: "kurze Absätze, natürlich und menschlich",
  banned_patterns:
    "keine typischen KI-Floskeln, keine übertriebene Werbesprache",
  instructions: "keine erfundenen Fakten",
  no_em_dash: true,
  platform: "LinkedIn",
  examples: [] as { label: string; text: string }[],
};
export type Voice = typeof defaults & {
  id: string;
  version: number;
  created_at?: string;
};
const choices = [
  ["perspective", "Perspektive", ["Ich", "Wir", "neutral"]],
  ["formality", "Ansprache", ["Du", "Sie", "neutral"]],
  ["emoji", "Emojis im Profil", ["keine", "wenig", "mittel", "mehr"]],
  ["sentence_style", "Satzlänge", ["kurz", "mittel", "gemischt"]],
  ["cta", "CTA im Profil", ["Frage", "soft CTA", "direkter CTA", "kein CTA"]],
] as const;
const textFields = [
  ["description", "Beschreibung"],
  ["tone", "Stimme / Ton"],
  ["preferences", "Stilvorlieben"],
  ["banned_patterns", "Verbotene Muster"],
  ["instructions", "Schreibanweisungen"],
] as const;

export function VoiceProfiles({
  base,
  write,
  value,
  onSelect,
  revision,
  onChange,
}: {
  base: string;
  write: Write;
  value: string;
  onSelect: (id: string) => void;
  revision: number;
  onChange: () => void;
}) {
  const voices = useData<{ items: Voice[] }>(`${base}/social/voices`, revision);
  const [editing, setEditing] = useState<Voice | "new" | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [examples, setExamples] = useState<{ label: string; text: string }[]>(
    [],
  );
  const selected = voices.data?.items.find((voice) => voice.id === value);
  const source = editing && editing !== "new" ? editing : defaults;
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    const settings = {
      ...defaults,
      ...Object.fromEntries(form),
      no_em_dash: form.get("no_em_dash") === "on",
      examples,
    };
    try {
      const result = await write<Voice>(
        editing !== "new" && editing
          ? `/social/voices/${editing.id}`
          : "/social/voices",
        {
          ...settings,
          ...(editing !== "new" && editing ? { version: editing.version } : {}),
        },
        editing === "new" ? "POST" : "PUT",
      );
      onSelect(result.id);
      onChange();
      setEditing(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="voice-workspace">
      <div className="form-grid">
        <label>
          Schreibprofil
          <select
            aria-label="Schreibprofil"
            value={value}
            onChange={(e) => onSelect(e.target.value)}
          >
            <option value="">Ohne Schreibprofil</option>
            {voices.data?.items.map((voice) => (
              <option value={voice.id} key={voice.id}>
                {voice.name}
              </option>
            ))}
          </select>
        </label>
        <div className="form-actions">
          <button
            className="button secondary small"
            onClick={() => {
              setEditing("new");
              setExamples([]);
              setError("");
            }}
          >
            Schreibprofil erstellen
          </button>
          {selected && (
            <button
              className="button secondary small"
              onClick={() => {
                setEditing(selected);
                setExamples(selected.examples);
                setError("");
              }}
            >
              Profil bearbeiten
            </button>
          )}
        </div>
      </div>
      <ErrorNote message={voices.error} />
      {voices.loading ? (
        <Spinner />
      ) : selected ? (
        <p className="small muted">
          {selected.tone} · {selected.perspective} · {selected.examples.length}{" "}
          Stilbeispiele ·{" "}
          {selected.no_em_dash ? "Ohne Gedankenstrich" : "Freie Zeichensetzung"}
        </p>
      ) : (
        <p className="small muted">
          Deine Stimme speichern und für neue Beiträge wiederverwenden. Auch
          ohne Markenprofil möglich.
        </p>
      )}
      {editing && (
        <Modal
          title={
            editing === "new"
              ? "Schreibprofil erstellen"
              : "Schreibprofil bearbeiten"
          }
          onClose={() => setEditing(null)}
          wide
        >
          <form className="modal-body" onSubmit={save}>
            <ErrorNote message={error} />
            <label>
              Profilname
              <input
                name="name"
                defaultValue={source.name}
                required
                maxLength={120}
              />
            </label>
            <div className="form-grid">
              {choices.map(([key, label, options]) => (
                <label key={key}>
                  {label}
                  <select name={key} defaultValue={source[key]}>
                    {options.map((option) => (
                      <option key={option}>{option}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            {textFields.map(([key, label]) => (
              <label key={key}>
                {label}
                <textarea
                  name={key}
                  defaultValue={source[key]}
                  rows={2}
                  maxLength={
                    key === "instructions" ? 1000 : key === "tone" ? 200 : 500
                  }
                />
              </label>
            ))}
            <label className="checkbox-line">
              <input
                name="no_em_dash"
                type="checkbox"
                defaultChecked={source.no_em_dash}
              />{" "}
              Kein Gedankenstrich
            </label>
            <h3>Eigene Beispielbeiträge</h3>
            <p className="small muted">
              Nur als Orientierung für Ton und Rhythmus. Die KI darf Beispiele
              weder kopieren noch eng paraphrasieren oder als Faktenquelle
              nutzen.
            </p>
            {examples.map((example, index) => (
              <div className="voice-example" key={index}>
                <label>
                  Beispiel {index + 1} · Bezeichnung
                  <input
                    value={example.label}
                    maxLength={80}
                    placeholder="z. B. persönlicher Ton"
                    onChange={(e) =>
                      setExamples(
                        examples.map((item, i) =>
                          i === index
                            ? { ...item, label: e.target.value }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  Beispiel {index + 1} · Beitrag
                  <textarea
                    required
                    minLength={3}
                    maxLength={1500}
                    rows={4}
                    value={example.text}
                    onChange={(e) =>
                      setExamples(
                        examples.map((item, i) =>
                          i === index
                            ? { ...item, text: e.target.value }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
                <button
                  type="button"
                  className="button secondary small"
                  onClick={() =>
                    setExamples(examples.filter((_, i) => i !== index))
                  }
                >
                  Beispiel entfernen
                </button>
              </div>
            ))}
            <button
              type="button"
              disabled={examples.length >= 3}
              className="button secondary small"
              onClick={() =>
                setExamples([...examples, { label: "", text: "" }])
              }
            >
              Beispiel hinzufügen
            </button>
            <div className="form-actions">
              <button className="button primary" disabled={busy}>
                Schreibprofil speichern
              </button>
              {editing !== "new" && (
                <button
                  type="button"
                  className="button secondary"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await write(
                        `/social/voices/${editing.id}`,
                        undefined,
                        "DELETE",
                      );
                      if (value === editing.id) onSelect("");
                      onChange();
                      setEditing(null);
                    } catch (e) {
                      setError((e as Error).message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Profil löschen
                </button>
              )}
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}
