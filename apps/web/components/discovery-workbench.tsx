"use client";
import { useEffect, useState } from "react";
import { Search, ShieldCheck } from "lucide-react";
import { request, dateTime } from "@/lib/api";
import type { Page } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Modal, Spinner } from "./ui";
import type { JourneyProps, Candidate, DiscoveryProvider, SearchDefinition, SearchFilters } from "./journey-types";
import { initialSearchFilters } from "./journey-types";
import { Pager, Progress, ScoreDetails, supportLabels, useOptionalData } from "./journey-shared";

export function DiscoveryWorkbench(props: JourneyProps) {
  const { base, write, notify, onChange, revision } = props;
  const [briefing, setBriefing] = useState(
    "Büros und Dienstleistungsunternehmen in Offenburg",
  );
  const [filters, setFilters] = useState<SearchFilters>(() =>
    props.demo
      ? initialSearchFilters
      : { ...initialSearchFilters, provider: "osm", city: "Offenburg", radius_km: 10, max_results: 50 },
  );
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
    (i) => i.name === "Firmensuche mit Lizenz",
  );
  return (
    <>
      <Heading
        title="Firmen finden"
        description="Suche Firmen in deiner Umgebung. Du entscheidest, welche übernommen werden."
      />
      {props.demo && filters.provider === "synthetic" && <DemoDiscoveryQuickAction {...props} />}
      <div className="journey-discovery-layout">
        <aside className="panel journey-search-panel">
          <div className="panel-head">
            <h2>Suche</h2>
          </div>
          <div className="modal-body">
            {activeProvider && (
              <div
                className={`provider-capability ${activeProvider.available ? "ok" : "off"}`}
                data-testid="provider-capability"
                title={activeProvider.reason || undefined}
              >
                <strong>{activeProvider.available ? "Verfügbar" : "Nicht verfügbar"}</strong>
                {!activeProvider.available && (
                  <span> · noch nicht eingerichtet, siehe Einstellungen → Status</span>
                )}
                <small>
                  Lizenz {activeProvider.license} · {activeProvider.cost}
                  {!!activeProvider.unsupported.length &&
                    ` · nicht filterbar: ${activeProvider.unsupported.map((u) => supportLabels[u] || u).join(", ")}`}
                </small>
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
                  filters.provider === "osm" || filters.provider === "northdata"
                    ? "osm-category-options"
                    : undefined
                }
              />
            </label>
            {(filters.provider === "osm" ||
              filters.provider === "northdata") && (
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
            <details className="more-filters">
              <summary>Weitere Filter</summary>
            <label>
              In eigenen Worten
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
              Felder daraus ausfüllen
            </button>
            <p className="small muted">
              Füllt Ort und Branchen aus deiner Beschreibung. Bitte danach prüfen.
            </p>
            {warnings.map((w, i) => (
              <p className="info-note small" key={i}>
                {w}
              </p>
            ))}
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
                <option value="northdata">
                  North Data · Registerdaten im Umkreis
                  {providers.data &&
                  !providers.data.items.find((p) => p.id === "northdata")
                    ?.available
                    ? " (nicht aktiviert)"
                    : ""}
                </option>
                {props.demo && (
                  <>
                    <option value="synthetic">Beispieldaten (nur Demo)</option>
                    <option value="pdl">People Data Labs (Lizenz nötig)</option>
                  </>
                )}
              </select>
            </label>
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
            </div>
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
                placeholder="z. B. Geschäftsführung"
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
                max={
                  filters.provider === "osm" || filters.provider === "northdata"
                    ? 200
                    : 25
                }
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
            <label>
              Name der Suche
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="z. B. Büros in der Ortenau"
                maxLength={120}
              />
            </label>
            </details>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />{" "}
              Filter geprüft. Ich nutze die Treffer nur für eigene Geschäftskontakte.
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
                <h2>Gespeicherte Suchen</h2>
                <p>Ein Klick übernimmt die Filter. Danach noch einmal prüfen und starten.</p>
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
                            ? `OpenStreetMap · ${item.filters.radius_km || 10} km`
                            : item.filters.provider === "northdata"
                              ? `North Data · ${item.filters.radius_km || 10} km`
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
                    : "Hier erscheinen die gefundenen Firmen. Wähle aus, welche du übernehmen willst."}
                </p>
              </div>
              {job && (
                <Badge tone={job.status === "succeeded" ? "green" : "neutral"}>
                  {job.status === "succeeded"
                    ? "Abgeschlossen"
                    : job.status === "queued"
                      ? "In Warteschlange"
                      : job.status === "running"
                        ? "Läuft"
                        : job.status}
                </Badge>
              )}
            </div>
            {running ? (
              <div className="loading-block">
                <Spinner /> Suche läuft. Das dauert meist unter einer Minute.
              </div>
            ) : job?.last_error ? (
              <ErrorNote
                message={`Die Suche ist fehlgeschlagen (${job.last_error}). Bitte später erneut versuchen oder den Status unter Einstellungen prüfen.`}
              />
            ) : !run ? (
              <Empty
                icon={Search}
                title="Noch keine Suche gestartet"
                description="Wähle Ort, Umkreis und Branchen und starte die Suche."
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
                    <option value="score">Passung</option>
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
                            <th>Passung</th>
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

export function DemoDiscoveryQuickAction({ write, notify, onChange }: JourneyProps) {
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
