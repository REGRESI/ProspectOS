"use client";
import { FormEvent, useState } from "react";
import { AlertTriangle, ExternalLink, Plug, PlugZap, Power } from "lucide-react";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Modal, Spinner } from "./ui";
import type { Write } from "./growth-modules";

/** M9: external outreach tools at the user's own risk. ProspectOS itself never automates
 * LinkedIn; it only talks to the official APIs of tools where the user has an account. */

export type Tool = {
  id: string;
  label: string;
  docs: string;
  price_hint: string;
  can: string[];
  cannot: string[];
  secret_fields: string[];
  config_fields: string[];
  configured: boolean;
  secrets_masked: Record<string, string>;
  config: Record<string, string>;
  active: boolean;
  last_test_ok: boolean | null;
  last_error: string;
  webhook_ready: boolean;
  webhook_events: string[];
};
export type Overview =
  | { available: false; notice: string }
  | {
      available: true;
      enabled: boolean;
      acknowledgment: string;
      acknowledged: { name: string; at: string; text: string } | null;
      tools: Tool[];
      handoffs: Record<string, number>;
      is_owner: boolean;
    };

const fieldLabels: Record<string, string> = {
  api_key: "API-Schlüssel",
  api_secret: "API-Secret",
  signing_secret: "Signatur-Geheimnis",
  linkedin_account_id: "LinkedIn-Konto-ID im Tool",
  prospect_list_id: "Prospect-Liste",
  outgoing_url: "Ziel-URL (https)",
};

function testBadge(tool: Tool) {
  if (!tool.configured) return <Badge>nicht verbunden</Badge>;
  if (!tool.active) return <Badge>ausgeschaltet</Badge>;
  if (tool.last_test_ok === true) return <Badge tone="green">verbunden</Badge>;
  if (tool.last_test_ok === false) return <Badge tone="red">Fehler: {tool.last_error}</Badge>;
  return <Badge tone="amber">nicht getestet</Badge>;
}

export function ConnectorsPage({
  base,
  write,
  notify,
}: {
  base: string;
  write: Write;
  notify: (m: string) => void;
}) {
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [editing, setEditing] = useState<Tool | null>(null);
  const [webhook, setWebhook] = useState<{ tool: string; url: string } | null>(null);
  const data = useData<Overview>(`${base}/connectors`, revision);

  async function run<T>(fn: () => Promise<T>, message: string) {
    setBusy(true);
    setError("");
    try {
      const result = await fn();
      setRevision((v) => v + 1);
      notify(message);
      return result;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  function showHook(tool: string, path?: string) {
    if (path) setWebhook({ tool, url: `${origin}/api${path}` });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const form = new FormData(event.currentTarget);
    const pick = (fields: string[]) =>
      Object.fromEntries(fields.map((f) => [f, String(form.get(f) || "")]));
    const body = {
      secrets: pick(editing.secret_fields),
      config: pick(editing.config_fields),
      active: form.get("active") === "on",
    };
    const result = await run(
      () => write<{ webhook_path?: string }>(`/connectors/${editing.id}`, body, "PUT"),
      `${editing.label} gespeichert.`,
    );
    if (result) {
      showHook(editing.label, result.webhook_path);
      setEditing(null);
    }
  }

  const view = data.data;
  return (
    <>
      <Heading
        title="Anschlüsse"
        description="Externe Outreach-Tools, bei denen du selbst ein Konto hast. ProspectOS übergibt nur Kontakte und liest Ereignisse zurück."
      />
      <ErrorNote message={error || data.error} />
      {!view ? (
        <div className="loading-block">
          <Spinner />
        </div>
      ) : !view.available ? (
        <Empty icon={Plug} title="Nicht freigeschaltet" description={view.notice} />
      ) : (
        <>
          <section
            className={`panel connector-switch ${view.enabled ? "on" : ""}`}
            data-testid="connector-switch"
          >
            <div className="connector-switch-icon">
              <AlertTriangle size={20} />
            </div>
            <div className="connector-switch-text">
              <h2>Externe Outreach-Tools {view.enabled ? "sind eingeschaltet" : "sind aus"}</h2>
              <p>
                Diese Tools senden Einladungen und Nachrichten über dein LinkedIn-Konto. ProspectOS
                selbst automatisiert LinkedIn nie.
              </p>
              {view.acknowledged && (
                <p className="muted small-print" data-testid="connector-ack">
                  Bestätigt von {view.acknowledged.name} am{" "}
                  {new Date(view.acknowledged.at).toLocaleString("de-DE")}.
                </p>
              )}
            </div>
            {view.is_owner ? (
              view.enabled ? (
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() =>
                    void run(() => write("/connectors/disable", {}), "Externe Tools ausgeschaltet.")
                  }
                >
                  <Power size={16} /> Ausschalten
                </button>
              ) : (
                <button className="button primary" onClick={() => setConfirming(true)}>
                  <PlugZap size={16} /> Einschalten …
                </button>
              )
            ) : (
              <Badge>Nur der Owner kann das ändern</Badge>
            )}
          </section>

          <div className="connector-grid" data-testid="connector-tools">
            {view.tools.map((tool) => (
              <article className="panel connector-card" key={tool.id} data-testid={`tool-${tool.id}`}>
                <header className="connector-head">
                  <h3>{tool.label}</h3>
                  {testBadge(tool)}
                </header>
                <p className="connector-price">{tool.price_hint}</p>
                <div className="connector-lists">
                  <div>
                    <h4>Kann</h4>
                    <ul>
                      {tool.can.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h4>Kann nicht</h4>
                    <ul className="cannot">
                      {tool.cannot.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  </div>
                </div>
                <footer className="connector-actions">
                  <a className="link-button" href={tool.docs} target="_blank" rel="noreferrer noopener">
                    Doku <ExternalLink size={13} />
                  </a>
                  {view.enabled && view.is_owner && (
                    <>
                      <button className="button secondary small" onClick={() => setEditing(tool)}>
                        {tool.configured ? "Bearbeiten" : "Verbinden"}
                      </button>
                      {tool.configured && (
                        <>
                          <button
                            className="button secondary small"
                            disabled={busy}
                            onClick={() =>
                              void run(
                                () => write(`/connectors/${tool.id}/test`, {}),
                                `Verbindung zu ${tool.label} getestet.`,
                              )
                            }
                          >
                            Testen
                          </button>
                          <button
                            className="link-button"
                            disabled={busy}
                            onClick={async () => {
                              const r = await run(
                                () =>
                                  write<{ webhook_path: string }>(
                                    `/connectors/${tool.id}/rotate-webhook`,
                                    {},
                                  ),
                                "Neue Webhook-Adresse erzeugt.",
                              );
                              if (r) showHook(tool.label, r.webhook_path);
                            }}
                          >
                            Neue Webhook-Adresse
                          </button>
                        </>
                      )}
                    </>
                  )}
                </footer>
              </article>
            ))}
          </div>
          <p className="muted small-print">
            Übergaben bisher:{" "}
            {Object.entries(view.handoffs).length
              ? Object.entries(view.handoffs)
                  .map(([state, n]) => `${state}: ${n}`)
                  .join(", ")
              : "keine"}
            . Preisangaben sind ungeprüfte Richtwerte; maßgeblich ist die Preisseite des Anbieters.
          </p>

          {confirming && (
            <Modal title="Externe Tools auf eigene Gefahr" onClose={() => setConfirming(false)}>
              <div className="connector-risk" data-testid="connector-risk">
                <p className="connector-risk-text">{view.acknowledgment}</p>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={accepted}
                    onChange={(e) => setAccepted(e.target.checked)}
                  />{" "}
                  Ich habe das gelesen und nutze die Tools auf eigene Gefahr.
                </label>
                <p className="muted small-print">
                  Dein Name, die Uhrzeit und dieser Text werden im Verlauf gespeichert. Du kannst die
                  Tools jederzeit wieder ausschalten.
                </p>
                <div className="modal-actions">
                  <button className="button secondary" onClick={() => setConfirming(false)}>
                    Abbrechen
                  </button>
                  <button
                    className="button primary"
                    disabled={!accepted || busy}
                    onClick={async () => {
                      const ok = await run(
                        () =>
                          write("/connectors/enable", {
                            accepted: true,
                            confirmation_text: view.acknowledgment,
                          }),
                        "Externe Tools eingeschaltet.",
                      );
                      if (ok) {
                        setConfirming(false);
                        setAccepted(false);
                      }
                    }}
                  >
                    Bestätigen und einschalten
                  </button>
                </div>
              </div>
            </Modal>
          )}

          {editing && (
            <Modal title={`${editing.label} verbinden`} onClose={() => setEditing(null)}>
              <form className="connector-form" onSubmit={save} data-testid="connector-form">
                {editing.secret_fields.map((f) => (
                  <label key={f}>
                    {fieldLabels[f] || f}
                    <input
                      name={f}
                      type="password"
                      autoComplete="off"
                      placeholder={editing.secrets_masked[f] || "einfügen"}
                    />
                  </label>
                ))}
                {editing.config_fields.map((f) => (
                  <label key={f}>
                    {fieldLabels[f] || f}
                    <input name={f} defaultValue={editing.config[f] || ""} />
                  </label>
                ))}
                <label className="check-row">
                  <input name="active" type="checkbox" defaultChecked={editing.active || !editing.configured} />{" "}
                  Aktiv (neue Übergaben erlaubt)
                </label>
                <p className="muted small-print">
                  Schlüssel werden verschlüsselt gespeichert und nie wieder angezeigt. Leere Felder
                  behalten den gespeicherten Wert.
                </p>
                <div className="modal-actions">
                  <button type="button" className="button secondary" onClick={() => setEditing(null)}>
                    Abbrechen
                  </button>
                  <button className="button primary" disabled={busy}>
                    Speichern
                  </button>
                </div>
              </form>
            </Modal>
          )}

          {webhook && (
            <Modal title={`Webhook für ${webhook.tool}`} onClose={() => setWebhook(null)}>
              <div className="connector-risk">
                <p>
                  Trage diese Adresse im Tool als Webhook ein. Sie wird nur jetzt angezeigt.
                </p>
                <code className="connector-hook" data-testid="webhook-url">
                  {webhook.url}
                </code>
                <div className="modal-actions">
                  <button
                    className="button secondary"
                    onClick={() => void navigator.clipboard?.writeText(webhook.url)}
                  >
                    Kopieren
                  </button>
                  <button className="button primary" onClick={() => setWebhook(null)}>
                    Fertig
                  </button>
                </div>
              </div>
            </Modal>
          )}
        </>
      )}
    </>
  );
}
