"use client";
import { FormEvent, useState } from "react";
import { Copy, ExternalLink } from "lucide-react";
import { request } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Spinner } from "./ui";
import type { Write } from "./growth-modules";
import { StyleNotice } from "./style-notice";
import { SkeletonTable } from "./table";

type PlanItem = {
  id: string;
  week: number;
  day: string;
  pillar: string;
  topic: string;
  hook: string;
  format: string;
  status: string;
  post_id: string | null;
  post?: { state: string; caption: string; variants: string[]; image_idea: string };
};
type Plan = {
  id: string;
  name: string;
  goal: string;
  audience: string;
  pillars: string[];
  cadence: number;
  weeks: number;
  status: string;
  storyline: string;
  job_id: string | null;
  items: PlanItem[];
};

const POST_STATE: Record<string, [string, string]> = {
  draft: ["Entwurf", "dot"],
  needs_review: ["zur Prüfung", "amber"],
  approved: ["freigegeben", "green"],
  scheduled: ["geplant", "blue"],
  published: ["veröffentlicht", "green"],
  published_manually: ["veröffentlicht", "green"],
  failed: ["fehlgeschlagen", "red"],
};

async function waitForJob(base: string, id: string) {
  for (let i = 0; i < 90; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const job = await request<{ status: string; last_error?: string; result?: Record<string, unknown> }>(`${base}/jobs/${id}`);
    if (job.status === "succeeded") return job.result || {};
    if (["failed", "dead", "ambiguous"].includes(job.status)) throw new Error(job.last_error || "Auftrag fehlgeschlagen");
  }
  throw new Error("Zeitüberschreitung");
}

export function ContentPlanner({ base, write }: { base: string; write: Write }) {
  const [revision, setRevision] = useState(0);
  const [active, setActive] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const plans = useData<{ items: Plan[] }>(`${base}/content/plans`, revision);
  const voices = useData<{ items: { id: string; name: string }[] }>(`${base}/social/voices`);
  const [form, setForm] = useState({
    name: "LinkedIn-Plan",
    goal: "",
    audience: "",
    pillars: ["", "", ""],
    cadence: 2,
    weeks: 6,
    voice_profile_id: "",
  });

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await write<{ id: string; job: { id: string } }>("/content/plans", {
        ...form,
        pillars: form.pillars.map((p) => p.trim()).filter(Boolean),
        voice_profile_id: form.voice_profile_id || null,
      });
      await waitForJob(base, r.job.id);
      setActive(r.id);
      setShowForm(false);
      setRevision((v) => v + 1);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const current = active || plans.data?.items[0]?.id || null;
  const formOpen = showForm || (!!plans.data && plans.data.items.length === 0);
  return (
    <>
      <Heading
        title="LinkedIn-Plan"
        description="Was du wann auf LinkedIn postest. Jeder Beitrag kommt in zwei Varianten, du wählst und gibst frei."
      >
        {plans.data && plans.data.items.length > 1 && (
          <select aria-label="Plan auswählen" value={current || ""} onChange={(e) => setActive(e.target.value)}>
            {plans.data.items.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
        <button className={`button ${formOpen ? "secondary" : "primary"}`} onClick={() => setShowForm(!formOpen)}>
          {formOpen && plans.data?.items.length ? "Abbrechen" : "Neuer Plan"}
        </button>
      </Heading>
      <ErrorNote message={error || plans.error} />
      <StyleNotice base={base} write={write} compact />
      {formOpen && (
      <section className="card plan-new">
        <h2>Neuer Plan</h2>
        <form className="planner-form" onSubmit={create}>
          <label>
            Name
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label className="wide">
            Ziel
            <input required minLength={5} placeholder="z. B. Sichtbarkeit bei Büroleitungen in der Ortenau" value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} />
          </label>
          <label className="wide">
            Zielgruppe
            <input required minLength={3} value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} />
          </label>
          {form.pillars.map((p, i) => (
            <label key={i}>
              Thema {i + 1}
              <input
                required={i < 3}
                value={p}
                onChange={(e) => setForm({ ...form, pillars: form.pillars.map((x, j) => (j === i ? e.target.value : x)) })}
              />
            </label>
          ))}
          {form.pillars.length < 4 && (
            <button type="button" className="button ghost small" onClick={() => setForm({ ...form, pillars: [...form.pillars, ""] })}>
              + 4. Thema
            </button>
          )}
          <label>
            Beiträge pro Woche
            <input type="number" min={1} max={5} value={form.cadence} onChange={(e) => setForm({ ...form, cadence: Number(e.target.value) })} />
          </label>
          <label>
            Wochen
            <input type="number" min={2} max={12} value={form.weeks} onChange={(e) => setForm({ ...form, weeks: Number(e.target.value) })} />
          </label>
          <label>
            Schreibstil
            <select value={form.voice_profile_id} onChange={(e) => setForm({ ...form, voice_profile_id: e.target.value })}>
              <option value="">Aus deinen eigenen Texten</option>
              {voices.data?.items.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
          <div className="form-actions wide">
            <button className="button primary" disabled={busy}>
              {busy ? <Spinner /> : "Plan erstellen"}
            </button>
            {busy && <span className="muted small">Der Plan wird geschrieben. Das dauert etwa eine Minute.</span>}
          </div>
        </form>
      </section>
      )}
      {current ? (
        <PlanView key={current + revision} base={base} write={write} planId={current} />
      ) : (
        !plans.loading && !formOpen && <Empty title="Noch kein Plan" description="Lege mit „Neuer Plan“ Ziel, Zielgruppe und Themen fest." />
      )}
    </>
  );
}

function PlanView({ base, write, planId }: { base: string; write: Write; planId: string }) {
  const [revision, setRevision] = useState(0);
  const plan = useData<Plan>(`${base}/content/plans/${planId}`, revision);
  if (plan.loading && !plan.data) return <SkeletonTable rows={6} cols={4} />;
  const p = plan.data;
  if (!p) return <ErrorNote message={plan.error} />;
  const weeks = Array.from({ length: p.weeks }, (_, i) => i + 1);
  return (
    <section data-testid="content-plan">
      <div className="plan-head">
        <h2>{p.name}</h2>
        <p className="muted">
          {p.goal} · {p.audience} · {p.cadence} Beiträge pro Woche
        </p>
      </div>
      {p.status !== "ready" && <ErrorNote message={p.status === "failed" ? "Plan konnte nicht erstellt werden." : ""} />}
      {p.storyline && (
        <p className="plan-storyline">
          <strong>Roter Faden:</strong> {p.storyline}
        </p>
      )}
      {weeks.map((w) => (
        <div key={w} className="plan-week">
          <h3>Woche {w}</h3>
          <div className="plan-items row-list">
            {p.items
              .filter((i) => i.week === w)
              .map((item) => (
                <PlanCard key={item.id + (item.post?.state || "")} base={base} write={write} plan={p} item={item} onChange={() => setRevision((v) => v + 1)} />
              ))}
          </div>
        </div>
      ))}
    </section>
  );
}

function PlanCard({ base, write, plan, item, onChange }: { base: string; write: Write; plan: Plan; item: PlanItem; onChange: () => void }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [imageNote, setImageNote] = useState("");
  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError("");
    try {
      await fn();
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  const post = item.post;
  return (
    <article className="plan-card">
      <header>
        <span className="plan-day">{item.day}</span>
        <span className="plan-topic">
          <strong>{item.topic}</strong>
          <small className="muted">
            {item.pillar}
            {item.hook ? ` · ${item.hook}` : ""}
          </small>
        </span>
        <Badge tone={!post ? "dot" : POST_STATE[post.state]?.[1] || "dot"}>
          {!post ? "noch kein Text" : POST_STATE[post.state]?.[0] || post.state}
        </Badge>
      </header>
      <ErrorNote message={error} />
      {!item.post_id ? (
        <button
          className="button secondary small"
          disabled={!!busy}
          onClick={() =>
            run("draft", async () => {
              const job = await write<{ id: string }>(`/content/plans/${plan.id}/items/${item.id}/draft`);
              await waitForJob(base, job.id);
            })
          }
        >
          {busy === "draft" ? <Spinner /> : "2 Varianten schreiben"}
        </button>
      ) : (
        post && (
          <>
            {post.variants.map((v, i) => (
              <details key={i} open={i === 0}>
                <summary>
                  Variante {i === 0 ? "A" : "B"} {post.caption === v ? "· gewählt" : ""}
                </summary>
                <pre className="today-preview">{v}</pre>
                {post.caption !== v && (
                  <button className="button ghost small" disabled={!!busy} onClick={() => run("v", () => write(`/content/posts/${item.post_id}/apply`, { variant: i }))}>
                    Diese Variante übernehmen
                  </button>
                )}
              </details>
            ))}
            {imageNote && <small className="muted">{imageNote}</small>}
            <div className="form-actions">
              <button
                className="button secondary small"
                disabled={!!busy}
                title={post.image_idea}
                onClick={() =>
                  run("img", async () => {
                    const job = await write<{ id: string }>("/social/images/generate", {
                      prompt: post.image_idea || item.topic,
                      alt_text: (post.image_idea || item.topic).slice(0, 200),
                      rights_confirmed: true,
                      post_context: item.topic,
                      aspect_ratio: "square",
                    });
                    await waitForJob(base, job.id);
                    const asset = await write<{ id: string }>(`/social/images/${job.id}/save`, { rights_confirmed: true });
                    await write(`/content/posts/${item.post_id}/apply`, { asset_id: asset.id, alt_text: (post.image_idea || item.topic).slice(0, 200) });
                    setImageNote("Bild erzeugt und angehängt. Du findest es auch unter Content → Bilder.");
                  })
                }
              >
                {busy === "img" ? <Spinner /> : "Bild erzeugen"}
              </button>
              {post.state === "draft" && (
                <button className="button secondary small" disabled={!!busy} onClick={() => run("rv", () => write(`/social/posts/${item.post_id}/submit-review`))}>
                  Zur Prüfung
                </button>
              )}
              {post.state === "needs_review" && (
                <button className="button primary small" disabled={!!busy} onClick={() => run("ap", () => write(`/social/posts/${item.post_id}/approve`))}>
                  Freigeben
                </button>
              )}
              {post.state === "approved" && (
                <>
                  <button
                    className="button primary small"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(post.caption);
                      } catch {
                        /* text remains visible for manual copy */
                      }
                      window.open("https://www.linkedin.com/feed/?shareActive=true", "_blank", "noopener,noreferrer");
                    }}
                  >
                    <Copy size={14} /> Kopieren & LinkedIn öffnen <ExternalLink size={12} />
                  </button>
                  <button
                    className="button secondary small"
                    disabled={!!busy}
                    onClick={() => {
                      const url = window.prompt("LinkedIn-URL des Beitrags (optional):") || null;
                      run("pub", () => write(`/social/posts/${item.post_id}/mark-published`, { url }));
                    }}
                  >
                    Als veröffentlicht markieren
                  </button>
                </>
              )}
            </div>
          </>
        )
      )}
    </article>
  );
}
