"use client";
import { FormEvent, useState } from "react";
import { CheckCircle2, FileDown, Printer, ScrollText, Tags } from "lucide-react";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Spinner } from "./ui";
import type { Write } from "./growth-modules";

type Letter = {
  id: string;
  contact: { id: string; name: string } | null;
  recipient: string[];
  subject: string;
  body: string;
  code: string;
  qr_url: string;
  state: "draft" | "approved" | "printed" | "cancelled";
  revision: number;
  style_issues: string[];
};
type Settings = Record<
  | "sender_name"
  | "sender_company"
  | "sender_street"
  | "sender_city"
  | "sender_phone"
  | "sender_email"
  | "sender_web"
  | "qr_target_url"
  | "qr_caption"
  | "subject"
  | "body_template"
  | "closing",
  string
> & { fonts: string; print_service_enabled: boolean };
type Listing = {
  items: Letter[];
  counts: Record<string, number>;
  open_letter_tasks: number;
  print_service: { enabled: boolean; options: { name: string; note: string }[] };
};

const stateLabels = { draft: "Entwurf", approved: "freigegeben", printed: "gedruckt", cancelled: "storniert" };
const stateTone = { draft: "neutral", approved: "green", printed: "purple", cancelled: "red" };
const settingFields: [keyof Settings, string, string?][] = [
  ["sender_company", "Firma"],
  ["sender_name", "Unterschrift"],
  ["sender_street", "Straße"],
  ["sender_city", "PLZ und Ort"],
  ["sender_phone", "Telefon"],
  ["sender_email", "E-Mail"],
  ["sender_web", "Website"],
  ["qr_target_url", "Zielseite für den QR-Code", "https://…/reinigungs-check/"],
  ["qr_caption", "Text neben dem QR-Code"],
  ["subject", "Betreff"],
  ["closing", "Gruß"],
];

async function download(path: string, body: unknown, csrf: string, filename: string) {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.message || detail.detail || `Download fehlgeschlagen (${response.status}).`);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function LettersPage({
  base,
  write,
  notify,
  csrf,
}: {
  base: string;
  write: Write;
  notify: (m: string) => void;
  csrf: string;
}) {
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const letters = useData<Listing>(`${base}/letters`, revision);
  const settings = useData<Settings>(`${base}/letters/settings`, revision);
  async function run(fn: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    try {
      await fn();
      setRevision((v) => v + 1);
      notify(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = Object.fromEntries(
      [...settingFields.map(([k]) => k), "body_template"].map((k) => [k, String(form.get(k) || "")]),
    );
    void run(() => write("/letters/settings", body, "PUT"), "Brief-Einstellungen gespeichert.");
  }
  const items = letters.data?.items || [];
  const approved = items.filter((l) => l.state === "approved");
  const drafts = items.filter((l) => l.state === "draft");
  return (
    <>
      <Heading
        title="Briefe"
        description="Persönliche Briefe für Firmen ohne LinkedIn. Mit QR-Code je Firma: ein Scan zeigt Interesse und legt eine Anruf-Aufgabe an."
      />
      <ErrorNote message={error || letters.error} />
      <section className="panel letter-toolbar" data-testid="letter-toolbar">
        <div className="letter-counts">
          <span>
            <strong>{letters.data?.open_letter_tasks ?? "–"}</strong> fällige Brief-Schritte
          </span>
          <span>
            <strong>{drafts.length}</strong> Entwürfe
          </span>
          <span>
            <strong>{approved.length}</strong> freigegeben
          </span>
          <span>
            <strong>{letters.data?.counts.printed ?? 0}</strong> gedruckt
          </span>
        </div>
        <div className="letter-actions">
          <button
            className="button secondary"
            disabled={busy || !letters.data?.open_letter_tasks}
            onClick={() =>
              run(
                () => write<{ created: unknown[] }>("/letters/prepare", { from_tasks: true }),
                "Briefentwürfe aus den fälligen Schritten erstellt.",
              )
            }
          >
            <ScrollText size={15} /> Briefe vorbereiten
          </button>
          <button
            className="button secondary"
            disabled={busy || !drafts.length}
            onClick={() =>
              run(async () => {
                for (const l of drafts) await write(`/letters/${l.id}/approve`);
              }, `${drafts.length} Briefe freigegeben.`)
            }
          >
            <CheckCircle2 size={15} /> Alle Entwürfe freigeben
          </button>
          <button
            className="button primary"
            disabled={busy || !approved.length}
            onClick={() =>
              run(
                () => download(`${base}/letters/print-pdf`, { all_approved: true }, csrf, "briefe-druck.pdf"),
                `Sammel-PDF mit ${approved.length} Briefen geladen.`,
              )
            }
          >
            <FileDown size={15} /> Sammel-PDF
          </button>
          <button
            className="button secondary"
            disabled={busy || !approved.length}
            onClick={() =>
              run(
                () => download(`${base}/letters/labels-pdf`, { all_approved: true }, csrf, "adressetiketten-3474.pdf"),
                "Etiketten (Zweckform 3474) geladen.",
              )
            }
          >
            <Tags size={15} /> Etiketten
          </button>
          <button
            className="button secondary"
            disabled={busy || !approved.length}
            onClick={() =>
              run(() => write("/letters/mark-printed", { all_approved: true }), "Als gedruckt markiert. Die Kampagnen laufen weiter.")
            }
          >
            <Printer size={15} /> Als gedruckt markieren
          </button>
        </div>
      </section>

      <div className="letter-layout">
        <section className="panel letter-list" data-testid="letter-list">
          {letters.loading && !letters.data ? (
            <div className="loading-block">
              <Spinner />
            </div>
          ) : items.length ? (
            <ul>
              {items.map((l) => (
                <li key={l.id} data-testid={`letter-${l.contact?.name}`}>
                  <div className="letter-head">
                    <div>
                      <strong>{l.recipient[0]}</strong>
                      <small className="muted">{l.recipient.slice(1).join(" · ")}</small>
                    </div>
                    <Badge tone={stateTone[l.state]}>{stateLabels[l.state]}</Badge>
                  </div>
                  <small className="muted">
                    Code {l.code} · <a href={`/api${base}/letters/${l.id}/pdf`} target="_blank" rel="noreferrer">Vorschau (PDF)</a>
                  </small>
                  {!!l.style_issues.length && <small className="flow-task-blocked">Stil: {l.style_issues.join(", ")}</small>}
                  {editing === l.id ? (
                    <form
                      className="form-grid"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const form = new FormData(event.currentTarget);
                        void run(async () => {
                          await write(
                            `/letters/${l.id}`,
                            { subject: String(form.get("subject")), body: String(form.get("body")), revision: l.revision },
                            "PATCH",
                          );
                          setEditing(null);
                        }, "Brief geändert. Bitte erneut freigeben.");
                      }}
                    >
                      <label className="span-2">
                        Betreff
                        <input name="subject" defaultValue={l.subject} maxLength={120} required />
                      </label>
                      <label className="span-2">
                        Text
                        <textarea name="body" defaultValue={l.body} rows={8} maxLength={3000} required />
                      </label>
                      <button className="button secondary small" disabled={busy}>
                        Speichern
                      </button>
                    </form>
                  ) : (
                    <p className="letter-body">{l.body}</p>
                  )}
                  {l.state !== "printed" && (
                    <div className="letter-row-actions">
                      <button className="button ghost small" onClick={() => setEditing(editing === l.id ? null : l.id)}>
                        {editing === l.id ? "Abbrechen" : "Bearbeiten"}
                      </button>
                      {l.state === "draft" && (
                        <button
                          className="button secondary small"
                          disabled={busy}
                          onClick={() => run(() => write(`/letters/${l.id}/approve`), "Brief freigegeben.")}
                        >
                          Freigeben
                        </button>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <Empty
              icon={ScrollText}
              title="Noch keine Briefe"
              description="Starte unter Kontakte → Ansprache ein Rezept mit Brief-Weg. Fällige Brief-Schritte werden hier zu Entwürfen."
            />
          )}
        </section>

        <aside className="panel letter-settings">
          <h2>Absender und QR-Code</h2>
          {settings.data ? (
            <form className="form-grid" onSubmit={saveSettings} key={revision}>
              {settingFields.map(([key, label, placeholder]) => (
                <label key={key} className={key === "qr_target_url" ? "span-2" : ""}>
                  {label}
                  <input name={key} defaultValue={settings.data![key] as string} placeholder={placeholder} maxLength={500} />
                </label>
              ))}
              <label className="span-2">
                Brieftext (Platzhalter: {"{evidence}"}, {"{company}"}, {"{sender_company}"}, {"{offer}"}, {"{region}"})
                <textarea name="body_template" defaultValue={settings.data.body_template} rows={7} maxLength={3000} />
              </label>
              <small className="span-2 muted">Schrift: {settings.data.fonts}. Layout nach DIN 5008, eine Seite.</small>
              <button className="button primary small" disabled={busy}>
                Speichern
              </button>
            </form>
          ) : (
            <Spinner />
          )}
          <h3>Druck-und-Versand-Dienst</h3>
          <p className="muted small-print">
            Ausgeschaltet. Vor einer Aktivierung Anbieter, Vertrag zur Auftragsverarbeitung und Kosten prüfen. Mögliche Anbieter:
          </p>
          <ul className="print-options">
            {letters.data?.print_service.options.map((o) => (
              <li key={o.name}>
                <strong>{o.name}</strong>
                <small className="muted">{o.note}</small>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </>
  );
}
