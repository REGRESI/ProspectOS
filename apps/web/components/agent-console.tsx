"use client";
import { FormEvent, useEffect, useState } from "react";
import { Bot, CheckCircle2, Circle, Loader2, Play, XCircle } from "lucide-react";
import { request } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Heading, Spinner } from "./ui";
import type { Write } from "./growth-modules";

type Step = { step: string; label: string; status: string; detail: string };
type Run = {
  id: string;
  kind: string;
  instruction: string;
  status: string;
  plan: { place: string; radius_km: number; companies: number; research: number; profiles: number; steps: string[]; provider: string };
  estimate: { lines: { label: string; cost_minor: number; note: string }[]; total_minor: number } | null;
  progress: Step[];
  results: {
    imported: { companies: number; linked_duplicates: number; facts: number } | null;
    top: { company_id: string; name: string; location: string; priority: number; reason: string; sources: string[] }[];
    contacts_created: number | null;
    campaign_id: string | null;
    today: { connect: number; message: number; followup: number } | null;
  };
  created_at: string;
};

const EXAMPLE = "Finde 200 Firmen in meiner Region, recherchiere sie, priorisiere sie und bereite eine Kampagne vor";

export function AgentConsole({ base, write, onNavigate }: { base: string; write: Write; onNavigate?: (p: string) => void }) {
  const [instruction, setInstruction] = useState(EXAMPLE);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const history = useData<{ items: Run[] }>(`${base}/agent/runs`, revision);

  useEffect(() => {
    if (!run || run.status !== "running") return;
    const t = setTimeout(async () => {
      try {
        setRun(await request<Run>(`${base}/agent/runs/${run.id}`));
      } catch (e) {
        setError((e as Error).message);
      }
    }, 3000);
    return () => clearTimeout(t);
  }, [run, base]);

  async function plan(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setRun(await write<Run>("/agent/plan", { instruction }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Heading
        eyebrow="AUFTRAG"
        title="Auftrags-Agent"
        description="Beschreibe, was passieren soll. Der Agent zeigt Plan und Kosten, startet erst nach Bestätigung und nutzt nur belegte Daten. Er sendet nichts nach außen."
      />
      <ErrorNote message={error} />
      <form className="panel pad agent-form" onSubmit={plan}>
        <label>
          Auftrag
          <textarea rows={3} value={instruction} onChange={(e) => setInstruction(e.target.value)} />
        </label>
        <div className="form-actions">
          <button className="button primary" disabled={busy || instruction.length < 5}>
            {busy ? <Spinner /> : <><Bot size={15} /> Plan erstellen</>}
          </button>
        </div>
      </form>
      {run && <RunView run={run} write={write} onUpdate={(r) => { setRun(r); setRevision((v) => v + 1); }} onNavigate={onNavigate} />}
      <AutopilotCard base={base} write={write} />
      {history.data && history.data.items.length > 0 && (
        <section className="panel pad">
          <h2>Letzte Aufträge</h2>
          <ul className="agent-history">
            {history.data.items.map((r) => (
              <li key={r.id}>
                <button className="link-button" onClick={() => setRun(r)}>
                  {r.kind === "autopilot" ? "Morgen-Autopilot" : r.instruction}
                </button>{" "}
                <Badge tone={r.status === "done" ? "green" : r.status === "failed" ? "red" : "neutral"}>{r.status}</Badge>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

function StepIcon({ status }: { status: string }) {
  if (status === "done") return <CheckCircle2 size={16} className="ok" />;
  if (status === "failed") return <XCircle size={16} className="bad" />;
  if (status === "running") return <Loader2 size={16} className="spin" />;
  return <Circle size={16} className="muted" />;
}

function RunView({ run, write, onUpdate, onNavigate }: { run: Run; write: Write; onUpdate: (r: Run) => void; onNavigate?: (p: string) => void }) {
  const [error, setError] = useState("");
  const euros = (minor: number) => (minor / 100).toLocaleString("de-DE", { style: "currency", currency: "USD" });
  return (
    <section className="panel pad" data-testid="agent-run">
      <div className="panel-head">
        <h2>Plan</h2>
        <Badge tone={run.status === "done" ? "green" : run.status === "failed" ? "red" : "amber"}>{run.status}</Badge>
      </div>
      <p className="muted">
        {run.plan.companies} Firmen · {run.plan.place} · {run.plan.radius_km} km · Quelle {run.plan.provider === "osm" ? "OpenStreetMap" : "North Data"}
      </p>
      <ErrorNote message={error} />
      <ol className="agent-steps">
        {run.progress.map((p, i) => (
          <li key={p.step} className={`agent-step ${p.status}`}>
            <StepIcon status={p.status} />
            <span>
              <strong>{p.label}</strong>
              {run.estimate && (
                <small className="muted">
                  {" "}
                  · {run.estimate.lines[i]?.note}
                  {run.estimate.lines[i]?.cost_minor ? ` · ≈ ${euros(run.estimate.lines[i].cost_minor)}` : ""}
                </small>
              )}
              {p.detail && <small className="agent-detail">{p.detail}</small>}
            </span>
          </li>
        ))}
      </ol>
      {run.estimate && <p><strong>Geschätzte Kosten: {euros(run.estimate.total_minor)}</strong> <small className="muted">(nur KI-Profile sind kostenpflichtig)</small></p>}
      <div className="form-actions">
        {run.status === "planned" && (
          <button
            className="button primary"
            onClick={async () => {
              try {
                onUpdate(await write<Run>(`/agent/runs/${run.id}/confirm`));
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <Play size={15} /> Bestätigen und starten
          </button>
        )}
        {(run.status === "planned" || run.status === "running") && (
          <button className="button ghost" onClick={async () => onUpdate(await write<Run>(`/agent/runs/${run.id}/cancel`))}>
            Abbrechen
          </button>
        )}
      </div>
      {run.results.top.length > 0 && (
        <>
          <h3>Ergebnisse</h3>
          <p className="muted small">
            {run.results.imported && `${run.results.imported.companies} neue Firmen, ${run.results.imported.facts} belegte Fakten · `}
            {run.results.contacts_created !== null && `${run.results.contacts_created} Ansprechpartner · `}
            {run.results.today && `Heute: ${run.results.today.connect} Anfragen`}
          </p>
          <ol className="candidate-list">
            {run.results.top.map((t) => (
              <li key={t.company_id} className="candidate">
                <div className="candidate-head">
                  <button className="link-button" onClick={() => onNavigate?.(`/companies/${t.company_id}`)}>
                    <strong>{t.name}</strong>
                  </button>
                  <span className="muted">{t.location}</span>
                  <Badge>Priorität {t.priority}</Badge>
                </div>
                <p className="candidate-reason">{t.reason}</p>
                {t.sources.length > 0 && (
                  <small className="candidate-sources">
                    {t.sources.map((s, i) => (
                      <a key={s} href={s} target="_blank" rel="noreferrer noopener">[{i + 1}]</a>
                    ))}
                  </small>
                )}
              </li>
            ))}
          </ol>
          <div className="form-actions">
            {run.results.campaign_id && <button className="button secondary small" onClick={() => onNavigate?.("/campaigns")}>Kampagne öffnen</button>}
            {run.results.today && <button className="button secondary small" onClick={() => onNavigate?.("/today")}>Zu „Heute“</button>}
          </div>
        </>
      )}
    </section>
  );
}

function AutopilotCard({ base, write }: { base: string; write: Write }) {
  const current = useData<{ enabled: boolean; hour: number; last_run_on: string | null; plan: { place: string; radius_km: number; companies: number; research: number } | null }>(`${base}/agent/autopilot`);
  const [form, setForm] = useState<{ place: string; radius_km: number; new_companies: number; research: number; hour: number } | null>(null);
  const [msg, setMsg] = useState("");
  const data = current.data;
  const f = form || {
    place: data?.plan?.place || "",
    radius_km: data?.plan?.radius_km || 30,
    new_companies: data?.plan?.companies || 30,
    research: data?.plan?.research ?? 20,
    hour: data?.hour ?? 6,
  };
  async function save(enabled: boolean) {
    try {
      await write("/agent/autopilot", { enabled, ...f, profiles: 0 }, "PUT");
      setMsg(enabled ? "Autopilot aktiv." : "Autopilot ausgeschaltet.");
    } catch (e) {
      setMsg((e as Error).message);
    }
  }
  return (
    <section className="panel pad">
      <h2>Morgen-Autopilot</h2>
      <p className="muted">
        Lädt täglich neue Firmen nach, recherchiert, bewertet und füllt „Heute“. Nur interne Schritte – Anfragen, E-Mails und Posts bleiben freigabepflichtig.
        {data?.last_run_on && ` Letzter Lauf: ${data.last_run_on}.`}
      </p>
      <div className="planner-form">
        <label>Ort<input value={f.place} onChange={(e) => setForm({ ...f, place: e.target.value })} /></label>
        <label>Radius km<input type="number" min={1} max={50} value={f.radius_km} onChange={(e) => setForm({ ...f, radius_km: Number(e.target.value) })} /></label>
        <label>Neue Firmen/Tag<input type="number" min={5} max={200} value={f.new_companies} onChange={(e) => setForm({ ...f, new_companies: Number(e.target.value) })} /></label>
        <label>Recherchen/Tag<input type="number" min={0} max={100} value={f.research} onChange={(e) => setForm({ ...f, research: Number(e.target.value) })} /></label>
        <label>Uhrzeit (ab)<input type="number" min={0} max={23} value={f.hour} onChange={(e) => setForm({ ...f, hour: Number(e.target.value) })} /></label>
      </div>
      <div className="form-actions">
        <button className="button primary small" onClick={() => save(true)}>{data?.enabled ? "Speichern" : "Aktivieren"}</button>
        {data?.enabled && <button className="button ghost small" onClick={() => save(false)}>Ausschalten</button>}
        {msg && <small role="status">{msg}</small>}
      </div>
    </section>
  );
}
