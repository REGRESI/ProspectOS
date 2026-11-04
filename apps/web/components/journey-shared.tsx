"use client";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { request } from "@/lib/api";
import { Badge } from "./ui";
import type { Lead, Completeness } from "./journey-types";

export const supportLabels: Record<string, string> = {
  employee_range: "Mitarbeiterzahl",
  job_titles: "Zielrollen",
  seniority: "Seniorität",
  contacts: "Ansprechpartner",
  radius_km: "Radius",
};

export function Progress({ value }: { value: Completeness | undefined }) {
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

export function Pager({
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

export function useQuery<T>(
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

export function ScoreDetails({ lead }: { lead: Pick<Lead, "score"> }) {
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

export function useOptionalData<T>(path: string | null, revision: number) {
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

export function safeDomain(value: string) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol)
      ? url.hostname
      : "Website nicht geprüft";
  } catch {
    return "Website nicht geprüft";
  }
}
