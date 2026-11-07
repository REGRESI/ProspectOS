"use client";
import { FormEvent, useEffect, useState } from "react";
import { Sparkles, Search, ShieldCheck } from "lucide-react";
import { request } from "@/lib/api";
import { Badge, ErrorNote, Heading, Spinner } from "./ui";
import type { ModuleProps } from "./growth-modules";

type Job = { id: string; status: string; last_error: string | null; result: { text?: string; citations?: string[]; unverified_claims?: string[]; run_id?: string; results?: { company: string; location: string; source: string; license: string }[]; notice?: string } };

export function IntelligenceConsole({ base, write, notify, onChange }: ModuleProps) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState("synthetic");
  useEffect(() => {
    if (!job?.id) return;
    let active = true;
    let polls = 0;
    const id = job.id;
    const timer = window.setInterval(async () => {
      try {
        const result = await request<Job>(`${base}/jobs/${id}`);
        if (active) setJob(result);
        if (!["queued", "retry", "running"].includes(result.status) || ++polls >= 90) window.clearInterval(timer);
      } catch (e) {
        if (active) setError((e as Error).message);
        window.clearInterval(timer);
      }
    }, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [base, job?.id]);
  async function submit(event: FormEvent<HTMLFormElement>, kind: "ai" | "search") {
    event.preventDefault(); setBusy(true); setError(""); setJob(null);
    const data = new FormData(event.currentTarget);
    try {
      const payload = kind === "ai" ? { purpose: data.get("purpose"), prompt: data.get("prompt") } : { provider, query: data.get("query"), city: data.get("city"), country: data.get("country"), industry: data.get("industry"), limit: Number(data.get("limit")), license_confirmed: data.get("license") === "on" };
      const result = await write<Job>(kind === "ai" ? "/ai/generate" : "/discovery/search", payload);
      setJob(result); notify("Auftrag gespeichert. Der Worker übernimmt die Verarbeitung.");
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <>
    <Heading title="Recherche" description="Websites lesen und Texte mit KI vorbereiten, mit Quellenangabe." />
    <div className="info-note"><ShieldCheck size={20}/><p>Generierte Texte sind Vorschläge. Quellenangaben belegen die Eingabe, keine automatische Faktenprüfung. Kein Auftrag versendet Nachrichten oder Beiträge.</p></div>
    <ErrorNote message={error}/>
    <div className="integration-grid">
      <form className="panel composer" onSubmit={(e) => submit(e,"search")}>
        <h2><Search size={18}/> Unternehmenssuche</h2>
        <label>Briefing<textarea name="query" defaultValue="Büros und Dienstleister in Offenburg" required maxLength={300}/></label>
        <label>Datenquelle<select value={provider} onChange={(e)=>setProvider(e.target.value)}><option value="synthetic">Synthetische Entwicklungsbeispiele</option><option value="pdl">People Data Labs · Lizenz erforderlich</option></select></label>
        <label>Stadt<input name="city" defaultValue="Offenburg" maxLength={100}/></label>
        <label>Land<input name="country" defaultValue="germany" required maxLength={100}/></label>
        <label>Branche<input name="industry" maxLength={120}/></label>
        <label>Maximale Ergebnisse<input name="limit" type="number" defaultValue={5} min={1} max={25} required/></label>
        <p className="small muted">Der Freitext wird als Briefing gespeichert. Strukturierte Filter steuern die lizenzierte Suche. Entwicklungsbeispiele sind feste fiktive Daten und keine recherchierten Treffer.</p>
        {provider==="pdl"&&<label className="checkbox-line"><input type="checkbox" name="license" required/> Erlaubten Nutzungszweck und Anbieter-Lizenz geprüft.</label>}
        <button className="button primary" disabled={busy||!!job&&["queued","running","retry"].includes(job.status)}>Suchauftrag anlegen</button>
      </form>
      <form className="panel composer" onSubmit={(e)=>submit(e,"ai")}>
        <h2><Sparkles size={18}/> Textvorschlag erstellen</h2>
        <label>Zweck<select name="purpose"><option value="caption">Beitrag</option><option value="research">Recherche-Zusammenfassung</option><option value="qualification">Qualifizierung</option><option value="outreach">Gesprächsentwurf</option><option value="reply">Antwortvorschlag · manuelle Prüfung</option></select></label>
        <label>Aufgabe<textarea name="prompt" rows={8} required minLength={3} maxLength={4000} placeholder="Beschreibe die Aufgabe und kennzeichne fehlende Fakten ausdrücklich."/></label>
        <p className="small muted">Benötigt LLM-Anbieter, Modell und konfigurierte Tokenpreise. Kosten werden vorab gegen das Workspace-Budget reserviert. Ohne Zugang erscheint ein konkreter Fehler; es gibt keine simulierte KI-Antwort.</p>
        <button className="button primary" disabled={busy||!!job&&["queued","running","retry"].includes(job.status)}>KI-Auftrag anlegen</button>
      </form>
    </div>
    {job&&<section className="panel integration-doc"><div className="section-title"><h2>Auftrag</h2><Badge>{job.status}</Badge></div>{["queued","running","retry"].includes(job.status)&&<p><Spinner/> Verarbeitung läuft. Ein gestarteter Worker ist erforderlich.</p>}<ErrorNote message={job.last_error||""}/>{job.result.text&&<><p style={{whiteSpace:"pre-wrap"}}>{job.result.text}</p><p className="small muted">Nicht verifizierter Vorschlag · Quellen: {job.result.citations?.join(", ")||"keine"}</p>{job.result.unverified_claims?.map((s,i)=><p className="small muted" key={i}>{s}</p>)}</>}{job.result.notice&&<p>{job.result.notice}</p>}{job.result.results?.map((r,i)=><article key={i}><h3>{r.company}</h3><p>{r.location} · {r.source}</p><small>{r.license}</small></article>)}{job.result.run_id&&<button className="button secondary" onClick={async()=>{try{const result=await write<{created:number}>(`/discovery/runs/${job.result.run_id}/import`);notify(`${result.created} Datensätze übernommen.`);onChange();}catch(e){setError((e as Error).message)}}}>Ergebnisse mit Herkunft übernehmen</button>}</section>}
  </>;
}
