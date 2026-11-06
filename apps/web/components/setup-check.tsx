"use client";
import { useState } from "react";
import { ArrowRight, RefreshCw } from "lucide-react";
import { useData } from "@/lib/use-data";
import { ErrorNote, Heading, Spinner } from "./ui";

type Light = "green" | "yellow" | "red" | "off";
type Item = { key: string; label: string; light: Light; status: string; detail: string; next: string; link: string };

const LIGHT_LABEL: Record<Light, string> = { green: "bereit", yellow: "unvollständig", red: "fehlt", off: "nicht verbunden" };

export function SetupCheck({ base, onNavigate }: { base: string; onNavigate: (p: string) => void }) {
  const [revision, setRevision] = useState(0);
  const data = useData<{ items: Item[]; summary: Record<Light, number> }>(`${base}/setup-check`, revision);
  const d = data.data;
  return (
    <>
      <Heading
        eyebrow="EINSTELLUNGEN"
        title="Setup-Check"
        description="Eine Ampel pro Integration und genau ein nächster Schritt. Werte werden nie angezeigt, nur ob sie vorhanden und bestätigt sind."
      />
      <ErrorNote message={data.error} />
      {!d ? (
        <Spinner />
      ) : (
        <section className="panel pad" data-testid="setup-check">
          <div className="table-toolbar">
            <span className="setup-summary">
              {(["green", "yellow", "red", "off"] as Light[]).map((l) => (
                <span key={l} className={`setup-dot ${l}`}>
                  {d.summary[l]} {LIGHT_LABEL[l]}
                </span>
              ))}
            </span>
            <button className="button ghost small" onClick={() => setRevision((v) => v + 1)}>
              <RefreshCw size={14} /> Neu prüfen
            </button>
          </div>
          <ul className="setup-list">
            {d.items.map((i) => (
              <li key={i.key} className={`setup-item ${i.light}`} data-testid={`setup-${i.key}`}>
                <span className={`setup-light ${i.light}`} aria-label={LIGHT_LABEL[i.light]} title={LIGHT_LABEL[i.light]} />
                <div>
                  <strong>{i.label}</strong> <span className="muted">· {i.status}</span>
                  {i.detail && <small className="muted setup-detail">{i.detail}</small>}
                  <p className="setup-next">
                    <span>Nächster Schritt:</span> {i.next}
                  </p>
                </div>
                <button className="button secondary small" onClick={() => onNavigate(i.link)}>
                  Öffnen <ArrowRight size={13} />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
