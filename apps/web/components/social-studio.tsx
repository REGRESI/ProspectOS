"use client";
import { useState, useCallback } from "react";
import Image from "next/image";
import {
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  FileText,
  MoreHorizontal,
  Sparkles,
} from "lucide-react";
import { useData } from "@/lib/use-data";
import { dateTime, postLabels } from "@/lib/api";
import type { Page, Post } from "@/lib/api";
import type { Asset, Brand, Write } from "./growth-modules";
import { Badge, Empty, ErrorNote, Heading, Modal, Spinner } from "./ui";
export function Social({
  base,
  write,
  notify,
  revision,
  onChange,
  calendar,
}: {
  base: string;
  write: Write;
  notify: (s: string) => void;
  revision: number;
  onChange: () => void;
  calendar: boolean;
}) {
  const { data, error, loading } = useData<Page<Post>>(
    `${base}/social/posts?limit=100`,
    revision,
  );
  const [topic, setTopic] = useState("");
  const [caption, setCaption] = useState("");
  const [altText, setAltText] = useState("");
  const [assetId, setAssetId] = useState("");
  const [brandId, setBrandId] = useState("");
  const assets = useData<Page<Asset>>(`${base}/assets?limit=100`, revision);
  const brands = useData<Page<Brand>>(`${base}/brands?limit=100`, revision);
  const integration = useData<{
    items: { name: string; status: string; reason: string; publish_available?:boolean }[];
  }>(`${base}/integrations`);
  const linkedin = integration.data?.items.find(
    (i) => i.name.toLowerCase() === "linkedin",
  );
  const selectedAsset = assets.data?.items.find(
    (asset) => asset.id === assetId,
  );

  const [variants, setVariants] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");
  const [editing, setEditing] = useState<Post | null>(null);
  const [publish,setPublish]=useState<Post|null>(null);
  const [publishTime,setPublishTime]=useState("");
  const [schedule, setSchedule] = useState<Post | null>(null);
  const [time, setTime] = useState("");
  const [monthOffset, setMonthOffset] = useState(0);
  const close = useCallback(() => setSchedule(null), []);
  async function generate() {
    setBusy(true);
    setLocalError("");
    try {
      const result = await write<{ variants: string[]; notice: string }>(
        "/social/captions/generate",
        { topic },
      );
      setVariants(result.variants);
      setCaption(result.variants[0] || "");
      notify(
        result.notice ||
          "Offline-Vorschläge erstellt. Kein KI-Anbieter verbunden.",
      );
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    setBusy(true);
    setLocalError("");
    try {
      await write(
        editing ? `/social/posts/${editing.id}` : "/social/posts",
        {
          caption,
          alt_text: altText,
          brand_id: brandId || null,
          asset_ids: assetId ? [assetId] : [],
          ...(editing ? { version: editing.version } : {}),
        },
        editing ? "PATCH" : "POST",
      );
      setCaption("");
      setAltText("");
      setAssetId("");
      setBrandId("");
      setEditing(null);
      onChange();
      notify("Beitrag gespeichert.");
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function action(post: Post, action: string, body: unknown = {}) {
    try {
      await write(`/social/posts/${post.id}/${action}`, body);
      onChange();
      notify(
        action === "schedule"
          ? "Im internen Kalender geplant. Keine LinkedIn-Veröffentlichung."
          : "Beitragsstatus aktualisiert.",
      );
      return true;
    } catch (e) {
      notify((e as Error).message);
      return false;
    }
  }
  const posts = data?.items || [];
  const berlinToday = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Berlin",
  }).format(new Date());
  const [berlinYear, berlinMonth] = berlinToday.split("-").map(Number);
  const month = new Date(berlinYear, berlinMonth - 1, 1);
  month.setMonth(month.getMonth() + monthOffset);
  const first = (month.getDay() + 6) % 7;
  const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const monthName = new Intl.DateTimeFormat("de-DE", {
    month: "long",
    year: "numeric",
  }).format(month);
  return (
    <>
      <Heading
        eyebrow={
          calendar ? "DEIN REDAKTIONELLER RHYTHMUS" : "IDEEN, DIE VERBINDEN"
        }
        title={
          calendar
            ? "Guter Content braucht einen Plan."
            : "Deine Perspektive. Deine Stimme."
        }
        description={
          calendar
            ? "Redaktionelle und ausdrücklich autorisierte Termine in Europe/Berlin."
            : "Entwickle Ideen, feile an deinem Text und bereite deinen nächsten Beitrag vor."
        }
      />
      <div className="provider-notice">
        <span className="linkedin-mark">in</span>
        <div>
          <strong>
            {linkedin?.status === "connected"
              ? "LinkedIn-Verbindung vorhanden."
              : linkedin
                ? "LinkedIn ist noch nicht verbunden."
                : "LinkedIn-Status wird geprüft."}
          </strong>
          <span>
            {" "}
            {linkedin?.reason || "Entwürfe und interne Planung sind verfügbar."}
          </span>
        </div>
        <Badge tone="neutral">{linkedin?.publish_available?"Freigabe erforderlich":"Kein Versand"}</Badge>
      </div>
      <ErrorNote message={error || localError} />
      {calendar ? (
        <section className="panel">
          <div className="panel-head calendar-toolbar">
            <div>
              <h2>{monthName}</h2>
              <p>Zeitzone: Europe/Berlin</p>
            </div>
            <div>
              <button
                className="icon-button"
                aria-label="Vorheriger Monat"
                onClick={() => setMonthOffset((v) => v - 1)}
              >
                <ChevronLeft size={18} />
              </button>
              <button
                className="button secondary"
                onClick={() => setMonthOffset(0)}
              >
                Heute
              </button>
              <button
                className="icon-button"
                aria-label="Nächster Monat"
                onClick={() => setMonthOffset((v) => v + 1)}
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
          <div className="calendar-grid">
            {["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"].map((day) => (
              <div className="calendar-weekday" key={day}>
                {day}
              </div>
            ))}
            {Array.from({ length: first }, (_, i) => (
              <div className="calendar-day outside" key={`empty-${i}`} />
            ))}
            {Array.from({ length: days }, (_, i) => {
              const date = new Date(
                month.getFullYear(),
                month.getMonth(),
                i + 1,
              );
              const today =
                berlinToday ===
                `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`;
              const scheduled = posts.filter(
                (p) =>
                  p.scheduled_at &&
                  new Intl.DateTimeFormat("sv-SE", {
                    timeZone: "Europe/Berlin",
                  }).format(new Date(p.scheduled_at)) ===
                    `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`,
              );
              return (
                <div className={`calendar-day ${today ? "today" : ""}`} key={i}>
                  <span>{i + 1}</span>
                  {scheduled.map((p) => (
                    <div className="calendar-post" key={p.id}>
                      <span>
                        {new Intl.DateTimeFormat("de-DE", {
                          timeZone: "Europe/Berlin",
                          hour: "2-digit",
                          minute: "2-digit",
                        }).format(new Date(p.scheduled_at!))}
                      </span>
                      <strong>{p.caption.slice(0, 55)}</strong>
                      <small>{p.state==="scheduled"&&p.publish_enabled?"Veröffentlichung autorisiert":postLabels[p.state]||p.state}</small>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </section>
      ) : (
        <div className="studio-layout">
          <section className="panel studio-editor">
            <div className="panel-head">
              <div>
                <h2>{editing ? "Beitrag bearbeiten" : "Neuer Beitrag"}</h2>
                <p>Erst die Idee. Dann die richtigen Worte.</p>
              </div>
              <Badge tone="purple">LinkedIn</Badge>
            </div>
            <div className="studio-body">
              <div className="form-grid">
                <label>
                  Markenprofil
                  <select
                    value={brandId}
                    onChange={(e) => setBrandId(e.target.value)}
                  >
                    <option value="">Ohne Markenprofil</option>
                    {brands.data?.items.map((brand) => (
                      <option key={brand.id} value={brand.id}>
                        {brand.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Bild aus privater Bibliothek
                  <select
                    value={assetId}
                    onChange={(e) => {
                      setAssetId(e.target.value);
                      const asset = assets.data?.items.find(
                        (a) => a.id === e.target.value,
                      );
                      if (asset) setAltText(asset.alt_text);
                    }}
                  >
                    <option value="">Textbeitrag ohne Bild</option>
                    {assets.data?.items.map((asset) => (
                      <option key={asset.id} value={asset.id}>
                        {asset.filename}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <ErrorNote message={assets.error || brands.error} />
              {selectedAsset && (
                <div className="composer-asset">
                  <Image
                    unoptimized
                    width={600}
                    height={360}
                    src={`/api${selectedAsset.url}`}
                    alt={altText || selectedAsset.alt_text}
                  />
                  <Badge tone="green">Privates Bild ausgewählt</Badge>
                </div>
              )}
              <label>
                Worüber möchtest du sprechen?
                <div className="topic-input">
                  <input
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    placeholder="z. B. Was ein sauberes Büro für Teams bedeutet"
                    maxLength={300}
                  />
                  <button
                    className="button secondary"
                    disabled={!topic.trim() || busy}
                    onClick={generate}
                  >
                    {busy ? <Spinner /> : <Sparkles size={15} />} Ideen
                    entwickeln
                  </button>
                </div>
              </label>
              <p className="offline-label">
                <CircleHelp size={12} /> Deterministische Offline-Vorschläge ·
                kein KI-Anbieter verbunden
              </p>
              {variants.length > 0 && (
                <div className="variant-tabs">
                  {variants.map((variant, i) => (
                    <button
                      className={`button ${caption === variant ? "primary" : "secondary"}`}
                      key={i}
                      onClick={() => setCaption(variant)}
                    >
                      Variante {i + 1}
                    </button>
                  ))}
                </div>
              )}
              <label>
                Dein Beitrag
                <textarea
                  aria-label="Beitragstext"
                  value={caption}
                  onChange={(e) => setCaption(e.target.value)}
                  rows={10}
                  maxLength={3000}
                  placeholder="Was möchtest du mit deinem Netzwerk teilen? Gute Beiträge beginnen mit einer eigenen Perspektive."
                />
              </label>
              <div className="editor-footer">
                <span>
                  <FileText size={14} /> Textbeitrag
                </span>
                <span>{caption.length} / 3.000 Zeichen</span>
              </div>
              <label>
                Bildbeschreibung / Kontext (optional)
                <input
                  value={altText}
                  onChange={(e) => setAltText(e.target.value)}
                  placeholder="Beschreibe den Bildinhalt für Menschen mit Sehbeeinträchtigung"
                  maxLength={1000}
                />
              </label>
              <div className="form-actions">
                {editing && (
                  <button
                    className="button secondary"
                    onClick={() => {
                      setEditing(null);
                      setCaption("");
                      setAltText("");
                      setAssetId("");
                      setBrandId("");
                    }}
                  >
                    Bearbeitung abbrechen
                  </button>
                )}
                <button
                  className="button primary"
                  disabled={!caption.trim() || busy}
                  onClick={save}
                >
                  {busy ? <Spinner /> : <Check size={16} />} Entwurf speichern
                </button>
              </div>
            </div>
          </section>
          <aside className="social-preview">
            <p className="eyebrow">VORSCHAU · NICHT VERÖFFENTLICHT</p>
            <div className="linkedin-preview">
              <div className="preview-author">
                <span className="workspace-avatar">P</span>
                <div>
                  <strong>Dein LinkedIn-Profil</strong>
                  <small>Vorschau · Konto nicht verbunden</small>
                </div>
                <MoreHorizontal size={20} />
              </div>
              <p className={caption ? "" : "muted"}>
                {caption ||
                  "Hier bekommt dein Beitrag ein Gesicht. Schreibe einen eigenen Text oder entwickle zuerst ein paar Ideen."}
              </p>
              {selectedAsset && (
                <div className="preview-asset">
                  <Image
                    unoptimized
                    width={500}
                    height={320}
                    src={`/api${selectedAsset.url}`}
                    alt={altText || selectedAsset.alt_text}
                  />
                </div>
              )}
              <div className="preview-divider" />
              <div className="preview-reactions">
                <span>Gefällt mir</span>
                <span>Kommentieren</span>
                <span>Teilen</span>
              </div>
            </div>
            <div className="preview-tip">
              <span className="step-icon purple">
                <Sparkles size={18} />
              </span>
              <div>
                <strong>Hilfreich statt laut.</strong>
                <p>
                  Eine klare Perspektive, ein konkretes Beispiel und eine offene
                  Frage sind ein guter Anfang.
                </p>
              </div>
            </div>
          </aside>
        </div>
      )}
      <section className="panel post-list">
        <div className="panel-head">
          <div>
            <h2>{calendar ? "Beiträge & Freigaben" : "Deine Beiträge"}</h2>
            <p>Entwürfe, Prüfungen und redaktionelle Termine.</p>
          </div>
          <Badge>{data?.total ?? 0} Beiträge</Badge>
        </div>
        {loading ? (
          <div className="loading-block">
            <Spinner />
          </div>
        ) : posts.length ? (
          <div className="post-rows">
            {posts.map((post) => (
              <article className="post-row" key={post.id}>
                <span className="post-icon">
                  <FileText size={20} />
                </span>
                <div className="post-content">
                  <div>
                    <Badge
                      tone={
                        post.state === "approved"
                          ? "green"
                          : post.state === "scheduled"
                            ? "purple"
                            : "neutral"
                      }
                    >
                      {postLabels[post.state] || post.state}
                    </Badge>
                    <small>
                      Revision {post.version}
                      {post.scheduled_at
                        ? ` · ${dateTime(post.scheduled_at)}`
                        : ""}
                    </small>
                  </div>
                  <p>{post.caption}</p>
                </div>
                <div className="post-actions">
                  {!calendar && (
                    <button
                      className="button secondary small"
                      onClick={() => {
                        setEditing(post);
                        setCaption(post.caption);
                        setAltText(post.alt_text);
                        setAssetId(post.asset_ids?.[0] || "");
                        setBrandId(post.brand_id || "");
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                    >
                      Bearbeiten
                    </button>
                  )}
                  {post.state === "draft" && (
                    <button
                      className="button secondary small"
                      onClick={() => action(post, "submit-review")}
                    >
                      Zur Prüfung
                    </button>
                  )}
                  {post.state === "needs_review" && (
                    <button
                      className="button secondary small"
                      onClick={() => action(post, "approve")}
                    >
                      Freigeben
                    </button>
                  )}
                  {post.state === "approved" && linkedin?.publish_available && <button className="button primary small" onClick={()=>{setPublish(post);setPublishTime("");}}>Auf LinkedIn veröffentlichen</button>}
                  {post.state === "approved" && (
                    <button
                      className="button primary small"
                      onClick={() => {
                        setSchedule(post);
                        setTime("");
                      }}
                    >
                      <CalendarDays size={14} /> Planen
                    </button>
                  )}
                  {post.state === "scheduled" && (
                    <button
                      className="button secondary small"
                      onClick={() => action(post, "cancel")}
                    >
                      Termin aufheben
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <Empty
            icon={FileText}
            title="Deine Ideen haben hier Platz."
            description="Speichere deinen ersten Entwurf. Danach kannst du ihn prüfen, freigeben und intern planen."
          />
        )}
      </section>
      {schedule && (
        <Modal title="Redaktionellen Termin planen" onClose={close}>
          <div className="modal-body">
            <p className="muted">
              Dieser Termin ist ein interner Planungseintrag. Es findet keine
              Veröffentlichung auf LinkedIn statt.
            </p>
            <label>
              Zeitpunkt in deiner lokalen Browser-Zeitzone
              <input
                type="datetime-local"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                required
              />
            </label>
            <p className="small muted">
              Im Kalender wird der Zeitpunkt in Europe/Berlin angezeigt. Bitte
              bei Zeitumstellungen den angezeigten Zeitpunkt prüfen.
            </p>
            <div className="form-actions">
              <button className="button secondary" onClick={close}>
                Abbrechen
              </button>
              <button
                className="button primary"
                disabled={!time || Number.isNaN(new Date(time).getTime())}
                onClick={async () => {
                  if (
                    await action(schedule, "schedule", {
                      scheduled_at: new Date(time).toISOString(),
                    })
                  )
                    setSchedule(null);
                }}
              >
                Intern planen
              </button>
            </div>
          </div>
        </Modal>
      )}
      {publish&&<Modal title="Offizielle Veröffentlichung bestätigen" onClose={()=>setPublish(null)}><div className="modal-body"><p>Du autorisierst die Veröffentlichung dieser freigegebenen Revision über das verbundene LinkedIn-Konto. Ein Worker prüft Rechte, Revision, Medien und Tageslimit erneut.</p><p style={{whiteSpace:"pre-wrap"}}>{publish.caption}</p><label>Optionaler Zeitpunkt (deine lokale Zeitzone)<input type="datetime-local" value={publishTime} onChange={e=>setPublishTime(e.target.value)}/></label><p className="small muted">Ohne Zeitpunkt wird die Veröffentlichung jetzt in die Queue gestellt. Ein Auftrag ist noch keine veröffentlichte Nachricht; der bestätigte Anbieterbeleg entscheidet.</p><div className="form-actions"><button className="button secondary" onClick={()=>setPublish(null)}>Abbrechen</button><button className="button primary" onClick={async()=>{const ok=await action(publish,"publish",{scheduled_at:publishTime?new Date(publishTime).toISOString():null,automation_authorized:false});if(ok)setPublish(null);}}>Veröffentlichung autorisieren</button></div></div></Modal>}
    </>
  );
}
