"use client";
import { useState } from "react";
import { ArrowDown, ArrowUp, ExternalLink } from "lucide-react";
import type { Page } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Empty, ErrorNote, Heading } from "./ui";
import type { JourneyProps } from "./journey-types";
import { Pager } from "./journey-shared";
import { AddContact, LeadProfile } from "./lead-database";
import { SearchInput, SkeletonTable } from "./table";
import { STAGE_LABELS, STAGE_TONE } from "./today-view";

type Stage = keyof typeof STAGE_LABELS;
type Row = {
  id: string;
  first_name: string;
  last_name: string;
  job_title: string;
  location: string;
  linkedin_url: string | null;
  company: string;
  company_id: string | null;
  outreach_stage: Stage;
  created_at: string;
};

/** Header cell that sorts on the server ("name" / "-name"). */
export function ServerSort({
  label,
  column,
  sort,
  onSort,
  descFirst = false,
  className = "",
}: {
  label: string;
  column: string;
  sort: string;
  onSort: (s: string) => void;
  descFirst?: boolean;
  className?: string;
}) {
  const active = sort.replace(/^-/, "") === column;
  const desc = sort.startsWith("-");
  const next = active ? (desc ? column : `-${column}`) : descFirst ? `-${column}` : column;
  return (
    <th
      className={`sortable ${className}`}
      scope="col"
      tabIndex={0}
      aria-sort={active ? (desc ? "descending" : "ascending") : "none"}
      onClick={() => onSort(next)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSort(next);
        }
      }}
    >
      {label}
      {active && (desc ? <ArrowDown size={12} /> : <ArrowUp size={12} />)}
    </th>
  );
}

export function ContactsTable(props: JourneyProps) {
  const { base, write, revision, onImport, onNavigate } = props;
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState("");
  const [sort, setSort] = useState("-created");
  const [page, setPage] = useState(1);
  const [local, setLocal] = useState(0);
  const [active, setActive] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const query = `${base}/contacts?page=${page}&limit=50&sort=${sort}&stage=${stage}&search=${encodeURIComponent(search)}`;
  const contacts = useData<Page<Row>>(query, revision + local);
  const counts = useData<{ counts: Record<Stage, number> }>(`${base}/today/pipeline`, revision + local);
  const total = counts.data ? Object.values(counts.data.counts).reduce((a, b) => a + b, 0) : 0;

  async function changeStage(id: string, next: Stage) {
    setError("");
    try {
      await write(`/contacts/${id}/outreach-stage`, { stage: next }, "PUT");
      setLocal((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <Heading title="Kontakte" description="Alle Ansprechpersonen mit ihrem Stand. Den Status änderst du direkt in der Liste.">
        <button className="button secondary" onClick={onImport}>
          CSV importieren
        </button>
        <button className="button primary" onClick={() => setAdding(true)}>
          Kontakt hinzufügen
        </button>
      </Heading>
      <ErrorNote message={error || contacts.error} />
      <div className="table-toolbar">
        <SearchInput
          value={search}
          onChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          label="Kontakte suchen"
          placeholder="Name, Firma, Rolle oder Ort"
        />
        <select
          aria-label="Status"
          value={stage}
          onChange={(e) => {
            setStage(e.target.value);
            setPage(1);
          }}
        >
          <option value="">Jeder Status</option>
          {(Object.keys(STAGE_LABELS) as Stage[]).map((k) => (
            <option key={k} value={k}>
              {STAGE_LABELS[k]}
              {counts.data ? ` (${counts.data.counts[k] ?? 0})` : ""}
            </option>
          ))}
        </select>
        <span className="count">
          {contacts.data ? `${contacts.data.total} von ${total || contacts.data.total}` : ""}
        </span>
      </div>
      {contacts.loading && !contacts.data ? (
        <SkeletonTable cols={5} />
      ) : !contacts.data?.items.length ? (
        <Empty
          title={search || stage ? "Keine Treffer" : "Noch keine Kontakte"}
          description={
            search || stage
              ? "Ändere die Suche oder den Status-Filter."
              : "Füge einen Kontakt hinzu oder importiere eine CSV-Datei."
          }
        />
      ) : (
        <>
          <div className="table-wrap">
            <table data-testid="contacts-table">
              <thead>
                <tr>
                  <ServerSort label="Name" column="name" sort={sort} onSort={setSort} />
                  <ServerSort label="Firma" column="company" sort={sort} onSort={setSort} className="hide-sm" />
                  <ServerSort label="Ort" column="location" sort={sort} onSort={setSort} className="hide-sm" />
                  <ServerSort label="Status" column="stage" sort={sort} onSort={setSort} />
                  <th scope="col" className="hide-sm">LinkedIn</th>
                  <ServerSort label="Hinzugefügt" column="created" sort={sort} onSort={setSort} descFirst className="hide-sm" />
                </tr>
              </thead>
              <tbody>
                {contacts.data.items.map((c) => (
                  <tr key={c.id} className="clickable" onClick={() => setActive(c.id)}>
                    <td className="cell-main">
                      <strong>{[c.first_name, c.last_name].filter(Boolean).join(" ")}</strong>
                      <small>{[c.job_title, c.company].filter(Boolean).join(" · ") || " "}</small>
                    </td>
                    <td className="hide-sm">
                      {c.company_id ? (
                        <button
                          className="link-button plain"
                          onClick={(e) => {
                            e.stopPropagation();
                            onNavigate?.(`/companies/${c.company_id}`);
                          }}
                        >
                          {c.company}
                        </button>
                      ) : (
                        <span className="muted">–</span>
                      )}
                    </td>
                    <td className="hide-sm">{c.location || <span className="muted">–</span>}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <span className={`stage-cell tone-${STAGE_TONE[c.outreach_stage]}`}>
                        <select
                          aria-label={`Status von ${c.first_name} ${c.last_name}`}
                          className="stage-select quiet"
                          value={c.outreach_stage}
                          onChange={(e) => changeStage(c.id, e.target.value as Stage)}
                        >
                          {(Object.keys(STAGE_LABELS) as Stage[]).map((k) => (
                            <option key={k} value={k}>
                              {STAGE_LABELS[k]}
                            </option>
                          ))}
                        </select>
                      </span>
                    </td>
                    <td className="hide-sm" onClick={(e) => e.stopPropagation()}>
                      {c.linkedin_url ? (
                        <a href={c.linkedin_url} target="_blank" rel="noreferrer noopener" className="link-button">
                          Profil <ExternalLink size={11} />
                        </a>
                      ) : (
                        <span className="muted">–</span>
                      )}
                    </td>
                    <td className="muted hide-sm">{new Date(c.created_at).toLocaleDateString("de-DE")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={page} total={contacts.data.total} limit={50} onPage={setPage} label="Kontakte" />
        </>
      )}
      {adding && (
        <AddContact
          {...props}
          onClose={() => setAdding(false)}
          onCreated={() => {
            setAdding(false);
            setLocal((v) => v + 1);
          }}
        />
      )}
      {active && (
        <LeadProfile
          {...props}
          contactId={active}
          onClose={() => setActive(null)}
          onUpdated={() => setLocal((v) => v + 1)}
        />
      )}
    </>
  );
}
