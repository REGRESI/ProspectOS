"use client";
import { useState } from "react";
import { useData } from "@/lib/use-data";
import { ErrorNote, Heading } from "./ui";
import { SkeletonTable } from "./table";

type Light = "green" | "yellow" | "red" | "off";
type Item = {
  key: string;
  label: string;
  light: Light;
  status: string;
  detail: string;
  next: string;
  tech?: string;
  link: string;
};

const LIGHT_LABEL: Record<Light, string> = {
  green: "bereit",
  yellow: "unvollständig",
  red: "fehlt",
  off: "nicht verbunden",
};

export function SetupCheck({ base, onNavigate }: { base: string; onNavigate: (p: string) => void }) {
  const [revision, setRevision] = useState(0);
  const data = useData<{ items: Item[]; summary: Record<Light, number> }>(`${base}/setup-check`, revision);
  const d = data.data;
  const open = d ? d.summary.yellow + d.summary.red : 0;
  return (
    <>
      <Heading
        title="Status"
        description={
          !d
            ? "Was eingerichtet ist und was als Nächstes zu tun ist."
            : open === 0
              ? "Alles Nötige ist eingerichtet."
              : `${open} ${open === 1 ? "Punkt braucht" : "Punkte brauchen"} noch deine Aufmerksamkeit.`
        }
      >
        <button className="button secondary" onClick={() => setRevision((v) => v + 1)}>
          Neu prüfen
        </button>
      </Heading>
      <ErrorNote message={data.error} />
      {!d ? (
        <SkeletonTable rows={7} cols={3} />
      ) : (
        <ul className="row-list setup-list" data-testid="setup-check">
          {d.items.map((i) => (
            <li key={i.key} className="setup-item" data-testid={`setup-${i.key}`}>
              <span className={`setup-light ${i.light}`} aria-label={LIGHT_LABEL[i.light]} title={LIGHT_LABEL[i.light]} />
              <div className="setup-body">
                <p className="setup-title">
                  <strong>{i.label}</strong>
                  <span className="muted">{i.status}</span>
                </p>
                <p className="setup-next">Nächster Schritt: {i.next}</p>
                {(i.detail || i.tech) && (
                  <p className="setup-tech">{[i.detail, i.tech].filter(Boolean).join(" · ")}</p>
                )}
              </div>
              <button className="button ghost small" onClick={() => onNavigate(i.link)}>
                Öffnen
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
