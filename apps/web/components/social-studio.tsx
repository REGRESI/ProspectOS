"use client";
import { ProbePost } from "./probe-post";
import { useState, useCallback } from "react";
import Image from "next/image";
import {
  CalendarDays,
  Check,
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
import {
  ContentCalendar,
  GenerationTools,
  PostInspector,
  PublishingRules,
} from "./social-tools";
import { VoiceProfiles } from "./voice-profiles";
import { StudioRefinements } from "./studio-refinements";
import { StudioMedia, imageModeLabels, type ImageMode } from "./studio-media";

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
  const [voiceId, setVoiceId] = useState("");
  const [generationId, setGenerationId] = useState("");
  const [imageMode, setImageMode] = useState<ImageMode>("none");
  const [extraAsset, setExtraAsset] = useState<Asset | null>(null);
  const [showImage, setShowImage] = useState(true);
  const assets = useData<Page<Asset>>(`${base}/assets?limit=100`, revision);
  const brands = useData<Page<Brand>>(`${base}/brands?limit=100`, revision);
  const integration = useData<{
    items: {
      name: string;
      status: string;
      reason: string;
      publish_available?: boolean;
    }[];
  }>(`${base}/integrations`);
  const linkedin = integration.data?.items.find(
    (i) => i.name.toLowerCase() === "linkedin",
  );
  const selectedAsset = assetId
    ? extraAsset?.id === assetId
      ? extraAsset
      : assets.data?.items.find((asset) => asset.id === assetId)
    : undefined;

  const [variants, setVariants] = useState<string[]>([]);
  const [variantNotes, setVariantNotes] = useState<
    {
      hook?: string;
      cta?: string;
      citations?: string[];
      unverified_claims?: string[];
    }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");
  const [editing, setEditing] = useState<Post | null>(null);
  const [publish, setPublish] = useState<Post | null>(null);
  const [publishTime, setPublishTime] = useState("");
  const [automationAuthorized, setAutomationAuthorized] = useState(false);
  const publishPolicy = useData<{ mode: string }>(
    `${base}/social/policy`,
    revision,
  );
  const [schedule, setSchedule] = useState<Post | null>(null);
  const [time, setTime] = useState("");
  const [inspected, setInspected] = useState<Post | null>(null);
  const [aiOpen, setAiOpen] = useState(false);
  const [previewDevice, setPreviewDevice] = useState<"desktop" | "mobile">(
    "desktop",
  );
  const [variantOrigin, setVariantOrigin] = useState<"offline" | "provider">(
    "offline",
  );
  const [savedAt, setSavedAt] = useState<string | null>(null);
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
      setVariantOrigin("offline");
      setGenerationId("");
      setVariantNotes([]);
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
          studio_context: {
            image_mode: imageMode,
            voice_profile_id: voiceId || null,
            generation_job_id: generationId || null,
          },
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
      setImageMode("none");
      setGenerationId("");
      onChange();
      setSavedAt(new Date().toISOString());
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
  return (
    <>
      <Heading
        eyebrow={
          calendar ? "DEIN REDAKTIONELLER RHYTHMUS" : "IDEEN, DIE VERBINDEN"
        }
        title={calendar ? "Content-Kalender" : "Beiträge erstellen"}
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
        <Badge tone="neutral">
          {linkedin?.publish_available
            ? "Freigabe erforderlich"
            : "Kein Versand"}
        </Badge>
      </div>
      <ErrorNote message={error || localError} />
      <PublishingRules base={base} write={write} />
      {!calendar && <ProbePost base={base} write={write} onChange={onChange} />}
      {calendar ? (
        <ContentCalendar posts={posts} onOpen={setInspected} />
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
              <div className="section-title">
                <div>
                  <strong>Inhalt & Marke</strong>
                  <p className="small muted">
                    {caption.trim()
                      ? "Ungespeicherter Entwurf"
                      : savedAt
                        ? `Zuletzt gespeichert: ${dateTime(savedAt)}`
                        : "Noch kein Entwurf gespeichert"}
                  </p>
                </div>
                <button
                  className="button secondary small"
                  onClick={() => setAiOpen(!aiOpen)}
                  aria-expanded={aiOpen}
                >
                  {aiOpen ? "KI-Werkzeuge schließen" : "KI-Assistent öffnen"}
                </button>
              </div>
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
              </div>
              <VoiceProfiles
                base={base}
                write={write}
                value={voiceId}
                onSelect={setVoiceId}
                revision={revision}
                onChange={onChange}
              />
              {aiOpen && (
                <GenerationTools
                  base={base}
                  write={write}
                  voiceId={voiceId}
                  initialTool={imageMode === "ai" ? "image" : "text"}
                  key={imageMode === "ai" ? "image" : "text"}
                  postContext={caption}
                  onJob={setGenerationId}
                  brands={brands.data?.items || []}
                  brandId={brandId}
                  topic={topic}
                  onChange={onChange}
                  onVariants={(items) => {
                    const texts = items
                      .map((item) => item.text)
                      .filter(Boolean);
                    setVariants(texts);
                    setVariantNotes(items);
                    setVariantOrigin("provider");
                    notify(
                      "Echte Modellvarianten geladen. Variante auswählen und Aussagen prüfen.",
                    );
                  }}
                  onAsset={(asset) => {
                    setExtraAsset(asset);
                    setAssetId(asset.id);
                    setAltText(asset.alt_text);
                    setImageMode("ai");
                    notify("Geprüftes Anbieterbild ausgewählt.");
                  }}
                />
              )}
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
                  <Badge tone="green">{imageModeLabels[imageMode]}</Badge>
                  <button
                    className="button secondary small"
                    onClick={() => {
                      setAssetId("");
                      setAltText("");
                      setImageMode("none");
                    }}
                  >
                    Bild entfernen
                  </button>
                  <div className="form-actions">
                    <span className="small muted">
                      Mittiger Zuschnitt als neue private Datei:
                    </span>
                    {(["square", "portrait", "original"] as const).map(
                      (crop) => (
                        <button
                          key={crop}
                          className="button secondary small"
                          disabled={busy}
                          onClick={async () => {
                            setBusy(true);
                            setLocalError("");
                            try {
                              const asset = await write<Asset>(
                                `/assets/${selectedAsset.id}/crop`,
                                { crop },
                              );
                              onChange();
                              setAssetId(asset.id);
                              setAltText(asset.alt_text);
                              notify(
                                "Neue private Bildfassung gespeichert. Bestehende Beiträge bleiben unverändert.",
                              );
                            } catch (e) {
                              setLocalError((e as Error).message);
                            } finally {
                              setBusy(false);
                            }
                          }}
                        >
                          {crop === "square"
                            ? "Quadrat 1:1"
                            : crop === "portrait"
                              ? "Hochformat 4:5"
                              : "Originalformat"}
                        </button>
                      ),
                    )}
                  </div>
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
                keine echte KI-Generierung
              </p>
              {variants.length > 0 && (
                <p className="small muted">
                  {variantOrigin === "provider"
                    ? "Echte Modellvorschläge · nicht automatisch verifizierte Aussagen"
                    : "Offline-Vorlagen · deterministisch, keine KI-Ausgabe"}
                </p>
              )}
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
              {variantOrigin === "provider" &&
                variantNotes[variants.indexOf(caption)] && (
                  <div className="variant-evidence">
                    <strong>Modellvorschlag · Prüfung erforderlich</strong>
                    {variantNotes[variants.indexOf(caption)].hook && (
                      <p>
                        Einstieg: {variantNotes[variants.indexOf(caption)].hook}
                      </p>
                    )}
                    {variantNotes[variants.indexOf(caption)].cta && (
                      <p>
                        Handlungsimpuls:{" "}
                        {variantNotes[variants.indexOf(caption)].cta}
                      </p>
                    )}
                    {variantNotes[
                      variants.indexOf(caption)
                    ].unverified_claims?.map((claim, i) => (
                      <p className="small muted" key={i}>
                        Unbestätigt: {claim}
                      </p>
                    ))}
                    <small>
                      Quellen-IDs:{" "}
                      {variantNotes[variants.indexOf(caption)].citations?.join(
                        ", ",
                      ) || "keine"}
                      . Kein automatischer Faktennachweis.
                    </small>
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
              <StudioRefinements
                base={base}
                write={write}
                caption={caption}
                parentJobId={generationId}
                voiceId={voiceId}
                brandId={brandId}
                revision={revision}
                onChange={onChange}
                onSelect={(text, jobId) => {
                  setCaption(text);
                  setGenerationId(jobId);
                  setVariantOrigin("provider");
                }}
              />
            </div>
          </section>
          <aside className="social-preview">
            <p className="eyebrow">VORSCHAU · NICHT VERÖFFENTLICHT</p>
            <div
              className="preview-device"
              role="group"
              aria-label="Vorschaugerät"
            >
              <button
                className={`button small ${previewDevice === "desktop" ? "primary" : "secondary"}`}
                onClick={() => setPreviewDevice("desktop")}
              >
                Desktop-Vorschau
              </button>
              <button
                className={`button small ${previewDevice === "mobile" ? "primary" : "secondary"}`}
                onClick={() => setPreviewDevice("mobile")}
              >
                Mobile Vorschau
              </button>
            </div>
            <div
              className="linkedin-preview"
              style={
                previewDevice === "mobile"
                  ? { maxWidth: 340, marginInline: "auto" }
                  : undefined
              }
            >
              <div className="preview-author">
                <span className="workspace-avatar">P</span>
                <div>
                  <strong>Dein LinkedIn-Profil</strong>
                  <small>
                    {linkedin?.status === "connected"
                      ? "Vorschau · verbundenes Konto"
                      : "Vorschau · Konto nicht verbunden"}
                  </small>
                </div>
                <MoreHorizontal size={20} />
              </div>
              <p className={caption ? "" : "muted"}>
                {caption ||
                  "Hier bekommt dein Beitrag ein Gesicht. Schreibe einen eigenen Text oder entwickle zuerst ein paar Ideen."}
              </p>
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={showImage}
                  onChange={(e) => setShowImage(e.target.checked)}
                />{" "}
                Bild in Vorschau anzeigen
              </label>
              <p className="small muted preview-mode-hint">
                {selectedAsset
                  ? imageModeLabels[imageMode]
                  : "Textbeitrag ohne Bild"}{" "}
                · Vorschau, keine Veröffentlichung
              </p>
              {showImage && selectedAsset && (
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
            <StudioMedia
              write={write}
              assets={assets.data?.items || []}
              loading={assets.loading}
              mode={imageMode}
              onMode={(mode) => {
                setImageMode(mode);
                setAssetId("");
                setAltText("");
                if (mode === "ai") setAiOpen(true);
              }}
              onAsset={(asset, mode) => {
                setExtraAsset(asset);
                setAssetId(asset.id);
                setAltText(asset.alt_text);
                setImageMode(mode);
              }}
              onChange={onChange}
              topic={topic || caption}
              brandId={brandId}
              voiceId={voiceId}
              selectedId={assetId}
            />
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
                  <button
                    className="button secondary small"
                    onClick={() => setInspected(post)}
                  >
                    Details & Revisionen
                  </button>
                  {!calendar && (
                    <button
                      className="button secondary small"
                      onClick={() => {
                        setEditing(post);
                        setVoiceId(post.studio_context?.voice_profile_id || "");
                        setGenerationId(
                          post.studio_context?.generation_job_id || "",
                        );
                        setImageMode(
                          post.studio_context?.image_mode ||
                            (post.asset_ids?.length ? "manual" : "none"),
                        );
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
                  <button
                    className="button secondary small"
                    onClick={() => action(post, "duplicate")}
                  >
                    Duplizieren
                  </button>
                  {!["archived", "publishing", "published"].includes(
                    post.state,
                  ) && (
                    <button
                      className="button secondary small"
                      onClick={() => action(post, "archive")}
                    >
                      Archivieren
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
                  {post.state === "approved" && linkedin?.publish_available && (
                    <button
                      className="button primary small"
                      onClick={() => {
                        setPublish(post);
                        setPublishTime("");
                        setAutomationAuthorized(false);
                      }}
                    >
                      Auf LinkedIn veröffentlichen
                    </button>
                  )}
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
      {inspected && (
        <PostInspector
          key={inspected.id}
          base={base}
          post={inspected}
          write={write}
          onChange={onChange}
          onClose={() => setInspected(null)}
        />
      )}
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
      {publish && (
        <Modal
          title="Offizielle Veröffentlichung bestätigen"
          onClose={() => setPublish(null)}
        >
          <div className="modal-body">
            <p>
              Du autorisierst die Veröffentlichung dieser freigegebenen Revision
              über das verbundene LinkedIn-Konto. Ein Worker prüft Rechte,
              Revision, Medien und Tageslimit erneut.
            </p>
            <p style={{ whiteSpace: "pre-wrap" }}>{publish.caption}</p>
            <label>
              Optionaler Zeitpunkt (deine lokale Zeitzone)
              <input
                type="datetime-local"
                value={publishTime}
                onChange={(e) => setPublishTime(e.target.value)}
              />
            </label>
            {publishPolicy.data?.mode === "authorized_auto" && (
              <label className="checkbox-line">
                <input
                  type="checkbox"
                  checked={automationAuthorized}
                  onChange={(e) => setAutomationAuthorized(e.target.checked)}
                />{" "}
                Diese freigegebene Revision innerhalb der Workspace-Regeln
                automatisch veröffentlichen.
              </label>
            )}
            <p className="small muted">
              Ohne Zeitpunkt wird die Veröffentlichung jetzt in die Queue
              gestellt. Ein Auftrag ist noch keine veröffentlichte Nachricht;
              der bestätigte Anbieterbeleg entscheidet.
            </p>
            <div className="form-actions">
              <button
                className="button secondary"
                onClick={() => setPublish(null)}
              >
                Abbrechen
              </button>
              <button
                className="button primary"
                onClick={async () => {
                  const ok = await action(publish, "publish", {
                    scheduled_at: publishTime
                      ? new Date(publishTime).toISOString()
                      : null,
                    automation_authorized: automationAuthorized,
                  });
                  if (ok) setPublish(null);
                }}
              >
                Veröffentlichung autorisieren
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
