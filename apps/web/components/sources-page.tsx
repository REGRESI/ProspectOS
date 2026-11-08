"use client";
import { useState } from "react";
import { Copy, Database, ExternalLink, Globe, ScrollText, UserRoundSearch } from "lucide-react";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Heading, Spinner } from "./ui";
import type { Write } from "./growth-modules";

type Source = {
  id: string;
  label: string;
  delivers: string;
  license: string;
  start_path: string;
  ready: boolean;
  reason: string | null;
  quality: {
    hits: number;
    hits_unit: string;
    contact_rate: number | null;
    contacts: number;
    verified_linkedin: number;
    verified_linkedin_rate: number | null;
    errors: Record<string, number>;
    error_count: number;
  };
};
const pct = (v: number | null) => (v === null ? "–" : `${Math.round(v * 100)} %`);

type Gap = {
  companies: number;
  without_contact: number;
  registered: number;
  unregistered: number;
  unknown: number;
  by_form: Record<string, number>;
  role_contacts: number;
  estimate: { extra_contacts: number; per_company: number; basis: string; measured: boolean };
  notice: string;
};
type Finder = {
  missing_websites: number;
  last: {
    status: string;
    error: string | null;
    result: {
      found: number;
      not_found: number;
      error: number;
      items: { company_id: string; company: string; result: string; website: string | null; reason: string }[];
    } | null;
  } | null;
};
type NameResult = { created: { name: string }[]; suggested: { name: string; company: string }[]; unclear: number };

/** M9d/M9e: companies without a contact person and honest ways to close the gap. */
function RegisterGapCard({ base, write, notify }: { base: string; write?: Write; notify?: (m: string) => void }) {
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [names, setNames] = useState<NameResult | null>(null);
  const gap = useData<Gap>(`${base}/sources/register-gap`, revision);
  const finder = useData<Finder>(`${base}/website-finder`, revision);
  async function run<T>(fn: () => Promise<T>, message: string) {
    setBusy(true);
    setError("");
    try {
      const result = await fn();
      setRevision((v) => v + 1);
      notify?.(message);
      return result;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }
  const g = gap.data;
  const last = finder.data?.last;
  return (
    <section className="panel source-panel register-gap" data-testid="register-gap">
      <h2>
        <UserRoundSearch size={16} /> Firmen ohne Ansprechpartner
      </h2>
      <ErrorNote message={error || gap.error} />
      {!g ? (
        <Spinner />
      ) : (
        <>
          <div className="gap-stats">
            <div>
              <strong>{g.without_contact}</strong>
              <span>von {g.companies} Firmen ohne Ansprechpartner</span>
            </div>
            <div>
              <strong>{g.registered}</strong>
              <span>registerpflichtig (GmbH, UG, AG, KG, OHG, e.K.)</span>
            </div>
            <div>
              <strong>{g.unregistered}</strong>
              <span>vermutlich ohne Register (Praxis, Kanzlei, GbR, Einzelunternehmen)</span>
            </div>
            <div>
              <strong>{g.unknown}</strong>
              <span>Rechtsform unbekannt</span>
            </div>
          </div>
          <p className="gap-estimate">
            North Data würde etwa <strong>{g.estimate.extra_contacts}</strong> Ansprechpartner ergänzen{" "}
            <Badge tone={g.estimate.measured ? "green" : "amber"}>{g.estimate.measured ? "gemessen" : "Annahme"}</Badge>
            <small className="journey-cell-sub">{g.estimate.basis}</small>
          </p>
          <p className="muted small-print">{g.notice}</p>
          {write && (
            <div className="gap-actions">
              <button
                className="button secondary small"
                disabled={busy || !g.without_contact}
                onClick={() =>
                  void run(
                    () => write<{ created: number }>("/companies/role-contacts", { all_without_contact: true }),
                    "Rollen-Adressen und Besuchsaufgaben angelegt.",
                  )
                }
              >
                <ScrollText size={14} /> Brief an die Geschäftsführung vorbereiten
              </button>
              <button
                className="button secondary small"
                disabled={busy || !g.without_contact}
                onClick={async () => {
                  const r = await run(
                    () => write<NameResult>("/companies/names-from-company-names", {}),
                    "Firmennamen ausgewertet.",
                  );
                  if (r) setNames(r);
                }}
              >
                Namen aus Firmennamen
              </button>
              <button
                className="button secondary small"
                disabled={busy || !finder.data?.missing_websites}
                onClick={() =>
                  void run(() => write("/companies/find-websites", {}), "Website-Suche gestartet (bis zu 25 Firmen).")
                }
              >
                <Globe size={14} /> Fehlende Websites suchen ({finder.data?.missing_websites ?? "–"})
              </button>
            </div>
          )}
          <p className="muted small-print">
            Rollen-Adressen sind keine Personen: Der Brief geht „An die Geschäftsführung“ (bzw. Praxis- oder
            Kita-Leitung), dazu eine Besuchsaufgabe „nach der zuständigen Person fragen“. Bereits angelegt:{" "}
            {g.role_contacts}.
          </p>
          {names && (
            <p className="small-print" data-testid="name-result">
              {names.created.length} Kontakte aus Firmennamen angelegt
              {names.suggested.length ? `, ${names.suggested.length} zur Prüfung (${names.suggested.map((s) => s.name).join(", ")})` : ""}
              , {names.unclear} ohne erkennbaren Namen. Quelle: Firmenname.
            </p>
          )}
          {last && (
            <div className="finder-report" data-testid="finder-report">
              <strong>Letzte Website-Suche: </strong>
              {last.result
                ? `${last.result.found} gefunden, ${last.result.not_found} ohne passenden Treffer, ${last.result.error} Fehler.`
                : last.status === "failed"
                  ? `fehlgeschlagen (${last.error})`
                  : "läuft …"}
              {last.result?.items.length ? (
                <ul>
                  {last.result.items.map((i) => (
                    <li key={i.company_id}>
                      {i.company}:{" "}
                      {i.result === "found" ? <Badge tone="green">{i.website}</Badge> : <span className="muted">{i.reason}</span>}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** Professional registers: start page plus the search term to paste. No automated queries. */
export function RegisterLinks({ base, companyId }: { base: string; companyId: string }) {
  const links = useData<{
    items: { id: string; label: string; url: string; search_term: string; suggested: boolean }[];
  }>(`${base}/companies/${companyId}/register-links`, 0);
  if (!links.data) return null;
  return (
    <section className="panel register-links" data-testid="register-links">
      <h2>Berufsregister (von Hand suchen)</h2>
      <ul className="print-options">
        {links.data.items.map((l) => (
          <li key={l.id}>
            <strong>
              <a href={l.url} target="_blank" rel="noreferrer noopener">
                {l.label} <ExternalLink size={12} />
              </a>{" "}
              {l.suggested && <Badge tone="green">passt</Badge>}
            </strong>
            <button
              className="link-button"
              onClick={() => void navigator.clipboard?.writeText(l.search_term)}
              title="Suchbegriff kopieren"
            >
              <Copy size={12} /> {l.search_term}
            </button>
          </li>
        ))}
      </ul>
      <p className="muted small-print">
        ProspectOS fragt diese Register nicht automatisch ab. Gefundene Namen mit Quelle und Datum eintragen.
      </p>
    </section>
  );
}

export function SourcesPage({
  base,
  onNavigate,
  write,
  notify,
}: {
  base: string;
  onNavigate?: (p: string) => void;
  write?: Write;
  notify?: (m: string) => void;
}) {
  const data = useData<{
    items: Source[];
    register_options: { name: string; status: string; note: string }[];
    notice: string;
  }>(`${base}/sources`, 0);
  return (
    <>
      <Heading
        title="Quellen"
        description="Woher deine Firmen und Kontakte kommen und wie gut jede Quelle liefert."
      />
      <ErrorNote message={data.error} />
      {!data.data ? (
        <div className="loading-block">
          <Spinner />
        </div>
      ) : (
        <>
          <section className="panel source-panel" data-testid="sources">
            <div className="table-scroll">
              <table className="source-table">
                <thead>
                  <tr>
                    <th>Quelle</th>
                    <th>Treffer</th>
                    <th>Mit Ansprechpartner</th>
                    <th>Geprüftes LinkedIn</th>
                    <th>Fehler (30 Tage)</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.data.items.map((s) => (
                    <tr key={s.id} data-testid={`source-${s.id}`}>
                      <td>
                        <strong>{s.label}</strong>
                        <small className="journey-cell-sub">{s.delivers}</small>
                        <small className="journey-cell-sub">{s.license}</small>
                      </td>
                      <td className="num">
                        {s.quality.hits} <small className="muted">{s.quality.hits_unit}</small>
                      </td>
                      <td className="num">{pct(s.quality.contact_rate)}</td>
                      <td className="num">
                        {pct(s.quality.verified_linkedin_rate)}
                        <small className="journey-cell-sub">
                          {s.quality.verified_linkedin} von {s.quality.contacts}
                        </small>
                      </td>
                      <td className="num">
                        {s.quality.error_count ? (
                          <span title={Object.entries(s.quality.errors).map(([k, v]) => `${k}: ${v}`).join(", ")}>
                            <Badge tone="red">{s.quality.error_count}</Badge>
                          </span>
                        ) : (
                          "0"
                        )}
                      </td>
                      <td>
                        {s.ready ? <Badge tone="green">bereit</Badge> : <Badge>nicht eingerichtet</Badge>}
                        {s.reason && <small className="journey-cell-sub">{s.reason}</small>}
                        <button className="link-button source-start" onClick={() => onNavigate?.(s.start_path)}>
                          Öffnen
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small-print source-notice">{data.data.notice}</p>
          </section>
          <RegisterGapCard base={base} write={write} notify={notify} />
          <section className="panel source-panel">
            <h2>
              <Database size={16} /> Handelsregister-Daten (nur lizenziert)
            </h2>
            <ul className="print-options">
              {data.data.register_options.map((o) => (
                <li key={o.name}>
                  <strong>
                    {o.name} <Badge>{o.status}</Badge>
                  </strong>
                  <small className="muted">{o.note}</small>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </>
  );
}
