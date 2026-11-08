"use client";
import { useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  CalendarClock,
  Check,
  Footprints,
  GitBranch,
  Hourglass,
  Link2,
  Mail,
  Phone,
  Plus,
  Play,
  ScrollText,
  SkipForward,
  Trash2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { dateTime } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Spinner } from "./ui";
import { useOptionalData } from "./journey-shared";
import type { Write } from "./growth-modules";

type StepKind = "linkedin_task" | "letter" | "call_task" | "visit_task" | "email" | "wait" | "condition";
type Step = {
  position: number;
  kind: StepKind;
  route: "any" | "linkedin" | "letter";
  wait_days: number;
  title: string;
  template: string;
  config: { if_reaction?: "stop" | number; if_none?: "next" | number };
  open_tasks?: number;
  waiting?: number;
};
type Flow = {
  campaign: { id: string; name: string; goal: string; status: string };
  steps: Step[];
  runs: Record<"active" | "waiting" | "stopped" | "completed", number>;
  stopped: { contact_id: string; reason: string }[];
  notice: string;
};
type Recipe = {
  id: string;
  name: string;
  description: string;
  steps: { kind: StepKind; kind_label: string; route: string; wait_days: number; title: string }[];
};
export type FlowTask = {
  id: string;
  kind: StepKind;
  kind_label: string;
  title: string;
  body: string;
  due_at: string;
  state: "open" | "blocked";
  blocked_reason: string;
  origin: string;
  campaign: { id: string; name: string } | null;
  contact: { id: string; name: string; route: string; linkedin_url: string | null; phone: string | null } | null;
  company: { id: string; name: string; location: string } | null;
};

export const stepIcons: Record<StepKind, LucideIcon> = {
  linkedin_task: Link2,
  letter: ScrollText,
  call_task: Phone,
  visit_task: Footprints,
  email: Mail,
  wait: Hourglass,
  condition: GitBranch,
};
const kindLabels: Record<StepKind, string> = {
  linkedin_task: "LinkedIn-Aufgabe",
  letter: "Brief",
  call_task: "Anruf",
  visit_task: "Besuch vor Ort",
  email: "E-Mail",
  wait: "Warten",
  condition: "Bedingung",
};
const routeLabels = { any: "alle Wege", linkedin: "nur LinkedIn-Weg", letter: "nur Brief-Weg" };

/** Due campaign steps for "Heute". Every step is done by a person and checked off here. */
export function FlowTasksSection({ base, write }: { base: string; write: Write }) {
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const data = useData<{ items: FlowTask[]; counts: { open: number; blocked: number } }>(
    `${base}/flow-tasks?due=today`,
    revision,
  );
  async function act(id: string, action: "done" | "skip") {
    setBusy(id);
    setError("");
    try {
      await write(`/flow-tasks/${id}/${action}`, {});
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  const items = data.data?.items || [];
  if (!items.length && !data.loading) return null;
  return (
    <section className="today-section flow-tasks" data-testid="flow-tasks">
      <h2 className="today-section-title">
        Fällige Schritte aus Kampagnen <Badge>{items.length}</Badge>
      </h2>
      <ErrorNote message={error || data.error} />
      <ul className="flow-task-list">
        {items.map((task) => {
          const Icon = stepIcons[task.kind] || CalendarClock;
          return (
            <li key={task.id} className={task.state} data-testid={`flow-task-${task.contact?.name}`}>
              <span className="flow-task-icon" aria-hidden>
                <Icon size={16} />
              </span>
              <div className="flow-task-main">
                <strong>{task.title}</strong>
                <small>
                  {task.contact?.name}
                  {task.company ? ` · ${task.company.name}` : ""}
                  {task.campaign ? ` · ${task.campaign.name}` : ""}
                </small>
                {task.state === "blocked" && <small className="flow-task-blocked">Gesperrt: {task.blocked_reason}</small>}
                {task.body && <p className="flow-task-body">{task.body}</p>}
              </div>
              <div className="flow-task-actions">
                {task.kind === "linkedin_task" && task.contact?.linkedin_url && task.state === "open" && (
                  <a className="button ghost small" href={task.contact.linkedin_url} target="_blank" rel="noreferrer">
                    Profil öffnen
                  </a>
                )}
                {task.kind === "call_task" && task.contact?.phone && task.state === "open" && (
                  <span className="flow-task-phone">{task.contact.phone}</span>
                )}
                <button
                  className="button primary small"
                  disabled={!!busy || task.state !== "open"}
                  onClick={() => act(task.id, "done")}
                >
                  <Check size={14} /> Erledigt
                </button>
                <button className="button ghost small" disabled={!!busy} onClick={() => act(task.id, "skip")}>
                  <SkipForward size={14} /> Überspringen
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function StepCard({
  step,
  index,
  count,
  positions,
  onChange,
  onMove,
  onRemove,
}: {
  step: Step;
  index: number;
  count: number;
  positions: number[];
  onChange: (s: Step) => void;
  onMove: (d: -1 | 1) => void;
  onRemove: () => void;
}) {
  const Icon = stepIcons[step.kind];
  return (
    <li className={`flow-step kind-${step.kind}`} data-testid={`flow-step-${index}`}>
      <span className="flow-step-icon" aria-hidden>
        <Icon size={16} />
      </span>
      <div className="flow-step-body">
        <div className="flow-step-head">
          <strong>{kindLabels[step.kind]}</strong>
          {step.route !== "any" && <Badge tone={step.route === "linkedin" ? "purple" : "amber"}>{routeLabels[step.route]}</Badge>}
          {!!step.open_tasks && <Badge tone="green">{step.open_tasks} offen</Badge>}
          {!!step.waiting && <Badge>{step.waiting} warten</Badge>}
          <span className="flow-step-tools">
            <button className="icon-button" aria-label="Nach oben" disabled={index === 0} onClick={() => onMove(-1)}>
              <ArrowUp size={14} />
            </button>
            <button className="icon-button" aria-label="Nach unten" disabled={index === count - 1} onClick={() => onMove(1)}>
              <ArrowDown size={14} />
            </button>
            <button className="icon-button" aria-label="Schritt entfernen" onClick={onRemove}>
              <Trash2 size={14} />
            </button>
          </span>
        </div>
        <div className="flow-step-fields">
          {step.kind === "wait" ? (
            <label>
              Tage warten
              <input
                type="number"
                min={1}
                max={180}
                value={step.wait_days}
                onChange={(e) => onChange({ ...step, wait_days: Number(e.target.value) })}
              />
            </label>
          ) : step.kind === "condition" ? (
            <div className="flow-branches">
              <label>
                Reaktion da
                <select
                  value={String(step.config.if_reaction ?? "stop")}
                  onChange={(e) =>
                    onChange({
                      ...step,
                      config: { ...step.config, if_reaction: e.target.value === "stop" ? "stop" : Number(e.target.value) },
                    })
                  }
                >
                  <option value="stop">Kampagne stoppen</option>
                  {positions
                    .filter((p) => p > step.position)
                    .map((p) => (
                      <option key={p} value={p}>
                        Springe zu Schritt {positions.indexOf(p) + 1}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Keine Reaktion
                <select
                  value={String(step.config.if_none ?? "next")}
                  onChange={(e) =>
                    onChange({
                      ...step,
                      config: { ...step.config, if_none: e.target.value === "next" ? "next" : Number(e.target.value) },
                    })
                  }
                >
                  <option value="next">Weiter mit dem nächsten Schritt</option>
                  {positions
                    .filter((p) => p > step.position)
                    .map((p) => (
                      <option key={p} value={p}>
                        Springe zu Schritt {positions.indexOf(p) + 1}
                      </option>
                    ))}
                </select>
              </label>
            </div>
          ) : (
            <>
              <label>
                Aufgabe
                <input value={step.title} maxLength={200} onChange={(e) => onChange({ ...step, title: e.target.value })} />
              </label>
              <label className="span-2">
                Text (optional, mit {"{first_name}"}, {"{company}"})
                <textarea
                  rows={2}
                  maxLength={3000}
                  value={step.template}
                  onChange={(e) => onChange({ ...step, template: e.target.value })}
                />
              </label>
            </>
          )}
          <label>
            Gilt für
            <select value={step.route} onChange={(e) => onChange({ ...step, route: e.target.value as Step["route"] })}>
              <option value="any">alle Wege</option>
              <option value="linkedin">nur LinkedIn-Weg</option>
              <option value="letter">nur Brief-Weg</option>
            </select>
          </label>
        </div>
      </div>
    </li>
  );
}

export function FlowBuilderPage({
  base,
  write,
  notify,
}: {
  base: string;
  write: Write;
  notify: (m: string) => void;
}) {
  const [revision, setRevision] = useState(0);
  const [chosen, setActive] = useState("");
  const [draft, setDraft] = useState<{ key: string; steps: Step[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [audience, setAudience] = useState("routed");
  const campaigns = useData<{ items: { id: string; name: string; status: string; runs: Record<string, number> }[] }>(
    `${base}/flow-campaigns`,
    revision,
  );
  const recipes = useData<{ items: Recipe[] }>(`${base}/flow-recipes`, 0);
  const summary = useData<{ routes: Record<string, number> }>(`${base}/channels/summary`, revision);
  const active = chosen || campaigns.data?.items[0]?.id || "";
  const flow = useOptionalData<Flow>(active ? `${base}/campaigns/${active}/flow` : null, revision);
  // Unsaved edits belong to one campaign and one loaded version of it.
  const flowKey = `${active}:${revision}`;
  const steps = draft && draft.key === flowKey ? draft.steps : (flow.data?.steps ?? null);
  const setSteps = (next: Step[]) => setDraft({ key: flowKey, steps: next });

  async function run<T>(fn: () => Promise<T>, message: (r: T) => string) {
    setBusy(true);
    setError("");
    try {
      const r = await fn();
      setRevision((v) => v + 1);
      notify(message(r));
      return r;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const positions = (steps || []).map((s) => s.position);
  const renumber = (list: Step[]): Step[] => {
    // Keep condition targets pointing at the same step after reordering.
    const map = new Map(list.map((s, i) => [s.position, i * 10]));
    return list.map((s, i) => ({
      ...s,
      position: i * 10,
      config:
        s.kind === "condition"
          ? {
              if_reaction:
                typeof s.config.if_reaction === "number" ? (map.get(s.config.if_reaction) ?? "stop") : "stop",
              if_none: typeof s.config.if_none === "number" ? (map.get(s.config.if_none) ?? "next") : "next",
            }
          : {},
    }));
  };
  const save = () =>
    run(
      () =>
        write(
          `/campaigns/${active}/flow`,
          {
            steps: (steps || []).map(({ position, kind, route, wait_days, title, template, config }) => ({
              position,
              kind,
              route,
              wait_days,
              title,
              template,
              config: kind === "condition" ? config : {},
            })),
          },
          "PUT",
        ),
      () => "Ablauf gespeichert. Gilt ab dem nächsten fälligen Schritt.",
    );

  return (
    <>
      <Heading
        title="Kampagnen"
        description="Schritte für LinkedIn, Brief, Anruf und Besuch. Jeder Kontakt geht genau einen Weg; eine Reaktion stoppt alles."
      />
      <ErrorNote message={error} />
      <section className="panel recipe-panel" data-testid="recipes">
        <div className="panel-head">
          <div>
            <h2>Aus Rezept starten</h2>
            <p>
              {summary.data
                ? `${summary.data.routes.linkedin} Kontakte mit LinkedIn-Weg, ${summary.data.routes.letter} mit Brief-Weg, ${summary.data.routes.none} ohne Weg.`
                : " "}
            </p>
          </div>
          <label className="recipe-audience">
            Für wen
            <select value={audience} onChange={(e) => setAudience(e.target.value)}>
              <option value="routed">Alle mit Weg</option>
              <option value="linkedin">Nur LinkedIn-Weg</option>
              <option value="letter">Nur Brief-Weg</option>
              <option value="">Noch niemand</option>
            </select>
          </label>
        </div>
        <div className="recipe-grid">
          {recipes.data?.items.map((r) => (
            <article key={r.id} className="recipe-card">
              <h3>{r.name}</h3>
              <p>{r.description}</p>
              <ol className="recipe-steps">
                {r.steps
                  .filter((s) => s.kind !== "condition")
                  .map((s, i) => {
                    const Icon = stepIcons[s.kind];
                    return (
                      <li key={i} title={s.title || s.kind_label}>
                        <Icon size={13} aria-hidden /> {s.kind === "wait" ? `${s.wait_days} T` : s.kind_label}
                      </li>
                    );
                  })}
              </ol>
              <button
                className="button secondary small"
                disabled={busy}
                onClick={() =>
                  run(
                    () =>
                      write<{ campaign: { id: string }; started: { started: number } }>("/campaigns/from-recipe", {
                        recipe: r.id,
                        audience,
                      }),
                    (res) => {
                      setActive(res.campaign.id);
                      return `Kampagne angelegt, ${res.started.started} Kontakte gestartet.`;
                    },
                  )
                }
              >
                <Play size={14} /> Starten
              </button>
            </article>
          ))}
        </div>
      </section>

      <div className="flow-layout">
        <aside className="panel flow-list">
          <h2>Deine Kampagnen</h2>
          {campaigns.data?.items.length ? (
            campaigns.data.items.map((c) => (
              <button key={c.id} className={`flow-list-item ${c.id === active ? "active" : ""}`} onClick={() => setActive(c.id)}>
                <strong>{c.name}</strong>
                <small>
                  {(c.runs.active || 0) + (c.runs.waiting || 0)} laufen · {c.runs.stopped || 0} gestoppt ·{" "}
                  {c.runs.completed || 0} fertig
                </small>
              </button>
            ))
          ) : (
            <p className="muted">Noch keine Kampagne. Starte oben mit einem Rezept.</p>
          )}
        </aside>
        <section className="panel flow-editor">
          {!active ? (
            <Empty icon={GitBranch} title="Keine Kampagne gewählt" description="Starte eine Kampagne aus einem Rezept." />
          ) : flow.loading && !flow.data ? (
            <div className="loading-block">
              <Spinner />
            </div>
          ) : (
            flow.data &&
            steps && (
              <>
                <div className="panel-head">
                  <div>
                    <h2>{flow.data.campaign.name}</h2>
                    <p>{flow.data.notice}</p>
                  </div>
                  <div className="flow-run-stats">
                    <Badge tone="green">{flow.data.runs.active} aktiv</Badge>
                    <Badge>{flow.data.runs.waiting} warten</Badge>
                    <Badge tone="red">{flow.data.runs.stopped} gestoppt</Badge>
                  </div>
                </div>
                <ol className="flow-steps">
                  {steps.map((s, i) => (
                    <StepCard
                      key={`${i}-${s.kind}`}
                      step={s}
                      index={i}
                      count={steps.length}
                      positions={positions}
                      onChange={(next) => setSteps(steps.map((x, j) => (j === i ? next : x)))}
                      onMove={(d) => {
                        const list = [...steps];
                        [list[i], list[i + d]] = [list[i + d], list[i]];
                        setSteps(renumber(list));
                      }}
                      onRemove={() => setSteps(renumber(steps.filter((_, j) => j !== i)))}
                    />
                  ))}
                </ol>
                <div className="flow-actions">
                  <label>
                    Schritt hinzufügen
                    <select
                      value=""
                      onChange={(e) => {
                        const kind = e.target.value as StepKind;
                        if (!kind) return;
                        const last = steps.length ? steps[steps.length - 1].position : -10;
                        setSteps([
                          ...steps,
                          {
                            position: last + 10,
                            kind,
                            route: "any",
                            wait_days: kind === "wait" ? 3 : 0,
                            title: kind === "wait" || kind === "condition" ? "" : kindLabels[kind],
                            template: "",
                            config: kind === "condition" ? { if_reaction: "stop", if_none: "next" } : {},
                          },
                        ]);
                      }}
                    >
                      <option value="">Auswählen</option>
                      {(Object.keys(kindLabels) as StepKind[]).map((k) => (
                        <option key={k} value={k}>
                          {kindLabels[k]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button className="button primary" disabled={busy || !steps.length} onClick={save}>
                    <Plus size={14} /> Ablauf speichern
                  </button>
                </div>
                {!!flow.data.stopped.length && (
                  <details className="flow-stopped">
                    <summary>{flow.data.stopped.length} gestoppte Kontakte</summary>
                    <ul>
                      {flow.data.stopped.map((s) => (
                        <li key={s.contact_id}>{s.reason}</li>
                      ))}
                    </ul>
                  </details>
                )}
              </>
            )
          )}
        </section>
      </div>
      <p className="muted small-print">Stand {dateTime(new Date().toISOString())}</p>
    </>
  );
}
