"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  Building2,
  Check,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  Filter,
  History,
  ListFilter,
  MessageSquare,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  Users,
} from "lucide-react";
import { request, dateTime, money, stageLabels } from "@/lib/api";
import type { Page } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Modal, Spinner } from "./ui";
import type {
  JourneyProps,
  Lead,
  LeadFilters,
  Company,
  Candidate,
  DiscoveryProvider,
  SearchDefinition,
  SearchFilters,
  Campaign,
  Draft,
  Completeness,
} from "./journey-types";
import {
  initialLeadFilters,
  initialSearchFilters,
  list,
} from "./journey-types";
import { CampaignAgent, CompanyEvidence } from "./sales-agent";

const supportLabels: Record<string, string> = {
  employee_range: "Mitarbeiterzahl",
  job_titles: "Zielrollen",
  seniority: "Seniorität",
  contacts: "Ansprechpartner",
  radius_km: "Radius",
};

function Progress({ value }: { value: Completeness | undefined }) {
  return (
    <span
      className="journey-completeness"
      title={
        value?.missing.length
          ? `Fehlt: ${value.missing.join(", ")}`
          : "Vollständigkeit der bekannten Felder"
      }
    >
      <span className="factor-track">
        <span style={{ width: `${value?.percent || 0}%` }} />
      </span>
      <small>{value ? `${value.percent}%` : "Unbekannt"}</small>
    </span>
  );
}
function Pager({
  page,
  total,
  limit,
  onPage,
  label = "Einträge",
}: {
  page: number;
  total: number;
  limit: number;
  onPage: (p: number) => void;
  label?: string;
}) {
  return (
    <div className="pagination">
      <span>
        {total} {label} · Seite {page} von{" "}
        {Math.max(1, Math.ceil(total / limit))}
      </span>
      <div>
        <button
          className="icon-button"
          aria-label="Vorherige Seite"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          <ChevronLeft size={17} />
        </button>
        <button
          className="icon-button"
          aria-label="Nächste Seite"
          disabled={page * limit >= total}
          onClick={() => onPage(page + 1)}
        >
          <ChevronRight size={17} />
        </button>
      </div>
    </div>
  );
}
function useQuery<T>(
  base: string,
  body: unknown,
  csrf: string,
  revision: number,
) {
  const serialized = JSON.stringify(body);
  const key = base + ":" + serialized;
  const [result, setResult] = useState<{
    key: string;
    revision: number;
    data: T | null;
    error: string;
  } | null>(null);
  useEffect(() => {
    let active = true;
    request<T>(
      `${base}/leads/query`,
      { method: "POST", body: serialized },
      csrf,
    )
      .then((data) => {
        if (active) setResult({ key, revision, data, error: "" });
      })
      .catch((e) => {
        if (active) setResult({ key, revision, data: null, error: e.message });
      });
    return () => {
      active = false;
    };
  }, [base, key, serialized, csrf, revision]);
  return {
    data:
      result?.key === key && result.revision === revision ? result.data : null,
    error:
      result?.key === key && result.revision === revision ? result.error : "",
    loading: result?.key !== key || result?.revision !== revision,
  };
}
function ScoreDetails({ lead }: { lead: Pick<Lead, "score"> }) {
  return (
    <section className="detail-section">
      <div className="section-title">
        <h3>ICP-Fit verstehen</h3>
        <Badge tone="purple">{lead.score.value}/100</Badge>
      </div>
      <div className="score-factors">
        {lead.score.factors.map((f) => (
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
      <p className="small muted">
        Unbekannt:{" "}
        {lead.score.missing_data.join(", ") || "keine zusätzlichen Angaben"}.
        Fit belegt weder Kaufabsicht noch Kaufwahrscheinlichkeit.
      </p>
    </section>
  );
}

export function DiscoveryWorkbench(props: JourneyProps) {
  const { base, write, notify, onChange, revision } = props;
  const [briefing, setBriefing] = useState(
    "Büros und Dienstleistungsunternehmen in Offenburg",
  );
  const [filters, setFilters] = useState<SearchFilters>(initialSearchFilters);
  const [confirmed, setConfirmed] = useState(false);
  const [name, setName] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [job, setJob] = useState<{
    id: string;
    status: string;
    last_error?: string;
    warnings?: string[];
    result: { run_id?: string; warnings?: string[] };
  } | null>(null);
  const [run, setRun] = useState("");
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("name");
  const [kind, setKind] = useState("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<Candidate | null>(null);
  const [localRevision, setLocalRevision] = useState(0);
  const saved = useData<Page<SearchDefinition>>(
    `${base}/discovery/searches?limit=100`,
    revision + localRevision,
  );
  const integrations = useData<{
    items: { name: string; status: string; reason: string }[];
  }>(`${base}/integrations`, revision);
  const providers = useData<{
    items: DiscoveryProvider[];
    osm_categories: { label: string; tags: string[] }[];
  }>(`${base}/discovery/providers`, revision);
  const activeProvider = providers.data?.items.find(
    (p) => p.id === filters.provider,
  );
  const results = useOptionalData<
    Page<Candidate> & {
      notice: string;
      duplicates?: number;
      meta?: {
        attribution?: string;
        radius_km?: number;
        center?: { display_name: string; source_url: string };
        warnings?: string[];
      };
    }
  >(
    run
      ? `${base}/discovery/runs/${run}/results?page=${page}&limit=25&search=${encodeURIComponent(search)}&sort=${sort}&entity_kind=${kind}`
      : null,
    revision + localRevision,
  );
  useEffect(() => {
    if (!job?.id) return;
    let active = true;
    let attempts = 0;
    const id = job.id;
    const timer = window.setInterval(async () => {
      try {
        const next = await request<typeof job>(`${base}/jobs/${id}`);
        if (!active || !next) return;
        setJob(next);
        if (next.result?.run_id) {
          setRun(next.result.run_id);
          if (next.result.warnings?.length)
            setWarnings((previous) =>
              Array.from(new Set([...previous, ...next.result.warnings!])),
            );
          setPage(1);
        }
        if (
          !["queued", "running", "retry"].includes(next.status) ||
          ++attempts >= 120
        )
          window.clearInterval(timer);
      } catch (e) {
        if (active) setError((e as Error).message);
        window.clearInterval(timer);
      }
    }, 1500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [base, job?.id]);
  const patch = <K extends keyof SearchFilters>(
    key: K,
    value: SearchFilters[K],
  ) => {
    setFilters((old) => ({ ...old, [key]: value }));
    setConfirmed(false);
  };
  async function interpret() {
    setBusy(true);
    setError("");
    try {
      const r = await write<{
        suggested_filters: SearchFilters;
        warnings: string[];
      }>("/discovery/interpret", { briefing });
      setFilters(r.suggested_filters);
      setWarnings(r.warnings);
      setConfirmed(false);
      notify("Vorschläge übernommen. Bitte alle Filter prüfen.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(runNow = false) {
    setBusy(true);
    setError("");
    try {
      const definition = await write<SearchDefinition>("/discovery/searches", {
        name:
          name ||
          `${filters.city || "Unternehmen"} · ${new Date().toLocaleDateString("de-DE")}`,
        briefing,
        filters: {
          ...filters,
          industries: filters.industries.filter(Boolean),
          excluded_industries: filters.excluded_industries.filter(Boolean),
          keywords: filters.keywords.filter(Boolean),
          job_titles: filters.job_titles.filter(Boolean),
          seniority: filters.seniority.filter(Boolean),
        },
      });
      setLocalRevision((v) => v + 1);
      if (runNow) {
        setSelected([]);
        setRun("");
        const queued = await write<NonNullable<typeof job>>(
          `/discovery/searches/${definition.id}/run`,
          { confirmed, license_confirmed: confirmed },
        );
        setJob(queued);
        setWarnings(queued.warnings || []);
        notify(
          "Suchauftrag gespeichert. Der Worker verarbeitet die geprüften Filter.",
        );
      } else notify("Suchkonfiguration gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function importSelected() {
    setBusy(true);
    setError("");
    try {
      const r = await write<{
        created: number;
        duplicates: number;
        companies: number;
        contacts: number;
        linked_duplicates?: number;
        facts?: number;
      }>(`/discovery/runs/${run}/import-selected`, { keys: selected });
      notify(
        `${r.created} neue Datensätze · ${r.duplicates} bereits vorhanden` +
          (r.linked_duplicates
            ? ` · ${r.linked_duplicates} mit bestehenden Firmen verknüpft`
            : "") +
          (r.facts ? ` · ${r.facts} belegte Angaben gespeichert` : ""),
      );
      setSelected([]);
      setLocalRevision((v) => v + 1);
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const running = !!job && ["queued", "running", "retry"].includes(job.status);
  const provider = integrations.data?.items.find(
    (i) => i.name === "Lead Discovery",
  );
  return (
    <>
      <Heading
        title="Lead Discovery"
        description="Zielkunden definieren, Quellen prüfen und ausgewählte Ergebnisse in deine Datenbank übernehmen."
      />
      {filters.provider === "synthetic" && (
        <DemoDiscoveryQuickAction {...props} />
      )}
      <div className="journey-discovery-layout">
        <aside className="panel journey-search-panel">
          <div className="panel-head">
            <h2>
              <Target size={17} /> Suchprofil
            </h2>
            <Badge tone={filters.provider === "osm" ? "green" : "neutral"}>
              {filters.provider === "synthetic"
                ? "Entwicklungsbeispiele"
                : filters.provider === "osm"
                  ? "OpenStreetMap"
                  : "Lizenzanbieter"}
            </Badge>
          </div>
          <div className="modal-body">
            <label>
              ICP-Briefing
              <textarea
                rows={3}
                value={briefing}
                onChange={(e) => {
                  setBriefing(e.target.value);
                  setConfirmed(false);
                }}
                maxLength={300}
              />
            </label>
            <button
              className="button secondary"
              onClick={interpret}
              disabled={busy || briefing.length < 3}
            >
              <Sparkles size={15} /> Filter vorschlagen
            </button>
            <p className="small muted">
              Regelbasierte Vorschläge. Nicht erkannter Freitext bleibt
              unbestätigt und wird nicht als Suchkriterium ausgegeben.
            </p>
            {warnings.map((w, i) => (
              <p className="info-note small" key={i}>
                {w}
              </p>
            ))}
            <label>
              Name der Suche
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z. B. Büros in der Ortenau"
                maxLength={120}
              />
            </label>
            <label>
              Datenquelle
              <select
                value={filters.provider}
                onChange={(e) =>
                  patch("provider", e.target.value as SearchFilters["provider"])
                }
              >
                <option value="osm">
                  OpenStreetMap · Orte & Firmen im Umkreis
                  {providers.data &&
                  !providers.data.items.find((p) => p.id === "osm")?.available
                    ? " (nicht aktiviert)"
                    : ""}
                </option>
                <option value="synthetic">
                  Synthetische Demo · keine Recherche
                </option>
                <option value="pdl">
                  People Data Labs · Lizenz erforderlich
                </option>
              </select>
            </label>
            {activeProvider && (
              <div
                className={`provider-capability ${activeProvider.available ? "ok" : "off"}`}
                data-testid="provider-capability"
              >
                <strong>
                  {activeProvider.available ? "Verfügbar" : "Nicht verfügbar"}
                </strong>{" "}
                · {activeProvider.license} · {activeProvider.cost}
                {activeProvider.reason && <p>{activeProvider.reason}</p>}
                {!!activeProvider.unsupported.length && (
                  <p className="small muted">
                    Nicht unterstützt:{" "}
                    {activeProvider.unsupported
                      .map((u) => supportLabels[u] || u)
                      .join(", ")}
                  </p>
                )}
              </div>
            )}
            {filters.provider === "pdl" &&
              provider?.status !== "configured" && (
                <div className="info-note">
                  <ShieldCheck size={16} />
                  <p>
                    Lizenzanbieter noch nicht konfiguriert. API-Zugang,
                    Lizenzfreigabe und Nutzungszweck müssen serverseitig
                    eingerichtet werden.
                  </p>
                </div>
              )}
            <div className="form-grid">
              <label>
                Land
                <input
                  value={filters.country}
                  onChange={(e) => patch("country", e.target.value)}
                  maxLength={100}
                />
              </label>
              <label>
                Region
                <input
                  value={filters.region}
                  onChange={(e) => patch("region", e.target.value)}
                  maxLength={100}
                />
              </label>
              <label>
                Stadt
                <input
                  value={filters.city}
                  onChange={(e) => patch("city", e.target.value)}
                  maxLength={100}
                />
              </label>
              <label>
                Radius in km
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={filters.radius_km ?? ""}
                  onChange={(e) =>
                    patch(
                      "radius_km",
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                />
              </label>
            </div>
            <label>
              Branchen
              <input
                value={filters.industries.join(", ")}
                onChange={(e) =>
                  patch(
                    "industries",
                    e.target.value.split(",").map((s) => s.trim()),
                  )
                }
                placeholder="Kommagetrennt"
                list={
                  filters.provider === "osm" ? "osm-category-options" : undefined
                }
              />
            </label>
            {filters.provider === "osm" && (
              <>
                <datalist id="osm-category-options">
                  {providers.data?.osm_categories.map((c) => (
                    <option key={c.label} value={c.label} />
                  ))}
                </datalist>
                <div className="chip-row" aria-label="OSM-Kategorien">
                  {providers.data?.osm_categories.map((c) => {
                    const active = filters.industries.includes(c.label);
                    return (
                      <button
                        type="button"
                        key={c.label}
                        className={`chip ${active ? "active" : ""}`}
                        title={c.tags.join(", ")}
                        aria-pressed={active}
                        onClick={() =>
                          patch(
                            "industries",
                            active
                              ? filters.industries.filter((i) => i !== c.label)
                              : [...filters.industries.filter(Boolean), c.label],
                          )
                        }
                      >
                        {c.label}
                      </button>
                    );
                  })}
                </div>
              </>
            )}
            <label>
              Ausgeschlossene Branchen
              <input
                value={filters.excluded_industries.join(", ")}
                onChange={(e) =>
                  patch(
                    "excluded_industries",
                    e.target.value.split(",").map((s) => s.trim()),
                  )
                }
              />
            </label>
            <div className="form-grid">
              <label>
                Mitarbeitende von
                <input
                  type="number"
                  min={0}
                  value={filters.min_employees ?? ""}
                  onChange={(e) =>
                    patch(
                      "min_employees",
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                />
              </label>
              <label>
                bis
                <input
                  type="number"
                  min={1}
                  value={filters.max_employees ?? ""}
                  onChange={(e) =>
                    patch(
                      "max_employees",
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                />
              </label>
            </div>
            <label>
              Unternehmens-Keywords
              <input
                value={filters.keywords.join(", ")}
                onChange={(e) =>
                  patch(
                    "keywords",
                    e.target.value.split(",").map((s) => s.trim()),
                  )
                }
              />
            </label>
            <label>
              Zielrollen
              <input
                value={filters.job_titles.join(", ")}
                onChange={(e) =>
                  patch(
                    "job_titles",
                    e.target.value.split(",").map((s) => s.trim()),
                  )
                }
                placeholder="Nur soweit lizenziert verfügbar"
              />
            </label>
            <label>
              Seniorität
              <input
                value={filters.seniority.join(", ")}
                onChange={(e) =>
                  patch(
                    "seniority",
                    e.target.value.split(",").map((s) => s.trim()),
                  )
                }
              />
            </label>
            <label>
              Maximale Ergebnisse
              <input
                type="number"
                min={1}
                max={filters.provider === "osm" ? 50 : 25}
                value={filters.max_results}
                onChange={(e) => patch("max_results", Number(e.target.value))}
              />
            </label>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={filters.exclude_customers}
                onChange={(e) => patch("exclude_customers", e.target.checked)}
              />{" "}
              Bereits bekannte Kunden ausschließen
            </label>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />{" "}
              Ich habe Filter und zulässigen Nutzungszweck geprüft.
            </label>
            <ErrorNote message={error} />
            <div className="form-actions">
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => save()}
              >
                Suche speichern
              </button>
              <button
                className="button primary"
                disabled={busy || running || !confirmed}
                onClick={() => save(true)}
              >
                {busy ? <Spinner /> : <Search size={15} />} Suche starten
              </button>
            </div>
          </div>
        </aside>
        <div className="journey-discovery-content">
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>Gespeicherte & letzte Suchen</h2>
                <p>
                  Konfiguration wiederverwenden, Filter vor jedem Start prüfen.
                </p>
              </div>
              <Badge>{saved.data?.total || 0}</Badge>
            </div>
            <div className="journey-saved-searches">
              {saved.data?.items.length ? (
                saved.data.items.map((item) => (
                  <button
                    key={item.id}
                    className="journey-saved-search"
                    onClick={() => {
                      setName(item.name);
                      setBriefing(item.briefing);
                      setFilters(item.filters);
                      setConfirmed(false);
                    }}
                  >
                    <Search size={15} />
                    <span>
                      <strong>{item.name}</strong>
                      <small>
                        {item.filters.city || item.filters.country} ·{" "}
                        {item.filters.provider === "synthetic"
                          ? "Demo"
                          : item.filters.provider === "osm"
                            ? `OSM · ${item.filters.radius_km || 10} km`
                            : "Lizenzanbieter"}
                      </small>
                    </span>
                  </button>
                ))
              ) : (
                <p className="muted">Noch keine Suchen gespeichert.</p>
              )}
            </div>
          </section>
          <section className="panel journey-results">
            <div className="panel-head">
              <div>
                <h2>
                  Ergebnisse {results.data ? `(${results.data.total})` : ""}
                </h2>
                <p>
                  {run
                    ? results.data?.notice
                    : "Ein Suchauftrag liefert nachvollziehbare Quellen und unbekannte Felder."}
                </p>
              </div>
              {job && (
                <Badge tone={job.status === "succeeded" ? "green" : "neutral"}>
                  {job.status === "succeeded"
                    ? "Abgeschlossen"
                    : job.status === "queued"
                      ? "In Warteschlange"
                      : job.status === "running"
                        ? "Wird verarbeitet"
                        : job.status}
                </Badge>
              )}
            </div>
            {running ? (
              <div className="loading-block">
                <Spinner /> Suchauftrag wird verarbeitet.
              </div>
            ) : job?.last_error ? (
              <ErrorNote
                message={`Suchauftrag nicht abgeschlossen: ${job.last_error}`}
              />
            ) : !run ? (
              <Empty
                icon={Search}
                title="Zuerst ein Suchprofil prüfen"
                description="Starte eine konfigurierte lizenzierte Suche oder ausdrücklich gekennzeichnete Entwicklungsbeispiele."
              />
            ) : (
              <>
                <div className="table-toolbar">
                  <div className="search-box">
                    <Search size={15} />
                    <input
                      aria-label="Discovery-Ergebnisse filtern"
                      value={search}
                      onChange={(e) => {
                        setSearch(e.target.value);
                        setPage(1);
                      }}
                      placeholder="Name, Ort oder Branche"
                    />
                  </div>
                  <select
                    aria-label="Ergebnistyp"
                    value={kind}
                    onChange={(e) => {
                      setKind(e.target.value);
                      setPage(1);
                    }}
                  >
                    <option value="all">Alle Datensätze</option>
                    <option value="company">Unternehmen</option>
                    <option value="person">Personen</option>
                  </select>
                  <select
                    aria-label="Discovery-Sortierung"
                    value={sort}
                    onChange={(e) => setSort(e.target.value)}
                  >
                    <option value="name">Name</option>
                    <option value="score">ICP-Fit</option>
                  </select>
                </div>
                <ErrorNote message={results.error} />
                {results.data?.meta?.center && (
                  <p className="small muted" data-testid="discovery-center">
                    Suchzentrum: {results.data.meta.center.display_name} ·
                    Radius {results.data.meta.radius_km} km
                    {results.data.duplicates
                      ? ` · ${results.data.duplicates} wahrscheinliche Dubletten markiert`
                      : ""}
                  </p>
                )}
                {results.loading ? (
                  <div className="loading-block">
                    <Spinner />
                  </div>
                ) : results.data?.items.length ? (
                  <>
                    <div className="journey-bulk-bar">
                      <span>{selected.length} ausgewählt</span>
                      <button
                        className="button primary small"
                        disabled={!selected.length || busy}
                        onClick={importSelected}
                      >
                        Auswahl übernehmen
                      </button>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>
                              <input
                                type="checkbox"
                                aria-label="Alle sichtbaren Ergebnisse auswählen"
                                checked={
                                  results.data.items.some((r) => !r.imported) &&
                                  results.data.items
                                    .filter((r) => !r.imported)
                                    .every((r) => selected.includes(r.key))
                                }
                                onChange={(e) =>
                                  setSelected(
                                    e.target.checked
                                      ? results
                                          .data!.items.filter(
                                            (r) => !r.imported,
                                          )
                                          .map((r) => r.key)
                                      : [],
                                  )
                                }
                              />
                            </th>
                            <th>Unternehmen / Kontakt</th>
                            <th>Ort · Branche</th>
                            <th>Quelle</th>
                            <th>ICP-Fit</th>
                            <th>Vollständigkeit</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {results.data.items.map((item) => (
                            <tr key={item.key}>
                              <td>
                                <input
                                  type="checkbox"
                                  aria-label={`${item.company} auswählen`}
                                  disabled={item.imported}
                                  checked={selected.includes(item.key)}
                                  onChange={(e) =>
                                    setSelected((old) =>
                                      e.target.checked
                                        ? [...old, item.key]
                                        : old.filter((k) => k !== item.key),
                                    )
                                  }
                                />
                              </td>
                              <td>
                                <button
                                  className="person-cell"
                                  onClick={() => setDetail(item)}
                                >
                                  <span>
                                    <strong>{item.company}</strong>
                                    <small>
                                      {[item.first_name, item.last_name]
                                        .filter(Boolean)
                                        .join(" ") ||
                                        item.domain ||
                                        "Keine Domain bekannt"}
                                    </small>
                                  </span>
                                </button>
                              </td>
                              <td>
                                {item.location || "Unbekannt"}
                                {typeof item.distance_km === "number" && (
                                  <> · {item.distance_km.toLocaleString("de-DE")} km</>
                                )}
                                <small className="journey-cell-sub">
                                  {item.industry || "Branche unbekannt"}
                                </small>
                              </td>
                              <td>
                                {item.source_url ? (
                                  <a
                                    href={item.source_url}
                                    target="_blank"
                                    rel="noreferrer"
                                  >
                                    {item.source}
                                  </a>
                                ) : (
                                  item.source
                                )}
                                <small className="journey-cell-sub">
                                  {item.observed_at
                                    ? dateTime(item.observed_at)
                                    : "Nicht verifiziert"}
                                </small>
                              </td>
                              <td>
                                <Badge tone="purple">
                                  {item.score.value}/100
                                </Badge>
                              </td>
                              <td>
                                <Progress value={item.completeness} />
                              </td>
                              <td>
                                {item.duplicate_of && !item.imported ? (
                                  <Badge tone="amber">
                                    <span title={item.duplicate_of.explanation}>
                                      Dublette? {item.duplicate_of.name}
                                    </span>
                                  </Badge>
                                ) : (
                                  <Badge
                                    tone={item.imported ? "green" : "neutral"}
                                  >
                                    {item.imported ? "Übernommen" : "Zur Prüfung"}
                                  </Badge>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <Pager
                      page={page}
                      total={results.data.total}
                      limit={25}
                      onPage={setPage}
                    />
                    {results.data.meta?.attribution && (
                      <p className="small muted osm-attribution">
                        Kartendaten{" "}
                        <a
                          href="https://www.openstreetmap.org/copyright"
                          target="_blank"
                          rel="noreferrer"
                        >
                          {results.data.meta.attribution}
                        </a>{" "}
                        · ODbL 1.0
                      </p>
                    )}
                  </>
                ) : (
                  <Empty
                    icon={Search}
                    title="Keine passenden Ergebnisse"
                    description="Prüfe die Filter oder wähle eine andere konfigurierte Datenquelle."
                  />
                )}
              </>
            )}
          </section>
        </div>
      </div>
      {detail && (
        <Modal title={detail.company} onClose={() => setDetail(null)} wide>
          <div className="modal-body">
            <div className="info-note">
              <ShieldCheck size={18} />
              <p>
                Quelle: {detail.source}. Status: {detail.confidence}. Öffentlich
                verfügbare Angaben sind keine Marketingeinwilligung.
              </p>
            </div>
            <dl className="journey-facts">
              <div>
                <dt>Ort</dt>
                <dd>{detail.location || "Unbekannt"}</dd>
              </div>
              <div>
                <dt>Branche</dt>
                <dd>{detail.industry || "Unbekannt"}</dd>
              </div>
              <div>
                <dt>Domain</dt>
                <dd>{detail.domain || "Nicht vorhanden"}</dd>
              </div>
              <div>
                <dt>Rolle</dt>
                <dd>{detail.job_title || "Nicht verfügbar"}</dd>
              </div>
              {detail.address && (
                <div>
                  <dt>Adresse</dt>
                  <dd>{detail.address}</dd>
                </div>
              )}
              {typeof detail.distance_km === "number" && (
                <div>
                  <dt>Entfernung</dt>
                  <dd>{detail.distance_km.toLocaleString("de-DE")} km</dd>
                </div>
              )}
              {detail.source_url && (
                <div>
                  <dt>Quelle</dt>
                  <dd>
                    <a href={detail.source_url} target="_blank" rel="noreferrer">
                      {detail.source_url}
                    </a>
                  </dd>
                </div>
              )}
              {detail.license && (
                <div>
                  <dt>Lizenz</dt>
                  <dd>{detail.license}</dd>
                </div>
              )}
            </dl>
            {detail.duplicate_of && (
              <div className="info-note warning">
                <p>
                  Wahrscheinliche Dublette von „{detail.duplicate_of.name}“:{" "}
                  {detail.duplicate_of.explanation} Bei Übernahme wird kein neues
                  Unternehmen angelegt; die Quelle wird als Beleg verknüpft.
                </p>
              </div>
            )}
            {detail.score.not_applicable?.length ? (
              <p className="small muted">{detail.score.notice}</p>
            ) : null}
            <ScoreDetails lead={detail} />
            <h3>Fehlende Felder</h3>
            <p className="muted">
              {detail.completeness.missing.join(", ") ||
                "Keine zusätzlichen Angaben"}
            </p>
            <button
              className="button primary"
              disabled={detail.imported}
              onClick={() => {
                setSelected((old) =>
                  old.includes(detail.key) ? old : [...old, detail.key],
                );
                setDetail(null);
              }}
            >
              Zur Importauswahl hinzufügen
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

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
        description="Kontakte qualifizieren, segmentieren und mit dem nächsten Schritt verbinden."
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
            <option value="score">ICP-Fit</option>
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
                    <th>ICP-Fit</th>
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

function AddContact({
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

type Context = {
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
                  ["outreach", "Outreach & Verlauf"],
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
                        Zum Outreach-Workspace <ArrowRight size={14} />
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

export function CompanyDirectory(props: JourneyProps) {
  const { base, revision, onNavigate } = props;
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [companyId, setCompanyId] = useState<string | null>(null);
  const companies = useData<Page<Company>>(
    `${base}/companies/summary?page=${page}&limit=25&search=${encodeURIComponent(search)}`,
    revision,
  );
  return (
    <>
      <Heading
        title="Unternehmen"
        description="Unternehmenswissen, zugehörige Kontakte und Verkaufschancen an einem Ort."
      />
      <section className="panel">
        <div className="table-toolbar">
          <div className="search-box">
            <Search size={16} />
            <input
              aria-label="Unternehmen suchen"
              placeholder="Name oder Standort"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <Badge>{companies.data?.total || 0} Unternehmen</Badge>
        </div>
        <ErrorNote message={companies.error} />
        {companies.loading ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : companies.data?.items.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Unternehmen</th>
                    <th>Standort</th>
                    <th>Branche</th>
                    <th>Kontakte</th>
                    <th>Deals</th>
                    <th>Quelle</th>
                    <th>Bekannte Angaben</th>
                  </tr>
                </thead>
                <tbody>
                  {companies.data.items.map((company) => (
                    <tr key={company.id}>
                      <td>
                        <button
                          className="person-cell"
                          onClick={() =>
                            onNavigate
                              ? onNavigate(`/companies/${company.id}`)
                              : setCompanyId(company.id)
                          }
                        >
                          <span className="contact-avatar">
                            <Building2 size={17} />
                          </span>
                          <span>
                            <strong>{company.name}</strong>
                            <small>
                              {company.website
                                ? safeDomain(company.website)
                                : "Keine Website hinterlegt"}
                            </small>
                          </span>
                          <ArrowRight size={14} />
                        </button>
                      </td>
                      <td>{company.location || "Unbekannt"}</td>
                      <td>{company.industry || "Unbekannt"}</td>
                      <td>
                        <strong>{company.contact_count}</strong>
                      </td>
                      <td>{company.deal_count}</td>
                      <td>
                        <Badge>{company.source}</Badge>
                      </td>
                      <td>
                        <Progress value={company.completeness} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              page={page}
              total={companies.data.total}
              limit={25}
              onPage={setPage}
              label="Unternehmen"
            />
          </>
        ) : (
          <Empty
            icon={Building2}
            title="Noch keine Unternehmen"
            description="Importiere Kontakte oder wähle Unternehmen aus einer Discovery-Suche."
          />
        )}
      </section>
      {companyId && (
        <Modal
          title="Unternehmensprofil"
          onClose={() => setCompanyId(null)}
          wide
        >
          <div className="modal-body">
            <CompanyProfile {...props} companyId={companyId} />
          </div>
        </Modal>
      )}
    </>
  );
}

type CompanyContext = {
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
        title={company?.name || "Unternehmensprofil"}
        description="Kontakte, Geschäftschancen und Herkunft im Zusammenhang."
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
                            {lead.job_title || "Rolle nicht bekannt"} · ICP{" "}
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
        title="Importverlauf"
        description="Datenübernahmen, Dubletten und zeilenbezogene Fehler nachvollziehen."
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

function useOptionalData<T>(path: string | null, revision: number) {
  const [result, setResult] = useState<{
    path: string;
    revision: number;
    data: T | null;
    error: string;
  } | null>(null);
  useEffect(() => {
    if (!path) return;
    let active = true;
    request<T>(path)
      .then((data) => {
        if (active) setResult({ path, revision, data, error: "" });
      })
      .catch((error) => {
        if (active)
          setResult({ path, revision, data: null, error: error.message });
      });
    return () => {
      active = false;
    };
  }, [path, revision]);
  return {
    data:
      path && result?.path === path && result.revision === revision
        ? result.data
        : null,
    error: path && result?.path === path ? result.error : "",
    loading: !!path && (result?.path !== path || result.revision !== revision),
  };
}

type SequenceStep = {
  id?: string;
  position: number;
  delay_days: number;
  channel: "linkedin_manual" | "email";
  template: string;
  requires_approval?: boolean;
};
type CampaignContext = {
  campaign: Campaign;
  sequence: SequenceStep[];
  audience: (Lead & { journey_status: string })[];
  drafts: Draft[];
  activities: {
    id: string;
    description: string;
    kind: string;
    created_at: string;
  }[];
  counts: {
    waiting: number;
    approved: number;
    completed: number;
    replied: number;
    suppressed: number;
  };
};
export function OutreachWorkbench(
  props: JourneyProps & { initialCampaignId?: string },
) {
  const { base, write, notify, onChange, revision, csrf, initialCampaignId } =
    props;
  const [active, setActive] = useState(initialCampaignId || "");
  const [tab, setTab] = useState<"campaign" | "inbox">(
    initialCampaignId ? "campaign" : "inbox",
  );
  const [create, setCreate] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [localRevision, setLocalRevision] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [leadId, setLeadId] = useState<string | null>(null);
  const campaigns = useData<Page<Campaign>>(
    `${base}/campaigns?limit=100`,
    revision + localRevision,
  );
  const workspace = useOptionalData<CampaignContext>(
    active ? `${base}/campaigns/${active}/workspace` : null,
    revision + localRevision,
  );
  const inbox = useData<Page<Draft>>(
    `${base}/outreach/inbox?limit=100`,
    revision + localRevision,
  );
  const contacts = useData<Page<Lead>>(`${base}/contacts?limit=100`, revision);
  const segments = useData<
    Page<{ id: string; name: string; filters: LeadFilters }>
  >(`${base}/segments?limit=100`, revision);
  const refresh = () => {
    setLocalRevision((v) => v + 1);
    onChange();
  };
  const closeCreate = useCallback(() => setCreate(false), []);
  async function createCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const form = new FormData(event.currentTarget);
      let ids = form.getAll("contacts").map(String);
      const segment = segments.data?.items.find(
        (s) => s.id === form.get("segment"),
      );
      if (segment) {
        const selection = await request<Page<Lead>>(
          `${base}/leads/query`,
          {
            method: "POST",
            body: JSON.stringify({
              ...initialLeadFilters,
              ...segment.filters,
              page: 1,
              limit: 100,
            }),
          },
          csrf,
        );
        ids = selection.items.map((c) => c.id);
      }
      const campaign = await write<Campaign>("/campaigns", {
        name: String(form.get("name")),
        goal: String(form.get("goal") || ""),
        status: "draft",
        contact_ids: ids,
      });
      setActive(campaign.id);
      setCreate(false);
      setTab("campaign");
      refresh();
      notify("Kampagne mit ausgewählter Zielgruppe angelegt.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function approve(item: Draft) {
    setBusy(true);
    setError("");
    try {
      await write(`/outreach/drafts/${item.id}/approve`);
      refresh();
      notify(
        "Aktuelle Nachrichtenrevision freigegeben. Es wurde nichts versendet.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function handoff(contactId: string, kind: string) {
    setBusy(true);
    setError("");
    try {
      await write("/outreach/handoffs", {
        contact_id: contactId,
        ...(active ? { campaign_id: active } : {}),
        kind,
        note: "Manuell im Outreach-Workspace dokumentiert.",
      });
      refresh();
      notify("Manueller Status als Selbstauskunft gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const current = workspace.data;
  return (
    <>
      <Heading
        title="Outreach-Workspace"
        description="Zielgruppe, Sequenz, Entwürfe und manuelle Gespräche in einem durchgängigen Ablauf."
      >
        <button className="button primary" onClick={() => setCreate(true)}>
          <Plus size={16} /> Neue Kampagne
        </button>
      </Heading>
      <div className="tabs journey-tabs">
        <button
          className={`tab ${tab === "campaign" ? "active" : ""}`}
          onClick={() => setTab("campaign")}
        >
          Kampagnen & Sequenzen
        </button>
        <button
          className={`tab ${tab === "inbox" ? "active" : ""}`}
          onClick={() => setTab("inbox")}
        >
          Entwürfe & Freigaben <Badge>{inbox.data?.total || 0}</Badge>
        </button>
      </div>
      <ErrorNote
        message={error || campaigns.error || workspace.error || inbox.error}
      />
      <div className="info-note">
        <ShieldCheck size={18} />
        <p>
          <strong>Manueller Übergabepunkt.</strong> LinkedIn bleibt ein
          manueller Handoff. Ein Kontaktstatus ist keine Werbeeinwilligung.
          E-Mail benötigt geprüfte Herkunft, gültigen Nachweis, Freigabe,
          Provider und eine letzte Sperrlistenprüfung.
        </p>
      </div>
      {tab === "inbox" ? (
        <section className="panel">
          <div className="panel-head">
            <h2>Zentraler Posteingang für Entwürfe</h2>
            <Badge>Kein Versand durch Entwurf</Badge>
          </div>
          {inbox.loading ? (
            <div className="loading-block">
              <Spinner />
            </div>
          ) : inbox.data?.items.length ? (
            <div className="journey-draft-inbox">
              {inbox.data.items.map((item) => (
                <article
                  className="journey-draft-card outreach-card"
                  key={item.id}
                >
                  <div className="section-title">
                    <h3>
                      {item.contact
                        ? `${item.contact.first_name} ${item.contact.last_name}`
                        : "Kontaktentwurf"}
                    </h3>
                    <Badge
                      tone={
                        item.approved_revision === item.revision
                          ? "green"
                          : "neutral"
                      }
                    >
                      {item.approved_revision === item.revision
                        ? "Freigegeben"
                        : "Prüfung erforderlich"}
                    </Badge>
                  </div>
                  <small>
                    {item.campaign?.name || "Ohne Kampagnenzuordnung"} ·
                    Revision {item.revision}
                  </small>
                  <p className="journey-draft-text">{item.content}</p>
                  {item.blocked_reasons?.map((reason, i) => (
                    <p className="small muted" key={i}>
                      {reason}
                    </p>
                  ))}
                  <div className="form-actions">
                    <button
                      className="button secondary small"
                      onClick={() => setDraft(item)}
                    >
                      Prüfen & bearbeiten
                    </button>
                    <button
                      className="button secondary small"
                      onClick={() => setLeadId(item.contact_id)}
                    >
                      Kontaktprofil
                    </button>
                    {item.state === "draft" && (
                      <button
                        className="button primary small"
                        disabled={busy}
                        onClick={() => approve(item)}
                      >
                        Revision freigeben
                      </button>
                    )}
                    {item.contact?.linkedin_url && (
                      <a
                        className="button secondary small"
                        href={item.contact.linkedin_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={() =>
                          handoff(item.contact_id, "profile_opened")
                        }
                      >
                        LinkedIn manuell öffnen <ExternalLink size={13} />
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              icon={MessageSquare}
              title="Noch keine Entwürfe zur Prüfung"
              description="Wähle eine Kampagne, ergänze ihre Sequenz und erstelle nachvollziehbare Entwürfe."
            />
          )}
        </section>
      ) : (
        <div className="journey-outreach-layout">
          <aside className="panel">
            <div className="panel-head">
              <h2>Kampagnen</h2>
              <Badge>{campaigns.data?.total || 0}</Badge>
            </div>
            <div className="journey-campaign-list">
              {campaigns.data?.items.length ? (
                campaigns.data.items.map((item) => (
                  <button
                    className={`journey-campaign-item ${active === item.id ? "active" : ""}`}
                    key={item.id}
                    onClick={() => setActive(item.id)}
                  >
                    <strong>{item.name}</strong>
                    <span>
                      {item.contacts} Kontakte{" "}
                      <Badge>
                        {(
                          {
                            draft: "Entwurf",
                            active: "Aktiv",
                            paused: "Pausiert",
                            completed: "Abgeschlossen",
                          } as Record<string, string>
                        )[item.status] || item.status}
                      </Badge>
                    </span>
                  </button>
                ))
              ) : (
                <p className="muted">
                  Beginne mit einer klaren Zielgruppe und einem Gesprächsziel.
                </p>
              )}
            </div>
          </aside>
          <div>
            {!active ? (
              <section className="panel">
                <Empty
                  icon={Users}
                  title="Eine Kampagne auswählen"
                  description="Definiere Ziel und Publikum, plane deine Sequenz und prüfe jeden Nachrichtenentwurf."
                >
                  <button
                    className="button primary"
                    onClick={() => setCreate(true)}
                  >
                    Erste Kampagne anlegen
                  </button>
                </Empty>
              </section>
            ) : workspace.loading ? (
              <section className="panel loading-block">
                <Spinner />
              </section>
            ) : (
              current && (
                <>
                  <section className="panel journey-campaign-summary">
                    <div className="panel-head">
                      <div>
                        <h2>{current.campaign.name}</h2>
                        <p>
                          {current.campaign.goal ||
                            "Noch kein Gesprächsziel hinterlegt."}
                        </p>
                      </div>
                      <select
                        aria-label="Kampagnenstatus"
                        value={current.campaign.status}
                        disabled={busy}
                        onChange={async (e) => {
                          setBusy(true);
                          try {
                            await write(
                              `/campaigns/${active}`,
                              { status: e.target.value },
                              "PATCH",
                            );
                            refresh();
                          } catch (error) {
                            setError((error as Error).message);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        <option value="draft">Entwurf</option>
                        <option value="active">Aktiv</option>
                        <option value="paused">Pausiert</option>
                        <option value="completed">Abgeschlossen</option>
                      </select>
                    </div>
                    <div className="journey-progress-counts">
                      {[
                        ["waiting", "Wartend"],
                        ["approved", "Freigegeben"],
                        ["completed", "Manuell erledigt"],
                        ["replied", "Antwort notiert"],
                        ["suppressed", "Gesperrt"],
                      ].map(([key, label]) => (
                        <div key={key}>
                          <strong>
                            {
                              current.counts[
                                key as keyof CampaignContext["counts"]
                              ]
                            }
                          </strong>
                          <small>{label}</small>
                        </div>
                      ))}
                    </div>
                  </section>
                  <SequenceEditor
                    key={`${active}:${localRevision}`}
                    steps={current.sequence}
                    channel={current.campaign.channel || "linkedin_manual"}
                    busy={busy}
                    onSave={async (channel, steps) => {
                      setBusy(true);
                      setError("");
                      try {
                        await write(
                          `/campaigns/${active}/sequence`,
                          { channel, steps },
                          "PUT",
                        );
                        refresh();
                        notify(
                          "Sequenz gespeichert. Keine Nachrichten versendet.",
                        );
                      } catch (error) {
                        setError((error as Error).message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  />
                  <CampaignAgent
                    {...props}
                    campaignId={active}
                    onRefresh={refresh}
                  />
                  <section className="panel">
                    <div className="panel-head">
                      <div>
                        <h2>Zielgruppe & Kontaktreise</h2>
                        <p>
                          Jeder manuelle Status ist als Selbstauskunft
                          gekennzeichnet.
                        </p>
                      </div>
                      <button
                        className="button primary small"
                        disabled={
                          busy ||
                          !current.audience.length ||
                          ["paused", "completed"].includes(
                            current.campaign.status,
                          )
                        }
                        onClick={async () => {
                          setBusy(true);
                          try {
                            const result = await write<{
                              created: number;
                              duplicates: number;
                              notice: string;
                            }>(`/campaigns/${active}/generate-drafts`);
                            refresh();
                            notify(
                              result.notice ||
                                `${result.created} Entwürfe erstellt, ${result.duplicates} bereits vorhanden.`,
                            );
                          } catch (error) {
                            setError((error as Error).message);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        <FileText size={14} /> Entwürfe aus Sequenz erstellen
                      </button>
                    </div>
                    {current.audience.length ? (
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Kontakt</th>
                              <th>Unternehmen</th>
                              <th>Status</th>
                              <th>Manuellen Verlauf dokumentieren</th>
                            </tr>
                          </thead>
                          <tbody>
                            {current.audience.map((lead) => (
                              <tr key={lead.id}>
                                <td>
                                  <button
                                    className="journey-link"
                                    onClick={() => setLeadId(lead.id)}
                                  >
                                    {lead.first_name} {lead.last_name}
                                  </button>
                                </td>
                                <td>{lead.company || "—"}</td>
                                <td>
                                  <Badge>{lead.journey_status}</Badge>
                                </td>
                                <td>
                                  <select
                                    aria-label={`Manueller Verlauf für ${lead.first_name} ${lead.last_name}`}
                                    value=""
                                    disabled={busy}
                                    onChange={(e) =>
                                      handoff(lead.id, e.target.value)
                                    }
                                  >
                                    <option value="">
                                      Aktion als Selbstauskunft notieren
                                    </option>
                                    <option value="profile_opened">
                                      Profil geöffnet
                                    </option>
                                    <option value="connection_requested">
                                      Kontaktanfrage manuell gestellt
                                    </option>
                                    <option value="connected">
                                      Verbindung manuell bestätigt
                                    </option>
                                    <option value="message_sent_manually">
                                      Nachricht selbst gesendet
                                    </option>
                                    <option value="replied">
                                      Antwort selbst erfasst
                                    </option>
                                    <option value="followup_due">
                                      Follow-up erforderlich
                                    </option>
                                  </select>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <Empty
                        icon={Users}
                        title="Noch keine Kontakte zugeordnet"
                        description="Öffne die Kontaktdatenbank und ordne ausgewählte Kontakte per Sammelaktion zu."
                      />
                    )}
                  </section>
                  <section className="panel">
                    <div className="panel-head">
                      <h2>Entwürfe dieser Kampagne</h2>
                      <button
                        className="button secondary small"
                        onClick={() => setTab("inbox")}
                      >
                        Zur Freigabe-Inbox <ArrowRight size={13} />
                      </button>
                    </div>
                    <div className="journey-draft-inbox">
                      {current.drafts.length ? (
                        current.drafts.map((item) => (
                          <article
                            className="journey-draft-card outreach-card"
                            key={item.id}
                          >
                            <div className="section-title">
                              <h3>
                                {current.audience.find(
                                  (c) => c.id === item.contact_id,
                                )?.first_name || "Nachricht"}
                              </h3>
                              <Badge
                                tone={
                                  item.approved_revision === item.revision
                                    ? "green"
                                    : "neutral"
                                }
                              >
                                {item.approved_revision === item.revision
                                  ? "Freigegeben"
                                  : "Entwurf"}
                              </Badge>
                            </div>
                            <p className="journey-draft-text">{item.content}</p>
                            <div className="form-actions">
                              <button
                                className="button secondary small"
                                onClick={() => setDraft(item)}
                              >
                                Entwurf prüfen
                              </button>
                              {item.state === "draft" && (
                                <button
                                  className="button primary small"
                                  disabled={busy}
                                  onClick={() => approve(item)}
                                >
                                  Revision freigeben
                                </button>
                              )}
                            </div>
                          </article>
                        ))
                      ) : (
                        <p className="muted">
                          Die Sequenz liefert Vorlagen. Erst die bewusste
                          Erstellung legt Kontaktentwürfe an.
                        </p>
                      )}
                    </div>
                  </section>
                  <section className="panel">
                    <div className="panel-head">
                      <h2>Kommunikationsverlauf</h2>
                    </div>
                    <div className="journey-timeline">
                      {current.activities.length ? (
                        current.activities.map((item) => (
                          <article key={item.id}>
                            <p>{item.description}</p>
                            <small>
                              {dateTime(item.created_at)} · {item.kind}
                            </small>
                          </article>
                        ))
                      ) : (
                        <p className="muted">
                          Noch keine manuellen Aktivitäten dokumentiert.
                        </p>
                      )}
                    </div>
                  </section>
                </>
              )
            )}
          </div>
        </div>
      )}
      {create && (
        <Modal title="Kampagne anlegen" onClose={closeCreate} wide>
          <form className="modal-body" onSubmit={createCampaign}>
            <div className="form-grid">
              <label>
                Kampagnenname
                <input name="name" required maxLength={200} />
              </label>
              <label>
                Gesprächsziel
                <input name="goal" maxLength={1000} />
              </label>
            </div>
            <label>
              Gespeichertes Segment
              <select name="segment">
                <option value="">Kontakte unten manuell auswählen</option>
                {segments.data?.items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="small muted">
              Bis zu 100 ausgewählte Kontakte. Bei einem Segment wird der
              aktuelle Filterstand übernommen.
            </p>
            <div className="journey-audience-picker">
              {contacts.data?.items.map((lead) => (
                <label className="checkbox-line" key={lead.id}>
                  <input type="checkbox" name="contacts" value={lead.id} />
                  <span>
                    {lead.first_name} {lead.last_name}
                    <small>
                      {lead.company || lead.job_title || "Keine Firmendaten"}
                    </small>
                  </span>
                </label>
              ))}
            </div>
            <ErrorNote message={error} />
            <div className="form-actions">
              <button
                type="button"
                className="button secondary"
                onClick={closeCreate}
              >
                Abbrechen
              </button>
              <button className="button primary" disabled={busy}>
                Kampagne anlegen
              </button>
            </div>
          </form>
        </Modal>
      )}
      {draft && (
        <DraftReview
          item={draft}
          write={write}
          onClose={() => setDraft(null)}
          onSaved={() => {
            setDraft(null);
            refresh();
            notify("Entwurf gespeichert. Vorherige Freigabe ist ungültig.");
          }}
        />
      )}
      {leadId && (
        <LeadProfile
          {...props}
          contactId={leadId}
          onClose={() => setLeadId(null)}
          onUpdated={refresh}
        />
      )}
    </>
  );
}

function SequenceEditor({
  steps,
  channel,
  busy,
  onSave,
}: {
  steps: SequenceStep[];
  channel: "linkedin_manual" | "email";
  busy: boolean;
  onSave: (
    channel: "linkedin_manual" | "email",
    steps: SequenceStep[],
  ) => Promise<void>;
}) {
  const [selectedChannel, setSelectedChannel] = useState(channel);
  const [items, setItems] = useState<SequenceStep[]>(
    steps.length
      ? steps
      : [
          {
            position: 1,
            delay_days: 0,
            channel,
            template:
              "Hallo {{first_name}},\n\nwelche Themen beschäftigen Ihr Team bei {{company}} aktuell?",
          },
        ],
  );
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Geplante Gesprächssequenz</h2>
          <p>
            Vorlagen sind Planungshilfen. Kein Schritt sendet automatisch eine
            LinkedIn-Nachricht.
          </p>
        </div>
        <select
          aria-label="Kampagnenkanal"
          value={selectedChannel}
          onChange={(e) => setSelectedChannel(e.target.value as typeof channel)}
        >
          <option value="linkedin_manual">LinkedIn · manuell</option>
          <option value="email">E-Mail · Policy-Prüfung erforderlich</option>
        </select>
      </div>
      <div className="journey-sequence">
        <p className="small muted">
          Verfügbare Variablen:{" "}
          {"{{first_name}}, {{last_name}}, {{company}}, {{job_title}}, {{evidence}}"}.
          {"{{evidence}}"} wird nur bei „Mit Belegen personalisieren“ mit bis zu
          zwei zitierten Unternehmensangaben gefüllt. Unbekannte Fakten werden
          nicht ergänzt.
        </p>
        {items.map((step, index) => (
          <article className="journey-sequence-step" key={index}>
            <span className="journey-step-number">{index + 1}</span>
            <div>
              <div className="section-title">
                <h3>
                  {index === 0 ? "Erste Nachricht" : `Follow-up ${index}`}
                </h3>
                <Badge>Freigabe erforderlich</Badge>
              </div>
              <label>
                Warten in Tagen
                <input
                  type="number"
                  min={0}
                  max={90}
                  value={step.delay_days}
                  onChange={(e) =>
                    setItems((old) =>
                      old.map((s, i) =>
                        i === index
                          ? { ...s, delay_days: Number(e.target.value) }
                          : s,
                      ),
                    )
                  }
                />
              </label>
              <label>
                Nachrichtenvorlage
                <textarea
                  rows={4}
                  value={step.template}
                  onChange={(e) =>
                    setItems((old) =>
                      old.map((s, i) =>
                        i === index ? { ...s, template: e.target.value } : s,
                      ),
                    )
                  }
                  maxLength={3000}
                />
              </label>
              {items.length > 1 && (
                <button
                  className="button secondary small"
                  onClick={() =>
                    setItems((old) => old.filter((_, i) => i !== index))
                  }
                >
                  Schritt entfernen
                </button>
              )}
            </div>
          </article>
        ))}
        <div className="form-actions">
          <button
            className="button secondary"
            disabled={items.length >= 8 || busy}
            onClick={() =>
              setItems((old) => [
                ...old,
                {
                  position: old.length + 1,
                  delay_days: 3,
                  channel: selectedChannel,
                  template:
                    "Hallo {{first_name}},\n\nich möchte mich noch einmal zu meiner vorherigen Nachricht melden.",
                },
              ])
            }
          >
            Schritt ergänzen
          </button>
          <button
            className="button primary"
            disabled={busy || items.some((s) => !s.template.trim())}
            onClick={() =>
              onSave(
                selectedChannel,
                items.map((s, i) => ({
                  position: i + 1,
                  delay_days: s.delay_days,
                  channel: selectedChannel,
                  template: s.template,
                })),
              )
            }
          >
            Sequenz speichern
          </button>
        </div>
      </div>
    </section>
  );
}
function DraftReview({
  item,
  write,
  onClose,
  onSaved,
}: {
  item: Draft;
  write: JourneyProps["write"];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [content, setContent] = useState(item.content);
  const [subject, setSubject] = useState(
    item.subject || "Gespräch vorbereiten",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal title="Nachrichtenrevision prüfen" onClose={onClose} wide>
      <form
        className="modal-body"
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          try {
            await write(
              `/outreach/drafts/${item.id}`,
              { content, subject, revision: item.revision },
              "PATCH",
            );
            onSaved();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Badge>
          Revision {item.revision} ·{" "}
          {item.source === "offline"
            ? "Offline-Vorlage"
            : item.source || "Benutzereingabe"}
        </Badge>
        <label>
          Betreff / interner Nachrichtentitel
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            required
            maxLength={200}
          />
        </label>
        <label>
          Nachrichteninhalt
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={8}
            required
            maxLength={3000}
          />
        </label>
        <p className="small muted">
          Speichern erhöht die Revision und hebt bestehende Freigaben auf. Eine
          Freigabe versendet keine Nachricht.
        </p>
        <ErrorNote message={error} />
        <div className="form-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Abbrechen
          </button>
          <button className="button primary" disabled={busy}>
            Revision speichern
          </button>
        </div>
      </form>
    </Modal>
  );
}

function safeDomain(value: string) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol)
      ? url.hostname
      : "Website nicht geprüft";
  } catch {
    return "Website nicht geprüft";
  }
}

function DemoDiscoveryQuickAction({ write, notify, onChange }: JourneyProps) {
  const [result, setResult] = useState<{
    id: string;
    results: unknown[];
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [imported, setImported] = useState(false);
  const [error, setError] = useState("");
  return (
    <section className="panel padded journey-demo-shortcut">
      <div>
        <strong>Synthetischer Demo-Ablauf</strong>
        <p className="small muted">
          Fünf feste Entwicklungsbeispiele; keine recherchierten Treffer für
          deine Filter.
        </p>
      </div>
      <ErrorNote message={error} />
      <button
        className="button secondary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            setResult(
              await write("/discovery/runs", {
                topic: "Explizite synthetische Entwicklungsbeispiele",
              }),
            );
            setImported(false);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        Beispielsuche starten
      </button>
      {result && (
        <div className="journey-inline-actions">
          <h2>{result.results.length} synthetische Beispiele</h2>
          <button
            className="button secondary"
            disabled={busy || imported}
            onClick={async () => {
              setBusy(true);
              try {
                const response = await write<{ created: number }>(
                  `/discovery/runs/${result.id}/import`,
                );
                setImported(true);
                onChange();
                notify(`${response.created} synthetische Kontakte importiert.`);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {imported ? "Importiert" : "Beispiele importieren"}
          </button>
        </div>
      )}
    </section>
  );
}
