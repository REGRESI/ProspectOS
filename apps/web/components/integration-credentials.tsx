"use client";
import { FormEvent, useState } from "react";
import { KeyRound, PlugZap, Trash2 } from "lucide-react";
import { dateTime } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Spinner } from "./ui";
import type { Write } from "./growth-modules";

type CredentialField = {
  name: string;
  label: string;
  secret: boolean;
  required: boolean;
  hint: string;
  source: "workspace" | "environment" | "missing";
  masked: string;
};

export type CredentialItem = {
  provider: string;
  label: string;
  purpose: string;
  fields: CredentialField[];
  status: "connected" | "missing" | "error" | "untested";
  missing: string[];
  last_tested_at: string | null;
  last_error: string;
  last_message: string;
  redirect_uri?: string;
  account?: {
    connected: boolean;
    author_urn?: string;
    scopes?: string[];
    can_post?: boolean;
  };
};

const statusLabel: Record<CredentialItem["status"], [string, string]> = {
  connected: ["Gekoppelt", "green"],
  missing: ["Fehlt", "neutral"],
  error: ["Fehler", "red"],
  untested: ["Nicht geprüft", "amber"],
};

const sourceLabel: Record<CredentialField["source"], string> = {
  workspace: "im Workspace gespeichert",
  environment: "aus Umgebungsvariable",
  missing: "nicht hinterlegt",
};

export function IntegrationCredentials({
  base,
  write,
}: {
  base: string;
  write: Write;
}) {
  const [revision, setRevision] = useState(0);
  const [oauthNote] = useState(() => {
    if (typeof window === "undefined") return "";
    const q = new URLSearchParams(window.location.search);
    if (q.get("linkedin_connected")) return "LinkedIn-Konto verbunden.";
    const err = q.get("linkedin_error");
    if (!err) return "";
    return err.startsWith("user_cancelled")
      ? "LinkedIn-Verbindung abgebrochen."
      : `LinkedIn hat die Verbindung abgelehnt (${err}).`;
  });
  const { data, error, loading } = useData<{
    encryption_ready: boolean;
    items: CredentialItem[];
  }>(`${base}/integrations/credentials`, revision);
  if (loading && !data) return <Spinner />;
  return (
    <section className="panel settings-panel" data-testid="credentials">
      <h2>Zugangsdaten</h2>
      <p className="muted">
        Werte werden verschlüsselt pro Workspace gespeichert und nur maskiert
        angezeigt. Ohne Eintrag gilt die Umgebungsvariable des Servers.
      </p>
      {oauthNote && (
        <p className="credential-result" role="status">
          {oauthNote}
        </p>
      )}
      <ErrorNote message={error} />
      {data && !data.encryption_ready && (
        <ErrorNote message="TOKEN_ENCRYPTION_KEY fehlt auf dem Server – Speichern ist gesperrt." />
      )}
      <div className="credential-list">
        {data?.items.map((item) => (
          <CredentialCard
            key={item.provider}
            item={item}
            write={write}
            onChange={() => setRevision((v) => v + 1)}
          />
        ))}
      </div>
    </section>
  );
}

function CredentialCard({
  item,
  write,
  onChange,
}: {
  item: CredentialItem;
  write: Write;
  onChange: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [label, tone] = statusLabel[item.status];
  const path = `/integrations/credentials/${item.provider}`;

  async function run(kind: string, action: () => Promise<unknown>) {
    setBusy(kind);
    setError("");
    try {
      const result = (await action()) as {
        test?: { message: string } | null;
      } | null;
      setMessage(result?.test?.message || "");
      setValues({});
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  function save(event: FormEvent) {
    event.preventDefault();
    const filled = Object.fromEntries(
      Object.entries(values).filter(([, v]) => v.trim()),
    );
    run("save", () => write(path, { values: filled, test: true }, "PUT"));
  }

  return (
    <article
      className="credential-card"
      data-testid={`credential-${item.provider}`}
    >
      <header className="section-title">
        <h3>
          <KeyRound size={16} /> {item.label}
        </h3>
        <Badge tone={tone}>{label}</Badge>
      </header>
      <p className="muted">{item.purpose}</p>
      <form onSubmit={save} className="credential-form">
        {item.fields.map((field) => (
          <label key={field.name}>
            <span>
              {field.label}
              {field.required ? "" : " (optional)"}
            </span>
            <input
              name={field.name}
              type={field.secret ? "password" : "text"}
              autoComplete="off"
              placeholder={
                field.masked ? `${field.masked} · ${sourceLabel[field.source]}` : field.hint || sourceLabel[field.source]
              }
              value={values[field.name] || ""}
              onChange={(e) =>
                setValues((v) => ({ ...v, [field.name]: e.target.value }))
              }
            />
            <small>
              {field.name} · {sourceLabel[field.source]}
            </small>
          </label>
        ))}
        {item.account && (
          <p className="muted small" data-testid="linkedin-account">
            {item.account.connected
              ? `Konto verbunden (${item.account.author_urn}). Posten ${item.account.can_post ? "erlaubt (w_member_social)" : "nicht gewährt"}.`
              : "Noch kein LinkedIn-Konto verbunden. Nach dem Speichern oben „Offiziell mit LinkedIn verbinden“ nutzen."}
          </p>
        )}
        {item.redirect_uri !== undefined && (
          <p className="muted small">
            Redirect-URL in der LinkedIn-App eintragen:{" "}
            <code>{item.redirect_uri || "LINKEDIN_REDIRECT_URI fehlt"}</code>
          </p>
        )}
        <ErrorNote message={error} />
        {(message || item.last_message) && (
          <p className={`credential-result ${item.status}`} role="status">
            {message || item.last_message}
            {item.last_tested_at && (
              <small> · geprüft {dateTime(item.last_tested_at)}</small>
            )}
          </p>
        )}
        <div className="form-actions">
          <button
            className="button primary small"
            type="submit"
            disabled={!!busy || !Object.values(values).some((v) => v.trim())}
          >
            {busy === "save" ? <Spinner /> : "Speichern und testen"}
          </button>
          <button
            className="button secondary small"
            type="button"
            disabled={!!busy || item.status === "missing"}
            onClick={() => run("test", () => write(`${path}/test`))}
          >
            {busy === "test" ? <Spinner /> : (
              <>
                <PlugZap size={14} /> Verbindung testen
              </>
            )}
          </button>
          {item.fields.some((f) => f.source === "workspace") && (
            <button
              className="button ghost small"
              type="button"
              disabled={!!busy}
              onClick={() => run("delete", () => write(path, undefined, "DELETE"))}
            >
              <Trash2 size={14} /> Entfernen
            </button>
          )}
        </div>
      </form>
    </article>
  );
}
