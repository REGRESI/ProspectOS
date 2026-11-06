"use client";
import { useState } from "react";
import { Trophy } from "lucide-react";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Spinner } from "./ui";
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

const TIER_TONE: Record<string, string> = { A: "green", B: "green", C: "amber", "?": "neutral", X: "red" };
const CHECK_LABEL: Record<string, [string, string]> = {
  passt: ["Website passt", "green"],
  unstimmig: ["Website unstimmig", "red"],
  unklar: ["Website-Bezug unklar", "amber"],
  keine_website: ["keine Website", "neutral"],
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
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const ranking = useData<{
    profile: { id: string; name: string };
    total: number;
    items: Candidate[];
    notice: string;
  }>(`${base}/ranking/companies?limit=150${showHidden ? "&include_excluded=true" : ""}`, revision);
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
  const templates = useData<{ items: { id: string; name: string; description: string }[] }>(
    `${base}/icp-templates`,
  );
  const needsProfile = ranking.error?.includes("ICP-Profil");
  return (
    <>
      <Heading
        eyebrow="QUALIFIZIERUNG"
        title="Top-Kandidaten"
        description="Rangliste nach ICP-Fit und Datenlage. Jede Position ist begründet, fehlende Fakten werden offen ausgewiesen."
      />
      <ErrorNote message={error || (needsProfile ? "" : ranking.error)} />
      {needsProfile && (
        <section className="panel pad">
          <h2>Noch kein ICP-Profil</h2>
          <p className="muted">Starte mit einer Vorlage und passe sie unter „Zielgruppen & ICP“ an.</p>
          <div className="form-actions">
            {templates.data?.items.map((t) => (
              <button
                key={t.id}
                className="button primary"
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
      {ranking.loading && !ranking.data ? (
        <Spinner />
      ) : ranking.data && ranking.data.items.length === 0 ? (
        <Empty
          title="Noch keine Unternehmen"
          description="Über Lead Discovery Firmen im Umkreis suchen und übernehmen – danach erscheint hier die Rangliste."
        />
      ) : (
        ranking.data && (
          <section className="panel pad">
            <div className="table-toolbar">
              <Badge tone="green">ICP: {ranking.data.profile.name}</Badge>
              <Badge>{ranking.data.total} {showHidden ? "inkl. ausgeblendete" : "bewertet"}</Badge>
              <label className="inline-toggle">
                <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} /> Ausgeblendete zeigen
              </label>
              <button className="button secondary small" disabled={busy} onClick={recheck} data-testid="recheck">
                {busy ? <Spinner /> : "Firma ↔ Website neu prüfen"}
              </button>
              <small className="muted">{ranking.data.items[0]?.formula}</small>
            </div>
            {note && <p className="muted small" role="status">{note}</p>}
            <ol className="candidate-list" data-testid="top-candidates">
              {ranking.data.items.map((c) => (
                <li key={c.company_id} className={`candidate${c.excluded ? " candidate-hidden" : ""}`}>
                  <div className="candidate-head">
                    <span className="candidate-rank">
                      <Trophy size={14} /> {c.rank}
                    </span>
                    <button
                      className="link-button"
                      onClick={() => onNavigate?.(`/companies/${c.company_id}`)}
                    >
                      <strong>{c.name}</strong>
                    </button>
                    <span className="muted">
                      {[c.location, c.industry].filter(Boolean).join(" · ")}
                    </span>
                    <Badge tone={c.priority >= 70 ? "green" : c.priority >= 40 ? "amber" : "neutral"}>
                      Priorität {c.priority}
                    </Badge>
                    {c.segment && <Badge tone={TIER_TONE[c.segment.tier]}>{c.segment.label}</Badge>}
                    {c.website_check && c.website_check.status !== "passt" && (
                      <span title={c.website_check.reason}>
                        <Badge tone={CHECK_LABEL[c.website_check.status][1]}>{CHECK_LABEL[c.website_check.status][0]}</Badge>
                      </span>
                    )}
                  </div>
                  <p className="candidate-reason">{c.reason}</p>
                  {c.website_check?.status === "unstimmig" && (
                    <small className="candidate-missing" data-testid="website-mismatch">
                      {c.website_check.reason}. Impressum-Daten sind als unbestätigt markiert und werden nicht verwendet.
                    </small>
                  )}
                  <small className="muted">
                    Fit {c.fit} · Datenlage {c.completeness} %
                    {c.known.length ? ` · belegt: ${c.known.join(", ")}` : ""}
                  </small>
                  {c.missing_facts.length > 0 && (
                    <small className="candidate-missing">
                      Fehlt: {c.missing_facts.join(", ")}
                    </small>
                  )}
                  {c.sources.length > 0 && (
                    <small className="candidate-sources">
                      Quellen:{" "}
                      {c.sources.map((s, i) => (
                        <a key={s} href={s} target="_blank" rel="noreferrer noopener">
                          [{i + 1}]
                        </a>
                      ))}
                    </small>
                  )}
                </li>
              ))}
            </ol>
            <p className="muted small">{ranking.data.notice}</p>
          </section>
        )
      )}
    </>
  );
}
