"use client";
import { FormEvent, useState } from "react";
import { CalendarRange, Copy, ExternalLink, ImagePlus, Sparkles } from "lucide-react";
import { request } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Spinner } from "./ui";
import type { Write } from "./growth-modules";

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
      setRevision((v) => v + 1);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const current = active || plans.data?.items[0]?.id || null;
  return (
    <>
      <Heading
        eyebrow="CONTENT"
        title="LinkedIn-Strategie"
        description="Ziel, Zielgruppe und Themensäulen festlegen. Daraus entsteht ein Plan mit rotem Faden, pro Post zwei Varianten im eigenen Stil."
      />
      <ErrorNote message={error || plans.error} />
      <section className="panel pad">
        <h2>
          <CalendarRange size={17} /> Neuer Plan
        </h2>
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
              Themensäule {i + 1}
              <input
                required={i < 3}
                value={p}
                onChange={(e) => setForm({ ...form, pillars: form.pillars.map((x, j) => (j === i ? e.target.value : x)) })}
              />
            </label>
          ))}
          {form.pillars.length < 4 && (
            <button type="button" className="button ghost small" onClick={() => setForm({ ...form, pillars: [...form.pillars, ""] })}>
              + 4. Säule
            </button>
          )}
          <label>
            Posts pro Woche
            <input type="number" min={1} max={5} value={form.cadence} onChange={(e) => setForm({ ...form, cadence: Number(e.target.value) })} />
          </label>
          <label>
            Wochen
            <input type="number" min={2} max={12} value={form.weeks} onChange={(e) => setForm({ ...form, weeks: Number(e.target.value) })} />
          </label>
          <label>
            Schreibprofil
            <select value={form.voice_profile_id} onChange={(e) => setForm({ ...form, voice_profile_id: e.target.value })}>
              <option value="">ohne (neutral)</option>
              {voices.data?.items.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
          <p className="muted small wide">Schreibprofil mit 3–5 eigenen Beispieltexten unter Social Studio → Schreibprofile anlegen.</p>
          <div className="form-actions wide">
            <button className="button primary" disabled={busy}>
              {busy ? <Spinner /> : <><Sparkles size={15} /> Plan erstellen</>}
            </button>
          </div>
        </form>
      </section>
      {plans.data && plans.data.items.length > 1 && (
        <div className="chip-row">
          {plans.data.items.map((p) => (
            <button key={p.id} className={`chip ${p.id === current ? "active" : ""}`} onClick={() => setActive(p.id)}>
              {p.name}
            </button>
          ))}
        </div>
      )}
      {current ? (
        <PlanView key={current + revision} base={base} write={write} planId={current} />
      ) : (
        !plans.loading && <Empty title="Noch kein Plan" description="Oben Ziel, Zielgruppe und Säulen eintragen." />
      )}
    </>
  );
}

function PlanView({ base, write, planId }: { base: string; write: Write; planId: string }) {
  const [revision, setRevision] = useState(0);
  const plan = useData<Plan>(`${base}/content/plans/${planId}`, revision);
  if (plan.loading && !plan.data) return <Spinner />;
  const p = plan.data;
  if (!p) return <ErrorNote message={plan.error} />;
  const weeks = Array.from({ length: p.weeks }, (_, i) => i + 1);
  return (
    <section className="panel pad" data-testid="content-plan">
      <h2>{p.name}</h2>
      <p className="muted">
        {p.goal} · {p.audience} · {p.cadence}× pro Woche
      </p>
      {p.status !== "ready" && <ErrorNote message={p.status === "failed" ? "Plan konnte nicht erstellt werden." : ""} />}
      {p.storyline && (
        <p className="info-note">
          <strong>Roter Faden:</strong> {p.storyline}
        </p>
      )}
      {weeks.map((w) => (
        <div key={w} className="plan-week">
          <h3>Woche {w}</h3>
          <div className="plan-items">
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
        <Badge>{item.day}</Badge>
        <Badge tone="neutral">{item.pillar}</Badge>
        <small className="muted">{item.format}</small>
        {post && <Badge tone={post.state === "approved" || post.state === "published_manually" ? "green" : "amber"}>{post.state}</Badge>}
      </header>
      <strong>{item.topic}</strong>
      <p className="muted small">{item.hook}</p>
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
                    setImageNote("Bild erzeugt, geprüft und angehängt (Bibliothek).");
                  })
                }
              >
                {busy === "img" ? <Spinner /> : <><ImagePlus size={14} /> Bild erzeugen</>}
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
