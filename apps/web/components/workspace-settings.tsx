"use client";
import { FormEvent, useState } from "react";
import { ArrowRight, CheckCircle2, Copy, ShieldCheck } from "lucide-react";
import { useData } from "@/lib/use-data";
import { dateTime } from "@/lib/api";
import { Badge, ErrorNote, Heading, Spinner } from "./ui";
import type { ModuleProps } from "./growth-modules";

type Setup = {
  business: string;
  region: string;
  target_customers: string;
  completed_steps: string[];
};
export function WorkspaceOnboarding({
  base,
  write,
  notify,
  revision,
  onChange,
  onNavigate,
  onImport,
  role,
}: {
  onNavigate: (p: string) => void;
  onImport: () => void;
  role: string;
} & ModuleProps) {
  const { data, error, loading } = useData<Setup>(
    `${base}/onboarding`,
    revision,
  );
  const [localError, setLocalError] = useState("");
  const [busy, setBusy] = useState(false);
  const editable = ["owner", "admin"].includes(role);
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setLocalError("");
    const values = new FormData(e.currentTarget);
    try {
      await write(
        "/onboarding",
        {
          business: values.get("business"),
          region: values.get("region"),
          target_customers: values.get("target_customers"),
          completed_steps: ["business"],
        },
        "PUT",
      );
      onChange();
      notify("Workspace-Profil gespeichert.");
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="EINSTELLUNGEN / WORKSPACE"
        title="Mein Angebot"
        description="Was du anbietest, wo und für wen. Daraus entstehen Zielgruppe und Texte."
      />
      <ErrorNote message={localError || error} />
      <div className="setup-layout">
        <section className="panel settings-panel">
          <h2>1 · Unternehmen und Zielkunden</h2>
          {loading ? (
            <Spinner />
          ) : (
            <form key={data?.business || "new"} onSubmit={save}>
              <label>
                Was bietest du an?
                <textarea
                  name="business"
                  defaultValue={data?.business}
                  maxLength={2000}
                  required
                  disabled={!editable}
                />
              </label>
              <label>
                Region
                <input
                  name="region"
                  defaultValue={data?.region}
                  maxLength={200}
                  disabled={!editable}
                />
              </label>
              <label>
                Wen möchtest du erreichen?
                <textarea
                  name="target_customers"
                  defaultValue={data?.target_customers}
                  maxLength={2000}
                  required
                  disabled={!editable}
                />
              </label>
              <button className="button primary" disabled={!editable || busy}>
                Geschäftskontext speichern
              </button>
              {!editable && (
                <p className="small muted">
                  Nur Owner und Admin dürfen diese Einstellungen ändern.
                </p>
              )}
            </form>
          )}
        </section>
        <section className="panel settings-panel">
          <h2>Nächste Schritte</h2>
          <div className="setup-steps">
            {[
              {
                title: "2 · Zielgruppe festlegen",
                text: "Kriterien, bekannte Fakten und Gewichte im Profil speichern.",
                path: "/audiences",
              },
              {
                title: "3 · Kontakte importieren oder Unternehmen suchen",
                text: "Mit nachvollziehbarer Quelle und ohne erfundene Kontaktdaten.",
                path: "/discover",
              },
              {
                title: "4 · KI-Anbieter prüfen",
                text: "Serverseitige Zugangsdaten und Preise werden vom Betreiber konfiguriert.",
                path: "/settings/integrations",
              },
              {
                title: "5 · LinkedIn offiziell verbinden",
                text: "Optional. Gewährte Rechte bleiben Voraussetzung für Publishing.",
                path: "/settings/integrations",
              },
              {
                title: "6 · Erste Kampagne oder Beitrag",
                text: "Entwürfe anlegen, prüfen und bewusst freigeben.",
                path: "/campaigns",
              },
            ].map((step) => (
              <button
                className="setup-step"
                key={step.title}
                onClick={() => onNavigate(step.path)}
              >
                <CheckCircle2 size={19} />
                <span>
                  <strong>{step.title}</strong>
                  <small>{step.text}</small>
                </span>
                <ArrowRight size={15} />
              </button>
            ))}
          </div>
          <div className="form-actions">
            <button className="button secondary" onClick={onImport}>
              CSV importieren
            </button>
            <button
              className="button secondary"
              onClick={() => onNavigate("/social/studio")}
            >
              Social-Entwurf erstellen
            </button>
          </div>
          <p className="small muted">
            Optionale Anbieter können später eingerichtet werden. Ein erledigter
            Arbeitsschritt ersetzt keine echte Anbieterfreigabe.
          </p>
        </section>
      </div>
    </>
  );
}

export function TeamSettings({
  base,
  write,
  notify,
  revision,
  onChange,
  role,
}: ModuleProps & { role: string }) {
  const { data, error, loading } = useData<{
    items: { id: string; name: string; email: string; role: string }[];
  }>(`${base}/members`, revision);
  const [localError, setLocalError] = useState("");
  const [invite, setInvite] = useState<{
    token: string;
    expires_at: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const editable = ["owner", "admin"].includes(role);
  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    try {
      const result = await write<{ token: string; expires_at: string }>(
        "/invites",
        { email: values.get("email"), role: values.get("role") },
      );
      setInvite(result);
      form.reset();
      notify("Einladung erstellt. Keine E-Mail versendet.");
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="EINSTELLUNGEN / ZUGRIFF"
        title="Team"
        description="Wer Zugriff hat und was er darf. Einladungen gelten einmal und nur für die genannte E-Mail-Adresse."
      />
      <ErrorNote message={localError || error} />
      <div className="setup-layout">
        <section className="panel settings-panel">
          <h2>Mitglieder</h2>
          {loading ? (
            <Spinner />
          ) : (
            <div className="home-rows">
              {data?.items.map((member) => (
                <div className="home-row" key={member.id}>
                  <span>
                    <strong>{member.name}</strong>
                    <small>{member.email}</small>
                  </span>
                  <select
                    aria-label={`Rolle für ${member.email}`}
                    value={member.role}
                    disabled={
                      !editable ||
                      (role !== "owner" &&
                        ["owner", "admin"].includes(member.role))
                    }
                    onChange={async (e) => {
                      try {
                        await write(
                          `/members/${member.id}`,
                          { role: e.target.value },
                          "PATCH",
                        );
                        onChange();
                        notify("Rolle aktualisiert.");
                      } catch (error) {
                        setLocalError((error as Error).message);
                      }
                    }}
                  >
                    {["owner", "admin", "editor", "approver", "analyst"].map(
                      (value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ),
                    )}
                  </select>
                </div>
              ))}
            </div>
          )}
        </section>
        <section className="panel settings-panel">
          <h2>Manuell einladen</h2>
          <form onSubmit={create}>
            <label>
              E-Mail-Adresse
              <input
                type="email"
                name="email"
                required
                maxLength={254}
                disabled={!editable}
              />
            </label>
            <label>
              Rolle
              <select name="role" defaultValue="editor" disabled={!editable}>
                {[
                  "editor",
                  "approver",
                  "analyst",
                  ...(role === "owner" ? ["admin"] : []),
                ].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <button className="button primary" disabled={!editable || busy}>
              Einladung erstellen
            </button>
          </form>
          {invite && (
            <div className="info-note">
              <ShieldCheck size={18} />
              <div>
                <p>
                  Privaten Einmal-Token nur dem vorgesehenen Empfänger sicher
                  übermitteln. Ablauf: {dateTime(invite.expires_at)}. Es wurde
                  keine E-Mail versendet.
                </p>
                <label>
                  Einladungstoken
                  <input readOnly value={invite.token} />
                </label>
                <button
                  className="button secondary"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(invite.token);
                      notify("Token kopiert.");
                    } catch {
                      setLocalError("Token bitte manuell kopieren.");
                    }
                  }}
                >
                  <Copy size={15} /> Sicher weitergeben
                </button>
                <p className="small muted">
                  Empfänger meldet sich mit der eingeladenen Adresse an und
                  akzeptiert den Token über die dokumentierte Einladungs-API.
                </p>
              </div>
            </div>
          )}
        </section>
      </div>
    </>
  );
}

export function BillingSettings({ base, write, revision }: ModuleProps) {
  const { data, error } = useData<{
    status: string;
    plan: string;
    configured: boolean;
    test_mode: boolean;
    entitlements: { max_contacts: number; max_assets: number };
  }>(`${base}/billing`, revision);
  const [localError, setLocalError] = useState("");
  const [busy, setBusy] = useState(false);
  async function open(path: string) {
    setBusy(true);
    try {
      const result = await write<{ url: string }>(path);
      const destination = new URL(result.url);
      if (
        destination.protocol !== "https:" ||
        !["checkout.stripe.com", "billing.stripe.com"].includes(
          destination.hostname,
        )
      )
        throw new Error("Unzulässiger Zahlungsanbieter-Link.");
      window.location.assign(destination.href);
    } catch (e) {
      setLocalError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <>
      <Heading
        eyebrow="EINSTELLUNGEN / ABRECHNUNG"
        title="Abo"
        description="Aktuell ausschließlich Stripe-Testmodus. Keine echten Produktionszahlungen."
      />
      <ErrorNote message={localError || error} />
      <section className="panel settings-panel">
        <div className="section-title">
          <h2>{data?.plan || "Plan wird geladen"}</h2>
          <Badge>{data?.status || "Lädt"}</Badge>
        </div>
        <div className="usage-grid">
          <div>
            <strong>{data?.entitlements.max_contacts ?? "—"}</strong>
            <p>Kontakte pro Workspace</p>
          </div>
          <div>
            <strong>{data?.entitlements.max_assets ?? "—"}</strong>
            <p>Private Bilder</p>
          </div>
        </div>
        <div className="form-actions">
          <button
            className="button primary"
            disabled={!data?.configured || busy}
            title={
              !data?.configured
                ? "Betreiber muss Stripe-Testzugang, Preis und Webhook konfigurieren."
                : undefined
            }
            onClick={() => open("/billing/checkout")}
          >
            Test-Abo öffnen
          </button>
          <button
            className="button secondary"
            disabled={!data?.configured || busy}
            onClick={() => open("/billing/portal")}
          >
            Test-Abo verwalten
          </button>
        </div>
        {!data?.configured && (
          <p className="small muted">
            Stripe ist nicht konfiguriert. Erforderlich: STRIPE_SECRET_KEY
            (Test), STRIPE_PRICE_ID, STRIPE_WEBHOOK_SECRET und geprüfter
            Webhook-Zugang.
          </p>
        )}
      </section>
    </>
  );
}

export function ProviderChecks({ write }: Pick<ModuleProps, "write">) {
  const [result, setResult] = useState<
    Record<
      string,
      {
        status: string;
        message: string;
        requirements?: string[];
        validated: boolean;
      }
    >
  >({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  return (
    <section className="panel settings-panel">
      <h2>Anbieterzugriff prüfen</h2>
      <p className="muted">
        Nur lesende Prüfungen. Ein erreichbares Konto ist noch keine
        Generierungs-, Sende- oder Veröffentlichungsfreigabe.
      </p>
      <ErrorNote message={error} />
      <div className="provider-checks">
        {[
          { id: "llm", label: "KI-Text" },
          { id: "images", label: "KI-Bilder" },
          { id: "linkedin", label: "LinkedIn" },
          { id: "discovery", label: "Firmensuche mit Lizenz" },
          { id: "stripe", label: "Stripe-Testmodus" },
          { id: "email", label: "E-Mail" },
        ].map((provider) => (
          <article className="provider-check-row" key={provider.id}>
            <div>
              <strong>{provider.label}</strong>
              {result[provider.id] && (
                <>
                  <p>{result[provider.id].message}</p>
                  {result[provider.id].requirements?.length ? (
                    <small>
                      Erforderlich:{" "}
                      {result[provider.id].requirements?.join(", ")}
                    </small>
                  ) : null}
                </>
              )}
            </div>
            <button
              className="button secondary small"
              disabled={!!busy}
              onClick={async () => {
                setBusy(provider.id);
                setError("");
                try {
                  const value = await write<{
                    status: string;
                    message: string;
                    requirements?: string[];
                    validated: boolean;
                  }>(`/providers/${provider.id}/test`);
                  setResult((r) => ({ ...r, [provider.id]: value }));
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy("");
                }
              }}
            >
              {busy === provider.id ? <Spinner /> : "Zugriff prüfen"}
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
