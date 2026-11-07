"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { request } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { ErrorNote, Heading } from "./ui";

/*
 * Content → Vorlagen. Images in the CleanStar look instead of AI images: colours, fonts
 * and logo from the cleanstar-rebrand repository (copied to /public/brand/cleanstar).
 * Each template is HTML; it is rendered through an SVG foreignObject into a canvas and
 * exported as PNG. The carousel becomes a PDF (one page per slide), the format LinkedIn
 * accepts for document posts. AI images exist only behind an explicit button elsewhere.
 */

export const BRAND = {
  ink: "#0b1220",
  night: "#0a1a33",
  blue: "#1a4fe0",
  sky: "#0086f6",
  cyan: "#00caf9",
  paper: "#f7f9fb",
  surface: "#edf1f5",
  muted: "#4a5566",
  domain: "cleanstar-dienstleistungen.de",
};
type Asset = { id: string; filename: string; alt_text: string; url: string; title?: string };
type Kind = "number" | "quote" | "carousel" | "device" | "beforeafter";
type Format = "portrait" | "square";
const SIZE: Record<Format, [number, number]> = { portrait: [1080, 1350], square: [1080, 1080] };
export const KINDS: { key: Kind; label: string; hint: string }[] = [
  { key: "number", label: "Zahlenkarte", hint: "Eine Zahl, die hängen bleibt." },
  { key: "quote", label: "Zitatkarte", hint: "Ein Satz von dir oder einem Kunden." },
  { key: "carousel", label: "Karussell", hint: "Mehrere Seiten als PDF für LinkedIn." },
  { key: "device", label: "Website im Gerät", hint: "Screenshot im Laptop- oder Handyrahmen." },
  { key: "beforeafter", label: "Vorher-Nachher", hint: "Zwei Fotos nebeneinander." },
];

export type Fields = {
  number: string;
  label: string;
  text: string;
  quote: string;
  author: string;
  role: string;
  slides: string;
  device: "laptop" | "phone";
  caption: string;
  before: string;
  after: string;
  dark: boolean;
};
export const DEFAULTS: Fields = {
  number: "12 %",
  label: "weniger Reinigungskosten",
  text: "Mit festen Teams und klaren Leistungsverzeichnissen statt Pauschalen.",
  quote: "Sauberkeit ist kein Zufall, sondern ein Plan, den jeder im Team kennt.",
  author: "Nico Schütterle",
  role: "CleanStar Dienstleistungen",
  slides: "Die neue CleanStar-Website\nWarum wir Preise offen zeigen\nSo funktioniert der Kostenrechner\nWas im Leistungsverzeichnis steht\nJetzt ansehen",
  device: "laptop",
  caption: "Die neue Website ist online",
  before: "Vorher",
  after: "Nachher",
  dark: false,
};

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

async function toDataUrl(url: string): Promise<string> {
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) throw new Error("Bild konnte nicht geladen werden.");
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Bild konnte nicht gelesen werden."));
    reader.readAsDataURL(blob);
  });
}

let brandCache: Promise<{ sans: string; serif: string; logo: string }> | null = null;
export function brandAssets() {
  brandCache ||= Promise.all([
    toDataUrl("/brand/cleanstar/instrument-sans-latin-wght.woff2"),
    toDataUrl("/brand/cleanstar/instrument-serif-subset.woff2"),
    toDataUrl("/brand/cleanstar/logo.svg"),
  ]).then(([sans, serif, logo]) => ({ sans, serif, logo }));
  return brandCache;
}

function baseCss(fonts: { sans: string; serif: string }, w: number, h: number, dark: boolean) {
  const bg = dark ? BRAND.night : BRAND.paper;
  const fg = dark ? "#ffffff" : BRAND.ink;
  const muted = dark ? "#a9b6cc" : BRAND.muted;
  return `
  @font-face { font-family: 'CS Sans'; src: url(${fonts.sans}) format('woff2'); font-weight: 400 700; }
  @font-face { font-family: 'CS Serif'; src: url(${fonts.serif}) format('woff2'); }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  .page { width: ${w}px; height: ${h}px; background: ${bg}; color: ${fg}; font-family: 'CS Sans', Arial, sans-serif;
    position: relative; overflow: hidden; display: flex; flex-direction: column; padding: 88px; }
  .muted { color: ${muted}; }
  .rule { width: 96px; height: 8px; background: ${BRAND.blue}; border-radius: 4px; }
  .foot { position: absolute; left: 88px; right: 88px; bottom: 72px; display: flex; align-items: center; justify-content: space-between;
    font-size: 26px; color: ${muted}; }
  .logo { height: 54px; ${dark ? "filter: brightness(0) invert(1);" : ""} }
  .eyebrow { font-size: 28px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: ${dark ? BRAND.cyan : BRAND.blue}; }
  `;
}

export function templateHtml(
  kind: Kind,
  f: Fields,
  format: Format,
  brand: { sans: string; serif: string; logo: string },
  images: { photo?: string; before?: string; after?: string },
  slide = 0,
): string {
  const [w, h] = SIZE[format];
  const css = baseCss(brand, w, h, f.dark);
  const foot = `<div class="foot"><img class="logo" src="${brand.logo}" alt=""/><span>${BRAND.domain}</span></div>`;
  let body = "";
  let extra = "";
  if (kind === "number") {
    extra = `.big { font-size: ${format === "portrait" ? 300 : 260}px; font-weight: 700; line-height: 0.95; letter-spacing: -0.04em; color: ${f.dark ? "#fff" : BRAND.blue}; margin-top: auto; }
      .label { font-size: 64px; font-weight: 600; line-height: 1.1; margin-top: 24px; max-width: 880px; }
      .text { font-size: 36px; line-height: 1.4; margin-top: 40px; max-width: 860px; margin-bottom: auto; }`;
    body = `<div class="rule"></div><div class="big">${esc(f.number)}</div><div class="label">${esc(f.label)}</div><div class="text muted">${esc(f.text)}</div>`;
  } else if (kind === "quote") {
    extra = `.mark { font-family: 'CS Serif', Georgia, serif; font-size: 260px; line-height: 0.7; color: ${BRAND.blue}; height: 150px; }
      .q { font-size: ${f.quote.length > 120 ? 54 : 66}px; font-weight: 600; line-height: 1.22; letter-spacing: -0.01em; margin-top: auto; margin-bottom: 56px; max-width: 900px; }
      .who { font-size: 34px; font-weight: 600; margin-bottom: auto; } .who small { display: block; font-size: 28px; font-weight: 400; margin-top: 6px; }`;
    body = `<div class="mark">“</div><div class="q">${esc(f.quote)}</div><div class="who">${esc(f.author)}<small class="muted">${esc(f.role)}</small></div>`;
  } else if (kind === "carousel") {
    const slides = f.slides.split("\n").map((s) => s.trim()).filter(Boolean);
    const total = Math.max(slides.length, 1);
    const i = Math.min(slide, total - 1);
    const first = i === 0;
    const last = i === total - 1 && total > 1;
    extra = `.n { font-size: 30px; font-weight: 600; color: ${BRAND.blue}; }
      .t { font-size: ${first ? 104 : 76}px; font-weight: 700; line-height: 1.05; letter-spacing: -0.03em; margin-top: auto; margin-bottom: auto; max-width: 900px; }
      .bar { position: absolute; left: 0; bottom: 0; height: 10px; background: ${BRAND.blue}; width: ${Math.round(((i + 1) / total) * 100)}%; }
      .next { font-size: 30px; font-weight: 600; }`;
    body = `<div class="n">${first ? "CleanStar" : `${i + 1} / ${total}`}</div><div class="t">${esc(slides[i] || "")}</div>
      ${last ? "" : `<div class="next muted">${first ? "Wischen →" : ""}</div>`}<div class="bar"></div>`;
  } else if (kind === "device") {
    const phone = f.device === "phone";
    extra = phone
      ? `.dev { margin: 40px auto 0; width: 470px; height: 940px; border-radius: 72px; background: ${BRAND.ink}; padding: 22px; box-shadow: 0 0 0 2px #2a3446; }
         .scr { width: 100%; height: 100%; border-radius: 52px; overflow: hidden; background: #fff; }
         .cap { font-size: 52px; font-weight: 700; line-height: 1.1; letter-spacing: -0.02em; text-align: center; }`
      : `.dev { margin: 72px auto 0; width: 920px; }
         .lid { background: ${BRAND.ink}; border-radius: 28px 28px 0 0; padding: 22px 22px 30px; }
         .scr { width: 100%; height: 520px; border-radius: 8px; overflow: hidden; background: #fff; }
         .base { height: 30px; background: #c3ccd8; border-radius: 0 0 22px 22px; margin: 0 -50px; }
         .cap { font-size: 64px; font-weight: 700; line-height: 1.08; letter-spacing: -0.02em; margin-top: 40px; max-width: 900px; }`;
    extra += `.scr img { width: 100%; height: 100%; object-fit: cover; object-position: top; display: block; }
      .ph { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 30px; color: ${BRAND.muted}; background: ${BRAND.surface}; }`;
    const shot = images.photo ? `<img src="${images.photo}" alt=""/>` : `<div class="ph">Screenshot wählen</div>`;
    body = phone
      ? `<div class="cap">${esc(f.caption)}</div><div class="dev"><div class="scr">${shot}</div></div>`
      : `<div class="eyebrow">Neu</div><div class="cap">${esc(f.caption)}</div><div class="dev"><div class="lid"><div class="scr">${shot}</div></div><div class="base"></div></div>`;
  } else {
    extra = `.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-top: 48px; flex: 1; margin-bottom: 120px; }
      .cell { position: relative; border-radius: 24px; overflow: hidden; background: ${BRAND.surface}; }
      .cell img { width: 100%; height: 100%; object-fit: cover; display: block; }
      .tag { position: absolute; left: 20px; top: 20px; background: ${BRAND.ink}; color: #fff; font-size: 28px; font-weight: 600; padding: 10px 20px; border-radius: 999px; }
      .cell.after .tag { background: ${BRAND.blue}; }
      .ph { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 28px; color: ${BRAND.muted}; }
      .cap { font-size: 60px; font-weight: 700; line-height: 1.08; letter-spacing: -0.02em; max-width: 900px; }`;
    const cell = (src: string | undefined, tag: string, cls: string) =>
      `<div class="cell ${cls}">${src ? `<img src="${src}" alt=""/>` : `<div class="ph">Foto wählen</div>`}<span class="tag">${esc(tag)}</span></div>`;
    body = `<div class="cap">${esc(f.caption)}</div><div class="pair">${cell(images.before, f.before, "before")}${cell(images.after, f.after, "after")}</div>`;
  }
  return `<div xmlns="http://www.w3.org/1999/xhtml"><style>${css}${extra}</style><div class="page">${body}${foot}</div></div>`;
}

export function slideCount(kind: Kind, f: Fields) {
  return kind === "carousel" ? Math.max(1, f.slides.split("\n").filter((s) => s.trim()).length) : 1;
}

/** Render HTML through an SVG foreignObject into a canvas. */
export async function renderCanvas(html: string, format: Format): Promise<HTMLCanvasElement> {
  const [w, h] = SIZE[format];
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}"><foreignObject width="100%" height="100%">${html}</foreignObject></svg>`;
  const img = new Image();
  img.width = w;
  img.height = h;
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  await img.decode();
  // Embedded fonts can need a moment inside an SVG image.
  await new Promise((r) => setTimeout(r, 120));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Zeichnen wird von diesem Browser nicht unterstützt.");
  ctx.drawImage(img, 0, 0, w, h);
  return canvas;
}

function canvasBlob(canvas: HTMLCanvasElement, type: string, quality?: number): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Export fehlgeschlagen."))), type, quality),
  );
}

/** Minimal PDF with one JPEG per page (DCTDecode). No external library. */
export async function pdfFromCanvases(canvases: HTMLCanvasElement[]): Promise<Blob> {
  const enc = new TextEncoder();
  const parts: (Uint8Array | string)[] = [];
  const offsets: number[] = [];
  let length = 0;
  const push = (chunk: Uint8Array | string) => {
    const bytes = typeof chunk === "string" ? enc.encode(chunk) : chunk;
    parts.push(bytes);
    length += bytes.length;
  };
  const obj = (n: number, body: (Uint8Array | string)[]) => {
    offsets[n] = length;
    push(`${n} 0 obj\n`);
    body.forEach(push);
    push("\nendobj\n");
  };
  push("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
  const pages = canvases.length;
  const kids = Array.from({ length: pages }, (_, i) => `${3 + i * 3} 0 R`).join(" ");
  obj(1, ["<< /Type /Catalog /Pages 2 0 R >>"]);
  obj(2, [`<< /Type /Pages /Kids [${kids}] /Count ${pages} >>`]);
  for (let i = 0; i < pages; i++) {
    const c = canvases[i];
    const jpeg = new Uint8Array(await (await canvasBlob(c, "image/jpeg", 0.92)).arrayBuffer());
    const page = 3 + i * 3;
    const w = c.width * 0.75;
    const h = c.height * 0.75;
    const content = `q ${w} 0 0 ${h} 0 0 cm /Im${i} Do Q`;
    obj(page, [
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${w} ${h}] /Resources << /XObject << /Im${i} ${page + 1} 0 R >> >> /Contents ${page + 2} 0 R >>`,
    ]);
    obj(page + 1, [
      `<< /Type /XObject /Subtype /Image /Width ${c.width} /Height ${c.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`,
      jpeg,
      "\nendstream",
    ]);
    obj(page + 2, [`<< /Length ${content.length} >>\nstream\n${content}\nendstream`]);
  }
  const xref = length;
  const count = 3 + pages * 3;
  let table = `xref\n0 ${count}\n0000000000 65535 f \n`;
  for (let n = 1; n < count; n++) table += `${String(offsets[n]).padStart(10, "0")} 00000 n \n`;
  push(table);
  push(`trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`);
  return new Blob(parts as BlobPart[], { type: "application/pdf" });
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function TemplatesPage({
  base,
  csrf,
  notify,
}: {
  base: string;
  csrf: string;
  notify: (m: string) => void;
}) {
  const [kind, setKind] = useState<Kind>("number");
  const [format, setFormat] = useState<Format>("portrait");
  const [fields, setFields] = useState<Fields>(DEFAULTS);
  const [slide, setSlide] = useState(0);
  const [brand, setBrand] = useState<{ sans: string; serif: string; logo: string } | null>(null);
  const [picked, setPicked] = useState<{ photo?: string; before?: string; after?: string }>({});
  const [images, setImages] = useState<{ photo?: string; before?: string; after?: string }>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const assets = useData<{ items: Asset[] }>(`${base}/assets?limit=100`, revision).data?.items || [];
  const upload = useRef<HTMLInputElement>(null);
  const [uploadSlot, setUploadSlot] = useState<"photo" | "before" | "after">("photo");

  useEffect(() => {
    brandAssets().then(setBrand).catch((e) => setError((e as Error).message));
  }, []);
  useEffect(() => {
    let active = true;
    (async () => {
      const out: typeof images = {};
      for (const slot of ["photo", "before", "after"] as const) {
        const id = picked[slot];
        const asset = assets.find((a) => a.id === id);
        if (asset) out[slot] = await toDataUrl(`/api${asset.url}`).catch(() => undefined);
      }
      if (active) setImages(out);
    })();
    return () => {
      active = false;
    };
    // assets identity changes on every load; ids are what matter
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picked.photo, picked.before, picked.after, assets.length]);

  const total = slideCount(kind, fields);
  const current = Math.min(slide, total - 1);
  const html = useMemo(
    () => (brand ? templateHtml(kind, fields, format, brand, images, current) : ""),
    [brand, kind, fields, format, images, current],
  );
  const [w, h] = SIZE[format];
  const set = <K extends keyof Fields>(key: K, value: Fields[K]) => setFields((f) => ({ ...f, [key]: value }));

  async function exportPng(save: boolean) {
    if (!brand) return;
    setBusy(save ? "save" : "png");
    setError("");
    try {
      const canvas = await renderCanvas(html, format);
      const blob = await canvasBlob(canvas, "image/png");
      const name = `cleanstar-${kind}-${new Date().toISOString().slice(0, 10)}.png`;
      if (!save) {
        download(blob, name);
        return;
      }
      const body = new FormData();
      body.append("file", new File([blob], name, { type: "image/png" }));
      body.append("alt_text", altText(kind, fields));
      body.append("rights_confirmed", "true");
      await request(`${base}/assets/upload`, { method: "POST", body }, csrf);
      setRevision((v) => v + 1);
      notify("In der Mediathek gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function exportPdf() {
    if (!brand) return;
    setBusy("pdf");
    setError("");
    try {
      const canvases = [];
      for (let i = 0; i < total; i++)
        canvases.push(await renderCanvas(templateHtml(kind, fields, format, brand, images, i), format));
      download(await pdfFromCanvases(canvases), `cleanstar-karussell-${new Date().toISOString().slice(0, 10)}.pdf`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function uploadPhoto(file: File) {
    setBusy("upload");
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("alt_text", file.name.replace(/\.[a-z]+$/i, "").slice(0, 200) || "Eigenes Foto");
      body.append("rights_confirmed", "true");
      const asset = await request<Asset>(`${base}/assets/upload`, { method: "POST", body }, csrf);
      setRevision((v) => v + 1);
      setPicked((p) => ({ ...p, [uploadSlot]: asset.id }));
      notify("Foto in der Mediathek gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  const photoPicker = (slot: "photo" | "before" | "after", label: string) => (
    <label>
      {label}
      <span className="copy-line">
        <select value={picked[slot] || ""} onChange={(e) => setPicked((p) => ({ ...p, [slot]: e.target.value || undefined }))}>
          <option value="">Aus der Mediathek wählen</option>
          {assets.map((a) => (
            <option key={a.id} value={a.id}>
              {a.title || a.alt_text || a.filename}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="button secondary small"
          disabled={!!busy}
          onClick={() => {
            setUploadSlot(slot);
            upload.current?.click();
          }}
        >
          Hochladen
        </button>
      </span>
    </label>
  );

  return (
    <>
      <Heading
        title="Vorlagen"
        description="Bilder in der CleanStar-Optik statt KI-Bildern. Text eintragen, eigenes Foto wählen, als PNG oder PDF speichern."
      >
        {kind === "carousel" ? (
          <button className="button primary" disabled={!brand || !!busy} onClick={exportPdf}>
            {busy === "pdf" ? "Erstelle PDF …" : "Als PDF speichern"}
          </button>
        ) : (
          <button className="button primary" disabled={!brand || !!busy} onClick={() => exportPng(false)}>
            {busy === "png" ? "Erstelle PNG …" : "Als PNG speichern"}
          </button>
        )}
      </Heading>
      <ErrorNote message={error} />
      <div className="section-tabs inline" role="tablist" aria-label="Vorlage">
        {KINDS.map((k) => (
          <button
            key={k.key}
            role="tab"
            aria-selected={kind === k.key}
            className={kind === k.key ? "active" : ""}
            onClick={() => {
              setKind(k.key);
              setSlide(0);
            }}
          >
            {k.label}
          </button>
        ))}
      </div>
      <div className="template-layout">
        <form className="template-form" onSubmit={(e) => e.preventDefault()}>
          <p className="muted">{KINDS.find((k) => k.key === kind)?.hint}</p>
          {kind === "number" && (
            <>
              <label>
                Zahl
                <input value={fields.number} onChange={(e) => set("number", e.target.value)} maxLength={12} />
              </label>
              <label>
                Bedeutung
                <input value={fields.label} onChange={(e) => set("label", e.target.value)} maxLength={60} />
              </label>
              <label>
                Erklärung
                <textarea rows={3} value={fields.text} onChange={(e) => set("text", e.target.value)} maxLength={160} />
              </label>
            </>
          )}
          {kind === "quote" && (
            <>
              <label>
                Zitat
                <textarea rows={4} value={fields.quote} onChange={(e) => set("quote", e.target.value)} maxLength={200} />
              </label>
              <label>
                Name
                <input value={fields.author} onChange={(e) => set("author", e.target.value)} maxLength={60} />
              </label>
              <label>
                Rolle oder Firma
                <input value={fields.role} onChange={(e) => set("role", e.target.value)} maxLength={60} />
              </label>
            </>
          )}
          {kind === "carousel" && (
            <label>
              Seiten (eine Zeile pro Seite)
              <textarea rows={8} value={fields.slides} onChange={(e) => set("slides", e.target.value)} maxLength={1200} />
            </label>
          )}
          {(kind === "device" || kind === "beforeafter") && (
            <label>
              Überschrift
              <input value={fields.caption} onChange={(e) => set("caption", e.target.value)} maxLength={80} />
            </label>
          )}
          {kind === "device" && (
            <>
              <label>
                Gerät
                <select value={fields.device} onChange={(e) => set("device", e.target.value as Fields["device"])}>
                  <option value="laptop">Laptop</option>
                  <option value="phone">Handy</option>
                </select>
              </label>
              {photoPicker("photo", "Screenshot")}
            </>
          )}
          {kind === "beforeafter" && (
            <>
              {photoPicker("before", "Foto vorher")}
              {photoPicker("after", "Foto nachher")}
              <label>
                Beschriftung links
                <input value={fields.before} onChange={(e) => set("before", e.target.value)} maxLength={20} />
              </label>
              <label>
                Beschriftung rechts
                <input value={fields.after} onChange={(e) => set("after", e.target.value)} maxLength={20} />
              </label>
            </>
          )}
          <label>
            Format
            <select value={format} onChange={(e) => setFormat(e.target.value as Format)}>
              <option value="portrait">Hochformat 4:5 (1080 × 1350)</option>
              <option value="square">Quadrat (1080 × 1080)</option>
            </select>
          </label>
          <label className="inline-toggle">
            <input type="checkbox" checked={fields.dark} onChange={(e) => set("dark", e.target.checked)} />
            Dunkler Hintergrund
          </label>
          {kind !== "carousel" && (
            <button type="button" className="button secondary" disabled={!brand || !!busy} onClick={() => exportPng(true)}>
              {busy === "save" ? "Speichere …" : "In Mediathek speichern"}
            </button>
          )}
          <input
            ref={upload}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) uploadPhoto(file);
              e.target.value = "";
            }}
          />
        </form>
        <div className="template-preview">
          <div
            className="template-frame"
            style={{ aspectRatio: `${w} / ${h}` }}
            data-testid="template-preview"
          >
            {html ? (
              // A data: URL preview of the exact export; next/image cannot optimise it.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                alt={`Vorschau ${KINDS.find((k) => k.key === kind)?.label}`}
                src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(
                  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"><foreignObject width="100%" height="100%">${html}</foreignObject></svg>`,
                )}`}
              />
            ) : (
              <span className="skeleton" style={{ width: "100%", height: "100%" }} />
            )}
          </div>
          {kind === "carousel" && (
            <div className="slide-nav">
              <button className="button ghost small" disabled={current === 0} onClick={() => setSlide(current - 1)}>
                Zurück
              </button>
              <span className="muted">
                Seite {current + 1} von {total}
              </span>
              <button className="button ghost small" disabled={current >= total - 1} onClick={() => setSlide(current + 1)}>
                Weiter
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function altText(kind: Kind, f: Fields) {
  if (kind === "number") return `${f.number} ${f.label}. ${f.text}`.slice(0, 900);
  if (kind === "quote") return `Zitat: ${f.quote} (${f.author})`.slice(0, 900);
  if (kind === "device") return `${f.caption}: Website im ${f.device === "phone" ? "Handy" : "Laptop"}`;
  if (kind === "beforeafter") return `${f.caption}: ${f.before} und ${f.after}`;
  return "CleanStar Karussell";
}
