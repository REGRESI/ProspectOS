"use client";
import { FormEvent, useState } from "react";
import { ArrowRight, Building2, ExternalLink, FileText, Filter, History, ListFilter, Plus, Search, Users } from "lucide-react";
import { dateTime, stageLabels } from "@/lib/api";
import type { Page } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Modal, Spinner } from "./ui";
import type { JourneyProps, Lead, LeadFilters, Company, Campaign, Draft } from "./journey-types";
import { initialLeadFilters, list } from "./journey-types";
import { Pager, Progress, ScoreDetails, useQuery } from "./journey-shared";

export function LeadDatabase(props: JourneyProps) {
  const {
    base,
    write,
    csrf,
    notify,
    onChange,
    revision,
    onImport,
    onNavigate,
  } = props;
  const [filters, setFilters] = useState<LeadFilters>(() => ({
    ...initialLeadFilters,
    icp_id:
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("icp")
        : null,
  }));
  const [advanced, setAdvanced] = useState(false);
  const [selection, setSelection] = useState<string[]>([]);
  const [active, setActive] = useState<string | null>(() =>
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("contact")
      : null,
  );
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [localRevision, setLocalRevision] = useState(0);
  const [segmentName, setSegmentName] = useState("");
  const [segmentId, setSegmentId] = useState("");
  const [bulkTag, setBulkTag] = useState("");
  const [bulkStatus, setBulkStatus] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const leads = useQuery<Page<Lead>>(
    base,
    filters,
    csrf,
    revision + localRevision,
  );
  const segments = useData<
    Page<{ id: string; name: string; filters: LeadFilters }>
  >(`${base}/segments?limit=100`, revision + localRevision);
  const campaigns = useData<Page<Campaign>>(
    `${base}/campaigns?limit=100`,
    revision + localRevision,
  );
  const profiles = useData<Page<{ id: string; name: string }>>(
    `${base}/icp-profiles?limit=100`,
    revision + localRevision,
  );
  const refresh = () => {
    setLocalRevision((v) => v + 1);
    onChange();
  };
  const change = <K extends keyof LeadFilters>(
    key: K,
    value: LeadFilters[K],
  ) => {
    setFilters((old) => ({ ...old, [key]: value, page: 1 }));
    setSelection([]);
    setSegmentId("");
  };
  async function bulk() {
    setBusy(true);
    setError("");
    try {
      const r = await write<{ updated: number; enrolled: number }>(
        "/leads/bulk",
        {
          contact_ids: selection,
          ...(bulkStatus ? { status: bulkStatus } : {}),
          tags_add: bulkTag
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          tags_remove: [],
          ...(campaignId ? { campaign_id: campaignId } : {}),
        },
      );
      notify(
        `${r.updated} Kontakte aktualisiert · ${r.enrolled} Kampagnenzuordnungen`,
      );
      setSelection([]);
      setBulkTag("");
      setBulkStatus("");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function saveSegment() {
    setBusy(true);
    setError("");
    try {
      await write("/segments", { name: segmentName, filters });
      setSegmentName("");
      refresh();
      notify("Segment mit seinen Filtern gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        title="Kontakte"
        description="Kontakte filtern, mehrere auf einmal bearbeiten und Auswahlen als Liste speichern."
      >
        <button className="button secondary" onClick={onImport}>
          <FileText size={16} /> CSV importieren
        </button>
        <button className="button primary" onClick={() => setAdding(true)}>
          <Plus size={16} /> Kontakt hinzufügen
        </button>
      </Heading>
      <section className="panel contacts-panel">
        <div className="table-toolbar">
          <div className="search-box">
            <Search size={16} />
            <input
              aria-label="Kontakte suchen"
              placeholder="Name, Unternehmen, Ort suchen …"
              value={filters.search}
              onChange={(e) => change("search", e.target.value)}
            />
          </div>
          <select
            aria-label="Gespeichertes Segment"
            value={segmentId}
            onChange={(e) => {
              setSegmentId(e.target.value);
              const item = segments.data?.items.find(
                (s) => s.id === e.target.value,
              );
              if (item)
                setFilters({ ...initialLeadFilters, ...item.filters, page: 1 });
              else setFilters(initialLeadFilters);
              setSelection([]);
            }}
          >
            <option value="">Alle Kontakte</option>
            {segments.data?.items.map((segment) => (
              <option value={segment.id} key={segment.id}>
                {segment.name}
              </option>
            ))}
          </select>
          <button
            className={`button secondary ${advanced ? "selected" : ""}`}
            aria-expanded={advanced}
            onClick={() => setAdvanced(!advanced)}
          >
            <Filter size={15} /> Filter
          </button>
          <select
            aria-label="Kontaktsortierung"
            value={filters.sort}
            onChange={(e) =>
              change("sort", e.target.value as LeadFilters["sort"])
            }
          >
            <option value="created">Neueste zuerst</option>
            <option value="name">Name</option>
            <option value="score">Passung</option>
          </select>
        </div>
        {advanced && (
          <form
            className="journey-filter-grid"
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              setFilters((old) => ({
                ...old,
                page: 1,
                location: String(form.get("location") || ""),
                job_title: String(form.get("role") || ""),
                tags: list(form.get("tags")),
                statuses: form.get("status")
                  ? [String(form.get("status"))]
                  : [],
                sources: form.get("source") ? [String(form.get("source"))] : [],
                has_email: String(
                  form.get("email"),
                ) as LeadFilters["has_email"],
                min_score: Number(form.get("score")),
                icp_id: String(form.get("icp") || "") || null,
              }));
              setSelection([]);
            }}
          >
            <label>
              Standort
              <input name="location" defaultValue={filters.location} />
            </label>
            <label>
              Rolle
              <input name="role" defaultValue={filters.job_title} />
            </label>
            <label>
              Status
              <select name="status" defaultValue={filters.statuses[0] || ""}>
                <option value="">Alle</option>
                <option value="new">Neu</option>
                <option value="qualified">Qualifiziert</option>
                <option value="contacted">Kontaktiert</option>
                <option value="archived">Archiviert</option>
              </select>
            </label>
            <label>
              Quelle
              <select name="source" defaultValue={filters.sources[0] || ""}>
                <option value="">Alle Quellen</option>
                <option value="csv_upload">CSV-Import</option>
                <option value="user_entry">Manueller Eintrag</option>
                <option value="synthetic_demo">Synthetische Demo</option>
              </select>
            </label>
            <label>
              E-Mail
              <select name="email" defaultValue={filters.has_email}>
                <option value="any">Beliebig</option>
                <option value="present">Vorhanden</option>
                <option value="missing">Fehlt</option>
              </select>
            </label>
            <label>
              Tags
              <input
                name="tags"
                defaultValue={filters.tags.join(", ")}
                placeholder="Kommagetrennt"
              />
            </label>
            <label>
              ICP-Profil
              <select name="icp" defaultValue={filters.icp_id || ""}>
                <option value="">Workspace-Standard</option>
                {profiles.data?.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              ICP-Fit ab
              <input
                name="score"
                type="number"
                min={0}
                max={100}
                defaultValue={filters.min_score}
              />
            </label>
            <div className="form-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => {
                  setFilters(initialLeadFilters);
                  setSelection([]);
                }}
              >
                Zurücksetzen
              </button>
              <button className="button primary">Filter anwenden</button>
            </div>
          </form>
        )}
        <ErrorNote message={error || leads.error} />
        {selection.length > 0 && (
          <div className="journey-bulk-bar">
            <strong>{selection.length} ausgewählt</strong>
            <label className="sr-only" htmlFor="bulk-status">
              Neuer Status
            </label>
            <select
              id="bulk-status"
              value={bulkStatus}
              onChange={(e) => setBulkStatus(e.target.value)}
            >
              <option value="">Status beibehalten</option>
              <option value="new">Neu</option>
              <option value="qualified">Qualifiziert</option>
              <option value="contacted">Kontaktiert</option>
              <option value="archived">Archiviert</option>
            </select>
            <input
              aria-label="Tags hinzufügen"
              placeholder="Tags hinzufügen"
              value={bulkTag}
              onChange={(e) => setBulkTag(e.target.value)}
            />
            <select
              aria-label="Auswahl einer Kampagne zuordnen"
              value={campaignId}
              onChange={(e) => setCampaignId(e.target.value)}
            >
              <option value="">Keine Kampagnenänderung</option>
              {campaigns.data?.items.map((c) => (
                <option value={c.id} key={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <button
              className="button primary small"
              disabled={busy || (!bulkTag && !bulkStatus && !campaignId)}
              onClick={bulk}
            >
              Auswahl aktualisieren
            </button>
          </div>
        )}
        {leads.loading ? (
          <div className="loading-block">
            <Spinner /> Kontakte laden …
          </div>
        ) : leads.data?.items.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>
                      <input
                        type="checkbox"
                        aria-label="Alle sichtbaren Kontakte auswählen"
                        checked={leads.data.items.every((c) =>
                          selection.includes(c.id),
                        )}
                        onChange={(e) =>
                          setSelection(
                            e.target.checked
                              ? leads.data!.items.map((c) => c.id)
                              : [],
                          )
                        }
                      />
                    </th>
                    <th>Kontakt</th>
                    <th>Unternehmen</th>
                    <th>Position</th>
                    <th>Standort</th>
                    <th>Passung</th>
                    <th>Vollständigkeit</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.data.items.map((lead, i) => (
                    <tr key={lead.id}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`${lead.first_name} ${lead.last_name} auswählen`}
                          checked={selection.includes(lead.id)}
                          onChange={(e) =>
                            setSelection((old) =>
                              e.target.checked
                                ? [...old, lead.id]
                                : old.filter((id) => id !== lead.id),
                            )
                          }
                        />
                      </td>
                      <td>
                        <button
                          className="person-cell"
                          onClick={() => setActive(lead.id)}
                        >
                          <span className={`contact-avatar avatar-${i % 5}`}>
                            {lead.first_name[0]}
                            {lead.last_name?.[0]}
                          </span>
                          <span>
                            <strong>
                              {lead.first_name} {lead.last_name}
                            </strong>
                            <small>
                              {lead.email || "Keine E-Mail hinterlegt"}
                            </small>
                          </span>
                        </button>
                        <div className="journey-inline-tags">
                          {lead.tags?.map((tag) => (
                            <Badge key={tag}>{tag}</Badge>
                          ))}
                        </div>
                      </td>
                      <td>
                        {lead.company_id ? (
                          <button
                            className="journey-link"
                            onClick={() =>
                              onNavigate?.(`/companies/${lead.company_id}`)
                            }
                          >
                            {lead.company || "Unternehmen"}
                            <ArrowRight size={12} />
                          </button>
                        ) : (
                          lead.company || "—"
                        )}
                      </td>
                      <td>{lead.job_title || "—"}</td>
                      <td>{lead.location || "Unbekannt"}</td>
                      <td>
                        <Badge
                          tone={lead.score.value >= 65 ? "green" : "purple"}
                        >
                          {lead.score.value}/100
                        </Badge>
                      </td>
                      <td>
                        <Progress value={lead.completeness} />
                      </td>
                      <td>
                        <Badge
                          tone={
                            lead.status === "qualified" ? "green" : "neutral"
                          }
                        >
                          {stageLabels[lead.status] ||
                            (
                              { archived: "Archiviert" } as Record<
                                string,
                                string
                              >
                            )[lead.status] ||
                            lead.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              page={filters.page}
              total={leads.data.total}
              limit={filters.limit}
              label="Kontakte"
              onPage={(page) => setFilters((old) => ({ ...old, page }))}
            />
          </>
        ) : (
          <Empty
            icon={Users}
            title="Keine Kontakte für diese Filter"
            description="Passe deine Filter an oder importiere deine erste CSV-Datei."
          >
            <button className="button secondary" onClick={onImport}>
              CSV importieren
            </button>
          </Empty>
        )}
      </section>
      <section className="panel journey-segment-save">
        <div>
          <h3>
            <ListFilter size={17} /> Aktuelle Ansicht wiederverwenden
          </h3>
          <p className="muted small">
            Ein Segment speichert Filter, keine eingefrorene Kontaktkopie.
          </p>
        </div>
        <input
          aria-label="Name des neuen Segments"
          placeholder="Segmentname"
          value={segmentName}
          onChange={(e) => setSegmentName(e.target.value)}
          maxLength={120}
        />
        <button
          className="button secondary"
          disabled={!segmentName.trim() || busy}
          onClick={saveSegment}
        >
          Segment speichern
        </button>
        <button
          className="button secondary"
          onClick={() => onNavigate?.("/imports/history")}
        >
          <History size={15} /> Importverlauf
        </button>
      </section>
      {active && (
        <LeadProfile
          {...props}
          contactId={active}
          onClose={() => setActive(null)}
          onUpdated={refresh}
        />
      )}{" "}
      {adding && (
        <AddContact
          {...props}
          onClose={() => setAdding(false)}
          onCreated={refresh}
        />
      )}
    </>
  );
}

export function AddContact({
  write,
  notify,
  onClose,
  onCreated,
}: JourneyProps & { onClose: () => void; onCreated: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      const form = new FormData(event.currentTarget);
      await write("/contacts", {
        first_name: String(form.get("first_name") || ""),
        last_name: String(form.get("last_name") || ""),
        company: String(form.get("company") || ""),
        job_title: String(form.get("job_title") || ""),
        location: String(form.get("location") || ""),
        email: String(form.get("email") || "") || null,
        phone: String(form.get("phone") || "") || null,
        linkedin_url: String(form.get("linkedin_url") || "") || null,
      });
      onCreated();
      onClose();
      notify("Kontakt angelegt.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Kontakt hinzufügen" onClose={onClose}>
      <form className="modal-body" onSubmit={submit}>
        <div className="form-grid">
          <label>
            Vorname
            <input name="first_name" required maxLength={120} />
          </label>
          <label>
            Nachname
            <input name="last_name" maxLength={120} />
          </label>
          <label>
            Unternehmen
            <input name="company" maxLength={240} />
          </label>
          <label>
            Position
            <input name="job_title" maxLength={240} />
          </label>
          <label>
            Standort
            <input name="location" maxLength={240} />
          </label>
          <label>
            E-Mail
            <input name="email" type="email" maxLength={254} />
          </label>
          <label>
            Telefon
            <input name="phone" maxLength={80} />
          </label>
          <label>
            LinkedIn-Profil
            <input name="linkedin_url" type="url" maxLength={500} />
          </label>
        </div>
        <ErrorNote message={error} />
        <div className="form-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Abbrechen
          </button>
          <button className="button primary" disabled={busy}>
            Speichern
          </button>
        </div>
      </form>
    </Modal>
  );
}

export type Context = {
  contact: Lead;
  company: Company | null;
  notes: { id: string; body: string; created_at: string }[];
  tasks: { id: string; title: string; state: string; due_at: string | null }[];
  drafts: Draft[];
  campaigns: Campaign[];
  activities: {
    id: string;
    kind: string;
    description: string;
    created_at: string;
  }[];
  missing_fields: string[];
};

export function LeadProfile(
  props: JourneyProps & {
    contactId: string;
    onClose: () => void;
    onUpdated?: () => void;
  },
) {
  const {
    base,
    write,
    notify,
    revision,
    contactId,
    onClose,
    onUpdated,
    onNavigate,
  } = props;
  const [localRevision, setLocalRevision] = useState(0);
  const context = useData<Context>(
    `${base}/contacts/${contactId}/context`,
    revision + localRevision,
  );
  const campaigns = useData<Page<Campaign>>(
    `${base}/campaigns?limit=100`,
    revision,
  );
  const members = useData<{
    items: { id: string; name?: string; email: string; role: string }[];
  }>(`${base}/members`, revision);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [campaignId, setCampaignId] = useState("");
  const [tab, setTab] = useState("profile");
  const refresh = () => {
    setLocalRevision((v) => v + 1);
    onUpdated?.();
  };
  const lead = context.data?.contact;
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!lead) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData(event.currentTarget);
      await write(
        `/contacts/${contactId}`,
        {
          first_name: String(form.get("first_name")),
          last_name: String(form.get("last_name")),
          company: lead.company,
          job_title: String(form.get("job_title") || ""),
          location: String(form.get("location") || ""),
          email: String(form.get("email") || "") || null,
          phone: lead.phone,
          linkedin_url: lead.linkedin_url,
          status: String(form.get("status")),
          version: lead.version,
        },
        "PATCH",
      );
      const owner = String(form.get("owner") || "");
      if (owner !== (lead.owner_id || ""))
        await write("/leads/bulk", {
          contact_ids: [contactId],
          owner_id: owner || null,
          tags_add: [],
          tags_remove: [],
        });
      refresh();
      notify("Kontakt gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function addRelated(
    event: FormEvent<HTMLFormElement>,
    kind: "notes" | "tasks",
  ) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy(true);
    try {
      await write(`/${kind}`, {
        contact_id: contactId,
        ...(kind === "notes"
          ? { body: String(form.get("text")) }
          : { title: String(form.get("text")) }),
      });
      formElement.reset();
      refresh();
      notify(kind === "notes" ? "Notiz gespeichert." : "Aufgabe angelegt.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={lead ? `${lead.first_name} ${lead.last_name}` : "Kontaktprofil"}
      onClose={onClose}
      wide
    >
      <div className="modal-body">
        <ErrorNote message={error || context.error} />
        {context.loading ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : (
          lead && (
            <>
              <div className="journey-profile-meta">
                <Badge>{lead.provenance?.source || lead.source}</Badge>
                <Badge tone={lead.provenance?.reviewed ? "green" : "neutral"}>
                  {lead.provenance?.reviewed
                    ? "Quelle geprüft"
                    : "Quelle nicht geprüft"}
                </Badge>
                <Progress value={lead.completeness} />
                {lead.linkedin_url && (
                  <a
                    className="button secondary small"
                    href={lead.linkedin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    LinkedIn manuell öffnen <ExternalLink size={14} />
                  </a>
                )}
              </div>
              <div className="tabs journey-tabs">
                {[
                  ["profile", "Profil & Qualifizierung"],
                  ["history", "Notizen & Aufgaben"],
                  ["outreach", "Nachrichten & Verlauf"],
                ].map(([id, label]) => (
                  <button
                    className={`tab ${tab === id ? "active" : ""}`}
                    key={id}
                    onClick={() => setTab(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {tab === "profile" && (
                <div className="journey-profile-grid">
                  <form onSubmit={save} key={lead.version}>
                    <div className="form-grid">
                      <label>
                        Vorname
                        <input
                          name="first_name"
                          defaultValue={lead.first_name}
                          required
                          maxLength={120}
                        />
                      </label>
                      <label>
                        Nachname
                        <input
                          name="last_name"
                          defaultValue={lead.last_name}
                          maxLength={120}
                        />
                      </label>
                      <label>
                        Position
                        <input
                          name="job_title"
                          defaultValue={lead.job_title}
                          maxLength={240}
                        />
                      </label>
                      <label>
                        Standort
                        <input
                          name="location"
                          defaultValue={lead.location}
                          maxLength={240}
                        />
                      </label>
                      <label>
                        E-Mail
                        <input
                          name="email"
                          defaultValue={lead.email || ""}
                          type="email"
                          maxLength={254}
                        />
                      </label>
                      <label>
                        Status
                        <select name="status" defaultValue={lead.status}>
                          <option value="new">Neu</option>
                          <option value="qualified">Qualifiziert</option>
                          <option value="contacted">Kontaktiert</option>
                          <option value="archived">Archiviert</option>
                        </select>
                      </label>
                      <label>
                        Verantwortlich
                        <select name="owner" defaultValue={lead.owner_id || ""}>
                          <option value="">Nicht zugewiesen</option>
                          {members.data?.items.map((member) => (
                            <option key={member.id} value={member.id}>
                              {member.name || member.email}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    {context.data?.company && (
                      <button
                        className="button secondary"
                        type="button"
                        onClick={() => {
                          onClose();
                          onNavigate?.(
                            `/companies/${context.data!.company!.id}`,
                          );
                        }}
                      >
                        <Building2 size={15} /> {context.data.company.name}{" "}
                        <ArrowRight size={14} />
                      </button>
                    )}
                    <div className="form-actions">
                      <button className="button primary" disabled={busy}>
                        Speichern
                      </button>
                    </div>
                  </form>
                  <ScoreDetails lead={lead} />
                </div>
              )}
              {tab === "history" && (
                <div className="journey-profile-grid">
                  <section>
                    <h3>Notizen</h3>
                    <form onSubmit={(e) => addRelated(e, "notes")}>
                      <label>
                        Neue Kontaktnotiz
                        <textarea
                          name="text"
                          required
                          maxLength={5000}
                          rows={3}
                        />
                      </label>
                      <button className="button secondary" disabled={busy}>
                        Notiz speichern
                      </button>
                    </form>
                    <div className="journey-timeline">
                      {context.data?.notes.map((n) => (
                        <article key={n.id}>
                          <p>{n.body}</p>
                          <small>{dateTime(n.created_at)}</small>
                        </article>
                      ))}
                    </div>
                  </section>
                  <section>
                    <h3>Nächste Schritte</h3>
                    <form onSubmit={(e) => addRelated(e, "tasks")}>
                      <label>
                        Neue Kontaktaufgabe
                        <input name="text" required maxLength={240} />
                      </label>
                      <button className="button secondary" disabled={busy}>
                        Aufgabe anlegen
                      </button>
                    </form>
                    {context.data?.tasks.map((t) => (
                      <article className="journey-task" key={t.id}>
                        <input
                          type="checkbox"
                          aria-label={`${t.title} erledigen`}
                          checked={t.state === "done"}
                          onChange={async (e) => {
                            try {
                              await write(
                                `/tasks/${t.id}`,
                                { state: e.target.checked ? "done" : "open" },
                                "PATCH",
                              );
                              refresh();
                            } catch (error) {
                              setError((error as Error).message);
                            }
                          }}
                        />
                        <span>
                          {t.title}
                          <small>
                            {t.due_at ? dateTime(t.due_at) : "Ohne Termin"}
                          </small>
                        </span>
                      </article>
                    ))}
                  </section>
                </div>
              )}
              {tab === "outreach" && (
                <>
                  <div className="journey-profile-grid">
                    <section>
                      <h3>Kampagnenzuordnung</h3>
                      <label>
                        Kampagne für diesen Kontakt
                        <select
                          value={campaignId}
                          onChange={(e) => setCampaignId(e.target.value)}
                        >
                          <option value="">Kampagne auswählen</option>
                          {campaigns.data?.items.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        className="button primary"
                        disabled={!campaignId || busy}
                        onClick={async () => {
                          setBusy(true);
                          try {
                            await write("/leads/bulk", {
                              contact_ids: [contactId],
                              campaign_id: campaignId,
                              tags_add: [],
                              tags_remove: [],
                            });
                            refresh();
                            notify("Kontakt zur Kampagne hinzugefügt.");
                          } catch (e) {
                            setError((e as Error).message);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        Kontakt zur Kampagne hinzufügen
                      </button>
                      {context.data?.campaigns.map((c) => (
                        <button
                          className="journey-link"
                          key={c.id}
                          onClick={() => {
                            onClose();
                            onNavigate?.(`/campaigns/${c.id}`);
                          }}
                        >
                          {c.name}
                          <ArrowRight size={13} />
                        </button>
                      ))}
                    </section>
                    <section>
                      <h3>Nachrichten & Freigaben</h3>
                      {context.data?.drafts.length ? (
                        context.data.drafts.map((d) => (
                          <article className="journey-message" key={d.id}>
                            <Badge>{d.state}</Badge>
                            <p>{d.content}</p>
                          </article>
                        ))
                      ) : (
                        <p className="muted">Noch keine Entwürfe vorhanden.</p>
                      )}
                      <button
                        className="button secondary"
                        onClick={() => {
                          onClose();
                          onNavigate?.("/outreach/workbench");
                        }}
                      >
                        Zur Kampagne <ArrowRight size={14} />
                      </button>
                    </section>
                  </div>
                  <h3>Aktivitäten</h3>
                  <div className="journey-timeline">
                    {context.data?.activities.length ? (
                      context.data.activities.map((a) => (
                        <article key={a.id}>
                          <p>{a.description}</p>
                          <small>
                            {dateTime(a.created_at)} · {a.kind}
                          </small>
                        </article>
                      ))
                    ) : (
                      <p className="muted">
                        Noch keine zugeordneten Aktivitäten.
                      </p>
                    )}
                  </div>
                </>
              )}
            </>
          )
        )}
      </div>
    </Modal>
  );
}
