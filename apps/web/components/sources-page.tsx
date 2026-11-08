"use client";
import { Database } from "lucide-react";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Heading, Spinner } from "./ui";

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

export function SourcesPage({ base, onNavigate }: { base: string; onNavigate?: (p: string) => void }) {
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
