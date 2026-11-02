"use client";
import { useState } from "react";
import type { FormEvent } from "react";
import { Plus, X, Target } from "lucide-react";
import type { JourneyProps } from "./journey-types";
import type { Page } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { ErrorNote, Spinner } from "./ui";
type Profile = {
  id?: string;
  name: string;
  locations: string[];
  industries: string[];
  excluded_industries: string[];
  roles: string[];
  needs: string[];
  min_employees: number | null;
  max_employees: number | null;
  required_fields: string[];
  optional_fields: string[];
  weights: Record<string, number>;
  version?: number;
  created_at?: string;
};
const blank: Profile = {
  name: "",
  locations: [],
  industries: [],
  excluded_industries: [],
  roles: [],
  needs: [],
  min_employees: null,
  max_employees: null,
  required_fields: [],
  optional_fields: [],
  weights: { location: 35, role: 35, industry: 30, size: 0, needs: 0 },
};
const criteria = {
  locations: "Regionen und Standorte",
  industries: "Zielbranchen",
  excluded_industries: "Ausgeschlossene Branchen",
  roles: "Bevorzugte Rollen",
  needs: "Belegbare Geschäftsbedürfnisse",
} as const;
const weightLabels: Record<string, string> = {
  location: "Standort",
  role: "Rolle",
  industry: "Branche",
  size: "Unternehmensgröße",
  needs: "Belegter Bedarf",
};
const fields: Record<string, string> = {
  email: "E-Mail",
  phone: "Telefon",
  company: "Firma",
  job_title: "Rolle",
  location: "Standort",
  linkedin_url: "LinkedIn-Profil",
};
function Terms({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const [input, setInput] = useState("");
  function add() {
    const term = input.trim();
    if (term && value.length < 30 && !value.includes(term))
      onChange([...value, term]);
    setInput("");
  }
  return (
    <div className="icp-terms">
      <label>
        {label}
        <span className="icp-term-entry">
          <input
            aria-label={label}
            value={input}
            maxLength={120}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
          <button
            className="icon-button"
            type="button"
            aria-label={`${label} hinzufügen`}
            disabled={!input.trim()}
            onClick={add}
          >
            <Plus size={16} />
          </button>
        </span>
      </label>
      <div className="journey-tags">
        {value.map((term) => (
          <button
            type="button"
            className="badge purple"
            key={term}
            onClick={() => onChange(value.filter((v) => v !== term))}
            aria-label={`${term} entfernen`}
          >
            {term} <X size={12} />
          </button>
        ))}
      </div>
    </div>
  );
}
export function ICPBuilder({
  base,
  write,
  revision,
  onChange,
  notify,
  onNavigate,
}: JourneyProps) {
  const profiles = useData<Page<Profile>>(
    `${base}/icp-profiles?limit=100`,
    revision,
  );
  const [selected, setSelected] = useState<Profile>(blank);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const total = Object.values(selected.weights).reduce((a, b) => a + b, 0);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (total !== 100) {
      setError("Gewichtungen müssen zusammen 100 ergeben.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const { id, version, created_at, ...body } = selected;
      void version;
      void created_at;
      const result = await write<Profile>(
        id ? `/icp-profiles/${id}` : "/icp-profiles",
        body,
        id ? "PUT" : "POST",
      );
      setSelected(result);
      onChange();
      notify("ICP-Profil gespeichert. Nur belegte Kriterien erhalten Punkte.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="journey-heading">
        <div>
          <span className="eyebrow">LEADS / INTELLIGENZ</span>
          <h1>ICP-Profile</h1>
          <p className="muted">
            Zielkunden strukturiert definieren und nachvollziehbar bewerten.
          </p>
        </div>
        <button
          className="button secondary"
          onClick={() => {
            setSelected(structuredClone(blank));
            setError("");
          }}
        >
          <Plus size={16} />
          Neues Profil
        </button>
      </div>
      <ErrorNote message={error || profiles.error} />
      <div className="icp-workbench">
        <aside className="panel padded">
          <h2>Gespeicherte Profile</h2>
          {profiles.loading ? (
            <Spinner />
          ) : profiles.data?.items.length ? (
            profiles.data.items.map((profile) => (
              <button
                key={profile.id}
                className={`icp-profile-option ${selected.id === profile.id ? "active" : ""}`}
                onClick={() => {
                  const {
                    id,
                    name,
                    locations,
                    industries,
                    excluded_industries,
                    roles,
                    needs,
                    min_employees,
                    max_employees,
                    required_fields,
                    optional_fields,
                    weights,
                    version,
                  } = profile;
                  setSelected({
                    id,
                    name,
                    locations,
                    industries,
                    excluded_industries,
                    roles,
                    needs,
                    min_employees,
                    max_employees,
                    required_fields,
                    optional_fields,
                    weights,
                    version,
                  });
                  setError("");
                }}
              >
                <Target size={16} />
                <span>
                  {profile.name}
                  <small>Revision {profile.version}</small>
                </span>
              </button>
            ))
          ) : (
            <p className="muted">
              Noch kein wiederverwendbares Profil. Lege rechts dein erstes
              Profil an.
            </p>
          )}
          <p className="small muted">
            Unbekannte Angaben sind fehlende Evidenz, kein negatives Signal. Ein
            Fit-Score ist keine Kaufwahrscheinlichkeit.
          </p>
        </aside>
        <form
          className="panel padded"
          onSubmit={save}
          key={selected.id || "new"}
        >
          <h2>{selected.id ? "Profil bearbeiten" : "Profil erstellen"}</h2>
          <label>
            Profilname
            <input
              value={selected.name}
              required
              maxLength={120}
              onChange={(e) =>
                setSelected({ ...selected, name: e.target.value })
              }
            />
          </label>
          <div className="form-grid">
            {Object.entries(criteria).map(([key, label]) => (
              <Terms
                key={`${selected.id}-${key}`}
                label={label}
                value={selected[key as keyof typeof criteria]}
                onChange={(values) =>
                  setSelected({ ...selected, [key]: values })
                }
              />
            ))}
          </div>
          <div className="form-grid">
            <label>
              Mitarbeiterzahl ab
              <input
                type="number"
                min={0}
                value={selected.min_employees ?? ""}
                onChange={(e) =>
                  setSelected({
                    ...selected,
                    min_employees: e.target.value
                      ? Number(e.target.value)
                      : null,
                  })
                }
              />
            </label>
            <label>
              Mitarbeiterzahl bis
              <input
                type="number"
                min={selected.min_employees ?? 1}
                value={selected.max_employees ?? ""}
                onChange={(e) =>
                  setSelected({
                    ...selected,
                    max_employees: e.target.value
                      ? Number(e.target.value)
                      : null,
                  })
                }
              />
            </label>
          </div>
          <h3>Gewichtung · {total}/100</h3>
          <div className="icp-weights">
            {Object.entries(weightLabels).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={selected.weights[key] ?? 0}
                  onChange={(e) =>
                    setSelected({
                      ...selected,
                      weights: {
                        ...selected.weights,
                        [key]: Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
            ))}
          </div>
          <h3>Feldanforderungen</h3>
          <div className="form-grid">
            {Object.entries(fields).map(([key, label]) => (
              <label key={key}>
                {label}
                <select
                  value={
                    selected.required_fields.includes(key)
                      ? "required"
                      : selected.optional_fields.includes(key)
                        ? "optional"
                        : "none"
                  }
                  onChange={(e) =>
                    setSelected({
                      ...selected,
                      required_fields: [
                        ...selected.required_fields.filter((k) => k !== key),
                        ...(e.target.value === "required" ? [key] : []),
                      ],
                      optional_fields: [
                        ...selected.optional_fields.filter((k) => k !== key),
                        ...(e.target.value === "optional" ? [key] : []),
                      ],
                    })
                  }
                >
                  <option value="none">Keine Vorgabe</option>
                  <option value="required">Erforderlich</option>
                  <option value="optional">Optional</option>
                </select>
              </label>
            ))}
          </div>
          <p className="small muted">
            Bedarf wird nur anhand vorhandener Recherchebelege gewertet.
            Fehlende Größen-, Rollen- oder Kontaktdaten werden nicht ergänzt.
          </p>
          <div className="journey-inline-actions">
            <button className="button primary" disabled={busy || total !== 100}>
              {busy ? "Speichert …" : "ICP-Profil speichern"}
            </button>
            {selected.id && (
              <button
                type="button"
                className="button secondary"
                onClick={() => onNavigate?.(`/contacts?icp=${selected.id}`)}
              >
                Auf Leadliste anwenden
              </button>
            )}
          </div>
        </form>
      </div>
    </>
  );
}
