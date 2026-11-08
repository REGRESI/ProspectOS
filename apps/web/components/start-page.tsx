"use client";
import { FormEvent, useState } from "react";
import { ArrowRight, Check, Compass } from "lucide-react";
import { useData } from "@/lib/use-data";
import { ErrorNote, Heading, Spinner } from "./ui";
import type { Write } from "./growth-modules";

type Step = { key: "company" | "area" | "audience" | "linkedin" | "campaign"; title: string; done: boolean; summary: string };
export type StartStatus = {
  steps: Step[];
  done: number;
  total: number;
  next: Step["key"] | null;
  settings: { sender_company: string; sender_name: string; offer: string; address_form: string; region: string };
};
const hints: Record<Step["key"], string> = {
  company: "Wer schreibt und was du anbietest. Steht später in jeder Nachricht und jedem Brief.",
  area: "Wo deine Kunden sitzen. Orte oder PLZ-Anfänge helfen beim Verteilen im Team.",
  audience: "Welche Firmen passen. Die Vorlage bewertet Praxen, Kanzleien und Büros höher.",
  linkedin: "Für Beiträge über die offizielle Schnittstelle. Kontaktanfragen klickst du immer selbst.",
  campaign: "Ein fertiges Rezept: Mit LinkedIn-Profil über LinkedIn, sonst per Brief.",
};

/** Small progress hint for Heute; disappears when all five steps are done. */
export function StartBanner({ base, onNavigate }: { base: string; onNavigate?: (p: string) => void }) {
  const data = useData<StartStatus>(`${base}/start`, 0);
  if (!data.data || data.data.done >= data.data.total) return null;
  return (
    <p className="start-banner" data-testid="start-banner">
      <Compass size={16} aria-hidden /> Geführter Start: {data.data.done} von {data.data.total} Schritten erledigt.
      <button className="link-button" onClick={() => onNavigate?.("/start")}>
        Weitermachen <ArrowRight size={14} />
      </button>
    </p>
  );
}

export function StartPage({
  base,
  write,
  notify,
  onNavigate,
}: {
  base: string;
  write: Write;
  notify: (m: string) => void;
  onNavigate?: (path: string) => void;
}) {
  const [revision, setRevision] = useState(0);
  const [open, setOpen] = useState<Step["key"] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = useData<StartStatus>(`${base}/start`, revision);
  const routes = useData<{ routes: Record<string, number> }>(`${base}/channels/summary`, revision);
  const current = open ?? data.data?.next ?? null;

  async function run(fn: () => Promise<unknown>, message: string, then?: () => void) {
    setBusy(true);
    setError("");
    try {
      await fn();
      setOpen(null);
      setRevision((v) => v + 1);
      notify(message);
      then?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const values = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    return new FormData(event.currentTarget);
  };
  if (!data.data)
    return (
      <div className="loading-block">
        <Spinner />
      </div>
    );
  const s = data.data.settings;
  const routed = routes.data ? routes.data.routes.linkedin + routes.data.routes.letter : 0;
  return (
    <>
      <Heading title="Geführter Start" description="Fünf Schritte bis zur ersten Aufgabe in Heute. Jeder Schritt dauert etwa eine Minute." />
      <ErrorNote message={error} />
      <ol className="start-steps" data-testid="start-steps">
        {data.data.steps.map((step, index) => (
          <li key={step.key} className={`start-step ${step.done ? "done" : ""} ${current === step.key ? "current" : ""}`}>
            <button className="start-step-head" onClick={() => setOpen(current === step.key ? null : step.key)}>
              <span className="start-step-number" aria-hidden>
                {step.done ? <Check size={14} /> : index + 1}
              </span>
              <span>
                <strong>{step.title}</strong>
                <small className="muted">{step.done && step.summary ? step.summary : hints[step.key]}</small>
              </span>
            </button>
            {current === step.key && (
              <div className="start-step-body">
                {step.key === "company" && (
                  <form
                    className="form-grid"
                    onSubmit={(e) => {
                      const f = values(e);
                      void run(
                        () =>
                          write(
                            "/start/company",
                            {
                              sender_company: f.get("sender_company"),
                              sender_name: f.get("sender_name"),
                              offer: f.get("offer"),
                              address_form: f.get("address_form"),
                            },
                            "PUT",
                          ),
                        "Firma gespeichert.",
                      );
                    }}
                  >
                    <label>
                      Firma
                      <input name="sender_company" required minLength={2} maxLength={80} defaultValue={s.sender_company} />
                    </label>
                    <label>
                      Dein Name
                      <input name="sender_name" required minLength={2} maxLength={80} defaultValue={s.sender_name} />
                    </label>
                    <label>
                      Angebot
                      <input name="offer" required minLength={3} maxLength={120} defaultValue={s.offer} />
                    </label>
                    <label>
                      Anrede
                      <select name="address_form" defaultValue={s.address_form}>
                        <option value="sie">Sie</option>
                        <option value="du">Du</option>
                      </select>
                    </label>
                    <button className="button primary small" disabled={busy}>
                      Weiter
                    </button>
                  </form>
                )}
                {step.key === "area" && (
                  <form
                    className="form-grid"
                    onSubmit={(e) => {
                      const f = values(e);
                      void run(
                        () =>
                          write(
                            "/start/area",
                            {
                              region: f.get("region"),
                              places: String(f.get("places") || "")
                                .split(",")
                                .map((p) => p.trim())
                                .filter(Boolean),
                            },
                            "PUT",
                          ),
                        "Gebiet gespeichert.",
                      );
                    }}
                  >
                    <label>
                      Region (wie im Satz „in …“)
                      <input name="region" required minLength={2} maxLength={60} defaultValue={s.region} placeholder="der Ortenau" />
                    </label>
                    <label>
                      Orte oder PLZ-Anfänge
                      <input name="places" placeholder="Lahr, Offenburg, 779" />
                    </label>
                    <button className="button primary small" disabled={busy}>
                      Weiter
                    </button>
                  </form>
                )}
                {step.key === "audience" && (
                  <div className="start-choice">
                    <p>Vorlage: Büro-Unterhaltsreinigung im Ortenaukreis (Praxen, Kanzleien, Steuerberater, Agenturen, Büros, Kitas).</p>
                    <button
                      className="button primary small"
                      disabled={busy}
                      onClick={() =>
                        run(
                          () => write("/icp-profiles/from-template", { template: "office_cleaning_ortenau" }),
                          "Zielgruppe angelegt.",
                        )
                      }
                    >
                      Vorlage übernehmen
                    </button>
                    <button className="button ghost small" onClick={() => onNavigate?.("/audiences")}>
                      Eigene Zielgruppe bauen
                    </button>
                  </div>
                )}
                {step.key === "linkedin" && (
                  <div className="start-choice">
                    <p>Die Verbindung nutzt die offizielle LinkedIn-Schnittstelle für deine Beiträge. Einladungen und Nachrichten sendest du immer selbst.</p>
                    <button className="button primary small" onClick={() => onNavigate?.("/settings/integrations")}>
                      LinkedIn verbinden
                    </button>
                    <button
                      className="button ghost small"
                      disabled={busy}
                      onClick={() => run(() => write("/start/linkedin/skip"), "Später verbinden.")}
                    >
                      Später
                    </button>
                  </div>
                )}
                {step.key === "campaign" && (
                  <div className="start-choice">
                    <p>
                      {routed
                        ? `${routed} Kontakte haben einen Weg (LinkedIn oder Brief). Das Rezept startet für alle.`
                        : "Noch keine Kontakte mit LinkedIn-Profil oder Postadresse. Importiere zuerst eine Liste oder finde Firmen."}
                    </p>
                    <button
                      className="button primary small"
                      disabled={busy || !routed}
                      onClick={() =>
                        run(
                          () =>
                            write("/campaigns/from-recipe", {
                              recipe: "office_linkedin",
                              audience: "routed",
                            }),
                          "Erste Kampagne gestartet. Deine Aufgaben stehen in Heute.",
                          () => onNavigate?.("/today"),
                        )
                      }
                    >
                      „Büro Ortenau mit LinkedIn“ starten
                    </button>
                    {!routed && (
                      <>
                        <button className="button ghost small" onClick={() => onNavigate?.("/imports")}>
                          Liste importieren
                        </button>
                        <button className="button ghost small" onClick={() => onNavigate?.("/discover")}>
                          Firmen finden
                        </button>
                        <button
                          className="button ghost small"
                          disabled={busy}
                          onClick={() => run(() => write("/channels/refresh"), "Wege neu berechnet.")}
                        >
                          Wege neu berechnen
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}
