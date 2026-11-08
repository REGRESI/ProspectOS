"use client";
import { FormEvent, useState } from "react";
import { Ban, Link2, Mail, MapPin, Phone, RefreshCw, Route } from "lucide-react";
import { dateTime } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Spinner } from "./ui";
import type { JourneyProps } from "./journey-types";

type Permission = { allowed: boolean; basis: string | null; reason: string | null };
export type Channels = {
  contact_id: string;
  route: "linkedin" | "letter" | "none";
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
