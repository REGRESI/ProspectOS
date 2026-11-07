"use client";
import { useState } from "react";
import { request } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Heading } from "./ui";
import { SearchInput, SkeletonTable, SortHeader, useTable } from "./table";

type Write = <T>(path: string, body?: unknown, method?: string) => Promise<T>;

const LEVEL: Record<string, { label: string; tone: string }> = {
  linkedin: { label: "LinkedIn geprüft", tone: "green" },
  email: { label: "Nur E-Mail", tone: "amber" },
  nothing: { label: "Nichts", tone: "red" },
};
export const PROFILE_STATUS: Record<string, { label: string; tone: string }> = {
  verified: { label: "Geprüft", tone: "green" },
  confirmed: { label: "Von dir bestätigt", tone: "green" },
  unchecked: { label: "Noch nicht geprüft", tone: "neutral" },
  unsure: { label: "Unsicher", tone: "amber" },
  not_found: { label: "Nicht gefunden", tone: "red" },
};

type Quality = {
  counts: {
    companies: number;
    with_contact: number;
    with_linkedin: number;
    only_email: number;
    nothing: number;
    contacts: number;
    contacts_unchecked: number;
    contacts_unsure: number;
    contacts_not_found: number;
  };
  sample: {
    company_id: string;
    company: string;
    location: string;
    website: string | null;
    level: string;
    contacts: {
      id: string;
      name: string;
      job_title: string;
      linkedin_status: string;
      linkedin_url: string | null;
      linkedin_reason: string;
    }[];
    emails: { email: string; kind: string }[];
  }[];
};

/** Starts the Brave check as a background job and reports back in one sentence. */
export function useProfileCheck(
  base: string,
  write: Write,
  notify: (m: string) => void,
  onDone: () => void,
) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function start(body: Record<string, unknown> = {}) {
    setBusy(true);
    setError("");
    try {
      const job = await write<{ id: string }>("/linkedin-check", body);
      notify("Profilprüfung läuft. Das dauert etwa eine Sekunde pro Kontakt.");
      for (let i = 0; i < 240; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const state = await request<{ status: string; result?: Record<string, number> }>(
          `${base}/jobs/${job.id}`,
        );
        if (state.status === "succeeded") {
          const r = state.result || {};
          notify(
            `${r.verified ?? 0} Profile geprüft, ${r.role_contacts ?? 0} neue Ansprechpartner, ${r.unsure ?? 0} unsicher, ${r.not_found ?? 0} nicht gefunden.`,
          );
          break;
        }
        if (["failed", "ambiguous", "cancelled"].includes(state.status)) {
          setError("Die Prüfung ist fehlgeschlagen. Bitte die Brave-Verbindung unter Einstellungen → Verbindungen prüfen.");
          break;
        }
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      onDone();
    }
  }
  return { busy, error, start };
}

export function DataQualityPage({
  base,
  write,
  notify,
}: {
  base: string;
  write: Write;
  notify: (m: string) => void;
}) {
  const [seed, setSeed] = useState(() => String(Date.now()));
  const [revision, setRevision] = useState(0);
  const { data, error, loading } = useData<Quality>(`${base}/data-quality?sample=20&seed=${seed}`, revision);
  const check = useProfileCheck(base, write, notify, () => setRevision((v) => v + 1));
  const c = data?.counts;
  const share = (n: number) => (c && c.companies ? Math.round((n / c.companies) * 100) : 0);
  return (
    <>
      <Heading
        title="Datenqualität"
        description="Wie viele Firmen du über LinkedIn, nur per E-Mail oder gar nicht erreichen kannst. Dazu eine Stichprobe zum Nachprüfen."
      >
        <button
          className="button primary"
          disabled={check.busy || !c || c.contacts_unchecked === 0}
          onClick={() => check.start({ limit: 200 })}
        >
          {check.busy ? "Prüfe Profile …" : `Profile prüfen${c ? ` (${c.contacts_unchecked})` : ""}`}
        </button>
      </Heading>
      <ErrorNote message={error || check.error} />
      {c ? (
        <div className="metrics" data-testid="quality-counts">
          <Metric label="Firmen" value={c.companies} />
          <Metric label="Mit Ansprechpartner" value={c.with_contact} note={`${share(c.with_contact)} %`} />
          <Metric label="Mit geprüftem LinkedIn" value={c.with_linkedin} note={`${share(c.with_linkedin)} %`} />
          <Metric label="Nur E-Mail" value={c.only_email} note={`${share(c.only_email)} %`} />
          <Metric label="Nichts" value={c.nothing} note={`${share(c.nothing)} %`} />
        </div>
      ) : (
        <SkeletonTable rows={1} cols={5} />
      )}
      {c && (
        <p className="muted small-print">
          {c.contacts} Ansprechpartner: {c.contacts_unchecked} noch nicht geprüft, {c.contacts_unsure} unsicher,{" "}
          {c.contacts_not_found} ohne LinkedIn-Profil. Gesucht wird über die Brave Search API, LinkedIn selbst wird nie aufgerufen.
          Gespeichert werden nur die Profiladresse und der Grund.
        </p>
      )}
      <section className="section-block">
        <div className="section-head">
          <h2>Stichprobe: 20 zufällige Firmen</h2>
          <button className="button secondary small" onClick={() => setSeed(String(Date.now()))}>
            Neue Stichprobe
          </button>
        </div>
        {loading && !data ? (
          <SkeletonTable rows={8} cols={4} />
        ) : (
          <div className="table-wrap">
            <table className="data-table" data-testid="quality-sample">
              <thead>
                <tr>
                  <th>Firma</th>
                  <th>Ansprechpartner</th>
                  <th>LinkedIn</th>
                  <th>E-Mail</th>
                  <th>Erreichbar</th>
                </tr>
              </thead>
              <tbody>
                {data?.sample.map((row) => (
                  <tr key={row.company_id}>
                    <td>
                      <a href={`/companies/${row.company_id}`}>
                        <strong>{row.company}</strong>
                      </a>
                      <small className="muted block">{row.location}</small>
                    </td>
                    <td>
                      {row.contacts.length ? (
                        row.contacts.map((p) => (
                          <span className="block" key={p.id}>
                            {p.name}
                            {p.job_title && <small className="muted"> · {p.job_title}</small>}
                          </span>
                        ))
                      ) : (
                        <span className="muted">keiner</span>
                      )}
                    </td>
                    <td>
                      {row.contacts.map((p) => (
                        <span className="block" key={p.id}>
                          {p.linkedin_url ? (
                            <a href={p.linkedin_url} target="_blank" rel="noreferrer">
                              Profil
                            </a>
                          ) : (
                            <Badge tone={PROFILE_STATUS[p.linkedin_status]?.tone}>
                              {PROFILE_STATUS[p.linkedin_status]?.label || p.linkedin_status}
                            </Badge>
                          )}
                          {p.linkedin_reason && <small className="muted"> {p.linkedin_reason}</small>}
                        </span>
                      ))}
                    </td>
                    <td>
                      {row.emails.length ? (
                        row.emails.map((m) => (
                          <span className="block" key={m.email}>
                            {m.email} <small className="muted">{m.kind}</small>
                          </span>
                        ))
                      ) : (
                        <span className="muted">keine</span>
                      )}
                    </td>
                    <td>
                      <Badge tone={LEVEL[row.level].tone}>{LEVEL[row.level].label}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function Metric({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      {note && <small className="muted">{note}</small>}
    </div>
  );
}

type Campaign = {
  items: {
    email: string;
    contact: string;
    source: string;
    source_url: string | null;
    company_id: string;
    company: string;
    location: string;
    kind: string;
  }[];
  total: number;
  personal: number;
  general: number;
  notice: string;
};

export function EmailCampaignPage({ base }: { base: string }) {
  const { data, error, loading } = useData<Campaign>(`${base}/email-campaign`);
  const [kind, setKind] = useState("");
  const items = (data?.items || []).filter((i) => !kind || i.kind === kind);
  const table = useTable(
    items,
    { search: (i) => `${i.company} ${i.email} ${i.contact} ${i.location}`, initialSort: "company" },
    {
      company: (i) => i.company,
      email: (i) => i.email,
      kind: (i) => i.kind,
      source: (i) => i.source,
    },
  );
  return (
    <>
      <Heading
        title="E-Mail-Kampagne"
        description="Alle Firmen ohne geprüftes LinkedIn-Profil, die eine E-Mail-Adresse haben. Die Liste füllt sich von selbst."
      />
      <ErrorNote message={error} />
      <p className="notice-line" data-testid="email-locked">
        <Badge tone="amber">Versand gesperrt</Badge> {data?.notice || "Hier wird nichts versendet."}
      </p>
      <div className="table-toolbar">
        <SearchInput value={table.query} onChange={table.setQuery} label="E-Mail-Liste durchsuchen" />
        <label className="inline-select">
          Art
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Art der Adresse">
            <option value="">Alle ({data?.total ?? 0})</option>
            <option value="persönlich">Persönlich ({data?.personal ?? 0})</option>
            <option value="allgemein">Allgemein ({data?.general ?? 0})</option>
          </select>
        </label>
      </div>
      {loading && !data ? (
        <SkeletonTable rows={8} cols={5} />
      ) : table.rows.length === 0 ? (
        <p className="empty-line">Keine Adressen. Firmen ohne LinkedIn-Profil mit E-Mail erscheinen hier.</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table" data-testid="email-campaign">
            <thead>
              <tr>
                <SortHeader label="Firma" column="company" table={table} />
                <SortHeader label="E-Mail" column="email" table={table} />
                <SortHeader label="Art" column="kind" table={table} />
                <SortHeader label="Quelle" column="source" table={table} />
              </tr>
            </thead>
            <tbody>
              {table.rows.map((r) => (
                <tr key={r.company_id + r.email}>
                  <td>
                    <strong>{r.company}</strong>
                    <small className="muted block">{r.location}</small>
                  </td>
                  <td>
                    {r.email}
                    {r.contact && <small className="muted block">{r.contact}</small>}
                  </td>
                  <td>
                    <Badge tone={r.kind === "persönlich" ? "green" : "neutral"}>{r.kind}</Badge>
                  </td>
                  <td>
                    {r.source_url ? (
                      <a href={r.source_url} target="_blank" rel="noreferrer">
                        {r.source}
                      </a>
                    ) : (
                      r.source
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
