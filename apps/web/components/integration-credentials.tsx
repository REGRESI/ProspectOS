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

const LINKEDIN_ERRORS: Record<string, string> = {
  user_cancelled_login: "Anmeldung bei LinkedIn abgebrochen. Nichts wurde gespeichert.",
  user_cancelled_authorize: "Freigabe bei LinkedIn abgelehnt. Nichts wurde gespeichert.",
  missing_code: "LinkedIn hat keinen Freigabecode zurückgegeben. Bitte erneut verbinden.",
  invalid_callback: "Ungültige Rückmeldung von LinkedIn. Bitte erneut verbinden.",
  not_signed_in: "Du warst bei der Rückkehr von LinkedIn nicht angemeldet. Bitte anmelden und erneut verbinden.",
  invalid_state: "Der Verbindungsversuch ist abgelaufen oder wurde schon verwendet (10 Minuten gültig). Bitte erneut verbinden.",
  permission_revoked: "Nur Owner/Admin dürfen LinkedIn verbinden.",
  encryption_key_missing: "TOKEN_ENCRYPTION_KEY fehlt auf dem Server – Verbindung nicht gespeichert.",
  token_provider_forbidden: "LinkedIn hat Client ID/Secret beim Token-Tausch abgelehnt. Zugangsdaten prüfen.",
  token_provider_rejected: "LinkedIn hat den Freigabecode abgelehnt (abgelaufen oder Redirect-URL weicht ab). Bitte erneut verbinden.",
  token_missing_credentials: "LinkedIn Client ID, Secret oder Redirect-URL fehlen.",
  token_provider_unavailable: "LinkedIn war nicht erreichbar. Bitte später erneut verbinden.",
};

function HostHint({ redirect }: { redirect: string }) {
  const [here] = useState(() =>
    typeof window === "undefined" ? "" : window.location.host,
  );
  let target = "";
  try {
    target = new URL(redirect).host;
  } catch {
    return null;
  }
  if (!here || here === target) return null;
  return (
    <p className="credential-result error small" role="note">
      Diese Seite ist unter {here} geöffnet, LinkedIn kehrt aber zu {target} zurück. Bitte
      ProspectOS über http://{target} öffnen, sonst fehlt nach der Rückkehr die Anmeldung.
    </p>
  );
}

function linkedinErrorText(code: string): string {
  return LINKEDIN_ERRORS[code] || `LinkedIn-Verbindung fehlgeschlagen (${code}).`;
}

export function IntegrationCredentials({
  base,
  write,
}: {
  base: string;
  write: Write;
}) {
  const [revision, setRevision] = useState(0);
  const [oauthNote] = useState<{ ok: boolean; text: string } | null>(() => {
    if (typeof window === "undefined") return null;
    const q = new URLSearchParams(window.location.search);
    if (q.get("linkedin_connected")) return { ok: true, text: "LinkedIn verbunden." };
    const err = q.get("linkedin_error");
    return err ? { ok: false, text: linkedinErrorText(err) } : null;
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
        <p
          className={`credential-result ${oauthNote.ok ? "connected" : "error"}`}
          role="status"
          data-testid="linkedin-oauth-result"
        >
          {oauthNote.text}
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
        {item.redirect_uri && <HostHint redirect={item.redirect_uri} />}
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
