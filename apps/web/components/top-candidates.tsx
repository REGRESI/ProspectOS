"use client";
import { useMemo, useState } from "react";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Spinner } from "./ui";
import { SearchInput, SkeletonTable, SortHeader, useTable } from "./table";
import type { Write } from "./growth-modules";

type Factor = { name: string; points: number; max_points: number; reason: string };
type Candidate = {
  rank: number;
  company_id: string;
  name: string;
  location: string;
  industry: string | null;
  website: string | null;
  priority: number;
  fit: number;
  completeness: number;
  reason: string;
  gaps: string[];
  factors: Factor[];
  known: string[];
  missing_facts: string[];
  sources: string[];
  formula: string;
  excluded?: boolean;
  segment?: { key: string; label: string; tier: "A" | "B" | "C" | "?" | "X"; reason: string };
  website_check?: { status: "passt" | "unstimmig" | "unklar" | "keine_website"; reason: string };
};

const TIER: Record<string, [string, string]> = {
  A: ["sehr gut", "green"],
  B: ["gut", "green"],
  C: ["eher nicht", "amber"],
  "?": ["unklar", "dot"],
  X: ["ausgeblendet", "red"],
};
const CHECK_LABEL: Record<string, [string, string]> = {
  passt: ["passt", "green"],
  unstimmig: ["unstimmig", "red"],
  unklar: ["unklar", "amber"],
  keine_website: ["keine", "dot"],
};

type Ranking = {
  profile: { id: string; name: string };
  total: number;
  items: Candidate[];
  notice: string;
};

export function TopCandidates({
  base,
  write,
  onNavigate,
}: {
  base: string;
  write: Write;
  onNavigate?: (path: string) => void;
}) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [tier, setTier] = useState("");
  const [place, setPlace] = useState("");
  const [site, setSite] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const ranking = useData<Ranking>(
    `${base}/ranking/companies?limit=500${showHidden ? "&include_excluded=true" : ""}`,
    revision,
  );
  const templates = useData<{ items: { id: string; name: string; description: string }[] }>(
    `${base}/icp-templates`,
  );
  const items = useMemo(
    () =>
      (ranking.data?.items || []).filter(
        (c) =>
          (!tier || c.segment?.tier === tier) &&
          (!place || c.location === place) &&
          (!site || c.website_check?.status === site),
      ),
    [ranking.data, tier, place, site],
  );
  const places = useMemo(
    () => [...new Set((ranking.data?.items || []).map((c) => c.location).filter(Boolean))].sort(),
    [ranking.data],
  );
  const table = useTable(
    items,
    { search: (c) => `${c.name} ${c.location} ${c.segment?.label || ""}` },
    {
      rank: (c) => c.rank,
      name: (c) => c.name,
      segment: (c) => "ABC?X".indexOf(c.segment?.tier || "?"),
      location: (c) => c.location,
      website: (c) => c.website_check?.status || "",
      priority: (c) => c.priority,
    },
  );
  async function recheck() {
    setBusy(true);
    setError("");
    try {
      const r = await write<{ companies: number; checks: Record<string, number> }>("/data-quality/recheck");
      setNote(
        `${r.companies} Firmen geprüft: ${r.checks.passt || 0} passen, ${r.checks.unstimmig || 0} unstimmig, ${r.checks.unklar || 0} unklar, ${r.checks.keine_website || 0} ohne Website.`,
      );
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const needsProfile = ranking.error?.includes("ICP-Profil");
  const data = ranking.data;
  return (
    <>
      <Heading
        title="Beste Treffer"
        description="Firmen, die am besten zu dir passen. Jede Position hat einen kurzen Grund."
      >
        <button className="button secondary" disabled={busy} onClick={recheck} data-testid="recheck">
          {busy ? <Spinner /> : "Websites erneut abgleichen"}
        </button>
        <button className="button primary" onClick={() => onNavigate?.("/discover")}>
          Firmen finden
        </button>
      </Heading>
      <ErrorNote message={error || (needsProfile ? "" : ranking.error)} />
      {needsProfile && (
        <section className="card">
          <h2>Wen willst du erreichen?</h2>
          <p className="muted">Wähle eine Vorlage. Du kannst sie später unter Einstellungen → Zielgruppe anpassen.</p>
          <div className="row-actions" style={{ justifyContent: "flex-start" }}>
            {templates.data?.items.map((t) => (
              <button
                key={t.id}
                className="button primary wrap"
                onClick={async () => {
                  try {
                    await write("/icp-profiles/from-template", { template: t.id });
                    setRevision((v) => v + 1);
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
                title={t.description}
              >
                Vorlage „{t.name}“ übernehmen
              </button>
            ))}
          </div>
        </section>
      )}
      {note && (
        <p className="muted small" role="status">
          {note}
        </p>
      )}
      {ranking.loading && !data ? (
        <SkeletonTable cols={5} />
      ) : data && data.items.length === 0 ? (
        <Empty
          title="Noch keine Firmen"
          description="Suche zuerst Firmen in deiner Umgebung, dann erscheint hier die Rangliste."
        >
          <button className="button primary" onClick={() => onNavigate?.("/discover")}>
            Firmen finden
          </button>
        </Empty>
      ) : (
        data && (
          <>
            <div className="table-toolbar">
              <SearchInput value={table.query} onChange={table.setQuery} label="Firmen durchsuchen" placeholder="Name, Ort oder Branche" />
              <select aria-label="Passung" value={tier} onChange={(e) => setTier(e.target.value)}>
                <option value="">Jede Passung</option>
                <option value="A">sehr gut</option>
                <option value="B">gut</option>
                <option value="C">eher nicht</option>
                <option value="?">unklar</option>
                {showHidden && <option value="X">ausgeblendet</option>}
              </select>
              <select aria-label="Ort" value={place} onChange={(e) => setPlace(e.target.value)}>
                <option value="">Alle Orte</option>
                {places.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
              <select aria-label="Website" value={site} onChange={(e) => setSite(e.target.value)}>
                <option value="">Jede Website</option>
                <option value="passt">Website passt</option>
                <option value="unstimmig">Website unstimmig</option>
                <option value="unklar">Website unklar</option>
                <option value="keine_website">Keine Website</option>
              </select>
              <label className="inline-toggle">
                <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} /> Ausgeblendete zeigen
              </label>
              <span className="count">
                {table.rows.length} von {data.total}
              </span>
            </div>
            <div className="table-wrap">
              <table data-testid="top-candidates">
                <thead>
                  <tr>
                    <SortHeader label="#" column="rank" table={table} className="num hide-sm" />
                    <SortHeader label="Firma" column="name" table={table} />
                    <SortHeader label="Passung" column="segment" table={table} />
                    <SortHeader label="Ort" column="location" table={table} className="hide-sm" />
                    <SortHeader label="Website" column="website" table={table} className="hide-sm" />
                    <SortHeader label="Punkte" column="priority" table={table} defaultDir="desc" className="num" />
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((c) => (
                    <tr
                      key={c.company_id}
                      className={`clickable${c.excluded ? " row-muted" : ""}`}
                      onClick={() => onNavigate?.(`/companies/${c.company_id}`)}
                    >
                      <td className="num muted hide-sm">{c.rank}</td>
                      <td className="cell-main">
                        <strong>{c.name}</strong>
                        <small title={c.reason}>
                          {c.website_check?.status === "unstimmig" ? (
                            <span data-testid="website-mismatch">{c.website_check.reason}</span>
                          ) : (
                            [
                              c.segment?.label,
                              `Datenlage ${c.completeness} %`,
                              c.missing_facts.length ? `fehlt: ${c.missing_facts.slice(0, 2).join(", ")}` : "",
                            ]
                              .filter(Boolean)
                              .join(" · ")
                          )}
                        </small>
                      </td>
                      <td>
                        {c.segment && (
                          <span title={c.segment.reason || c.segment.label}>
                            <Badge tone={TIER[c.segment.tier]?.[1]}>{TIER[c.segment.tier]?.[0]}</Badge>
                          </span>
                        )}
                      </td>
                      <td className="hide-sm">{c.location || <span className="muted">–</span>}</td>
                      <td className="hide-sm">
                        {c.website_check && (
                          <span title={c.website_check.reason}>
                            <Badge tone={CHECK_LABEL[c.website_check.status][1]}>{CHECK_LABEL[c.website_check.status][0]}</Badge>
                          </span>
                        )}
                      </td>
                      <td className="num">
                        <strong>{c.priority}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="table-foot">
              <span>Zielgruppe: {data.profile.name}</span>
              <span>Punkte: Zielgruppe 50 %, Passung 30 %, Datenlage 20 %</span>
            </p>
          </>
        )
      )}
    </>
  );
}
