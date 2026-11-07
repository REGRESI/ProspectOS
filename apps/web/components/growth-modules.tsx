"use client";
import { FormEvent, useCallback, useState } from "react";
import Image from "next/image";
import {
  Plus,
  Upload,
  Check,
  ImageIcon,
  Palette,
  ListTodo,
  StickyNote,
  Send,
  ShieldCheck,
  CalendarDays,
  Users,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  ArrowRight,
} from "lucide-react";
import { request, dateTime } from "@/lib/api";
import type { Page, Contact } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Modal, Spinner } from "./ui";
export type Write = <T>(
  path: string,
  body?: unknown,
  method?: string,
) => Promise<T>;
export type ModuleProps = {
  base: string;
  write: Write;
  notify: (s: string) => void;
  revision: number;
  onChange: () => void;
  csrf: string;
};
export type Asset = {
  title?: string; description?: string; tags?: string[]; rights_note?: string; uploaded_by?: string | null;
  id: string;
  filename: string;
  content_type: string;
  size: number;
  alt_text: string;
  created_at: string;
  url: string;
};
export type Brand = {
  id: string;
  name: string;
  voice: string;
  audience: string;
  pillars: string[];
  primary_color: string;
};
type Task = {
  id: string;
  title: string;
  due_at: string | null;
  state: string;
  contact_id: string | null;
};
type Note = {
  id: string;
  body: string;
  contact_id: string | null;
  created_at: string;
};
type Campaign = {
  id: string;
  name: string;
  goal: string;
  status: string;
  contacts: number;
};
type Job = {
  id: string;
  kind: string;
  status: string;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  created_at: string;
  result: Record<string, unknown>;
};
function Pager({
  page,
  total,
  onPage,
}: {
  page: number;
  total: number;
  onPage: (page: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total} Einträge · Seite {page}
      </span>
      <div>
        <button
          className="icon-button"
          aria-label="Vorherige Seite"
          disabled={page === 1}
          onClick={() => onPage(page - 1)}
        >
          <ChevronLeft size={18} />
        </button>
        <button
          className="icon-button"
          aria-label="Nächste Seite"
          disabled={page * 25 >= total}
          onClick={() => onPage(page + 1)}
        >
          <ChevronRight size={18} />
        </button>
      </div>
    </div>
  );
}
export function AssetLibrary({
  base,
  csrf,
  notify,
  revision,
  onChange,
}: ModuleProps) {
  const [page, setPage] = useState(1);
  const { data, error, loading } = useData<Page<Asset>>(
    `${base}/assets?page=${page}&limit=25`,
    revision,
  );
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const close = useCallback(() => setOpen(false), []);
  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setLocalError("");
    const body = new FormData(event.currentTarget);
    body.set("file", file);
    body.set("rights_confirmed", "true");
    try {
      await request(`${base}/assets/upload`, { method: "POST", body }, csrf);
      onChange();
      close();
      setFile(null);
      notify(
        "Bild sicher gespeichert. Nur Mitglieder dieses Workspaces können es aufrufen.",
      );
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="DEINE VISUELLE HANDSCHRIFT"
        title="Bilder"
        description="Deine Bilder für Beiträge, mit Beschreibung und Nutzungsrechten."
      >
        <button className="button primary" onClick={() => setOpen(true)}>
          <Upload size={16} /> Bild hochladen
        </button>
      </Heading>
      <ErrorNote message={error} />
      {loading ? (
        <div className="loading-block">
          <Spinner />
        </div>
      ) : data?.items.length ? (
        <>
          <div className="asset-grid">
            {data.items.map((asset) => (
              <article className="panel asset-card" key={asset.id}>
                <div className="asset-image">
                  <Image
                    unoptimized
                    width={480}
                    height={320}
                    src={`/api${asset.url}`}
                    alt={asset.alt_text}
                  />
                </div>
                <div className="asset-info">
                  <h2 title={asset.filename}>{asset.filename}</h2>
                  <p>{asset.alt_text}</p>
                  <div>
                    <Badge tone="green">
                      <ShieldCheck size={11} /> Privat
                    </Badge>
                    <small>
                      {Math.ceil(asset.size / 1024)} KB ·{" "}
                      {asset.content_type.replace("image/", "").toUpperCase()}
                    </small>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <Pager page={page} total={data.total} onPage={setPage} />
        </>
      ) : (
        <section className="panel">
          <Empty
            icon={ImageIcon}
            title="Deine Marke verdient eigene Bilder."
            description="Lade dein erstes Bild hoch. Es bleibt privat und steht dir beim Beitrag schreiben zur Verfügung."
          >
            <button className="button primary" onClick={() => setOpen(true)}>
              <Upload size={16} /> Erstes Bild hochladen
            </button>
          </Empty>
        </section>
      )}
      {open && (
        <Modal title="Bild sicher hochladen" onClose={close}>
          <form className="modal-body" onSubmit={upload}>
            <label className="upload-zone">
              <ImageIcon size={30} />
              <strong>{file?.name || "Bild auswählen"}</strong>
              <span>PNG, JPEG oder WebP · keine SVG-Dateien</span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                required
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <label>
              Bildbeschreibung / Alt-Text
              <textarea
                name="alt_text"
                required
                maxLength={1000}
                rows={3}
                placeholder="Beschreibe, was auf dem Bild zu sehen ist."
              />
            </label>
            <label className="checkbox-label">
              <input type="checkbox" name="rights_confirmed" required />
              Ich verfüge über die nötigen Rechte, dieses Bild im Workspace zu
              nutzen.
            </label>
            <ErrorNote message={localError} />
            <div className="form-actions">
              <button
                className="button secondary"
                type="button"
                onClick={close}
              >
                Abbrechen
              </button>
              <button className="button primary" disabled={!file || busy}>
                {busy ? <Spinner /> : <Upload size={16} />} Privat speichern
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
export function BrandProfiles({
  base,
  write,
  notify,
  revision,
  onChange,
}: ModuleProps) {
  const { data, error, loading } = useData<Page<Brand>>(
    `${base}/brands?limit=100`,
    revision,
  );
  const [editing, setEditing] = useState<Brand | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");
  const close = useCallback(() => {
    setOpen(false);
    setEditing(null);
    setLocalError("");
  }, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    setBusy(true);
    setLocalError("");
    try {
      await write(
        editing ? `/brands/${editing.id}` : "/brands",
        {
          name: f.get("name"),
          voice: f.get("voice"),
          audience: f.get("audience"),
          pillars: String(f.get("pillars") || "")
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          primary_color: f.get("primary_color"),
        },
        editing ? "PUT" : "POST",
      );
      onChange();
      close();
      notify("Markenprofil gespeichert.");
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="KONSISTENT AUFTRETEN"
        title="Markenprofile"
        description="Zielgruppe, Ton und Themen deiner Marke an einem Ort."
      >
        <button className="button primary" onClick={() => setOpen(true)}>
          <Plus size={16} /> Markenprofil
        </button>
      </Heading>
      <ErrorNote message={error} />
      {loading ? (
        <Spinner />
      ) : data?.items.length ? (
        <div className="brand-grid">
          {data.items.map((brand) => (
            <article className="panel brand-card" key={brand.id}>
              <div className="brand-card-header">
                <span
                  className="brand-color"
                  style={{ background: brand.primary_color }}
                >
                  {brand.name.slice(0, 1)}
                </span>
                <Badge tone="purple">Markenprofil</Badge>
              </div>
              <h2>{brand.name}</h2>
              <span className="eyebrow">FÜR WEN</span>
              <p>{brand.audience || "Noch keine Zielgruppe hinterlegt."}</p>
              <span className="eyebrow">WIE WIR KLINGEN</span>
              <p>{brand.voice || "Noch keine Tonalität hinterlegt."}</p>
              <div className="pillar-tags">
                {brand.pillars.map((pillar) => (
                  <Badge key={pillar}>{pillar}</Badge>
                ))}
              </div>
              <button
                className="button secondary"
                onClick={() => {
                  setEditing(brand);
                  setOpen(true);
                }}
              >
                Profil bearbeiten <ArrowRight size={14} />
              </button>
            </article>
          ))}
        </div>
      ) : (
        <section className="panel">
          <Empty
            icon={Palette}
            title="Was macht deine Marke aus?"
            description="Definiere deine Stimme und die Themen, für die du stehen möchtest."
          >
            <button className="button primary" onClick={() => setOpen(true)}>
              Erstes Markenprofil anlegen
            </button>
          </Empty>
        </section>
      )}
      {open && (
        <Modal
          title={editing ? "Markenprofil bearbeiten" : "Deine Marke definieren"}
          onClose={close}
        >
          <form className="modal-body" onSubmit={save}>
            <label>
              Markenname
              <input
                name="name"
                defaultValue={editing?.name}
                required
                maxLength={120}
              />
            </label>
            <label>
              Zielgruppe
              <textarea
                name="audience"
                defaultValue={editing?.audience}
                rows={3}
                maxLength={2000}
                placeholder="Wen möchtest du erreichen?"
              />
            </label>
            <label>
              Tonalität
              <textarea
                name="voice"
                defaultValue={editing?.voice}
                rows={3}
                maxLength={2000}
                placeholder="z. B. klar, nahbar, fachkundig – ohne Floskeln"
              />
            </label>
            <label>
              Content-Säulen (kommagetrennt)
              <input
                name="pillars"
                defaultValue={editing?.pillars.join(", ")}
                placeholder="Team, Fachwissen, Einblicke"
                maxLength={1000}
              />
            </label>
            <label>
              Markenfarbe
              <input
                name="primary_color"
                className="color-input"
                type="color"
                defaultValue={editing?.primary_color || "#6854d9"}
              />
            </label>
            <ErrorNote message={localError} />
            <div className="form-actions">
              <button
                type="button"
                className="button secondary"
                onClick={close}
              >
                Abbrechen
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? <Spinner /> : <Check size={16} />} Markenprofil
                speichern
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
export function TaskNotes({
  base,
  write,
  notify,
  revision,
  onChange,
}: ModuleProps) {
  const [tab, setTab] = useState<"tasks" | "notes">("tasks");
  const [page, setPage] = useState(1);
  const tasks = useData<Page<Task>>(
    `${base}/tasks?page=${page}&limit=25`,
    revision,
  );
  const notes = useData<Page<Note>>(
    `${base}/notes?page=${page}&limit=25`,
    revision,
  );
  const contacts = useData<Page<Contact>>(
    `${base}/contacts?limit=100`,
    revision,
  );
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const close = useCallback(() => {
    setOpen(false);
    setError("");
  }, []);
  const person = (id: string | null) => {
    const c = contacts.data?.items.find((c) => c.id === id);
    return c
      ? `${c.first_name} ${c.last_name}`
      : id
        ? "Verknüpfter Kontakt"
        : "Ohne Kontaktzuordnung";
  };
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(event.currentTarget);
    const contact = String(f.get("contact_id") || "");
    try {
      await write(`/${tab}`, {
        ...(tab === "tasks"
          ? {
              title: f.get("title"),
              due_at: f.get("due_at")
                ? new Date(String(f.get("due_at"))).toISOString()
                : null,
            }
          : { body: f.get("body") }),
        ...(contact ? { contact_id: contact } : {}),
      });
      onChange();
      close();
      notify(tab === "tasks" ? "Aufgabe angelegt." : "Notiz gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="DEN FADEN BEHALTEN"
        title="Aufgaben"
        description="Nächste Schritte und Notizen zu deinen Kontakten."
      >
        <button className="button primary" onClick={() => setOpen(true)}>
          <Plus size={16} /> {tab === "tasks" ? "Aufgabe" : "Notiz"} hinzufügen
        </button>
      </Heading>
      <section className="panel">
        <div className="table-toolbar">
          <div className="module-tabs">
            <button
              aria-pressed={tab === "tasks"}
              className={tab === "tasks" ? "active" : ""}
              onClick={() => {
                setTab("tasks");
                setPage(1);
              }}
            >
              <ListTodo size={16} /> Aufgaben
            </button>
            <button
              aria-pressed={tab === "notes"}
              className={tab === "notes" ? "active" : ""}
              onClick={() => {
                setTab("notes");
                setPage(1);
              }}
            >
              <StickyNote size={16} /> Notizen
            </button>
          </div>
        </div>
        <ErrorNote message={tab === "tasks" ? tasks.error : notes.error} />
        {(tab === "tasks" ? tasks.loading : notes.loading) ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : tab === "tasks" ? (
          tasks.data?.items.length ? (
            <div className="task-list">
              {tasks.data.items.map((task) => (
                <article
                  className={`task-row ${task.state === "done" ? "completed" : ""}`}
                  key={task.id}
                >
                  <button
                    className="task-toggle"
                    aria-label={
                      task.state === "done"
                        ? `Aufgabe ${task.title} wieder öffnen`
                        : `Aufgabe ${task.title} erledigen`
                    }
                    aria-pressed={task.state === "done"}
                    onClick={async () => {
                      try {
                        await write(
                          `/tasks/${task.id}`,
                          { state: task.state === "done" ? "open" : "done" },
                          "PATCH",
                        );
                        onChange();
                        notify("Aufgabenstatus aktualisiert.");
                      } catch (e) {
                        notify((e as Error).message);
                      }
                    }}
                  >
                    {task.state === "done" && <Check size={15} />}
                  </button>
                  <div>
                    <h2>{task.title}</h2>
                    <p>
                      {person(task.contact_id)}
                      {task.due_at && (
                        <>
                          {" "}
                          · <CalendarDays size={11} /> {dateTime(task.due_at)}
                        </>
                      )}
                    </p>
                  </div>
                  <Badge tone={task.state === "done" ? "green" : "neutral"}>
                    {task.state === "done" ? "Erledigt" : "Offen"}
                  </Badge>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              icon={ListTodo}
              title="Platz für den nächsten Schritt."
              description="Lege deine erste Aufgabe an – mit optionalem Kontakt und Fälligkeit."
            />
          )
        ) : notes.data?.items.length ? (
          <div className="note-list">
            {notes.data.items.map((note) => (
              <article className="note-card" key={note.id}>
                <div>
                  <span className="activity-icon">
                    <StickyNote size={17} />
                  </span>
                  <span>{person(note.contact_id)}</span>
                  <small>{dateTime(note.created_at)}</small>
                </div>
                <p>{note.body}</p>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            icon={StickyNote}
            title="Kontext macht den Unterschied."
            description="Halte Erkenntnisse und Gesprächsnotizen für dein Team fest."
          />
        )}
        <Pager
          page={page}
          total={(tab === "tasks" ? tasks.data?.total : notes.data?.total) || 0}
          onPage={setPage}
        />
      </section>
      {open && (
        <Modal
          title={tab === "tasks" ? "Neue Aufgabe" : "Neue Notiz"}
          onClose={close}
        >
          <form className="modal-body" onSubmit={create}>
            {tab === "tasks" ? (
              <>
                <label>
                  Aufgabentitel
                  <input
                    name="title"
                    required
                    maxLength={200}
                    placeholder="z. B. Nächstes Gespräch vorbereiten"
                  />
                </label>
                <label>
                  Fällig am (lokale Browser-Zeitzone)
                  <input name="due_at" type="datetime-local" />
                </label>
              </>
            ) : (
              <label>
                Notiz
                <textarea
                  name="body"
                  rows={6}
                  required
                  maxLength={5000}
                  placeholder="Was möchtest du festhalten?"
                />
              </label>
            )}
            <label>
              Kontakt (optional)
              <select name="contact_id">
                <option value="">Keine Zuordnung</option>
                {contacts.data?.items.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.first_name} {c.last_name} · {c.company}
                  </option>
                ))}
              </select>
              <small className="muted">
                Auswahl der ersten 100 Kontakte im Workspace.
              </small>
            </label>
            <ErrorNote message={error} />
            <div className="form-actions">
              <button
                type="button"
                className="button secondary"
                onClick={close}
              >
                Abbrechen
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? <Spinner /> : <Check size={16} />} Speichern
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
export function Campaigns({
  base,
  write,
  notify,
  revision,
  onChange,
}: ModuleProps) {
  const [page, setPage] = useState(1);
  const { data, error, loading } = useData<Page<Campaign>>(
    `${base}/campaigns?page=${page}&limit=25`,
    revision,
  );
  const contacts = useData<Page<Contact>>(
    `${base}/contacts?limit=100`,
    revision,
  );
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const close = useCallback(() => {
    setOpen(false);
    setSelected([]);
    setLocalError("");
  }, []);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    setBusy(true);
    setLocalError("");
    try {
      await write("/campaigns", {
        name: f.get("name"),
        goal: f.get("goal"),
        status: "draft",
        contact_ids: selected,
      });
      onChange();
      close();
      notify(
        "Kampagne als Entwurf gespeichert. Keine Nachricht wurde versendet.",
      );
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="BEZIEHUNGEN MIT RICHTUNG"
        title="Kampagnen"
        description="Kontakte gruppieren und Gesprächsentwürfe vorbereiten."
      >
        <button className="button primary" onClick={() => setOpen(true)}>
          <Plus size={16} /> Kampagne erstellen
        </button>
      </Heading>
      <div className="provider-notice">
        <ShieldCheck size={23} />
        <div>
          <strong>Entwürfe sind keine Versandfreigabe.</strong>
          <span>
            {" "}
            Kampagnen strukturieren deine Arbeit. Es werden keine
            LinkedIn-Nachrichten oder E-Mails automatisch versendet.
          </span>
        </div>
        <Badge>Manueller Workflow</Badge>
      </div>
      <ErrorNote message={error} />
      {loading ? (
        <Spinner />
      ) : data?.items.length ? (
        <section className="panel">
          <div className="campaign-list">
            {data.items.map((campaign) => (
              <article className="campaign-card" key={campaign.id}>
                <span className="step-icon purple">
                  <Send size={20} />
                </span>
                <div className="campaign-info">
                  <h2>{campaign.name}</h2>
                  <p>{campaign.goal || "Kein Ziel hinterlegt."}</p>
                  <small>
                    <Users size={12} /> {campaign.contacts} Kontakte · Kein
                    automatischer Versand
                  </small>
                </div>
                <div className="campaign-actions">
                  <label>
                    Status
                    <select
                      aria-label={`Status von ${campaign.name}`}
                      value={campaign.status}
                      onChange={async (e) => {
                        try {
                          await write(
                            `/campaigns/${campaign.id}`,
                            { status: e.target.value },
                            "PATCH",
                          );
                          onChange();
                          notify("Kampagnenstatus gespeichert.");
                        } catch (e) {
                          notify((e as Error).message);
                        }
                      }}
                    >
                      {Object.entries({
                        draft: "Entwurf",
                        active: "Aktiv",
                        paused: "Pausiert",
                        completed: "Abgeschlossen",
                      }).map(([key, value]) => (
                        <option key={key} value={key}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    className="button secondary small"
                    disabled={busy || !campaign.contacts}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        const result = await write<{
                          created: number;
                          notice: string;
                        }>(`/campaigns/${campaign.id}/drafts`);
                        notify(
                          `${result.created} Entwürfe erstellt. ${result.notice}`,
                        );
                      } catch (e) {
                        notify((e as Error).message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    <Send size={13} /> Offline-Entwürfe
                  </button>
                </div>
              </article>
            ))}
          </div>
          <Pager page={page} total={data.total} onPage={setPage} />
        </section>
      ) : (
        <section className="panel">
          <Empty
            icon={Send}
            title="Deine erste Kampagne beginnt mit einem Ziel."
            description="Wähle passende Kontakte und halte fest, welches Gespräch du starten möchtest."
          >
            <button className="button primary" onClick={() => setOpen(true)}>
              Erste Kampagne erstellen
            </button>
          </Empty>
        </section>
      )}
      {open && (
        <Modal title="Neue Kampagne planen" onClose={close} wide>
          <form className="modal-body" onSubmit={create}>
            <div className="form-grid">
              <label>
                Kampagnenname
                <input name="name" required maxLength={120} />
              </label>
              <label>
                Gesprächsziel
                <input
                  name="goal"
                  maxLength={500}
                  placeholder="z. B. Bedarf im persönlichen Gespräch verstehen"
                />
              </label>
            </div>
            <div className="section-title">
              <h3>Kontakte auswählen</h3>
              <Badge tone="purple">{selected.length} ausgewählt</Badge>
            </div>
            <p className="small muted">
              Erste 100 Kontakte. Eine Auswahl erteilt keine Erlaubnis zum
              Werbeversand.
            </p>
            <div className="contact-choice-list">
              {contacts.data?.items.length ? (
                contacts.data.items.map((contact) => (
                  <label className="contact-choice" key={contact.id}>
                    <input
                      type="checkbox"
                      checked={selected.includes(contact.id)}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, contact.id]
                            : selected.filter((id) => id !== contact.id),
                        )
                      }
                    />
                    <span>
                      <strong>
                        {contact.first_name} {contact.last_name}
                      </strong>
                      <small>{contact.company || "Kein Unternehmen"}</small>
                    </span>
                  </label>
                ))
              ) : (
                <p className="muted small">
                  Lege zuerst Kontakte an oder importiere sie per CSV.
                </p>
              )}
            </div>
            <ErrorNote message={localError} />
            <div className="form-actions">
              <button
                className="button secondary"
                type="button"
                onClick={close}
              >
                Abbrechen
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? <Spinner /> : <Check size={16} />} Kampagne speichern
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
export function Operations({
  base,
  write,
  notify,
  revision,
  onChange,
}: ModuleProps) {
  const [page, setPage] = useState(1);
  const jobs = useData<Page<Job>>(
    `${base}/jobs?page=${page}&limit=25`,
    revision,
  );
  const usage = useData<{
    ai_spent_minor: number;
    ai_budget_minor: number;
    ai_reserved_minor: number;
    spent_usd: number;
    spent_estimated_usd: number;
    reserved_usd: number;
    budget_usd: number;
    available_usd: number;
  }>(`${base}/usage`, revision);
  const money = (v: number) =>
    new Intl.NumberFormat("de-DE", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 2,
      maximumFractionDigits: v > 0 && v < 1 ? 4 : 2,
    }).format(v);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function budget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const form = new FormData(event.currentTarget);
      await write(
        "/usage/budget",
        { ai_budget_minor: Math.round(Number(form.get("budget")) * 100) },
        "PUT",
      );
      onChange();
      notify("Budget gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="TRANSPARENZ IM BETRIEB"
        title="Kosten"
        description="Was die KI diesen Monat gekostet hat, dein Budget und alle Hintergrundaufträge."
      >
        <button className="button secondary" onClick={onChange}>
          <RefreshCw size={16} /> Aktualisieren
        </button>
      </Heading>
      <ErrorNote message={error || usage.error || jobs.error} />
      <div className="usage-grid">
        <section className="panel usage-card">
          <span>Verbraucht</span>
          <strong>{usage.data ? money(usage.data.spent_usd) : "—"}</strong>
          <small>
            Tatsächliche Kosten laut Anbieter
            {usage.data && usage.data.spent_estimated_usd > 0
              ? `, davon ${money(usage.data.spent_estimated_usd)} geschätzt`
              : ""}
          </small>
        </section>
        <section className="panel usage-card">
          <span>Reserviert</span>
          <strong>{usage.data ? money(usage.data.reserved_usd) : "—"}</strong>
          <small>Obergrenze laufender Aufrufe, wird danach freigegeben</small>
        </section>
        <section className="panel usage-card">
          <span>Budget</span>
          <strong>{usage.data ? money(usage.data.budget_usd) : "—"}</strong>
          <small>Konfigurierter Kostenrahmen</small>
        </section>
      </div>
      {usage.data && (
        <form className="panel budget-form" onSubmit={budget}>
          <div>
            <h2>Monatsbudget für KI</h2>
            <p>
              Ist das Budget erreicht, pausieren alle KI-Aufträge bis zum nächsten Monat.
            </p>
          </div>
          <label>
            Budget in US-Dollar
            <input
              name="budget"
              type="number"
              min={0}
              max={100000}
              step="0.01"
              defaultValue={usage.data.ai_budget_minor / 100}
              required
            />
          </label>
          <button className="button secondary" disabled={busy}>
            Budget speichern
          </button>
        </form>
      )}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Hintergrundaufträge</h2>
            <p>Nur tatsächlich angelegte Aufträge erscheinen hier.</p>
          </div>
        </div>
        {jobs.loading ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : jobs.data?.items.length ? (
          <div className="job-list">
            {jobs.data.items.map((job) => (
              <article className="job-row" key={job.id}>
                <div className="section-title">
                  <h3>{job.kind}</h3>
                  <Badge
                    tone={
                      job.status === "succeeded"
                        ? "green"
                        : job.status === "failed"
                          ? "red"
                          : "neutral"
                    }
                  >
                    {job.status}
                  </Badge>
                </div>
                <p>
                  {dateTime(job.created_at)} · Versuch {job.attempts}/
                  {job.max_attempts}
                </p>
                {job.last_error && (
                  <p className="error-note">{job.last_error}</p>
                )}
                {Object.keys(job.result || {}).length > 0 && (
                  <details>
                    <summary>Ergebnis ansehen</summary>
                    <pre>{JSON.stringify(job.result, null, 2)}</pre>
                  </details>
                )}
                {job.status === "failed" && job.attempts < job.max_attempts && (
                  <button
                    className="button secondary small"
                    onClick={async () => {
                      try {
                        await write(`/jobs/${job.id}/retry`);
                        onChange();
                        notify("Auftrag erneut eingeplant.");
                      } catch (e) {
                        notify((e as Error).message);
                      }
                    }}
                  >
                    <RefreshCw size={13} /> Erneut versuchen
                  </button>
                )}
              </article>
            ))}
          </div>
        ) : (
          <Empty
            icon={RefreshCw}
            title="Keine Hintergrundaufträge"
            description="Sobald eine unterstützte Aktion einen Auftrag startet, erscheint ihr Verlauf hier."
          />
        )}
        <Pager page={page} total={jobs.data?.total || 0} onPage={setPage} />
      </section>
    </>
  );
}
export function OutreachDrafts({ base, notify, revision }: ModuleProps) {
  const [page, setPage] = useState(1);
  const { data, error, loading } = useData<
    Page<{
      id: string;
      contact_id: string;
      content: string;
      source: string;
      send_allowed: boolean;
      reason: string;
    }>
  >(`${base}/outreach/drafts?page=${page}&limit=25`, revision);
  return (
    <>
      <Heading
        eyebrow="PERSÖNLICH VORBEREITET"
        title="Entwürfe"
        description="Gespeicherte Nachrichtenentwürfe. Nichts wird automatisch gesendet."
      />
      <div className="provider-notice">
        <ShieldCheck size={23} />
        <div>
          <strong>Manueller Übergabepunkt.</strong>
          <span>
            {" "}
            Prüfe Anlass, Inhalt und zulässige Kontaktaufnahme selbst. Ein
            Entwurf erlaubt keinen Werbeversand.
          </span>
        </div>
        <Badge>Kein Versand</Badge>
      </div>
      <ErrorNote message={error} />
      {loading ? (
        <Spinner />
      ) : data?.items.length ? (
        <section className="panel">
          <div className="draft-grid">
            {data.items.map((draft) => (
              <article className="outreach-card" key={draft.id}>
                <Badge tone="purple">
                  {draft.source === "offline"
                    ? "Offline-Vorschlag"
                    : draft.source}
                </Badge>
                <p>{draft.content}</p>
                <small>{draft.reason}</small>
                <button
                  className="button secondary small"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(draft.content);
                      notify("Entwurf kopiert. Es wurde nichts versendet.");
                    } catch {
                      notify(
                        "Kopieren nicht verfügbar. Bitte Text markieren und kopieren.",
                      );
                    }
                  }}
                >
                  Entwurf kopieren
                </button>
              </article>
            ))}
          </div>
          <Pager page={page} total={data.total} onPage={setPage} />
        </section>
      ) : (
        <section className="panel">
          <Empty
            icon={Send}
            title="Noch keine Gesprächsentwürfe"
            description="Erstelle einen Entwurf im Kontaktdetail oder für die Kontakte einer Kampagne."
          />
        </section>
      )}
    </>
  );
}
