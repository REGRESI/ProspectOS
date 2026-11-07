"use client";
import { FormEvent, useEffect, useState } from "react";
import { request } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, ErrorNote, Heading, Modal } from "./ui";
import { SkeletonTable } from "./table";

type Write = <T>(path: string, body?: unknown, method?: string) => Promise<T>;
type Team = {
  members: { id: string; name: string; email: string; role: string; role_label: string; me: boolean }[];
  invites: { id: string; email: string; role_label: string; expires_at: string; expired: boolean }[];
  mail: "link" | "email";
  can_invite: boolean;
};

/* Settings → Team: invite users (Inhaber or Mitglied). There is no system mailing yet,
   so an invitation is a one-time link to copy. Each user has an own LinkedIn connection
   and an own writing profile. */
export function TeamPage({
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
  const { data, error, loading } = useData<Team>(`${base}/team`, revision);
  const [open, setOpen] = useState(false);
  const [link, setLink] = useState<{ link: string; email: string; role_label: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState("");
  const reload = () => setRevision((v) => v + 1);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setLocalError("");
    try {
      const result = await write<{ link: string; email: string; role_label: string }>("/team/invites", {
        email: form.get("email"),
        role: form.get("role"),
      });
      setLink(result);
      setOpen(false);
      reload();
    } catch (e) {
      setLocalError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function act(path: string, message: string) {
    setLocalError("");
    try {
      await write(path, undefined, "DELETE");
      notify(message);
      reload();
    } catch (e) {
      setLocalError((e as Error).message);
    }
  }
  return (
    <>
      <Heading
        title="Team"
        description="Wer in diesem Workspace arbeitet. Jede Person hat eine eigene LinkedIn-Verbindung und ein eigenes Schreibprofil."
      >
        {data?.can_invite && (
          <button className="button primary" onClick={() => setOpen(true)}>
            Person einladen
          </button>
        )}
      </Heading>
      <ErrorNote message={error || localError} />
      {link && (
        <div className="notice-box" data-testid="invite-link">
          <p>
            Einladung für <strong>{link.email}</strong> als {link.role_label}. Es gibt noch kein System-Mailing,
            schick den Link deshalb selbst. Er gilt 7 Tage und nur einmal.
          </p>
          <div className="copy-line">
            <input readOnly value={link.link} aria-label="Einladungslink" onFocus={(e) => e.currentTarget.select()} />
            <button
              className="button secondary"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(link.link);
                  notify("Link kopiert.");
                } catch {
                  notify("Kopieren ging nicht. Bitte den Link markieren und kopieren.");
                }
              }}
            >
              Link kopieren
            </button>
          </div>
        </div>
      )}
      {loading && !data ? (
        <SkeletonTable rows={3} cols={3} />
      ) : (
        <div className="table-wrap">
          <table className="data-table" data-testid="team-members">
            <thead>
              <tr>
                <th>Name</th>
                <th>E-Mail</th>
                <th>Rolle</th>
                <th className="align-right">Aktion</th>
              </tr>
            </thead>
            <tbody>
              {data?.members.map((m) => (
                <tr key={m.id}>
                  <td>
                    <strong>{m.name}</strong>
                    {m.me && <span className="muted"> · du</span>}
                  </td>
                  <td>{m.email}</td>
                  <td>
                    <Badge tone={m.role === "owner" ? "green" : "neutral"}>{m.role_label}</Badge>
                  </td>
                  <td className="align-right">
                    {myRole === "owner" && !m.me && (
                      <button
                        className="button ghost small danger"
                        onClick={() => act(`/team/members/${m.id}`, `${m.name} entfernt.`)}
                      >
                        Entfernen
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {data?.invites.map((i) => (
                <tr key={i.id}>
                  <td className="muted">Eingeladen</td>
                  <td>{i.email}</td>
                  <td>
                    <Badge tone="amber">{i.expired ? "Abgelaufen" : `${i.role_label}, offen`}</Badge>
                  </td>
                  <td className="align-right">
                    {data.can_invite && (
                      <button
                        className="button ghost small"
                        onClick={() => act(`/team/invites/${i.id}`, "Einladung zurückgezogen.")}
                      >
                        Zurückziehen
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && (
        <Modal title="Person einladen" onClose={() => setOpen(false)}>
          <form className="modal-form" onSubmit={invite}>
            <label>
              E-Mail-Adresse
              <input name="email" type="email" required autoComplete="off" />
            </label>
            <label>
              Rolle
              <select name="role" defaultValue="member">
                <option value="member">Mitglied: arbeitet mit, verwaltet keine Nutzer</option>
                {myRole === "owner" && <option value="owner">Inhaber: darf alles, auch Nutzer verwalten</option>}
              </select>
            </label>
            <p className="muted">Es wird keine E-Mail verschickt. Du bekommst einen Link zum Weitergeben.</p>
            <div className="modal-actions">
              <button type="button" className="button secondary" onClick={() => setOpen(false)}>
                Abbrechen
              </button>
              <button className="button primary" disabled={busy}>
                Link erstellen
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

type Preview = {
  email: string;
  workspace: string;
  role_label: string;
  has_account: boolean;
  can_register: boolean;
};

/* /einladung#<token>: accept an invitation. New users set name and password (local
   sign-in); existing users sign in first and accept. */
export function InvitePage({
  onJoined,
  csrf,
}: {
  onJoined: (workspaceId: string) => void;
  csrf?: string;
}) {
  const [token] = useState(() => (typeof window === "undefined" ? "" : window.location.hash.slice(1)));
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState(token ? "" : "Der Einladungslink ist unvollständig.");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!token) return;
    request<Preview>(`/v1/invites/${encodeURIComponent(token)}`)
      .then(setPreview)
      .catch((e) => setError((e as Error).message));
  }, [token]);
  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (form.get("password") !== form.get("repeat")) {
      setError("Die Passwörter stimmen nicht überein.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await request<{ workspace_id: string }>(`/v1/invites/${encodeURIComponent(token)}/register`, {
        method: "POST",
        body: JSON.stringify({ name: form.get("name"), password: form.get("password") }),
      });
      onJoined(result.workspace_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-card" aria-label="Einladung">
        <h1>Einladung</h1>
        <ErrorNote message={error} />
        {preview && (
          <>
            <p>
              Du wirst als <strong>{preview.role_label}</strong> in den Workspace <strong>{preview.workspace}</strong>{" "}
              eingeladen ({preview.email}).
            </p>
            {preview.can_register ? (
              <form className="login-form" onSubmit={register}>
                <label>
                  Dein Name
                  <input name="name" required minLength={2} autoComplete="name" />
                </label>
                <label>
                  Passwort (mindestens 10 Zeichen)
                  <input name="password" type="password" required minLength={10} autoComplete="new-password" />
                </label>
                <label>
                  Passwort wiederholen
                  <input name="repeat" type="password" required minLength={10} autoComplete="new-password" />
                </label>
                <button className="button primary login-submit" disabled={busy}>
                  Konto anlegen und beitreten
                </button>
              </form>
            ) : csrf ? (
              <button
                className="button primary login-submit"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    const r = await request<{ workspace_id: string }>(
                      `/v1/invites/${encodeURIComponent(token)}/accept`,
                      { method: "POST", body: "{}" },
                      csrf,
                    );
                    onJoined(r.workspace_id);
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Einladung annehmen
              </button>
            ) : (
              <p className="muted">
                Für diese Adresse gibt es schon ein Konto. Melde dich zuerst auf der Startseite an und öffne den
                Link danach noch einmal.
              </p>
            )}
          </>
        )}
      </section>
    </main>
  );
}
