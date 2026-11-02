"use client";
import Image from "next/image";
import { useState } from "react";
import type { Asset, Write } from "./growth-modules";
import { ErrorNote, Spinner } from "./ui";
export type ImageMode = "none" | "ai" | "manual" | "auto" | "random";
export const imageModeLabels: Record<ImageMode, string> = {
  none: "Kein Bild",
  ai: "KI-Bild generieren",
  manual: "Aus Medienbibliothek wählen",
  auto: "Automatisch passendes Bild aus Medienbibliothek wählen",
  random: "Zufälliges Bild aus Medienbibliothek wählen",
};
export function StudioMedia({
  write,
  assets,
  mode,
  onMode,
  onAsset,
  onChange,
  topic,
  brandId,
  voiceId,
  selectedId,
  loading,
}: {
  write: Write;
  assets: Asset[];
  mode: ImageMode;
  onMode: (mode: ImageMode) => void;
  onAsset: (asset: Asset, mode: ImageMode) => void;
  onChange: () => void;
  topic: string;
  brandId: string;
  voiceId: string;
  selectedId: string;
  loading: boolean;
}) {
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Asset | null>(null);
  const visible = assets.filter((asset) =>
    [asset.filename, asset.title, asset.description, ...(asset.tags || [])]
      .join(" ")
      .toLocaleLowerCase("de")
      .includes(query.toLocaleLowerCase("de")),
  );
  return (
    <section className="studio-media">
      <label>
        Bildquelle
        <select
          aria-label="Bildquelle"
          value={mode}
          onChange={(e) => {
            onMode(e.target.value as ImageMode);
            setReason("");
            setError("");
          }}
        >
          {Object.entries(imageModeLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Bild aus privater Bibliothek
        <select
          value={selectedId}
          onChange={(e) => {
            const asset = assets.find((item) => item.id === e.target.value);
            if (asset) onAsset(asset, "manual");
            else onMode("none");
          }}
        >
          <option value="">Textbeitrag ohne Bild</option>
          {assets.map((asset) => (
            <option value={asset.id} key={asset.id}>
              {asset.title || asset.filename}
            </option>
          ))}
        </select>
      </label>
      {mode === "ai" && (
        <p className="small muted">
          Öffne den KI-Assistenten → KI-Bild. Dort kannst du Motiv, Stil und
          Format wählen und das erzeugte Bild vor der Übernahme prüfen.
        </p>
      )}
      {(mode === "auto" || mode === "random") && (
        <>
          <button
            className="button secondary"
            disabled={busy || loading}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                const result = await write<{ asset: Asset; reason: string }>(
                  "/social/media/select",
                  {
                    mode,
                    topic,
                    brand_id: brandId || null,
                    voice_profile_id: voiceId || null,
                  },
                );
                onAsset(result.asset, mode);
                setReason(result.reason);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? <Spinner /> : null}
            {mode === "auto"
              ? "Passendes Bild vorschlagen"
              : "Zufälliges Bild wählen"}
          </button>
          <p className="small muted">
            {reason ||
              "Nur geprüfte Bilder deines Workspaces. Du kannst jeden Vorschlag durch eine manuelle Auswahl ersetzen."}
          </p>
        </>
      )}
      {mode !== "none" && (
        <details open={mode === "manual"}>
          <summary>Mediengalerie · {assets.length} Bilder</summary>
          <label>
            Bilder durchsuchen
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Titel, Beschreibung oder Tags"
            />
          </label>
          {loading ? (
            <Spinner />
          ) : visible.length ? (
            <div className="studio-gallery">
              {visible.map((asset) => (
                <article key={asset.id}>
                  <button
                    className={`gallery-choice ${selectedId === asset.id ? "selected" : ""}`}
                    aria-label={`Bild wählen: ${asset.title || asset.filename}`}
                    aria-pressed={selectedId === asset.id}
                    onClick={() => {
                      onAsset(asset, "manual");
                      setReason("");
                    }}
                  >
                    <Image
                      src={`/api${asset.url}`}
                      unoptimized
                      width={220}
                      height={140}
                      alt={asset.alt_text}
                    />
                    <span>{asset.title || asset.filename}</span>
                    <small>{asset.tags?.join(" · ")}</small>
                  </button>
                  <button
                    className="button secondary small"
                    onClick={() => setEditing(asset)}
                  >
                    Metadaten bearbeiten
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <p className="small muted">
              Keine passenden Bilder. Lade Bilder mit bestätigten Rechten unter
              Medien hoch oder ändere die Suche.
            </p>
          )}
        </details>
      )}
      <ErrorNote message={error} />
      {editing && (
        <form
          className="voice-example"
          onSubmit={async (e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            setBusy(true);
            setError("");
            try {
              const asset = await write<Asset>(
                `/assets/${editing.id}/metadata`,
                {
                  title: form.get("title"),
                  description: form.get("description"),
                  alt_text: form.get("alt_text"),
                  rights_note: form.get("rights_note"),
                  tags: String(form.get("tags") || "")
                    .split(",")
                    .map((tag) => tag.trim())
                    .filter(Boolean),
                },
                "PATCH",
              );
              onChange();
              if (selectedId === asset.id) onAsset(asset, mode);
              setEditing(null);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Bildtitel
            <input name="title" defaultValue={editing.title} maxLength={200} />
          </label>
          <label>
            Beschreibung
            <textarea
              name="description"
              defaultValue={editing.description}
              maxLength={2000}
            />
          </label>
          <label>
            Alternativtext
            <input
              name="alt_text"
              defaultValue={editing.alt_text}
              required
              maxLength={1000}
            />
          </label>
          <label>
            Tags (mit Komma trennen)
            <input
              name="tags"
              defaultValue={editing.tags?.join(", ")}
              maxLength={1000}
            />
          </label>
          <label>
            Quelle / Rechtehinweis
            <input
              name="rights_note"
              defaultValue={editing.rights_note}
              maxLength={1000}
            />
          </label>
          <small>
            Hochgeladen:{" "}
            {new Date(editing.created_at).toLocaleDateString("de-DE")}
            {editing.uploaded_by
              ? ` · Nutzer ${editing.uploaded_by.slice(0, 8)}`
              : " · älteres Bibliotheksbild"}
          </small>
          <div className="form-actions">
            <button className="button primary small" disabled={busy}>
              Metadaten speichern
            </button>
            <button
              type="button"
              className="button secondary small"
              onClick={() => setEditing(null)}
            >
              Schließen
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
