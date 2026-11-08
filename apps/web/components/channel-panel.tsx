"use client";
import { FormEvent, useState } from "react";
import { Ban, Link2, Mail, MapPin, Phone, RefreshCw, Route } from "lucide-react";
import { dateTime } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Spinner } from "./ui";
import type { JourneyProps } from "./journey-types";
import { ReactionForm } from "./inbox";
import type { Overview } from "./connectors-page";

type Permission = { allowed: boolean; basis: string | null; reason: string | null };
export type Channels = {
  contact_id: string;
  route: "linkedin" | "letter" | "tool" | "none";
  route_label: string;
  route_reason: string;
  route_mode: "auto" | "manual";
  route_set_at: string | null;
  points: {
    id: string;
    channel: "linkedin" | "postal" | "email" | "phone";
    value: string;
    kind: string;
    source: string;
    source_url: string | null;
    observed_at: string;
    verified: boolean;
  }[];
  permissions: Record<"linkedin" | "letter" | "email" | "phone" | "visit", Permission>;
  objection: { reason: string; at: string } | null;
};

const channelLabels = {
  linkedin: "LinkedIn",
  letter: "Brief",
  email: "E-Mail",
  phone: "Telefon",
  visit: "Besuch",
} as const;
const pointIcons = { linkedin: Link2, postal: MapPin, email: Mail, phone: Phone };
const pointLabels = {
  linkedin: "LinkedIn-Profil",
  postal: "Postadresse",
  email: "E-Mail",
  phone: "Telefon",
};

export function ChannelPanel(
  props: JourneyProps & { contactId: string; onChanged?: () => void },
) {
  const { base, write, notify, revision, contactId, onChanged } = props;
  const [local, setLocal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = useData<Channels>(
    `${base}/contacts/${contactId}/channels`,
    revision + local,
  );
  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    try {
      await action();
      setLocal((v) => v + 1);
      onChanged?.();
      notify(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function phoneBasis(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void run(
      () =>
        write(`/contacts/${contactId}/legal-basis`, {
          channel: "phone",
          basis: "concrete_interest",
          occasion: String(form.get("occasion")),
          evidence: String(form.get("evidence")),
        }),
      "Konkretes Interesse festgehalten. Anrufen ist jetzt möglich.",
    );
  }
  const c = data.data;
  if (!c)
    return data.error ? (
      <ErrorNote message={data.error} />
    ) : (
      <div className="loading-block">
        <Spinner />
      </div>
    );
  return (
    <div className="channel-panel" data-testid="channel-panel">
      <ErrorNote message={error} />
      <section className={`route-card route-${c.route}`}>
        <div>
          <span className="route-eyebrow">
            <Route size={14} /> Aktiver Weg
          </span>
          <strong className="route-name">{c.route_label}</strong>
          <p>{c.route_reason || "Noch nicht berechnet."}</p>
          <small className="muted">
            {c.route_mode === "manual" ? "Von Hand gewählt" : "Automatisch"}
            {c.route_set_at ? ` · ${dateTime(c.route_set_at)}` : ""}
          </small>
        </div>
        <div className="route-actions">
          <label>
            Weg ändern
            <select
              aria-label="Weg ändern"
              value=""
              disabled={busy}
              onChange={(e) =>
                e.target.value &&
                run(
                  () =>
                    write(`/contacts/${contactId}/route`, { route: e.target.value }, "PUT"),
                  "Weg gespeichert.",
                )
              }
            >
              <option value="">Auswählen</option>
              <option value="auto">Automatisch</option>
              <option value="linkedin">LinkedIn</option>
              <option value="letter">Brief</option>
              <option value="none">Kein Weg</option>
            </select>
          </label>
          <button
            className="button ghost small"
            disabled={busy}
            onClick={() =>
              run(() => write(`/contacts/${contactId}/channels/refresh`), "Kanäle aktualisiert.")
            }
          >
            <RefreshCw size={14} /> Aus Quellen aktualisieren
          </button>
        </div>
      </section>

      <HandoffBox
        base={base}
        contactId={contactId}
        revision={revision + local}
        linkedinAllowed={c.permissions.linkedin.allowed}
        busy={busy}
        onHandoff={(tool, target) =>
          run(
            () => write(`/contacts/${contactId}/handoff`, { tool, target }),
            "Übergabe gestartet. Der Kontakt erscheint nicht mehr in Heute.",
          )
        }
      />

      {c.objection && (
        <p className="info-note warning" role="status">
          <Ban size={15} /> Widerspruch vom {dateTime(c.objection.at)}: {c.objection.reason}. Alle
          Kanäle sind gesperrt.
        </p>
      )}

      <section>
        <h3 className="channel-heading">Erlaubt pro Kanal</h3>
        <ul className="permission-grid">
          {(Object.keys(channelLabels) as (keyof typeof channelLabels)[]).map((key) => {
            const p = c.permissions[key];
            return (
              <li key={key} className={p.allowed ? "ok" : "off"}>
                <strong>{channelLabels[key]}</strong>
                <Badge tone={p.allowed ? "green" : "neutral"}>{p.allowed ? "erlaubt" : "gesperrt"}</Badge>
                <small>{p.allowed ? p.basis : p.reason}</small>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <h3 className="channel-heading">Erreichbar über</h3>
        {c.points.length ? (
          <ul className="point-list">
            {c.points.map((p) => {
              const Icon = pointIcons[p.channel];
              return (
                <li key={p.id}>
                  <Icon size={15} aria-hidden />
                  <div>
                    <span className="point-value">{p.value}</span>
                    <small className="muted">
                      {pointLabels[p.channel]}
                      {p.channel === "email" || p.channel === "phone"
                        ? p.kind === "general"
                          ? " · allgemein"
                          : " · persönlich"
                        : ""}
                      {p.channel === "linkedin" && !p.verified ? " · ungeprüft" : ""} · {p.source} ·{" "}
                      {dateTime(p.observed_at)}
                      {p.source_url && (
                        <>
                          {" · "}
                          <a href={p.source_url} target="_blank" rel="noreferrer">
                            Quelle
                          </a>
                        </>
                      )}
                    </small>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="muted">
            Noch keine Kontaktwege. Recherchiere das Impressum der Firma oder trag Daten von Hand
            ein.
          </p>
        )}
      </section>

      {!c.objection && !c.permissions.phone.allowed && c.points.some((p) => p.channel === "phone") && (
        <details className="evidence-add">
          <summary>Konkretes Interesse festhalten (für Anrufe)</summary>
          <form className="form-grid" onSubmit={phoneBasis}>
            <label>
              Anlass
              <input name="occasion" required minLength={3} maxLength={300} placeholder="z. B. Anfrage über die Website am 3.11." />
            </label>
            <label>
              Nachweis
              <input name="evidence" required minLength={3} maxLength={1000} placeholder="Was genau hat die Person gesagt oder getan?" />
            </label>
            <button className="button secondary small" disabled={busy}>
              Festhalten
            </button>
          </form>
        </details>
      )}

      {!c.objection && (
        <ReactionForm
          contactId={contactId}
          write={write}
          onDone={(message) => {
            setLocal((v) => v + 1);
            onChanged?.();
            notify(message);
          }}
        />
      )}

      {!c.objection && (
        <details className="evidence-add danger">
          <summary>Widerspruch eintragen</summary>
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              const reason = String(new FormData(event.currentTarget).get("reason"));
              void run(
                () => write(`/contacts/${contactId}/objection`, { reason }),
                "Widerspruch gespeichert. Alle geplanten Schritte sind gestoppt.",
              );
            }}
          >
            <label className="span-2">
              Grund
              <input name="reason" required minLength={3} maxLength={200} placeholder="z. B. Bitte keine Werbung (Telefonat 8.11.)" />
            </label>
            <button className="button secondary small" disabled={busy}>
              Alle Kanäle sperren
            </button>
          </form>
        </details>
      )}
    </div>
  );
}

type HandoffItem = {
  id: string;
  tool: string;
  tool_label: string;
  target: string;
  state: string;
  last_event: string;
  error: string;
  created_at: string;
};
const handoffStates: Record<string, [string, string]> = {
  queued: ["wird übergeben", "amber"],
  handed_over: ["im Tool", "green"],
  replied: ["geantwortet", "purple"],
  stopping: ["wird gestoppt", "amber"],
  paused: ["im Tool pausiert", "neutral"],
  stopped: ["im Tool von Hand stoppen", "red"],
  failed: ["fehlgeschlagen", "red"],
  ambiguous: ["unklar, im Tool prüfen", "red"],
};

/** M9: hand a contact with a verified LinkedIn profile to a connected external tool. */
function HandoffBox({
  base,
  contactId,
  revision,
  linkedinAllowed,
  busy,
  onHandoff,
}: {
  base: string;
  contactId: string;
  revision: number;
  linkedinAllowed: boolean;
  busy: boolean;
  onHandoff: (tool: string, target: string) => void;
}) {
  const overview = useData<Overview>(`${base}/connectors`, revision);
  const handoffs = useData<{ items: HandoffItem[] }>(
    `${base}/handoffs?contact_id=${contactId}`,
    revision,
  );
  const [tool, setTool] = useState("");
  const [target, setTarget] = useState("");
  const view = overview.data;
  if (!view || !view.available || !view.enabled) return null;
  const ready = view.tools.filter((t) => t.configured && t.active);
  const items = handoffs.data?.items || [];
  return (
    <section className="handoff-box" data-testid="handoff-box">
      <h3 className="channel-heading">Externes Tool (eigene Gefahr)</h3>
      {items.length > 0 && (
        <ul className="point-list">
          {items.map((h) => {
            const [label, tone] = handoffStates[h.state] || [h.state, "neutral"];
            return (
              <li key={h.id}>
                <strong>{h.tool_label}</strong> · {h.target}{" "}
                <Badge tone={tone}>{label}</Badge>
                {h.last_event && <small className="muted"> · zuletzt: {h.last_event}</small>}
                {h.error && <small className="muted"> · {h.error}</small>}
              </li>
            );
          })}
        </ul>
      )}
      {!linkedinAllowed ? (
        <p className="muted small-print">Nur Kontakte mit geprüftem LinkedIn-Profil können übergeben werden.</p>
      ) : ready.length === 0 ? (
        <p className="muted small-print">Kein Tool verbunden. Einstellungen → Anschlüsse.</p>
      ) : (
        <form
          className="handoff-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (tool && target.trim()) onHandoff(tool, target.trim());
          }}
        >
          <label>
            Tool
            <select value={tool} onChange={(e) => setTool(e.target.value)} aria-label="Tool">
              <option value="">Auswählen</option>
              {ready.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Ziel-Kampagne im Tool
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder={tool === "expandi" ? "Webhook-URL der Kampagne" : "Kampagnen-ID"}
              aria-label="Ziel-Kampagne"
            />
          </label>
          <button className="button secondary small" disabled={busy || !tool || !target.trim()}>
            An Tool übergeben
          </button>
        </form>
      )}
      <p className="muted small-print">
        Übergeben werden nur Name, Firma, Position und LinkedIn-URL; E-Mail nur mit Rechtsgrundlage.
      </p>
    </section>
  );
}
