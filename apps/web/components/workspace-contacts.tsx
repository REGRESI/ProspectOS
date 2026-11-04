"use client";
import { useEffect, useState, useCallback, FormEvent } from "react";
import { ArrowRight, ArrowUpRight, Building2, Check, ChevronLeft, ChevronRight, CircleHelp, Copy, Plus, Search, ShieldCheck, Sparkles, Target, Upload, X, ExternalLink } from "lucide-react";
import { Badge, Empty, Modal, Spinner, Heading, ErrorNote } from "./ui";
import { OperationalHome } from "./operational-home";
import { useData } from "@/lib/use-data";
import { request, number, stageLabels } from "@/lib/api";
import type { Contact, Page, Icp, Preview } from "@/lib/api";

export type Write = <T>(path: string, body?: unknown, method?: string) => Promise<T>;

export function Overview({
  base,
  revision,
  name,
  go,
  openImport,
}: {
  base: string;
  revision: number;
  name: string;
  go: (path: string) => void;
  openImport: () => void;
}) {
  return (
    <OperationalHome
      base={base}
      revision={revision}
      name={name}
      go={go}
      openImport={openImport}
    />
  );
}

export function Contacts({
  base,
  revision,
  write,
  notify,
  openImport,
  onChange,
}: {
  base: string;
  revision: number;
  write: Write;
  notify: (s: string) => void;
  openImport: () => void;
  onChange: () => void;
}) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Contact | null>(null);
  const [add, setAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [draft, setDraft] = useState("");
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(search);
      setPage(1);
    }, 250);
    return () => clearTimeout(t);
  }, [search]);
  const { data, error, loading } = useData<Page<Contact>>(
    `${base}/contacts?search=${encodeURIComponent(query)}&page=${page}&limit=25`,
    revision,
  );
  const close = useCallback(() => {
    setSelected(null);
    setAdd(false);
    setDraft("");
    setFormError("");
  }, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    const f = new FormData(event.currentTarget);
    const fields = Object.fromEntries(f.entries());
    try {
      await write(
        selected ? `/contacts/${selected.id}` : "/contacts",
        { ...fields, ...(selected ? { version: selected.version } : {}) },
        selected ? "PATCH" : "POST",
      );
      onChange();
      close();
      notify(selected ? "Kontakt aktualisiert." : "Kontakt angelegt.");
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="DEINE KONTAKTBASIS"
        title="Aus Kontakten werden Verbindungen."
        description="Alle relevanten Menschen, ihr Kontext und dein nächster Schritt."
      >
        <button className="button secondary" onClick={openImport}>
          <Upload size={16} /> CSV importieren
        </button>
        <button className="button primary" onClick={() => setAdd(true)}>
          <Plus size={17} /> Kontakt hinzufügen
        </button>
      </Heading>
      <div className="panel contacts-panel">
        <div className="table-toolbar">
          <div className="tabs">
            <span className="tab active">
              Alle Kontakte <span>{data?.total ?? "—"}</span>
            </span>
          </div>
          <div className="search-box">
            <Search size={16} />
            <input
              aria-label="Kontakte suchen"
              placeholder="Name, Unternehmen, Ort suchen …"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button
                className="icon-button"
                aria-label="Suche löschen"
                onClick={() => setSearch("")}
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>
        <ErrorNote message={error} />
        {loading ? (
          <div className="loading-block">
            <Spinner /> Kontakte laden …
          </div>
        ) : data?.items.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Kontakt</th>
                    <th>Unternehmen</th>
                    <th>Position</th>
                    <th>Standort</th>
                    <th>
                      ICP-Fit <CircleHelp size={12} />
                    </th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((contact, i) => (
                    <tr key={contact.id} onClick={() => setSelected(contact)}>
                      <td>
                        <button
                          className="person-cell"
                          onClick={() => setSelected(contact)}
                        >
                          <span className={`contact-avatar avatar-${i % 5}`}>
                            {contact.first_name?.[0]}
                            {contact.last_name?.[0]}
                          </span>
                          <span>
                            <strong>
                              {contact.first_name} {contact.last_name}
                            </strong>
                            <small>
                              {contact.email || "Keine E-Mail hinterlegt"}
                            </small>
                          </span>
                        </button>
                      </td>
                      <td>
                        <span className="company-cell">
                          {contact.company || "—"}
                        </span>
                      </td>
                      <td>{contact.job_title || "—"}</td>
                      <td>{contact.location || "Unbekannt"}</td>
                      <td>
                        <span
                          className={`score ${contact.score.value >= 65 ? "high" : contact.score.value >= 35 ? "medium" : "low"}`}
                          title="Deterministischer ICP-Fit, keine Kaufwahrscheinlichkeit"
                        >
                          <span />
                          {contact.score.value} <small>/100</small>
                        </span>
                      </td>
                      <td>
                        <Badge
                          tone={
                            contact.status === "qualified" ? "green" : "neutral"
                          }
                        >
                          {contact.status === "archived"
                            ? "Archiviert"
                            : stageLabels[contact.status] || contact.status}
                        </Badge>
                      </td>
                      <td>
                        <ArrowUpRight size={15} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <span>
                {number(data.total)} Kontakte · Seite {page} von{" "}
                {Math.max(1, Math.ceil(data.total / 25))}
              </span>
              <div>
                <button
                  className="icon-button"
                  disabled={page === 1}
                  aria-label="Vorherige Seite"
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  className="icon-button"
                  disabled={page * 25 >= data.total}
                  aria-label="Nächste Seite"
                  onClick={() => setPage(page + 1)}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          </>
        ) : (
          <Empty
            title={
              query
                ? "Keine passenden Kontakte"
                : "Dein nächster guter Kontakt wartet."
            }
            description={
              query
                ? "Versuche einen anderen Namen, Ort oder Unternehmensnamen."
                : "Importiere deine erste CSV-Datei oder lege einen Kontakt manuell an."
            }
          >
            <button
              className="button primary"
              onClick={query ? () => setSearch("") : openImport}
            >
              {query ? (
                "Suche zurücksetzen"
              ) : (
                <>
                  <Upload size={16} /> Kontakte importieren
                </>
              )}
            </button>
          </Empty>
        )}
      </div>
      <p className="data-caption">
        <ShieldCheck size={13} /> Fehlende Daten bleiben unbekannt. Ein
        ICP-Score ist keine Kaufwahrscheinlichkeit.
      </p>
      {(selected || add) && (
        <Modal
          title={selected ? "Kontakt im Detail" : "Neuen Kontakt anlegen"}
          onClose={close}
          wide
        >
          <div className="modal-body">
            <form onSubmit={save}>
              <div className="form-grid">
                <label>
                  Vorname
                  <input
                    name="first_name"
                    defaultValue={selected?.first_name}
                    required
                    maxLength={120}
                  />
                </label>
                <label>
                  Nachname
                  <input
                    name="last_name"
                    defaultValue={selected?.last_name}
                    required
                    maxLength={120}
                  />
                </label>
                <label>
                  Unternehmen
                  <input
                    name="company"
                    defaultValue={selected?.company}
                    maxLength={240}
                  />
                </label>
                <label>
                  Position
                  <input
                    name="job_title"
                    defaultValue={selected?.job_title}
                    maxLength={240}
                  />
                </label>
                <label>
                  Standort
                  <input
                    name="location"
                    defaultValue={selected?.location}
                    maxLength={240}
                  />
                </label>
                <label>
                  Status
                  <select
                    name="status"
                    defaultValue={selected?.status || "new"}
                  >
                    {Object.entries({
                      new: "Neu",
                      qualified: "Qualifiziert",
                      contacted: "Kontaktiert",
                      archived: "Archiviert",
                    }).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  E-Mail (optional)
                  <input
                    name="email"
                    type="email"
                    defaultValue={selected?.email || ""}
                  />
                </label>
                <label>
                  Telefon (optional)
                  <input name="phone" defaultValue={selected?.phone || ""} />
                </label>
                <label className="full-width">
                  LinkedIn-Profil (optional)
                  <input
                    name="linkedin_url"
                    type="url"
                    defaultValue={selected?.linkedin_url || ""}
                    placeholder="https://www.linkedin.com/in/…"
                  />
                </label>
              </div>
              <ErrorNote message={formError} />
              <div className="form-actions">
                <button
                  className="button secondary"
                  type="button"
                  onClick={close}
                >
                  Schließen
                </button>
                <button className="button primary" disabled={saving}>
                  {saving ? <Spinner /> : <Check size={16} />} Speichern
                </button>
              </div>
            </form>
            {selected && (
              <>
                <section className="detail-section">
                  <div className="section-title">
                    <h3>ICP-Fit verstehen</h3>
                    <Badge tone="purple">{selected.score.value} / 100</Badge>
                  </div>
                  <div className="score-factors">
                    {selected.score.factors.map((f) => (
                      <div key={f.name}>
                        <span>
                          <strong>{f.name}</strong>
                          <b>
                            {f.points}/{f.max_points}
                          </b>
                        </span>
                        <div className="factor-track">
                          <span
                            style={{
                              width: `${f.max_points ? (f.points / f.max_points) * 100 : 0}%`,
                            }}
                          />
                        </div>
                        <small>{f.reason}</small>
                      </div>
                    ))}
                  </div>
                  {selected.score.missing_data.length > 0 && (
                    <p className="muted">
                      Unbekannt: {selected.score.missing_data.join(", ")}
                    </p>
                  )}
                  <small className="muted">
                    Quelle: {selected.source} · Fit-Score, keine Kaufabsicht.
                  </small>
                </section>
                <section className="detail-section">
                  <h3>Gespräch vorbereiten</h3>
                  <p className="muted">
                    Offline-Entwurf aus vorhandenen Kontaktdaten. Es wird keine
                    Nachricht versendet.
                  </p>
                  <button
                    className="button secondary"
                    onClick={async () => {
                      try {
                        const result = await write<{ content: string }>(
                          "/outreach/drafts",
                          { contact_id: selected.id },
                        );
                        setDraft(result.content);
                        notify("Offline-Entwurf erstellt. Kein Versand.");
                      } catch (e) {
                        setFormError((e as Error).message);
                      }
                    }}
                  >
                    <Sparkles size={16} /> Gesprächsentwurf erstellen
                  </button>
                  {draft && (
                    <>
                      <textarea
                        aria-label="Nachrichtenentwurf"
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        rows={5}
                      />
                      <div className="form-actions">
                        <button
                          className="button secondary"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(draft);
                              notify("Entwurf kopiert.");
                            } catch {
                              notify(
                                "Kopieren nicht verfügbar. Text bitte markieren und kopieren.",
                              );
                            }
                          }}
                        >
                          <Copy size={14} /> Kopieren
                        </button>
                        {selected.linkedin_url && (
                          <a
                            className="button secondary"
                            target="_blank"
                            rel="noopener noreferrer"
                            href={selected.linkedin_url}
                          >
                            Profil manuell öffnen <ExternalLink size={14} />
                          </a>
                        )}
                      </div>
                    </>
                  )}
                </section>
              </>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}

export function ImportModal({
  base,
  csrf,
  onClose,
  onDone,
}: {
  base: string;
  csrf: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function inspect() {
    if (!file) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("file", file);
    if (Object.keys(mapping).length)
      form.append("mapping", JSON.stringify(mapping));
    try {
      const result = await request<Preview>(
        `${base}/imports/preview`,
        { method: "POST", body: form },
        csrf,
      );
      setPreview(result);
      setMapping(result.mapping);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function commit() {
    if (!preview) return;
    setBusy(true);
    try {
      await request(
        `${base}/imports/${preview.id}/commit`,
        { method: "POST", body: "{}" },
        csrf,
      );
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Kontakte aus CSV importieren" onClose={onClose} wide>
      <div className="modal-body">
        <div className="import-progress">
          <span className="done">
            1 <b>Datei auswählen</b>
          </span>
          <i />
          <span className={preview ? "done" : ""}>
            2 <b>Prüfen & zuordnen</b>
          </span>
          <i />
          <span>
            3 <b>Importieren</b>
          </span>
        </div>
        <p className="muted">
          UTF-8, auch mit BOM. Komma, Semikolon und Tab werden erkannt. Fehlende
          E-Mails und Domains sind erlaubt.
        </p>
        <label className="upload-zone">
          <Upload size={30} />
          <strong>{file?.name || "Deine CSV-Datei auswählen"}</strong>
          <span>Nur rechtmäßig erhobene Daten importieren · maximal 3 MB</span>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              setPreview(null);
              setMapping({});
            }}
          />
        </label>
        <ErrorNote message={error} />
        {preview && (
          <>
            <div className="import-totals">
              <div>
                <strong>{preview.total}</strong>
                <small>Zeilen insgesamt</small>
              </div>
              <div>
                <strong>{preview.valid}</strong>
                <small>Gültige Zeilen</small>
              </div>
              <div>
                <strong>{preview.duplicates}</strong>
                <small>Dubletten</small>
              </div>
              <div>
                <strong>{preview.invalid}</strong>
                <small>Mit Fehlern</small>
              </div>
            </div>
            <details className="mapping">
              <summary>Spaltenzuordnung bearbeiten</summary>
              <div className="form-grid">
                {Object.entries(mapping).map(([key, value]) => (
                  <label key={key}>
                    {key}
                    <select
                      value={value}
                      onChange={(e) =>
                        setMapping({ ...mapping, [key]: e.target.value })
                      }
                    >
                      <option value="">Nicht importieren</option>
                      {preview.headers.map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <button
                className="button secondary"
                onClick={inspect}
                disabled={busy}
              >
                Zuordnung neu prüfen
              </button>
            </details>
            <div className="table-scroll preview-table">
              <table>
                <thead>
                  <tr>
                    <th>Zeile</th>
                    <th>Kontakt</th>
                    <th>Unternehmen</th>
                    <th>Prüfung</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.slice(0, 8).map((row) => (
                    <tr key={row.row}>
                      <td>{row.row}</td>
                      <td>
                        {row.first_name} {row.last_name}
                      </td>
                      <td>{row.company || "—"}</td>
                      <td>
                        {row.errors.length ? (
                          <Badge tone="red">{row.errors.join(", ")}</Badge>
                        ) : row.duplicate ? (
                          <Badge>Dubletten-Kandidat</Badge>
                        ) : (
                          <Badge tone="green">Gültig</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small">
              Vorschau der ersten {Math.min(preview.rows.length, 8)} Zeilen.
              Erkannte Dubletten werden nicht erneut angelegt; fehlerhafte
              Zeilen werden übersprungen.
            </p>
          </>
        )}
        <div className="form-actions">
          <button className="button secondary" onClick={onClose}>
            Abbrechen
          </button>
          {preview ? (
            <button
              className="button primary"
              onClick={commit}
              disabled={busy || preview.valid === 0}
            >
              {busy ? <Spinner /> : <Check size={16} />} Gültige Kontakte
              importieren
            </button>
          ) : (
            <button
              className="button primary"
              onClick={inspect}
              disabled={!file || busy}
            >
              {busy ? <Spinner /> : <ArrowRight size={16} />} Datei prüfen
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}

export function Companies({ base, revision }: { base: string; revision: number }) {
  const [page, setPage] = useState(1);
  const { data, error, loading } = useData<
    Page<{
      id: string;
      name: string;
      location?: string;
      city?: string;
      domain?: string;
      contact_count?: number;
    }>
  >(`${base}/companies?page=${page}&limit=25`, revision);
  return (
    <>
      <Heading
        eyebrow="UNTERNEHMENSKONTEXT"
        title="Die Unternehmen hinter deinen Kontakten."
        description="Aus importierten und manuell angelegten Kontakten – ohne erfundene Firmendaten."
      />
      <ErrorNote message={error} />
      <section className="panel">
        {loading ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : data?.items.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Unternehmen</th>
                    <th>Standort</th>
                    <th>Domain</th>
                    <th>Kontakte</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((company) => (
                    <tr key={company.id}>
                      <td>
                        <div className="person-cell">
                          <span className="contact-avatar avatar-1">
                            <Building2 size={18} />
                          </span>
                          <strong>{company.name}</strong>
                        </div>
                      </td>
                      <td>{company.location || company.city || "Unbekannt"}</td>
                      <td>{company.domain || "Nicht hinterlegt"}</td>
                      <td>{company.contact_count ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <span>
                {data.total} Unternehmen · Seite {page}
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
            icon={Building2}
            title="Noch keine Unternehmen"
            description="Unternehmen werden zusammen mit deinen Kontakten angelegt."
          />
        )}
      </section>
    </>
  );
}

export function Audiences({
  base,
  write,
  notify,
  onChange,
}: {
  base: string;
  write: Write;
  notify: (s: string) => void;
  onChange: () => void;
}) {
  const { data, error, loading } = useData<Icp>(`${base}/icp`);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const split = (key: string) =>
      String(form.get(key) || "")
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);
    const weights = {
      location: Number(form.get("location_weight")),
      role: Number(form.get("role_weight")),
      industry: Number(form.get("industry_weight")),
    };
    if (Object.values(weights).reduce((a, b) => a + b, 0) !== 100) {
      setSaveError("Die Gewichtungen müssen zusammen genau 100 ergeben.");
      return;
    }
    setBusy(true);
    setSaveError("");
    try {
      await write(
        "/icp",
        {
          name: form.get("name"),
          locations: split("locations"),
          roles: split("roles"),
          industries: split("industries"),
          weights,
        },
        "PUT",
      );
      onChange();
      notify(
        "ICP gespeichert. Scores werden mit den neuen Kriterien berechnet.",
      );
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="KLARHEIT VOR REICHWEITE"
        title="Wer passt wirklich zu dir?"
        description="Definiere dein ideales Kundenprofil. Jeder Fit-Score bleibt nachvollziehbar."
      />
      <div className="icp-layout">
        <section className="panel padded">
          <div className="panel-head">
            <div>
              <h2>Dein ideales Kundenprofil</h2>
              <p>Kriterien als kommagetrennte Begriffe eingeben.</p>
            </div>
            <span className="step-icon purple">
              <Target size={22} />
            </span>
          </div>
          <ErrorNote message={error || saveError} />
          {loading ? (
            <Spinner />
          ) : (
            data && (
              <form onSubmit={save}>
                <label>
                  Profilname
                  <input name="name" defaultValue={data.name} required />
                </label>
                <label>
                  Standorte
                  <input
                    name="locations"
                    defaultValue={data.locations.join(", ")}
                    placeholder="Offenburg, Freiburg, Karlsruhe"
                  />
                </label>
                <label>
                  Relevante Positionen
                  <input
                    name="roles"
                    defaultValue={data.roles.join(", ")}
                    placeholder="Geschäftsführer, Office, Facility"
                  />
                </label>
                <label>
                  Branchen
                  <input
                    name="industries"
                    defaultValue={data.industries.join(", ")}
                    placeholder="Optional – nur belegte Branchendaten werden gewertet"
                  />
                </label>
                <h3 className="weight-heading">
                  Gewichtung · insgesamt 100 Punkte
                </h3>
                <div className="form-grid weights">
                  <label>
                    Standort
                    <input
                      type="number"
                      name="location_weight"
                      min={0}
                      max={100}
                      defaultValue={data.weights.location}
                      required
                    />
                  </label>
                  <label>
                    Position
                    <input
                      type="number"
                      name="role_weight"
                      min={0}
                      max={100}
                      defaultValue={data.weights.role}
                      required
                    />
                  </label>
                  <label>
                    Branche
                    <input
                      type="number"
                      name="industry_weight"
                      min={0}
                      max={100}
                      defaultValue={data.weights.industry}
                      required
                    />
                  </label>
                </div>
                <div className="form-actions">
                  <button className="button primary" disabled={busy}>
                    {busy ? <Spinner /> : <Check size={16} />} Kundenprofil
                    speichern
                  </button>
                </div>
              </form>
            )
          )}
        </section>
        <aside className="panel icp-explainer">
          <span className="large-icon">
            <ShieldCheck size={30} />
          </span>
          <h2>
            Fit erklären.
            <br />
            Nichts erfinden.
          </h2>
          <p>
            Der Score zeigt, wie gut bekannte Kontaktdaten zu deinen Kriterien
            passen.
          </p>
          <ul>
            <li>Jeder Faktor hat eine sichtbare Begründung.</li>
            <li>Fehlende Informationen bleiben unbekannt.</li>
            <li>Keine erfundene Firmengröße oder Kaufabsicht.</li>
            <li>Ein hoher Score ist keine Versandfreigabe.</li>
          </ul>
          <Badge tone="purple">Deterministisches Scoring · v1</Badge>
        </aside>
      </div>
    </>
  );
}
