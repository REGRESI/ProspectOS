"use client";
import { useState } from "react";
import { Gauge, Shuffle } from "lucide-react";
import { dateTime } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Spinner } from "./ui";
import type { Write } from "./growth-modules";

type Member = {
  user_id: string;
  name: string;
  role: string;
  is_me: boolean;
  contacts: number;
  open_tasks: number;
  daily_limit: number;
  weekly_limit: number;
  sent_24h: number;
  sent_7d: number;
  remaining_today: number;
  acceptance_rate: number | null;
  stale_open: { contact_id: string; name: string; sent_at: string; linkedin_url: string | null }[];
  territory: string[];
  receives_leads: boolean;
};

function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const share = Math.min(1, max ? value / max : 0);
  return (
    <div className="pace-meter" aria-label={`${label}: ${value} von ${max}`}>
      <span className="pace-meter-label">
        {label}
        <strong>
          {value}/{max}
        </strong>
      </span>
      <span className="pace-meter-track">
        <span className={`pace-meter-fill ${share >= 1 ? "full" : share >= 0.8 ? "near" : ""}`} style={{ width: `${share * 100}%` }} />
      </span>
    </div>
  );
}

export function TeamPace({
  base,
  write,
  notify,
  myRole,
}: {
  base: string;
  write: Write;
  notify: (m: string) => void;
  myRole: string;
}) {
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const data = useData<{ members: Member[]; unassigned: number; notice: string }>(`${base}/team/pace`, revision);
  const canManage = myRole === "owner" || myRole === "admin";
  async function run(fn: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    try {
      await fn();
      setRevision((v) => v + 1);
      notify(message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel team-pace" data-testid="team-pace">
      <div className="panel-head">
        <div>
          <h2>
            <Gauge size={16} /> Verteilung und Tempo
          </h2>
          <p>{data.data?.notice}</p>
        </div>
        {canManage && (
          <div className="team-distribute">
            <span className="muted">{data.data?.unassigned ?? "–"} Kontakte ohne Zuständigkeit</span>
            <button
              className="button secondary small"
              disabled={busy || !data.data?.unassigned}
              onClick={() =>
                run(() => write("/team/distribute", { mode: "round_robin" }), "Leads abwechselnd verteilt.")
              }
            >
              <Shuffle size={14} /> Abwechselnd verteilen
            </button>
            <button
              className="button secondary small"
              disabled={busy || !data.data?.unassigned}
              onClick={() => run(() => write("/team/distribute", { mode: "territory" }), "Leads nach Gebiet verteilt.")}
            >
              Nach Gebiet verteilen
            </button>
          </div>
        )}
      </div>
      <ErrorNote message={error || data.error} />
      {!data.data ? (
        <div className="loading-block">
          <Spinner />
        </div>
      ) : (
        <ul className="pace-list">
          {data.data.members.map((m) => (
            <li key={m.user_id} data-testid={`pace-${m.name}`}>
              <div className="pace-head">
                <strong>{m.name}</strong>
                {m.is_me && <Badge tone="purple">du</Badge>}
                <span className="muted">
                  {m.contacts} Kontakte · {m.open_tasks} offene Aufgaben
                </span>
              </div>
              <div className="pace-meters">
                <Meter value={m.sent_24h} max={m.daily_limit} label="Einladungen heute" />
                <Meter value={m.sent_7d} max={m.weekly_limit} label="Diese Woche" />
                <div className="pace-rate">
                  Annahmequote
                  <strong>{m.acceptance_rate === null ? "–" : `${Math.round(m.acceptance_rate * 100)} %`}</strong>
                </div>
              </div>
              {!!m.stale_open.length && (
                <details className="pace-stale">
                  <summary>
                    {m.stale_open.length} Einladungen seit über 3 Wochen offen: in LinkedIn zurückziehen
                  </summary>
                  <ul>
                    {m.stale_open.map((s) => (
                      <li key={s.contact_id}>
                        {s.linkedin_url ? (
                          <a href={s.linkedin_url} target="_blank" rel="noreferrer">
                            {s.name}
                          </a>
                        ) : (
                          s.name
                        )}{" "}
                        <small className="muted">gesendet {dateTime(s.sent_at)}</small>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              {(canManage || m.is_me) && (
                <form
                  className="pace-settings"
                  key={`${m.user_id}-${revision}`}
                  onSubmit={(event) => {
                    event.preventDefault();
                    const f = new FormData(event.currentTarget);
                    void run(
                      () =>
                        write(
                          `/team/members/${m.user_id}/settings`,
                          {
                            daily_invite_limit: Number(f.get("daily")),
                            weekly_invite_limit: Number(f.get("weekly")),
                            territory: String(f.get("territory") || "")
                              .split(",")
                              .map((t) => t.trim())
                              .filter(Boolean),
                            receives_leads: f.get("receives") === "on",
                          },
                          "PUT",
                        ),
                      "Gespeichert.",
                    );
                  }}
                >
                  <label>
                    Limit pro Tag
                    <input name="daily" type="number" min={1} max={30} defaultValue={m.daily_limit} />
                  </label>
                  <label>
                    pro Woche
                    <input name="weekly" type="number" min={1} max={150} defaultValue={m.weekly_limit} />
                  </label>
                  <label className="pace-territory">
                    Gebiet (Orte oder PLZ-Anfänge, kommagetrennt)
                    <input name="territory" defaultValue={m.territory.join(", ")} placeholder="z. B. Lahr, 779" />
                  </label>
                  <label className="checkbox-line">
                    <input name="receives" type="checkbox" defaultChecked={m.receives_leads} /> bekommt neue Leads
                  </label>
                  <button className="button ghost small" disabled={busy}>
                    Speichern
                  </button>
                </form>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
