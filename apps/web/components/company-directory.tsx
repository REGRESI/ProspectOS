"use client";
import { useState } from "react";
import { ArrowRight, Building2, Check, ChevronLeft, ExternalLink, FileText, Plus, ShieldCheck, Sparkles } from "lucide-react";
import { dateTime, money, stageLabels } from "@/lib/api";
import type { Page } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Modal, Spinner } from "./ui";
import { RegisterLinks } from "./sources-page";
import type { JourneyProps, Lead, Company } from "./journey-types";
import { CompanyEvidence } from "./sales-agent";
import { Pager, safeDomain, useOptionalData } from "./journey-shared";
import { LeadProfile } from "./lead-database";
import { SearchInput, SkeletonTable } from "./table";
import { ServerSort } from "./contacts-table";

export function ResearchBatchButton({ write }: { write: JourneyProps["write"] }) {
  const [state, setState] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <span className="research-batch">
      <button
        className="button secondary"
        disabled={busy}
        title="Liest Website und Impressum der Firmen, die noch nicht geprüft wurden (bis zu 50)"
        onClick={async () => {
          setBusy(true);
          try {
            const r = await write<{ queued: number; skipped_already_researched: number }>(
              "/companies/research-batch",
              { limit: 50, only_missing: true },
            );
            setState(
              `${r.queued} Recherchen eingeplant` +
                (r.skipped_already_researched
                  ? `, ${r.skipped_already_researched} bereits recherchiert`
                  : ""),
            );
          } catch (e) {
            setState((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? <Spinner /> : "Websites prüfen"}
      </button>
      {state && (
        <small className="muted" role="status">
          {state}
        </small>
      )}
    </span>
  );
}

const SOURCE_LABEL: Record<string, string> = {
  osm: "OpenStreetMap",
  northdata: "Handelsregister",
  user_entry: "Eigene Eingabe",
  csv_import: "Import",
  synthetic_demo: "Beispiel",
};

export function CompanyDirectory(props: JourneyProps) {
  const { base, revision, onNavigate } = props;
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("name");
  const [page, setPage] = useState(1);
  const [companyId, setCompanyId] = useState<string | null>(null);
  const companies = useData<Page<Company>>(
    `${base}/companies/summary?page=${page}&limit=50&sort=${sort}&search=${encodeURIComponent(search)}`,
    revision,
  );
  const open = (id: string) => (onNavigate ? onNavigate(`/companies/${id}`) : setCompanyId(id));
  return (
    <>
      <Heading title="Alle Firmen" description="Jede Firma, die du gefunden oder importiert hast.">
        <ResearchBatchButton write={props.write} />
        <button className="button primary" onClick={() => onNavigate?.("/discover")}>
          Firmen finden
        </button>
      </Heading>
      <ErrorNote message={companies.error} />
      <div className="table-toolbar">
        <SearchInput
          value={search}
          onChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          label="Unternehmen suchen"
          placeholder="Name, Ort oder Branche"
        />
        <span className="count">{companies.data ? `${companies.data.total} Firmen` : ""}</span>
      </div>
      {companies.loading && !companies.data ? (
        <SkeletonTable cols={4} />
      ) : companies.data?.items.length ? (
        <>
          <div className="table-wrap">
            <table data-testid="companies-table">
              <thead>
                <tr>
                  <ServerSort label="Firma" column="name" sort={sort} onSort={setSort} />
                  <ServerSort label="Ort" column="location" sort={sort} onSort={setSort} />
                  <ServerSort label="Kontakte" column="contacts" sort={sort} onSort={setSort} descFirst className="hide-sm" />
                  <th scope="col" className="hide-sm">Quelle</th>
                  <th scope="col" className="num hide-sm">Angaben</th>
                  <ServerSort label="Hinzugefügt" column="created" sort={sort} onSort={setSort} descFirst className="hide-sm" />
                </tr>
              </thead>
              <tbody>
                {companies.data.items.map((company) => (
                  <tr key={company.id} className="clickable" onClick={() => open(company.id)}>
                    <td className="cell-main">
                      <strong>{company.name}</strong>
                      <small>{company.website ? safeDomain(company.website) : "Keine Website"}</small>
                    </td>
                    <td>{company.location || <span className="muted">–</span>}</td>
                    <td className="num hide-sm">{company.contact_count || <span className="muted">0</span>}</td>
                    <td className="muted hide-sm">{SOURCE_LABEL[company.source] || company.source}</td>
                    <td className="num muted hide-sm" title="Anteil der bekannten Angaben">
                      {company.completeness?.percent ?? 0} %
                    </td>
                    <td className="muted hide-sm">
                      {company.created_at ? new Date(company.created_at).toLocaleDateString("de-DE") : "–"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={page} total={companies.data.total} limit={50} onPage={setPage} label="Firmen" />
        </>
      ) : (
        <Empty
          title={search ? "Keine Treffer" : "Noch keine Firmen"}
          description={search ? "Ändere den Suchbegriff." : "Suche Firmen in deiner Umgebung oder importiere eine Liste."}
        >
          {!search && (
            <button className="button primary" onClick={() => onNavigate?.("/discover")}>
              Firmen finden
            </button>
          )}
        </Empty>
      )}
      {companyId && (
        <Modal title="Firmenprofil" onClose={() => setCompanyId(null)} wide>
          <div className="modal-body">
            <CompanyProfile {...props} companyId={companyId} />
          </div>
        </Modal>
      )}
    </>
  );
}

export type CompanyContext = {
  company: Company;
  contacts: Lead[];
  contacts_total: number;
  deals: { id: string; title: string; stage: string; amount: number }[];
  notes: { id: string; body: string; created_at: string }[];
  tasks: { id: string; title: string; state: string; due_at: string | null }[];
  research: {
    id?: string;
    url?: string;
    title?: string;
    text?: string;
    source_id?: string;
    confidence?: string;
  }[];
  activities: {
    id: string;
    kind: string;
    description: string;
    created_at: string;
  }[];
};

export function CompanyProfile(props: JourneyProps & { companyId: string }) {
  const { base, companyId, revision, onNavigate, write, notify, onChange } =
    props;
  const detail = useData<CompanyContext>(
    `${base}/companies/${companyId}`,
    revision,
  );
  const [contactId, setContactId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [researchConsent, setResearchConsent] = useState<string | null>(null);
  const company = detail.data?.company;
  return (
    <>
      <Heading
        title={company?.name || "Firmenprofil"}
        description="Ansprechpersonen, Angaben aus dem Impressum und woher die Firma stammt."
      >
        <button
          className="button secondary"
          onClick={() => onNavigate?.("/companies")}
        >
          <ChevronLeft size={15} /> Alle Unternehmen
        </button>
      </Heading>
      <ErrorNote message={detail.error || error} />
      {detail.loading ? (
        <div className="loading-block">
          <Spinner />
        </div>
      ) : (
        company && (
          <>
            <section className="panel journey-company-summary">
              <div>
                <span className="journey-company-mark">
                  <Building2 size={28} />
                </span>
                <h2>{company.name}</h2>
                <p>
                  {company.location || "Standort unbekannt"} ·{" "}
                  {company.industry || "Branche unbekannt"}
                </p>
                <div className="journey-inline-tags">
                  <Badge>{company.source}</Badge>
                  <Badge>
                    {detail.data?.contacts_total ?? company.contact_count}{" "}
                    Kontakte
                  </Badge>
                  <Badge>{company.deal_count} Deals</Badge>
                </div>
              </div>
              <div className="journey-company-actions">
                {company.website && (
                  <a
                    className="button secondary"
                    href={company.website}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Website öffnen <ExternalLink size={14} />
                  </a>
                )}
                <button
                  className="button secondary"
                  onClick={() => onNavigate?.("/social/studio")}
                >
                  <Sparkles size={15} /> Content entwickeln
                </button>
                <button
                  className="button primary"
                  onClick={() => onNavigate?.("/pipeline")}
                >
                  <ArrowRight size={15} /> Zur Pipeline
                </button>
              </div>
            </section>
            <RegisterLinks base={base} companyId={companyId} />
            <div className="journey-profile-grid">
              <section className="panel">
                <div className="panel-head">
                  <h2>Kontakte im Unternehmen</h2>
                  <Badge>{detail.data?.contacts_total || 0}</Badge>
                </div>
                {detail.data?.contacts.length ? (
                  <div className="journey-related-list">
                    {detail.data.contacts.map((lead) => (
                      <button
                        className="journey-related-item"
                        key={lead.id}
                        onClick={() => setContactId(lead.id)}
                      >
                        <span className="contact-avatar">
                          {lead.first_name[0]}
                          {lead.last_name?.[0]}
                        </span>
                        <span>
                          <strong>
                            {lead.first_name} {lead.last_name}
                          </strong>
                          <small>
                            {lead.job_title || "Rolle nicht bekannt"} · Passung{" "}
                            {lead.score.value}/100
                          </small>
                        </span>
                        <ArrowRight size={15} />
                      </button>
                    ))}
                  </div>
                ) : (
                  <Empty
                    title="Noch keine Kontaktperson"
                    description="Unternehmensdaten werden nicht automatisch zu erfundenen Personendaten ergänzt."
                  />
                )}
              </section>
              <section className="panel">
                <div className="panel-head">
                  <h2>Verkaufschancen</h2>
                  <Badge>{detail.data?.deals.length || 0}</Badge>
                </div>
                <div className="journey-related-list">
                  {detail.data?.deals.length ? (
                    detail.data.deals.map((deal) => (
                      <article className="journey-related-item" key={deal.id}>
                        <span>
                          <strong>{deal.title}</strong>
                          <small>{stageLabels[deal.stage] || deal.stage}</small>
                        </span>
                        <b>{money(deal.amount)}</b>
                      </article>
                    ))
                  ) : (
                    <p className="muted">
                      Noch keine zugeordneten Verkaufschancen.
                    </p>
                  )}
                </div>
              </section>
            </div>
            <div className="journey-profile-grid">
              <section className="panel">
                <div className="panel-head">
                  <h2>Recherche & Quellen</h2>
                </div>
                <div className="modal-body">
                  <div className="info-note">
                    <ShieldCheck size={18} />
                    <p>
                      Quelle: {company.source}. Angaben bleiben unbekannt,
                      solange keine belastbaren Nachweise vorliegen.
                    </p>
                  </div>
                  {company.provenance &&
                    Object.entries(company.provenance)
                      .filter(([, value]) => value != null && value !== "")
                      .map(([key, value]) => (
                        <p className="small" key={key}>
                          <strong>{key}</strong>:{" "}
                          {typeof value === "string"
                            ? value
                            : JSON.stringify(value)}
                        </p>
                      ))}
                  {detail.data?.research.length ? (
                    detail.data.research.map((fact, i) => (
                      <article className="journey-evidence" key={fact.id || i}>
                        <h3>{fact.title || "Recherchequelle"}</h3>
                        <p>{fact.text}</p>
                        {fact.url && (
                          <a
                            className="journey-link"
                            href={fact.url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            Quelle öffnen <ExternalLink size={13} />
                          </a>
                        )}
                        <small>
                          {fact.confidence || "Nicht extern bestätigt"}
                        </small>
                      </article>
                    ))
                  ) : (
                    <p className="muted">
                      Noch keine verknüpften Recherchebelege.
                    </p>
                  )}
                  {company.website && (
                    <label className="check-line">
                      <input
                        type="checkbox"
                        checked={researchConsent === companyId}
                        onChange={(event) =>
                          setResearchConsent(
                            event.target.checked ? companyId : null,
                          )
                        }
                      />
                      Nutzungsrechte für diese Website geprüft; Recherche
                      ausdrücklich beauftragen.
                    </label>
                  )}
                  {company.website && (
                    <button
                      disabled={researchConsent !== companyId}
                      className="button secondary"
                      onClick={async () => {
                        try {
                          await write(`/companies/${companyId}/research`);
                          notify(
                            "Recherche angefragt. Geprüfte Domain, Nutzungsrechte und Netzwerkschutz werden serverseitig vorausgesetzt.",
                          );
                          onChange();
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    >
                      Rechercheauftrag für diese Website anfragen
                    </button>
                  )}
                </div>
              </section>
              <section className="panel">
                <div className="panel-head">
                  <h2>Notizen & nächste Schritte</h2>
                </div>
                <div className="modal-body">
                  {detail.data?.notes.map((note) => (
                    <article className="journey-evidence" key={note.id}>
                      <p>{note.body}</p>
                      <small>{dateTime(note.created_at)}</small>
                    </article>
                  ))}
                  {detail.data?.tasks.map((task) => (
                    <article className="journey-task" key={task.id}>
                      <Badge tone={task.state === "done" ? "green" : "neutral"}>
                        {task.state === "done" ? "Erledigt" : "Offen"}
                      </Badge>
                      <span>
                        {task.title}
                        <small>
                          {task.due_at ? dateTime(task.due_at) : "Ohne Termin"}
                        </small>
                      </span>
                    </article>
                  ))}
                  {!detail.data?.notes.length && !detail.data?.tasks.length && (
                    <p className="muted">
                      Öffne ein Kontaktprofil, um Notizen und Aufgaben
                      zuzuordnen.
                    </p>
                  )}
                </div>
              </section>
            </div>
            <CompanyEvidence
              {...props}
              companyId={companyId}
              website={company.website ?? null}
            />
            <section className="panel">
              <div className="panel-head">
                <h2>Aktivitäten</h2>
              </div>
              <div className="journey-timeline">
                {detail.data?.activities.length ? (
                  detail.data.activities.map((a) => (
                    <article key={a.id}>
                      <p>{a.description}</p>
                      <small>
                        {dateTime(a.created_at)} · {a.kind}
                      </small>
                    </article>
                  ))
                ) : (
                  <p className="muted">Noch keine zugeordneten Aktivitäten.</p>
                )}
              </div>
            </section>
          </>
        )
      )}
      {contactId && (
        <LeadProfile
          {...props}
          contactId={contactId}
          onClose={() => setContactId(null)}
        />
      )}
    </>
  );
}

export function ImportHistory(props: JourneyProps) {
  const { base, revision, onImport } = props;
  const imports = useData<
    Page<{
      id: string;
      status: string;
      created_at: string;
      total: number;
      summary: Record<string, unknown>;
      headers: string[];
    }>
  >(`${base}/imports/history`, revision);
  const [reportId, setReportId] = useState("");
  const report = useOptionalData<{
    id: string;
    status: string;
    summary: Record<string, unknown>;
    errors: { row: number; errors: string[] }[];
    total: number;
  }>(reportId ? `${base}/imports/${reportId}/report` : null, revision);
  return (
    <>
      <Heading
        title="Importe"
        description="Welche Listen du importiert hast, was übernommen wurde und was nicht."
      >
        <button className="button primary" onClick={onImport}>
          <Plus size={15} /> CSV importieren
        </button>
      </Heading>
      <ErrorNote message={imports.error} />
      <section className="panel">
        {imports.loading ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : imports.data?.items.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Import</th>
                  <th>Status</th>
                  <th>Zeilen</th>
                  <th>Ergebnis</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {imports.data.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      {dateTime(item.created_at)}
                      <small className="journey-cell-sub">
                        {item.id.slice(0, 8)}
                      </small>
                    </td>
                    <td>
                      <Badge>{item.status}</Badge>
                    </td>
                    <td>{item.total}</td>
                    <td>
                      {Object.entries(item.summary)
                        .filter(([key]) =>
                          [
                            "created",
                            "duplicates",
                            "invalid",
                            "deleted",
                          ].includes(key),
                        )
                        .map(([key, value]) => (
                          <span className="small" key={key}>
                            {
                              (
                                {
                                  created: "Neu",
                                  duplicates: "Dubletten",
                                  invalid: "Ungültig",
                                  deleted: "Gelöscht",
                                } as Record<string, string>
                              )[key]
                            }
                            : {String(value)}{" "}
                          </span>
                        ))}
                    </td>
                    <td>
                      <button
                        className="button secondary small"
                        onClick={() => setReportId(item.id)}
                      >
                        Bericht öffnen
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            icon={FileText}
            title="Noch keine Importe"
            description="Dein erster CSV-Import erscheint nach der Vorschau hier."
          />
        )}
      </section>
      {reportId && (
        <Modal title="Importbericht" onClose={() => setReportId("")} wide>
          <div className="modal-body">
            <ErrorNote message={report.error} />
            {report.loading ? (
              <Spinner />
            ) : (
              report.data && (
                <>
                  <p>
                    {report.data.total} Zeilen · Status {report.data.status}
                  </p>
                  {report.data.errors.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Zeile</th>
                            <th>Validierung</th>
                          </tr>
                        </thead>
                        <tbody>
                          {report.data.errors.map((row) => (
                            <tr key={row.row}>
                              <td>{row.row}</td>
                              <td>{row.errors.join("; ")}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="info-note">
                      <Check size={18} />
                      <p>
                        Keine gespeicherten Zeilenfehler. Nach der Übernahme
                        werden sensible Rohdaten verworfen.
                      </p>
                    </div>
                  )}
                </>
              )
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
