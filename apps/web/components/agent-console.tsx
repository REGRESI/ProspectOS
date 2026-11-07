"use client";
import { FormEvent, useEffect, useState } from "react";
import { CheckCircle2, Circle, Loader2, Play, XCircle } from "lucide-react";
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
  ledger?: { estimate_minor: number; actual_minor: number; budget_minor: number | null; note: string } | null;
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
        title="Autopilot"
        description="Findet jeden Morgen neue Firmen und bereitet die Texte für „Heute“ vor. Gesendet wird nichts ohne dich."
      />
      <ErrorNote message={error} />
      <AutopilotCard base={base} write={write} />
      <form className="card agent-form" onSubmit={plan}>
        <h2>Einmaliger Auftrag</h2>
        <p className="muted small">Beschreibe in einem Satz, was passieren soll. Du siehst Plan und Kosten, bevor etwas startet.</p>
        <label>
          Auftrag
          <textarea rows={3} value={instruction} onChange={(e) => setInstruction(e.target.value)} />
        </label>
        <div className="form-actions">
          <button className="button secondary" disabled={busy || instruction.length < 5}>
            {busy ? <Spinner /> : "Plan erstellen"}
          </button>
        </div>
      </form>
      {run && <RunView run={run} write={write} onUpdate={(r) => { setRun(r); setRevision((v) => v + 1); }} onNavigate={onNavigate} />}
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
      {run.ledger && (
        <p className="muted small" data-testid="run-ledger">
          Ledger: tatsächlich {euros(run.ledger.actual_minor)}
          {run.ledger.budget_minor !== null && run.ledger.budget_minor !== undefined ? ` · Budget pro Lauf ${euros(run.ledger.budget_minor)}` : ""}
          {run.ledger.note ? ` · ${run.ledger.note}` : ""}
        </p>
      )}
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

type Ledger = { estimate_minor: number; actual_minor: number; budget_minor: number | null; note: string };
type Autopilot = {
  enabled: boolean;
  hour: number;
  last_run_on: string | null;
  next_area?: string;
  plan: { place: string; radius_km: number; companies: number; research: number; profiles?: number; budget_minor?: number } | null;
  budget: { workspace_budget_minor: number; spent_minor: number; spent_usd?: number; reserved_minor: number; period: string };
  rotation: string[];
  recent?: { id: string; status: string; place: string; created_at: string; ledger: Ledger }[];
};

function AutopilotCard({ base, write }: { base: string; write: Write }) {
  const [revision, setRevision] = useState(0);
  const current = useData<Autopilot>(`${base}/agent/autopilot`, revision);
  const [form, setForm] = useState<{ place: string; radius_km: number; new_companies: number; research: number; profiles: number; budget: number; hour: number } | null>(null);
  const [msg, setMsg] = useState("");
  const data = current.data;
  const usd = (minor: number) => (minor / 100).toLocaleString("de-DE", { style: "currency", currency: "USD" });
  const f = form || {
    place: data?.plan?.place || "Ortenaukreis",
    radius_km: data?.plan?.radius_km || 30,
    new_companies: data?.plan?.companies || 30,
    research: data?.plan?.research ?? 20,
    profiles: data?.plan?.profiles ?? 0,
    budget: (data?.plan?.budget_minor ?? 50) / 100,
    hour: data?.hour ?? 6,
  };
  async function save(enabled: boolean) {
    try {
      const { budget, ...rest } = f;
      await write("/agent/autopilot", { enabled, ...rest, budget_minor: Math.round(budget * 100) }, "PUT");
      setMsg(enabled ? "Autopilot aktiv." : "Autopilot ausgeschaltet.");
      setForm(null);
      setRevision((v) => v + 1);
    } catch (e) {
      setMsg((e as Error).message);
    }
  }
  const area = f.place.trim().toLowerCase();
  const rotating = area === "ortenaukreis" || area === "ortenau";
  return (
    <section className="card autopilot-card" data-testid="autopilot">
      <h2>Jeden Morgen</h2>
      <p className="muted">
        Sucht neue Firmen, liest Website und Impressum, bewertet sie und bereitet die Texte in „Heute“ vor. Senden und Posten bleibt bei dir.
        {data?.last_run_on && ` Letzter Lauf: ${data.last_run_on}.`}
      </p>
      <div className="planner-form">
        <label>Gebiet<input value={f.place} onChange={(e) => setForm({ ...f, place: e.target.value })} /></label>
        <label>Umkreis in km<input type="number" min={1} max={50} value={f.radius_km} onChange={(e) => setForm({ ...f, radius_km: Number(e.target.value) })} /></label>
        <label>Neue Firmen pro Tag<input type="number" min={5} max={200} value={f.new_companies} onChange={(e) => setForm({ ...f, new_companies: Number(e.target.value) })} /></label>
        <label>Websites lesen pro Tag<input type="number" min={0} max={100} value={f.research} onChange={(e) => setForm({ ...f, research: Number(e.target.value) })} /></label>
        <label>KI-Firmenprofile pro Tag<input type="number" min={0} max={50} value={f.profiles} onChange={(e) => setForm({ ...f, profiles: Number(e.target.value) })} /></label>
        <label>Budget pro Lauf (USD)<input type="number" min={0} max={50} step={0.1} value={f.budget} onChange={(e) => setForm({ ...f, budget: Number(e.target.value) })} /></label>
        <label>Startet ab (Uhr)<input type="number" min={0} max={23} value={f.hour} onChange={(e) => setForm({ ...f, hour: Number(e.target.value) })} /></label>
      </div>
      {rotating && (
        <p className="muted small">
          Ortenaukreis: jeden Tag ein anderer Ort mit 12 km Radius ({data?.rotation.slice(0, 6).join(", ")} …).
          {data?.next_area ? ` Nächster Lauf: ${data.next_area}.` : ""}
        </p>
      )}
      {data && (
        <p className="muted small" data-testid="autopilot-budget">
          KI-Budget {data.budget.period}: {(data.budget.spent_usd ?? data.budget.spent_minor / 100).toLocaleString("de-DE", { style: "currency", currency: "USD", maximumFractionDigits: 4 })} von {usd(data.budget.workspace_budget_minor)} verbraucht
          {data.budget.reserved_minor ? `, ${usd(data.budget.reserved_minor)} reserviert` : ""}. Reicht das Budget nicht, lässt der Autopilot die KI-Profile weg; kostenlose Schritte laufen weiter.
        </p>
      )}
      <div className="form-actions">
        <button className="button primary small" onClick={() => save(true)}>{data?.enabled ? "Speichern" : "Aktivieren"}</button>
        {data?.enabled && <button className="button ghost small" onClick={() => save(false)}>Ausschalten</button>}
        {msg && <small role="status">{msg}</small>}
      </div>
      {data?.recent && data.recent.length > 0 && (
        <ul className="agent-history">
          {data.recent.map((r) => (
            <li key={r.id}>
              {new Date(r.created_at).toLocaleDateString("de-DE")} · {r.place} · <Badge tone={r.status === "done" ? "green" : r.status === "failed" ? "red" : "neutral"}>{r.status}</Badge>{" "}
              <small className="muted">Kosten {usd(r.ledger.actual_minor)}{r.ledger.note ? ` · ${r.ledger.note}` : ""}</small>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
