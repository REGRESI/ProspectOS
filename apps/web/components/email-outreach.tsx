"use client";
import { FormEvent, useState } from "react";
import { Globe, Inbox, Mail, RefreshCw, ShieldCheck } from "lucide-react";
import { dateTime, request } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Spinner } from "./ui";
import type { Write } from "./growth-modules";

type MailboxItem = {
  id: string;
  email: string;
  display_name: string;
  domain: string;
  smtp: string;
  imap: string;
  status: string;
  paused_reason: string;
  last_error: string;
  last_tested_at: string | null;
  ramp: { start: string; start_limit: number; step: number; max: number };
  capacity_today: number;
  window: string;
  stats: { sent: number; bounced: number };
};
type DnsReport = { domain: string; ready: boolean; advice: string; checks: { name: string; ok: boolean; value: string; fix: string }[] };

const PRESETS: Record<string, { smtp_host: string; smtp_port: number; smtp_security: string; imap_host: string }> = {
  "Google Workspace (App-Passwort)": { smtp_host: "smtp.gmail.com", smtp_port: 465, smtp_security: "ssl", imap_host: "imap.gmail.com" },
  "Microsoft 365": { smtp_host: "smtp.office365.com", smtp_port: 587, smtp_security: "starttls", imap_host: "outlook.office365.com" },
  IONOS: { smtp_host: "smtp.ionos.de", smtp_port: 465, smtp_security: "ssl", imap_host: "imap.ionos.de" },
  Strato: { smtp_host: "smtp.strato.de", smtp_port: 465, smtp_security: "ssl", imap_host: "imap.strato.de" },
};

export function MailboxManager({ base, write }: { base: string; write: Write }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [open, setOpen] = useState(false);
  const [dns, setDns] = useState<Record<string, DnsReport>>({});
  const boxes = useData<{ items: MailboxItem[] }>(`${base}/mailboxes`, revision);
  const [form, setForm] = useState({
    email: "",
    display_name: "",
    password: "",
    smtp_host: "",
    smtp_port: 465,
    smtp_security: "ssl",
    imap_host: "",
    signature: "",
    sender_footer: "",
  });
  const set = (k: string, v: string | number) => setForm((f) => ({ ...f, [k]: v }));

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError("");
    try {
      await fn();
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    run("add", async () => {
      await write("/mailboxes", { ...form, test: true });
      setOpen(false);
      setForm((f) => ({ ...f, password: "" }));
    });
  }

  return (
    <section className="panel settings-panel" data-testid="mailboxes">
      <div className="panel-head">
        <h2>
          <Mail size={17} /> Versandpostfächer
        </h2>
        <button className="button secondary small" onClick={() => setOpen((v) => !v)}>
          Postfach hinzufügen
        </button>
      </div>
      <p className="muted">
        Kaltakquise nur aus echten Postfächern auf separaten Zweitdomains (keine Subdomains der Hauptdomain), nie über
        Resend. Beim Speichern werden SMTP-Anmeldung und IMAP-Posteingang geprüft; das Passwort wird verschlüsselt
        gespeichert und nie angezeigt.
      </p>
      <ErrorNote message={error || boxes.error} />
      {open && (
        <form className="mailbox-form" onSubmit={submit}>
          <label>
            Anbieter-Vorlage
            <select
              defaultValue=""
              onChange={(e) => {
                const p = PRESETS[e.target.value];
                if (p) setForm((f) => ({ ...f, ...p }));
              }}
            >
              <option value="">Eigene Einstellungen</option>
              {Object.keys(PRESETS).map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <label>
            E-Mail-Adresse
            <input required type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />
          </label>
          <label>
            Anzeigename
            <input value={form.display_name} onChange={(e) => set("display_name", e.target.value)} />
          </label>
          <label>
            App-Passwort
            <input required type="password" autoComplete="new-password" value={form.password} onChange={(e) => set("password", e.target.value)} />
          </label>
          <label>
            SMTP-Server
            <input required value={form.smtp_host} onChange={(e) => set("smtp_host", e.target.value)} />
          </label>
          <label>
            SMTP-Port
            <input type="number" value={form.smtp_port} onChange={(e) => set("smtp_port", Number(e.target.value))} />
          </label>
          <label>
            Verschlüsselung
            <select value={form.smtp_security} onChange={(e) => set("smtp_security", e.target.value)}>
              <option value="ssl">SSL/TLS (465)</option>
              <option value="starttls">STARTTLS (587)</option>
            </select>
          </label>
          <label>
            IMAP-Server (Port 993)
            <input required value={form.imap_host} onChange={(e) => set("imap_host", e.target.value)} />
          </label>
          <label className="wide">
            Signatur
            <textarea rows={3} value={form.signature} onChange={(e) => set("signature", e.target.value)} />
          </label>
          <label className="wide">
            Absenderangaben (Pflicht in jeder Mail: Firma, Anschrift, ggf. Register)
            <textarea required minLength={10} rows={2} value={form.sender_footer} onChange={(e) => set("sender_footer", e.target.value)} />
          </label>
          <p className="muted small wide">
            OAuth für Google Workspace und Microsoft 365 ist noch nicht verfügbar – bitte ein App-Passwort verwenden.
          </p>
          <div className="form-actions wide">
            <button className="button primary" disabled={!!busy}>
              {busy === "add" ? <Spinner /> : "Verbindung testen und speichern"}
            </button>
          </div>
        </form>
      )}
      {boxes.loading && !boxes.data ? (
        <Spinner />
      ) : boxes.data?.items.length ? (
        <ul className="mailbox-list">
          {boxes.data.items.map((b) => (
            <li key={b.id} className="mailbox">
              <header>
                <strong>{b.email}</strong>
                <Badge tone={b.status === "active" ? "green" : b.status === "error" ? "red" : "amber"}>
                  {b.status === "active" ? "aktiv" : b.status === "error" ? "Fehler" : "pausiert"}
                </Badge>
                <small className="muted">
                  heute noch {b.capacity_today} · Hochlauf {b.ramp.start_limit}+{b.ramp.step}/Tag bis {b.ramp.max} · {b.window}
                </small>
              </header>
              {b.paused_reason && <p className="credential-result error">{b.paused_reason}</p>}
              {b.last_error && <p className="credential-result error">Letzter Fehler: {b.last_error}</p>}
              <small className="muted">
                {b.smtp} · {b.imap} · gesendet {b.stats.sent}, Bounces {b.stats.bounced}
                {b.last_tested_at ? ` · geprüft ${dateTime(b.last_tested_at)}` : ""}
              </small>
              <div className="form-actions">
                <button className="button secondary small" disabled={!!busy} onClick={() => run("t" + b.id, () => write(`/mailboxes/${b.id}/test`))}>
                  <ShieldCheck size={14} /> Verbindung testen
                </button>
                <button
                  className="button secondary small"
                  disabled={!!busy}
                  onClick={() =>
                    run("d" + b.id, async () => {
                      const r = await request<DnsReport>(`${base}/mailboxes/${b.id}/dns`);
                      setDns((d) => ({ ...d, [b.id]: r }));
                    })
                  }
                >
                  <Globe size={14} /> DNS prüfen
                </button>
                <button className="button secondary small" disabled={!!busy} onClick={() => run("s" + b.id, () => write(`/mailboxes/${b.id}/sync`))}>
                  <Inbox size={14} /> Posteingang prüfen
                </button>
                <button
                  className="button ghost small"
                  disabled={!!busy}
                  onClick={() => run("p" + b.id, () => write(`/mailboxes/${b.id}`, { status: b.status === "active" ? "paused" : "active" }, "PATCH"))}
                >
                  {b.status === "active" ? "Pausieren" : "Aktivieren"}
                </button>
              </div>
              {dns[b.id] && (
                <table className="dns-table">
                  <tbody>
                    {dns[b.id].checks.map((c) => (
                      <tr key={c.name}>
                        <th>{c.name}</th>
                        <td>
                          <Badge tone={c.ok ? "green" : "red"}>{c.ok ? "ok" : "fehlt"}</Badge>
                        </td>
                        <td className="dns-value">{c.ok ? c.value : c.fix}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">Noch kein Postfach verbunden.</p>
      )}
    </section>
  );
}

type EmailView = {
  contacts: {
    contact_id: string;
    name: string;
    email: string | null;
    eligibility: { allowed: boolean; reasons: string[]; basis: { label: string; country: string } | null };
    drafts: { step: number; id: string; subject: string; content: string; state: string }[];
    messages: { step: number; state: string; scheduled_at: string; sent_at: string | null; error: string }[];
  }[];
  metrics: Record<string, number>;
  notice: string;
};

export function CampaignEmail({ base, write, campaignId }: { base: string; write: Write; campaignId: string }) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState("");
  const [step, setStep] = useState(0);
  const [subject, setSubject] = useState("Büroreinigung für {company}");
  const [basisFor, setBasisFor] = useState<string | null>(null);
  const view = useData<EmailView>(`${base}/campaigns/${campaignId}/email`, revision);
  const c = `/campaigns/${campaignId}/email`;

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setError("");
    setInfo("");
    try {
      const r = (await fn()) as Record<string, unknown>;
      if (r && "scheduled" in r) {
        const blocked = (r.blocked as unknown[]) || [];
        setInfo(`${r.scheduled} eingeplant · ${blocked.length} blockiert · ${r.waiting_for_capacity} warten auf Kapazität`);
      } else if (r && "approved" in r) setInfo(`${r.approved} freigegeben`);
      else if (r && "created" in r) setInfo(`${r.created} Entwürfe erstellt`);
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  const v = view.data;
  const allowed = v?.contacts.filter((x) => x.eligibility.allowed).length || 0;
  return (
    <section className="panel pad" data-testid="campaign-email">
      <div className="panel-head">
        <h2>
          <Mail size={17} /> E-Mail-Sequenz
        </h2>
        <button className="button ghost small" onClick={() => setRevision((x) => x + 1)} aria-label="Aktualisieren">
          <RefreshCw size={14} />
        </button>
      </div>
      <ErrorNote message={error || view.error} />
      {info && <p className="credential-result connected" role="status">{info}</p>}
      {v && (
        <div className="email-metrics">
          {Object.entries(v.metrics).map(([k, n]) => (
            <Badge key={k}>
              {k}: {n}
            </Badge>
          ))}
          <small className="muted">
            {allowed}/{v.contacts.length} Kontakte mit zulässiger Rechtsgrundlage
          </small>
        </div>
      )}
      <div className="form-actions email-step">
        <label>
          Schritt
          <input type="number" min={0} max={20} value={step} onChange={(e) => setStep(Number(e.target.value))} />
        </label>
        <label className="grow">
          Betreff (Platzhalter: {"{name} {company} {city}"})
          <input value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <button className="button secondary small" disabled={!!busy} onClick={() => run("dr", () => write(`${c}/drafts`, { step_position: step, subject }))}>
          Entwürfe erstellen
        </button>
        <button className="button secondary small" disabled={!!busy} onClick={() => run("ap", () => write(`${c}/approve`, { all_for_step: step }))}>
          Alle Entwürfe von Schritt {step} freigeben
        </button>
        <button className="button primary small" disabled={!!busy} onClick={() => run("sc", () => write(`${c}/schedule`, { step_position: step }))}>
          Versand einplanen
        </button>
      </div>
      {view.loading && !v ? (
        <Spinner />
      ) : (
        <ul className="email-contacts">
          {v?.contacts.map((x) => (
            <li key={x.contact_id}>
              <div>
                <strong>{x.name}</strong> <span className="muted">{x.email || "keine E-Mail"}</span>{" "}
                {x.eligibility.allowed ? (
                  <Badge tone="green">{x.eligibility.basis?.label}</Badge>
                ) : (
                  <Badge tone="red">Versand blockiert</Badge>
                )}
              </div>
              {!x.eligibility.allowed && (
                <small className="candidate-missing">
                  {x.eligibility.reasons.join(" ")}{" "}
                  <button className="link-button" onClick={() => setBasisFor(x.contact_id)}>
                    Rechtsgrundlage dokumentieren
                  </button>
                </small>
              )}
              {basisFor === x.contact_id && (
                <LegalBasisForm
                  contactId={x.contact_id}
                  write={write}
                  onDone={() => {
                    setBasisFor(null);
                    setRevision((r) => r + 1);
                  }}
                />
              )}
              {x.drafts.map((d) => (
                <details key={d.id}>
                  <summary>
                    Schritt {d.step}: {d.subject} · <em>{d.state}</em>
                  </summary>
                  <pre className="today-preview">{d.content}</pre>
                </details>
              ))}
              {x.messages.map((m, i) => (
                <small key={i} className="muted">
                  Schritt {m.step}: {m.state}
                  {m.sent_at ? ` · gesendet ${dateTime(m.sent_at)}` : ` · geplant ${dateTime(m.scheduled_at)}`}
                  {m.error ? ` · ${m.error}` : ""}
                </small>
              ))}
            </li>
          ))}
        </ul>
      )}
      {v && <p className="muted small">{v.notice}</p>}
    </section>
  );
}

function LegalBasisForm({ contactId, write, onDone }: { contactId: string; write: Write; onDone: () => void }) {
  const [basis, setBasis] = useState("consent");
  const [evidence, setEvidence] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  return (
    <form
      className="legal-basis-form"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await write("/legal-bases", { contact_id: contactId, basis, evidence, evidence_url: url || null, country: "DE" });
          onDone();
        } catch (err) {
          setError((err as Error).message);
        }
      }}
    >
      <ErrorNote message={error} />
      <label>
        Rechtsgrundlage
        <select value={basis} onChange={(e) => setBasis(e.target.value)}>
          <option value="consent">Einwilligung</option>
          <option value="existing_customer_7_3">Bestandskunde (§7 Abs. 3 UWG)</option>
          <option value="recipient_request">Anfrage des Empfängers</option>
          <option value="other">Sonstige (in DE nicht ausreichend)</option>
        </select>
      </label>
      <label>
        Nachweis (wann, wie, wodurch)
        <input required minLength={10} value={evidence} onChange={(e) => setEvidence(e.target.value)} />
      </label>
      <label>
        Nachweis-URL (optional, https)
        <input value={url} onChange={(e) => setUrl(e.target.value)} />
      </label>
      <button className="button secondary small">Speichern</button>
    </form>
  );
}
