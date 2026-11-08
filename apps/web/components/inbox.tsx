"use client";
import { FormEvent, useState } from "react";
import { Inbox as InboxIcon, Link2, Mail, MessageSquare, Phone, QrCode, Globe } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { dateTime } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Spinner } from "./ui";
import type { Write } from "./growth-modules";

type Status = "new" | "answered" | "meeting" | "not_interested";
type Reaction = {
  id: string;
  kind: string;
  kind_label: string;
  channel: string;
  text: string;
  code: string | null;
  status: Status;
  status_label: string;
  created_at: string;
  contact: { id: string; name: string; phone: string | null } | null;
  company: { id: string; name: string } | null;
};
const channelIcons: Record<string, LucideIcon> = {
  email: Mail,
  linkedin: Link2,
  letter: QrCode,
  web: Globe,
  phone: Phone,
  manual: MessageSquare,
};
const statusTone: Record<Status, string> = { new: "purple", answered: "neutral", meeting: "green", not_interested: "red" };
const statusOrder: Status[] = ["new", "answered", "meeting", "not_interested"];
const statusLabels: Record<Status, string> = {
  new: "neu",
  answered: "beantwortet",
  meeting: "Termin",
  not_interested: "kein Interesse",
};

export function InboxPage({
  base,
  write,
  notify,
  onNavigate,
}: {
  base: string;
  write: Write;
  notify: (m: string) => void;
  onNavigate?: (path: string) => void;
}) {
  const [revision, setRevision] = useState(0);
  const [filter, setFilter] = useState<"" | Status>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = useData<{ items: Reaction[]; total: number; counts: Record<Status, number> }>(
    `${base}/inbox${filter ? `?status=${filter}` : ""}`,
    revision,
  );
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
  function byCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    void run(async () => {
      await write("/reactions/by-code", { code: String(values.get("code")), text: String(values.get("text") || "") });
      form.reset();
    }, "Anfrage zugeordnet. Alle geplanten Schritte für diesen Kontakt sind gestoppt.");
  }
  const counts = data.data?.counts;
  return (
    <>
      <Heading
        title="Posteingang"
        description="Alle Antworten an einem Ort. Jede Reaktion stoppt die geplanten Schritte dieses Kontakts und legt eine Aufgabe in Heute an."
      />
      <ErrorNote message={error || data.error} />
      <div className="inbox-layout">
        <section className="panel inbox-list" data-testid="inbox">
          <div className="inbox-filters" role="tablist" aria-label="Status">
            <button className={`chip ${filter === "" ? "active" : ""}`} onClick={() => setFilter("")}>
              Alle
            </button>
            {statusOrder.map((s) => (
              <button key={s} className={`chip ${filter === s ? "active" : ""}`} onClick={() => setFilter(s)}>
                {statusLabels[s]} {counts ? `(${counts[s]})` : ""}
              </button>
            ))}
          </div>
          {data.loading && !data.data ? (
            <div className="loading-block">
              <Spinner />
            </div>
          ) : data.data?.items.length ? (
            <ul className="reaction-list">
              {data.data.items.map((r) => {
                const Icon = channelIcons[r.channel] || MessageSquare;
                return (
                  <li key={r.id} className={`reaction status-${r.status}`} data-testid={`reaction-${r.contact?.name}`}>
                    <span className="reaction-icon" aria-hidden>
                      <Icon size={16} />
                    </span>
                    <div className="reaction-main">
                      <div className="reaction-head">
                        <strong>{r.contact?.name || "Unbekannt"}</strong>
                        {r.company && <span className="muted">{r.company.name}</span>}
                        <Badge tone={statusTone[r.status]}>{r.status_label}</Badge>
                      </div>
                      <small className="muted">
                        {r.kind_label} · {dateTime(r.created_at)}
                        {r.code ? ` · Code ${r.code}` : ""}
                      </small>
                      {r.text && <p className="reaction-text">{r.text}</p>}
                      <div className="reaction-actions">
                        <label>
                          Status
                          <select
                            aria-label={`Status für ${r.contact?.name}`}
                            value={r.status}
                            disabled={busy}
                            onChange={(e) =>
                              run(
                                () => write(`/reactions/${r.id}`, { status: e.target.value }, "PATCH"),
                                "Status gespeichert.",
                              )
                            }
                          >
                            {statusOrder.map((s) => (
                              <option key={s} value={s}>
                                {statusLabels[s]}
                              </option>
                            ))}
                          </select>
                        </label>
                        {r.contact?.phone && <span className="flow-task-phone">{r.contact.phone}</span>}
                        <button className="button ghost small" onClick={() => onNavigate?.("/today")}>
                          Zur Aufgabe in Heute
                        </button>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <Empty
              icon={InboxIcon}
              title="Noch keine Antworten"
              description="Sobald jemand antwortet, einen QR-Code scannt oder anfragt, steht es hier."
            />
          )}
        </section>
        <aside className="panel inbox-side">
          <h2>Anfrage mit Code zuordnen</h2>
          <p className="muted">
            Steht in einer Anfrage über die Website ein Code aus dem Brief (z. B. ?ref=K7M2QX9A), trag ihn hier ein.
          </p>
          <form className="form-grid" onSubmit={byCode}>
            <label className="span-2">
              Code
              <input name="code" required minLength={6} maxLength={20} autoCapitalize="characters" />
            </label>
            <label className="span-2">
              Text der Anfrage (optional)
              <textarea name="text" rows={3} maxLength={4000} />
            </label>
            <button className="button primary small" disabled={busy}>
              Zuordnen
            </button>
          </form>
        </aside>
      </div>
    </>
  );
}

/** Small form inside a contact: record a reaction by hand (LinkedIn reply, call, other). */
export function ReactionForm({
  contactId,
  write,
  onDone,
}: {
  contactId: string;
  write: Write;
  onDone: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <details className="evidence-add">
      <summary>Reaktion eintragen</summary>
      <ErrorNote message={error} />
      <form
        className="form-grid"
        onSubmit={async (event) => {
          event.preventDefault();
          const form = event.currentTarget;
          const values = new FormData(form);
          setBusy(true);
          setError("");
          try {
            await write(`/contacts/${contactId}/reactions`, {
              kind: String(values.get("kind")),
              text: String(values.get("text") || ""),
            });
            form.reset();
            onDone("Reaktion gespeichert. Geplante Schritte sind gestoppt, eine Aufgabe steht in Heute.");
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Was ist passiert?
          <select name="kind" defaultValue="linkedin_replied">
            <option value="linkedin_replied">LinkedIn: Antwort</option>
            <option value="linkedin_accepted">LinkedIn: Einladung angenommen</option>
            <option value="phone_call">Anruf erhalten</option>
            <option value="web_inquiry">Anfrage über die Website</option>
            <option value="other">Sonstiges</option>
          </select>
        </label>
        <label className="span-2">
          Antworttext (optional)
          <textarea name="text" rows={3} maxLength={4000} />
        </label>
        <button className="button secondary small" disabled={busy}>
          Speichern
        </button>
      </form>
    </details>
  );
}
