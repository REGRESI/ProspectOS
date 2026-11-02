"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import Image from "next/image";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  History,
  ImageIcon,
  MessageSquare,
  Sparkles,
} from "lucide-react";
import { request, dateTime, postLabels } from "@/lib/api";
import type { Page, Post } from "@/lib/api";
import { useData } from "@/lib/use-data";
import type { Asset, Brand, ModuleProps, Write } from "./growth-modules";
import { Badge, Empty, ErrorNote, Heading, Modal, Spinner } from "./ui";

type Variant = {
  text: string;
  hook?: string;
  cta?: string;
  citations?: string[];
  unverified_claims?: string[];
};
type GenerationJob = {
  id: string;
  status: string;
  last_error?: string | null;
  result: {
    variants?: Variant[];
    asset?: Asset;
    text?: string;
    provider?: string;
    notice?: string;
    unverified_claims?: string[];
  };
};
const pending = (job: GenerationJob | null) =>
  !!job && ["queued", "running", "retry"].includes(job.status);

export function useGenerationJob(
  base: string,
  onComplete: (job: GenerationJob) => void,
) {
  const [job, setJob] = useState<GenerationJob | null>(null);
  const [pollError, setPollError] = useState("");
  const completion = useRef(onComplete);
  useEffect(() => {
    completion.current = onComplete;
  }, [onComplete]);
  useEffect(() => {
    if (!job?.id) return;
    let active = true;
    let attempts = 0;
    const id = job.id;
    const timer = window.setInterval(async () => {
      try {
        const next = await request<GenerationJob>(`${base}/jobs/${id}`);
        if (!active) return;
        setJob(next);
        if (!["queued", "running", "retry"].includes(next.status)) {
          window.clearInterval(timer);
          if (next.status === "succeeded") completion.current(next);
        } else if (++attempts >= 120) {
          window.clearInterval(timer);
          setPollError(
            "Der Auftrag läuft weiter. Den aktuellen Status findest du unter Einstellungen → Aufträge & Budget.",
          );
        }
      } catch (e) {
        if (active) setPollError((e as Error).message);
        window.clearInterval(timer);
      }
    }, 1500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [base, job?.id]);
  return { job, setJob, pollError, setPollError };
}

export function GenerationTools({
  base,
  write,
  brands,
  brandId,
  topic,
  onVariants,
  onAsset,
  onChange,
}: {
  base: string;
  write: Write;
  brands: Brand[];
  brandId: string;
  topic: string;
  onVariants: (variants: Variant[]) => void;
  onAsset: (asset: Asset) => void;
  onChange: () => void;
}) {
  const [tool, setTool] = useState<"text" | "image">("text");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [imageResult, setImageResult] = useState<Asset | null>(null);
  const [imageReviewed, setImageReviewed] = useState(false);
  const imageRequirements = useData<{
    configured: boolean;
    requirements: string[];
    max_cost_minor?: number;
  }>(`${base}/social/images/requirements`);
  const { job, setJob, pollError, setPollError } = useGenerationJob(
    base,
    (completed) => {
      if (completed.result.variants?.length)
        onVariants(completed.result.variants);
      if (completed.result.asset) {
        setImageResult(completed.result.asset);
        setImageReviewed(false);
      }
      if (!completed.result.variants?.length && !completed.result.asset)
        setError(
          "Der Auftrag lieferte keinen verwendbaren Text oder gespeicherten Bildnachweis. Bitte den Auftrag prüfen.",
        );
    },
  );
  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPollError("");
    setBusy(true);
    setImageResult(null);
    const form = new FormData(event.currentTarget);
    try {
      const body =
        tool === "text"
          ? {
              topic: form.get("topic"),
              audience: form.get("audience"),
              tone: form.get("tone"),
              objective: form.get("objective"),
              post_type: form.get("post_type"),
              instructions: form.get("instructions"),
              brand_id: brandId || null,
              variants: 3,
            }
          : {
              prompt: form.get("prompt"),
              alt_text: form.get("alt_text"),
              brand_id: brandId || null,
              rights_confirmed: form.get("rights") === "on",
            };
      const result = await write<GenerationJob>(
        tool === "text" ? "/social/generate" : "/social/images/generate",
        body,
      );
      setJob(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const selectedBrand = brands.find((brand) => brand.id === brandId);
  return (
    <section className="social-generation">
      <div className="social-tool-tabs" role="group" aria-label="KI-Werkzeug">
        <button
          className={`button small ${tool === "text" ? "primary" : "secondary"}`}
          onClick={() => setTool("text")}
        >
          <Sparkles size={14} /> KI-Text
        </button>
        <button
          className={`button small ${tool === "image" ? "primary" : "secondary"}`}
          onClick={() => setTool("image")}
        >
          <ImageIcon size={14} /> KI-Bild
        </button>
      </div>
      <ErrorNote
        message={
          error ||
          pollError ||
          (job && ["failed", "ambiguous"].includes(job.status)
            ? `Auftrag ${job.status}: ${job.last_error || "Anbieterantwort nicht bestätigt."}${job.status === "ambiguous" ? " Ausgang und mögliche Kosten vor einem neuen Auftrag beim Anbieter prüfen." : ""}`
            : "")
        }
      />
      <form onSubmit={generate} key={tool}>
        {tool === "text" ? (
          <>
            <label>
              Thema für KI-Vorschläge
              <input
                name="topic"
                defaultValue={topic}
                required
                minLength={3}
                maxLength={300}
              />
            </label>
            <div className="form-grid">
              <label>
                Zielpublikum
                <input
                  name="audience"
                  defaultValue={selectedBrand?.audience || ""}
                  maxLength={1000}
                />
              </label>
              <label>
                Tonalität
                <input
                  name="tone"
                  defaultValue={
                    selectedBrand?.voice || "Sachlich und hilfreich"
                  }
                  maxLength={300}
                />
              </label>
            </div>
            <div className="form-grid">
              <label>
                Ziel des Beitrags
                <select name="objective">
                  <option value="discussion">Gespräch anstoßen</option>
                  <option value="education">Wissen vermitteln</option>
                  <option value="brand_awareness">
                    Positionierung stärken
                  </option>
                </select>
              </label>
              <label>
                Beitragsart
                <select name="post_type">
                  <option value="insight">Perspektive / Insight</option>
                  <option value="question">Frage an das Netzwerk</option>
                  <option value="how_to">Praktischer Leitfaden</option>
                  <option value="story">Eigene Erfahrung</option>
                </select>
              </label>
            </div>
            <label>
              Überarbeitungswunsch / belegbarer Kontext
              <textarea
                name="instructions"
                rows={3}
                maxLength={2000}
                placeholder="Zum Beispiel: kürzer, klarerer Einstieg, keine unbelegten Zahlen. Fehlende Fakten ausdrücklich offen lassen."
              />
            </label>
            <p className="small muted">
              Drei echte Varianten aus dem konfigurierten Modell. Quellen und
              Aussagen bleiben prüfpflichtig. Ohne Anbieterzugang wird keine
              KI-Antwort simuliert.
            </p>
          </>
        ) : (
          <>
            <label>
              Bildidee
              <textarea
                name="prompt"
                required
                minLength={3}
                maxLength={1000}
                rows={3}
                placeholder="Beschreibe ein eigenes Motiv, Stil und Farben. Keine fiktiven Kundenerfolge oder Personen als Tatsachen darstellen."
              />
            </label>
            <label>
              Alternativtext für das erzeugte Motiv
              <input name="alt_text" required minLength={3} maxLength={1000} />
            </label>
            <label className="checkbox-line">
              <input type="checkbox" name="rights" required /> Ich prüfe die
              Nutzungsrechte und das Ergebnis vor der Verwendung.
            </label>
            <p className="small muted">
              Ein konfigurierter Bildanbieter und ein freigegebener Kostenrahmen
              sind erforderlich. Als erzeugt gilt das Bild erst nach Speicherung
              der echten Anbieterbytes in deiner privaten Bibliothek.
            </p>
          </>
        )}
        {tool === "image" && imageRequirements.data?.max_cost_minor != null && (
          <p className="small muted">
            Maximal reservierter Kostenrahmen:{" "}
            {new Intl.NumberFormat("de-DE", {
              style: "currency",
              currency: "USD",
            }).format(imageRequirements.data.max_cost_minor / 100)}{" "}
            pro Bildauftrag. Tatsächliche Anbietergebühren können separat
            abgerechnet werden.
          </p>
        )}
        {tool === "image" &&
          imageRequirements.data &&
          !imageRequirements.data.configured && (
            <div className="info-note">
              <p>
                <strong>Bildanbieter einrichten</strong>
                {imageRequirements.data.requirements.join(" · ")}
              </p>
            </div>
          )}
        <button
          className="button primary"
          disabled={
            busy ||
            pending(job) ||
            (tool === "image" && imageRequirements.data?.configured === false)
          }
        >
          {busy || pending(job) ? <Spinner /> : <Sparkles size={15} />}{" "}
          {tool === "text"
            ? "Drei KI-Varianten anfordern"
            : "Echtes Bild anfordern"}
        </button>
      </form>
      {job && (
        <div className="generation-status" role="status">
          <Badge>{job.status}</Badge>
          <span>
            Auftrag {job.id.slice(0, 8)} ·{" "}
            {job.result.notice ||
              "Kein Versand oder Publishing durch Generierung."}
          </span>
        </div>
      )}
      {imageResult && (
        <section className="generated-image-review">
          <Image
            unoptimized
            width={500}
            height={400}
            src={`/api${imageResult.url}`}
            alt={imageResult.alt_text}
          />
          <p>
            Das echte Anbieterbild ist privat gespeichert, aber noch nicht zur
            Bibliothek freigegeben.
          </p>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={imageReviewed}
              onChange={(e) => setImageReviewed(e.target.checked)}
            />{" "}
            Motiv, Nutzungsrechte und Alternativtext geprüft.
          </label>
          <button
            className="button secondary"
            disabled={!imageReviewed || busy}
            onClick={async () => {
              if (!job) return;
              setBusy(true);
              try {
                const asset = await write<Asset>(
                  `/social/images/${job.id}/save`,
                  { rights_confirmed: true },
                );
                onChange();
                onAsset(asset);
                setImageResult(null);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Nach Prüfung in Bibliothek übernehmen
          </button>
        </section>
      )}
    </section>
  );
}

export function PublishingRules({
  base,
  write,
}: {
  base: string;
  write: Write;
}) {
  const policy = useData<{
    mode: "manual" | "authorized_auto";
    max_posts_daily: number;
  }>(`${base}/social/policy`);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSaved("");
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      await write(
        "/social/policy",
        { mode: form.get("mode"), max_posts_daily: Number(form.get("limit")) },
        "PUT",
      );
      setSaved(
        "Regeln gespeichert. Jede Veröffentlichung benötigt weiterhin eine explizit autorisierte, freigegebene Revision.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="panel social-policy">
      <summary>Veröffentlichungsregeln & Tageslimit</summary>
      <div className="modal-body">
        <ErrorNote message={error || policy.error} />
        {policy.loading ? (
          <Spinner />
        ) : (
          policy.data && (
            <form onSubmit={save}>
              <div className="form-grid">
                <label>
                  Freigabemodus
                  <select name="mode" defaultValue={policy.data.mode}>
                    <option value="manual">Manuelle Freigabe je Beitrag</option>
                    <option value="authorized_auto">
                      Automatisch für ausdrücklich autorisierte Inhalte
                    </option>
                  </select>
                </label>
                <label>
                  Maximale Veröffentlichungen pro UTC-Tag
                  <input
                    type="number"
                    name="limit"
                    defaultValue={policy.data.max_posts_daily}
                    min={1}
                    max={10}
                    required
                  />
                </label>
              </div>
              <p className="small muted">
                Kein Autopilot für ungeprüfte Inhalte. Rechte, aktuelle
                Revision, Scopes und Limits werden vor jedem Versuch erneut
                geprüft. Unklare Anbieterantworten erfordern Abgleich.
              </p>
              <button className="button secondary" disabled={busy}>
                Regeln speichern
              </button>
              {saved && <p role="status">{saved}</p>}
            </form>
          )
        )}
      </div>
    </details>
  );
}

const berlinDate = (value: string | Date) =>
  new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Berlin" }).format(
    new Date(value),
  );
const iso = (date: Date) => date.toISOString().slice(0, 10);
const utcDate = (value: string) => new Date(`${value}T12:00:00Z`);

export function ContentCalendar({
  posts,
  onOpen,
}: {
  posts: Post[];
  onOpen: (post: Post) => void;
}) {
  const [view, setView] = useState<"month" | "week" | "list">("month");
  const [offset, setOffset] = useState(0);
  const today = berlinDate(new Date());
  const anchor = utcDate(today);
  if (view === "month") anchor.setUTCMonth(anchor.getUTCMonth() + offset, 1);
  else
    anchor.setUTCDate(
      anchor.getUTCDate() - ((anchor.getUTCDay() + 6) % 7) + offset * 7,
    );
  const days =
    view === "month"
      ? new Date(
          Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth() + 1, 0),
        ).getUTCDate()
      : 7;
  const first = view === "month" ? (anchor.getUTCDay() + 6) % 7 : 0;
  const dates = Array.from({ length: days }, (_, i) => {
    const value = new Date(anchor);
    value.setUTCDate((view === "month" ? 1 : anchor.getUTCDate()) + i);
    return iso(value);
  });
  const scheduled = posts
    .filter((post) => post.scheduled_at)
    .sort((a, b) => a.scheduled_at!.localeCompare(b.scheduled_at!));
  const label =
    view === "list"
      ? "Geplante Beiträge"
      : new Intl.DateTimeFormat("de-DE", {
          month: "long",
          year: "numeric",
          timeZone: "UTC",
        }).format(anchor);
  const card = (post: Post) => (
    <button
      type="button"
      className="calendar-post"
      key={post.id}
      onClick={() => onOpen(post)}
      aria-label={`Beitrag öffnen: ${post.caption.slice(0, 70)}`}
    >
      <span>{dateTime(post.scheduled_at!)}</span>
      <strong>{post.caption.slice(0, 75)}</strong>
      <small>
        {post.state === "scheduled" && post.publish_enabled
          ? "Veröffentlichung autorisiert"
          : postLabels[post.state] || post.state}
      </small>
    </button>
  );
  return (
    <section className="panel">
      <div className="panel-head calendar-toolbar">
        <div>
          <h2>{label}</h2>
          <p>Europe/Berlin · Termin auswählen, bearbeiten und prüfen</p>
        </div>
        <div
          className="calendar-views"
          role="group"
          aria-label="Kalenderansicht"
        >
          {(
            [
              ["month", "Monat"],
              ["week", "Woche"],
              ["list", "Liste"],
            ] as const
          ).map(([key, title]) => (
            <button
              key={key}
              className={`button small ${view === key ? "primary" : "secondary"}`}
              onClick={() => {
                setView(key);
                setOffset(0);
              }}
            >
              {title}
            </button>
          ))}
          <button
            disabled={view === "list"}
            className="icon-button"
            aria-label="Vorheriger Zeitraum"
            onClick={() => setOffset(offset - 1)}
          >
            <ChevronLeft size={18} />
          </button>
          <button
            className="button secondary small"
            onClick={() => setOffset(0)}
          >
            Heute
          </button>
          <button
            disabled={view === "list"}
            className="icon-button"
            aria-label="Nächster Zeitraum"
            onClick={() => setOffset(offset + 1)}
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </div>
      {view === "list" ? (
        <div className="calendar-list">
          {scheduled.length ? (
            scheduled.map(card)
          ) : (
            <Empty
              icon={CalendarDays}
              title="Noch keine Termine"
              description="Gib einen Beitrag frei und plane ihn im Kalender ein."
            />
          )}
        </div>
      ) : (
        <div
          className={view === "month" ? "calendar-grid" : "calendar-week-grid"}
        >
          {["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"].map((day) => (
            <div className="calendar-weekday" key={day}>
              {day}
            </div>
          ))}
          {Array.from({ length: first }, (_, i) => (
            <div className="calendar-day outside" key={`outside-${i}`} />
          ))}
          {dates.map((day) => (
            <div
              key={day}
              className={`calendar-day ${today === day ? "today" : ""}`}
            >
              <span>{Number(day.slice(-2))}</span>
              {scheduled
                .filter((post) => berlinDate(post.scheduled_at!) === day)
                .map(card)}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function PostInspector({
  base,
  post,
  write,
  onChange,
  onClose,
}: {
  base: string;
  post: Post;
  write: Write;
  onChange: () => void;
  onClose: () => void;
}) {
  const [current, setCurrent] = useState(post);
  const [caption, setCaption] = useState(post.caption);
  const [time, setTime] = useState(
    post.scheduled_at
      ? new Date(
          new Date(post.scheduled_at).getTime() -
            new Date(post.scheduled_at).getTimezoneOffset() * 60000,
        )
          .toISOString()
          .slice(0, 16)
      : "",
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const history = useData<{
    items: {
      revision: number;
      snapshot: {
        caption: string;
        alt_text: string;
        brand_id?: string | null;
        asset_ids?: string[];
      };
      created_at: string;
    }[];
  }>(`${base}/social/posts/${post.id}/revisions`, current.version);
  async function mutate(action: string, body: unknown = {}, method = "POST") {
    setError("");
    setBusy(true);
    try {
      const result = await write<Post>(
        `/social/posts/${post.id}${action ? `/${action}` : ""}`,
        body,
        method,
      );
      setCurrent(result);
      onChange();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Beitrag im Kalender" onClose={onClose} wide>
      <div className="modal-body">
        <div className="section-title">
          <Badge>{postLabels[current.state] || current.state}</Badge>
          <small>Revision {current.version}</small>
        </div>
        <ErrorNote message={error} />
        <label>
          Beitrag im Kalender bearbeiten
          <textarea
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            rows={6}
            maxLength={3000}
          />
        </label>
        <button
          className="button secondary"
          disabled={
            busy ||
            !caption.trim() ||
            caption === current.caption ||
            current.state === "publishing"
          }
          onClick={() =>
            mutate(
              "",
              {
                caption,
                alt_text: current.alt_text,
                brand_id: current.brand_id || null,
                asset_ids: current.asset_ids || [],
                version: current.version,
              },
              "PATCH",
            )
          }
        >
          Änderung speichern und Freigabe zurücksetzen
        </button>
        <p className="small muted">
          Bearbeitung verwirft die Freigabe und den bisherigen Termin. Eine neue
          Prüfung ist erforderlich.
        </p>
        <div className="form-actions">
          {current.state === "draft" && (
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => mutate("submit-review")}
            >
              Zur Prüfung
            </button>
          )}
          {current.state === "needs_review" && (
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => mutate("approve")}
            >
              Freigeben
            </button>
          )}
        </div>
        {["approved", "scheduled"].includes(current.state) && (
          <>
            <label>
              Redaktionellen Termin ändern (lokale Browser-Zeitzone)
              <input
                type="datetime-local"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </label>
            <div className="form-actions">
              <button
                className="button primary"
                disabled={
                  busy || !time || Number.isNaN(new Date(time).getTime())
                }
                onClick={() =>
                  mutate("schedule", {
                    scheduled_at: new Date(time).toISOString(),
                  })
                }
              >
                Redaktionellen Termin speichern
              </button>
              {current.state === "scheduled" && (
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() => mutate("cancel")}
                >
                  Termin aufheben
                </button>
              )}
            </div>
            <p className="small muted">
              Interne Terminplanung autorisiert keine externe Veröffentlichung.
            </p>
          </>
        )}
        <section className="revision-list">
          <h3>
            <History size={16} /> Gespeicherte Revisionen
          </h3>
          <ErrorNote message={history.error} />
          {history.loading ? (
            <Spinner />
          ) : history.data?.items.length ? (
            history.data.items.map((version) => (
              <details key={version.revision}>
                <summary>
                  Revision {version.revision} · {dateTime(version.created_at)}
                </summary>
                <p style={{ whiteSpace: "pre-wrap" }}>
                  {version.snapshot.caption}
                </p>
                <small>
                  {version.snapshot.asset_ids?.length || 0} Bildzuordnungen
                </small>
              </details>
            ))
          ) : (
            <p className="small muted">
              Für diesen älteren Entwurf ist noch kein Revisionssnapshot
              vorhanden. Neue Änderungen werden versioniert gespeichert.
            </p>
          )}
        </section>
      </div>
    </Modal>
  );
}

type Interaction = {
  id: string;
  source: "manual";
  author: string;
  content: string;
  post_url?: string;
  created_at: string;
  status: "open" | "reviewed";
  reply_draft: string;
};
export function EngagementWorkspace({
  base,
  write,
  notify,
  onChange,
  revision,
}: ModuleProps) {
  const data = useData<Page<Interaction>>(
    `${base}/social/interactions?limit=100`,
    revision,
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Interaction | null>(null);
  const [reply, setReply] = useState("");
  const { job, setJob, pollError } = useGenerationJob(base, (result) => {
    if (result.result.text) setReply(result.result.text);
    else setError("Kein verwendbarer Antwortvorschlag vorhanden.");
  });
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await write("/social/interactions", {
        author: form.get("author"),
        content: form.get("content"),
        ...(form.get("url") ? { post_url: form.get("url") } : {}),
      });
      onChange();
      notify("Manuelle Interaktion mit Quellenkennzeichnung gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="SOCIAL · ENGAGEMENT"
        title="Interaktionen prüfen"
        description="Manuell erfasster Kontext und geprüfte Antwortentwürfe. Kein automatisches Lesen fremder Feeds, Kommentieren oder Liken."
      />
      <div className="info-note">
        <MessageSquare size={18} />
        <p>
          <strong>Quelle: manuell erfasst.</strong> LinkedIn-Kommentarzugriff
          ist nicht pauschal verfügbar. Diese Ansicht erfindet keine externen
          Interaktionen und löst keine Netzwerkaktionen aus.
        </p>
      </div>
      <ErrorNote message={error || data.error} />
      <details className="panel social-policy">
        <summary>Interaktion manuell erfassen</summary>
        <form className="modal-body" onSubmit={add}>
          <div className="form-grid">
            <label>
              Autor / Quelle
              <input name="author" required maxLength={200} />
            </label>
            <label>
              Beitragslink (optional)
              <input name="url" type="url" maxLength={2000} />
            </label>
          </div>
          <label>
            Manuell bereitgestellter Kommentar
            <textarea name="content" required maxLength={5000} rows={4} />
          </label>
          <button className="button primary" disabled={busy}>
            Interaktion speichern
          </button>
        </form>
      </details>
      <section className="panel">
        {data.loading ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : data.data?.items.length ? (
          <div className="post-rows">
            {data.data.items.map((item) => (
              <article className="post-row" key={item.id}>
                <div className="post-content">
                  <div className="section-title">
                    <h3>{item.author}</h3>
                    <Badge>
                      {item.status === "reviewed" ? "Geprüft" : "Offen"} ·
                      manuell
                    </Badge>
                  </div>
                  <p>{item.content}</p>
                  <small>{dateTime(item.created_at)}</small>
                </div>
                <button
                  className="button secondary"
                  onClick={() => {
                    setSelected(item);
                    setReply(item.reply_draft || "");
                    setJob(null);
                    setError("");
                  }}
                >
                  Antwort prüfen
                </button>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            icon={MessageSquare}
            title="Noch keine Interaktionen"
            description="Erfasse einen berechtigt bereitgestellten Kommentar, um einen Antwortentwurf vorzubereiten."
          />
        )}
      </section>
      {selected && (
        <Modal
          title="Antwortentwurf prüfen"
          onClose={() => setSelected(null)}
          wide
        >
          <div className="modal-body">
            <blockquote>{selected.content}</blockquote>
            <ErrorNote
              message={
                error ||
                pollError ||
                (job?.last_error ? `KI-Auftrag: ${job.last_error}` : "")
              }
            />
            <button
              className="button secondary"
              disabled={pending(job) || busy}
              onClick={async () => {
                setBusy(true);
                try {
                  setJob(
                    await write<GenerationJob>(
                      `/social/interactions/${selected.id}/suggest`,
                    ),
                  );
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {pending(job) ? <Spinner /> : <Sparkles size={14} />} Echten
              KI-Antwortvorschlag anfordern
            </button>
            <p className="small muted">
              Ohne konfigurierten Anbieter erscheint ein Fehler. Ein Vorschlag
              ist ungeprüft und wird niemals automatisch veröffentlicht.
            </p>
            <label>
              Geprüfter Antwortentwurf
              <textarea
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                rows={6}
                maxLength={3000}
              />
            </label>
            <div className="form-actions">
              <button
                className="button secondary"
                disabled={!reply.trim()}
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(reply);
                    notify("Antwortentwurf kopiert. Keine Veröffentlichung.");
                  } catch {
                    setError(
                      "Kopieren nicht verfügbar. Bitte Text manuell markieren.",
                    );
                  }
                }}
              >
                Text für manuelle Antwort kopieren
              </button>
              <button
                className="button primary"
                disabled={busy || !reply.trim()}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await write(
                      `/social/interactions/${selected.id}`,
                      { status: "reviewed", reply_draft: reply },
                      "PATCH",
                    );
                    onChange();
                    setSelected(null);
                    notify(
                      "Antwortentwurf geprüft gespeichert. Nichts veröffentlicht.",
                    );
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Als geprüft speichern
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
