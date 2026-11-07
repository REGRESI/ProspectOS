"use client";
import { IntegrationCredentials } from "./integration-credentials";
import { MailboxManager } from "./email-outreach";
import { useState, useCallback, FormEvent } from "react";
import { Building2, Check, ChevronLeft, ChevronRight, Plus, Search, ShieldCheck, Sparkles, Target } from "lucide-react";
import { Badge, Empty, Modal, Spinner, Heading, ErrorNote } from "./ui";
import { ProviderChecks } from "./workspace-settings";
import { useData } from "@/lib/use-data";
import { request, money, dateTime, stageLabels } from "@/lib/api";
import type { Contact, Page, Deal, Activity } from "@/lib/api";
import type { Write } from "./workspace-contacts";

export function Pipeline({
  base,
  write,
  notify,
  revision,
  onChange,
}: {
  base: string;
  write: Write;
  notify: (s: string) => void;
  revision: number;
  onChange: () => void;
}) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("created");
  const [view, setView] = useState("board");
  const [detail, setDetail] = useState<{
    id: string;
    title: string;
    amount: number;
    stage: string;
    contact: { id: string; name: string } | null;
    company: { id: string; name: string } | null;
    tasks: {
      id: string;
      title: string;
      state: string;
      due_at: string | null;
    }[];
    notes: { id: string; body: string; created_at: string }[];
    notice: string;
  } | null>(null);
  const { data, error, loading } = useData<
    Page<Deal> & { open_value: number; won_value: number }
  >(
    `${base}/deals?limit=100&page=${page}&search=${encodeURIComponent(search)}&sort=${sort}`,
    revision,
  );
  async function moveDeal(id: string, stage: string) {
    try {
      await write(`/deals/${id}`, { stage }, "PATCH");
      onChange();
      notify("Phase aktualisiert.");
    } catch (e) {
      notify((e as Error).message);
    }
  }
  async function inspectDeal(id: string) {
    try {
      setDetail(await request(`${base}/deals/${id}/context`));
    } catch (e) {
      notify((e as Error).message);
    }
  }
  const [open, setOpen] = useState(false);
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [stageFilter, setStageFilter] = useState("all");
  const contacts = useData<Page<Contact>>(
    `${base}/contacts?limit=100`,
    revision,
  );
  const stages = Object.keys(stageLabels).filter((s) => s !== "lost");
  const close = useCallback(() => setOpen(false), []);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const f = new FormData(event.currentTarget);
    setBusy(true);
    try {
      const contact = String(f.get("contact_id") || "");
      await write("/deals", {
        title: f.get("title"),
        amount: Math.round(Number(f.get("value")) * 100),
        stage: "new",
        ...(contact ? { contact_id: contact } : {}),
      });
      setOpen(false);
      onChange();
      notify("Verkaufschance angelegt.");
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="CRM / PIPELINE"
        title="Pipeline"
        description="Phasen, Werte und nächste Schritte. Verschiebe Karten per Drag-and-drop oder nutze die tastaturbedienbare Phasenauswahl."
      >
        <button className="button primary" onClick={() => setOpen(true)}>
          <Plus size={17} /> Verkaufschance
        </button>
      </Heading>
      <div className="pipeline-summary">
        <div>
          <span>Offener Pipeline-Wert</span>
          <strong>{money(data?.open_value || 0)}</strong>
        </div>
        <div>
          <span>Verkaufschancen</span>
          <strong>{data?.total ?? "—"}</strong>
        </div>
        <div>
          <span>Gewonnen</span>
          <strong>{money(data?.won_value || 0)}</strong>
        </div>
        <label className="pipeline-filter">
          Ansicht
          <select
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
          >
            <option value="all">Alle aktiven Phasen</option>
            {Object.entries(stageLabels).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="pipeline-toolbar">
        <label>
          Verkaufschancen suchen
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            maxLength={200}
          />
        </label>
        <label>
          Sortierung
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="created">Zuletzt angelegt</option>
            <option value="amount">Höchster Wert</option>
            <option value="title">Titel A–Z</option>
          </select>
        </label>
        <div className="calendar-views">
          <button
            className={view === "board" ? "active" : ""}
            onClick={() => setView("board")}
          >
            Kanban
          </button>
          <button
            className={view === "list" ? "active" : ""}
            onClick={() => setView("list")}
          >
            Listenansicht
          </button>
        </div>
      </div>
      <ErrorNote message={error} />
      {loading ? (
        <div className="loading-block">
          <Spinner />
        </div>
      ) : view === "list" ? (
        <section className="panel">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Verkaufschance</th>
                  <th>Wert</th>
                  <th>Phase</th>
                </tr>
              </thead>
              <tbody>
                {data?.items
                  .filter(
                    (d) => stageFilter === "all" || d.stage === stageFilter,
                  )
                  .map((deal) => (
                    <tr key={deal.id}>
                      <td>
                        <button
                          className="journey-link"
                          onClick={() => inspectDeal(deal.id)}
                        >
                          {deal.title}
                        </button>
                      </td>
                      <td>{money(deal.amount)}</td>
                      <td>
                        <select
                          aria-label={`Phase ändern ${deal.title}`}
                          value={deal.stage}
                          onChange={(e) => moveDeal(deal.id, e.target.value)}
                        >
                          {Object.entries(stageLabels).map(([key, value]) => (
                            <option key={key} value={key}>
                              {value}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <div className="kanban">
          {(stageFilter === "all" ? stages : [stageFilter]).map((stage, i) => {
            const items = data?.items.filter((d) => d.stage === stage) || [];
            return (
              <section
                className="kanban-column"
                key={stage}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const id = e.dataTransfer.getData(
                    "application/prospectos-deal",
                  );
                  if (id) void moveDeal(id, stage);
                }}
              >
                <div className="kanban-head">
                  <span className={`stage-dot stage-${i % 4}`} />
                  <h2>{stageLabels[stage]}</h2>
                  <span>{items.length}</span>
                </div>
                <div className="kanban-total">
                  {money(items.reduce((sum, d) => sum + d.amount, 0))}
                </div>
                {items.map((deal) => (
                  <article
                    className="deal-card"
                    key={deal.id}
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData(
                        "application/prospectos-deal",
                        deal.id,
                      );
                      e.dataTransfer.effectAllowed = "move";
                    }}
                  >
                    <span className="deal-icon">
                      <Building2 size={15} />
                    </span>
                    <h3>
                      <button
                        className="journey-link"
                        onClick={() => inspectDeal(deal.id)}
                      >
                        {deal.title}
                      </button>
                    </h3>
                    <strong>{money(deal.amount)}</strong>
                    <label>
                      Phase ändern
                      <select
                        value={deal.stage}
                        onChange={async (e) => {
                          try {
                            await write(
                              `/deals/${deal.id}`,
                              { stage: e.target.value },
                              "PATCH",
                            );
                            onChange();
                            notify("Phase aktualisiert.");
                          } catch (error) {
                            notify((error as Error).message);
                          }
                        }}
                      >
                        {Object.entries(stageLabels).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </label>
                  </article>
                ))}
                {!items.length && (
                  <p className="kanban-empty">
                    Hier ist Platz für deine
                    <br />
                    nächste Chance.
                  </p>
                )}
              </section>
            );
          })}
        </div>
      )}
      {data && data.total > 100 && (
        <div className="pagination">
          <span>
            Seite {page} · {data.total} Verkaufschancen. Summen über alle
            Suchtreffer.
          </span>
          <div>
            <button
              className="button secondary small"
              disabled={page <= 1}
              onClick={() => setPage(page - 1)}
            >
              Zurück
            </button>
            <button
              className="button secondary small"
              disabled={page * 100 >= data.total}
              onClick={() => setPage(page + 1)}
            >
              Weiter
            </button>
          </div>
        </div>
      )}
      {detail && (
        <Modal title={detail.title} onClose={() => setDetail(null)} wide>
          <div className="modal-body">
            <div className="section-title">
              <strong>{money(detail.amount)}</strong>
              <Badge>{stageLabels[detail.stage]}</Badge>
            </div>
            <div className="journey-company-actions">
              {detail.contact && (
                <a
                  className="button secondary"
                  href={`/contacts?contact=${encodeURIComponent(detail.contact.id)}`}
                >
                  {detail.contact.name} · Kontakt öffnen
                </a>
              )}
              {detail.company && (
                <a
                  className="button secondary"
                  href={`/companies/${encodeURIComponent(detail.company.id)}`}
                >
                  {detail.company.name} · Unternehmen öffnen
                </a>
              )}
            </div>
            <div className="journey-profile-grid">
              <section>
                <h3>Nächste Aufgaben</h3>
                {detail.tasks.length ? (
                  detail.tasks.map((task) => (
                    <div className="journey-task" key={task.id}>
                      <span>
                        <strong>{task.title}</strong>
                        <small>
                          {task.state} ·{" "}
                          {task.due_at ? dateTime(task.due_at) : "Ohne Termin"}
                        </small>
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="muted small">Keine verknüpften Aufgaben.</p>
                )}
              </section>
              <section>
                <h3>Kontaktnotizen</h3>
                {detail.notes.length ? (
                  detail.notes.map((note) => (
                    <div className="journey-evidence" key={note.id}>
                      {note.body}
                      <small>{dateTime(note.created_at)}</small>
                    </div>
                  ))
                ) : (
                  <p className="muted small">Keine verknüpften Notizen.</p>
                )}
              </section>
            </div>
            <p className="small muted">{detail.notice}</p>
          </div>
        </Modal>
      )}
      {open && (
        <Modal title="Neue Verkaufschance" onClose={close}>
          <form className="modal-body" onSubmit={create}>
            <label>
              Titel
              <input
                name="title"
                required
                maxLength={240}
                placeholder="z. B. Büroreinigung · Musterfirma"
              />
            </label>
            <label>
              Kontakt (optional)
              <select name="contact_id">
                <option value="">Kein Kontakt zugeordnet</option>
                {contacts.data?.items.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.first_name} {c.last_name} · {c.company}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Wert in Euro
              <input
                name="value"
                type="number"
                min={0}
                max={100000000}
                step="0.01"
                defaultValue={0}
                required
              />
            </label>
            <ErrorNote message={formError} />
            <div className="form-actions">
              <button
                className="button secondary"
                type="button"
                onClick={close}
              >
                Abbrechen
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? <Spinner /> : <Plus size={16} />} Anlegen
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

export function Integrations({ base, write }: { base: string; write: Write }) {
  const [localError, setLocalError] = useState("");
  const [revision, setRevision] = useState(0);
  const { data, error, loading } = useData<{
    items: {
      name: string;
      status: string;
      reason: string;
      connect_available?: boolean;
      scopes?: string[];
    }[];
  }>(`${base}/integrations`, revision);
  return (
    <>
      <Heading
        eyebrow="BEWUSST VERBUNDEN"
        title="Verbindungen"
        description="Zugänge zu LinkedIn, KI und Suchdiensten. Schlüssel werden verschlüsselt gespeichert und nie angezeigt."
      />
      <div className="info-note integration-intro">
        <ShieldCheck size={22} />
        <p>
          <strong>Keine Verbindung wird simuliert.</strong> Was hier als verbunden
          gilt, ist wirklich verbunden. Den Gesamtstand siehst du unter Status.
        </p>
      </div>
      <ErrorNote message={localError || error} />
      {loading ? (
        <Spinner />
      ) : (
        <div className="integration-grid">
          {data?.items.map((integration) => (
            <section className="panel provider-card" key={integration.name}>
              <div className="section-title">
                <h2>{integration.name}</h2>
                <Badge
                  tone={
                    integration.status === "connected" ? "green" : "neutral"
                  }
                >
                  {(
                    {
                      connected: "Verbunden",
                      configured: "Konfiguriert",
                      available: "Verfügbar",
                      offline: "Offline-Modus",
                      not_configured: "nicht eingerichtet",
                      missing_credentials: "Zugangsdaten fehlen",
                      disabled: "Deaktiviert",
                      expired: "Abgelaufen",
                    } as Record<string, string>
                  )[integration.status] || `Status: ${integration.status}`}
                </Badge>
              </div>
              <p>{integration.reason}</p>
              {integration.name === "LinkedIn" && (
                <div className="form-actions">
                  {integration.status === "connected" ? (
                    <button
                      className="button secondary"
                      onClick={async () => {
                        try {
                          await write("/integrations/linkedin/disconnect");
                          setRevision((v) => v + 1);
                        } catch (e) {
                          setLocalError((e as Error).message);
                        }
                      }}
                    >
                      Verbindung entfernen
                    </button>
                  ) : (
                    <button
                      className="button secondary"
                      disabled={!integration.connect_available}
                      title={
                        integration.connect_available
                          ? "Offiziellen OAuth-Dialog öffnen"
                          : "Operator muss OAuth-Zugang und Token-Verschlüsselung konfigurieren."
                      }
                      onClick={async () => {
                        try {
                          const result = await write<{
                            authorization_url: string;
                          }>("/integrations/linkedin/start");
                          window.location.assign(result.authorization_url);
                        } catch (e) {
                          setLocalError((e as Error).message);
                        }
                      }}
                    >
                      Offiziell mit LinkedIn verbinden
                    </button>
                  )}
                </div>
              )}

              <div className="provider-footer">
                <ShieldCheck size={14} /> Berechtigungen und Anbieterstatus
                werden serverseitig geprüft
              </div>
            </section>
          ))}
        </div>
      )}
      <IntegrationCredentials base={base} write={write} />
      <MailboxManager base={base} write={write} />
      <ProviderChecks write={write} />
      <section className="panel integration-doc">
        <h2>Bereit für den nächsten Schritt?</h2>
        <p>
          Die Voraussetzungen für echte Anbieter stehen in der
          Repository-Dokumentation. LinkedIn benötigt eine offizielle App und
          gewährte Publishing-Berechtigungen. Zugangsdaten gehören in sichere
          Umgebungseinstellungen.
        </p>
        <span className="doc-path">
          docs/LINKEDIN_INTEGRATION.md · docs/OPERATIONS.md
        </span>
      </section>
    </>
  );
}

export function Audit({ base }: { base: string }) {
  const [page, setPage] = useState(1);
  const { data, error, loading } = useData<Page<Activity>>(
    `${base}/audit?page=${page}&limit=25`,
  );
  return (
    <>
      <Heading
        eyebrow="NACHVOLLZIEHBARKEIT"
        title="Verlauf"
        description="Wer wann was geändert hat."
      />
      <ErrorNote message={error} />
      <section className="panel">
        {loading ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : data?.items.length ? (
          <>
            <div className="activity-list audit-list">
              {data.items.map((activity) => (
                <div className="activity-row" key={activity.id}>
                  <span className="activity-icon">
                    <ShieldCheck size={17} />
                  </span>
                  <div>
                    <p>{activity.description}</p>
                    <small>
                      {activity.kind} · {dateTime(activity.created_at)}
                    </small>
                  </div>
                  <Badge>Protokolliert</Badge>
                </div>
              ))}
            </div>
            <div className="pagination">
              <span>
                {data.total} Aktivitäten · Seite {page}
              </span>
              <div>
                <button
                  className="icon-button"
                  aria-label="Vorherige Seite"
                  disabled={page === 1}
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  className="icon-button"
                  aria-label="Nächste Seite"
                  disabled={page * 25 >= data.total}
                  onClick={() => setPage(page + 1)}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          </>
        ) : (
          <Empty
            icon={ShieldCheck}
            title="Noch keine Aktivitäten"
            description="Sobald du Kontakte importierst oder Inhalte bearbeitest, wird es hier sichtbar."
          />
        )}
      </section>
    </>
  );
}

export function Discovery({
  write,
  notify,
  onChange,
}: {
  write: Write;
  notify: (s: string) => void;
  onChange: () => void;
}) {
  const [topic, setTopic] = useState(
    "Büros und Dienstleistungsunternehmen in Offenburg",
  );
  const [result, setResult] = useState<{
    id: string;
    status: string;
    results: {
      external_key: string;
      company: string;
      first_name: string;
      last_name: string;
      job_title: string;
      location: string;
      source: string;
      license: string;
      confidence: string;
      observed_at: string;
    }[];
    notice: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [imported, setImported] = useState(false);
  async function search(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResult(await write("/discovery/runs", { topic }));
      setImported(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function importResults() {
    if (!result) return;
    setBusy(true);
    try {
      const imported = await write<{ created: number }>(
        `/discovery/runs/${result.id}/import`,
      );
      setImported(true);
      onChange();
      notify(`${imported.created} synthetische Kontakte importiert.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="PASSENDE UNTERNEHMEN ENTDECKEN"
        title="Neue Möglichkeiten beginnen hier."
        description="Probiere die Firmensuche mit Beispieldaten aus."
      />
      <div className="provider-notice">
        <Sparkles size={23} />
        <div>
          <strong>Synthetischer Beispielanbieter.</strong>
          <span>
            {" "}
            Kein Datenanbieter verbunden. Die Ergebnisse sind feste, fiktive
            Datensätze und keine recherchierten Treffer zu deiner Anfrage.
          </span>
        </div>
        <Badge tone="purple">Demo-Daten</Badge>
      </div>
      <section className="panel padded">
        <div className="panel-head">
          <div>
            <h2>Dein Recherche-Ziel</h2>
            <p>
              Ein echter Anbieter benötigt separat geprüfte Zugangsdaten und
              Nutzungsrechte.
            </p>
          </div>
          <Target size={22} />
        </div>
        <form onSubmit={search}>
          <label>
            Welche Unternehmen interessieren dich?
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              required
              maxLength={300}
              rows={3}
            />
          </label>
          <div className="form-actions">
            <button className="button primary" disabled={busy || !topic.trim()}>
              {busy ? <Spinner /> : <Search size={16} />} Beispielsuche starten
            </button>
          </div>
        </form>
        <ErrorNote message={error} />
      </section>
      {result && (
        <section className="panel post-list">
          <div className="panel-head">
            <div>
              <h2>{result.results.length} synthetische Beispiele</h2>
              <p>{result.notice}</p>
            </div>
            <button
              className="button primary"
              disabled={busy || imported}
              onClick={importResults}
            >
              {imported ? (
                <>
                  <Check size={16} /> Importiert
                </>
              ) : (
                <>
                  <Plus size={16} /> Beispiele importieren
                </>
              )}
            </button>
          </div>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Fiktives Unternehmen</th>
                  <th>Fiktiver Kontakt</th>
                  <th>Standort</th>
                  <th>Herkunft</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((row) => (
                  <tr key={row.external_key}>
                    <td>
                      <strong>{row.company}</strong>
                    </td>
                    <td>
                      {row.first_name} {row.last_name}
                      <br />
                      <small>{row.job_title}</small>
                    </td>
                    <td>{row.location}</td>
                    <td>
                      <Badge tone="purple">Synthetisch</Badge>
                      <br />
                      <small>
                        {row.source} · {row.license}
                      </small>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
