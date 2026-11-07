"use client";
import { FormEvent, useState } from "react";
import { request, type Session, type Workspace } from "@/lib/api";
import { Badge, ErrorNote, Heading, Modal } from "./ui";

/* Settings → Workspaces: rename, archive and delete. Deleting asks for the exact name;
   the open and the last workspace cannot be deleted (the server checks it too). */

function kindLabel(w: Workspace) {
  if (w.kind === "production") return <Badge tone="green">Produktiv</Badge>;
  if (w.kind === "demo") return <Badge tone="amber">Demo</Badge>;
  return null;
}

export function WorkspacesAdmin({
  session,
  active,
  notify,
  onSessionChange,
}: {
  session: Session;
  active: Workspace;
  notify: (message: string) => void;
  onSessionChange: () => Promise<void> | void;
}) {
  const [renaming, setRenaming] = useState<Workspace | null>(null);
  const [deleting, setDeleting] = useState<Workspace | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const csrf = session.csrf_token;
  const total = session.workspaces.length;

  async function call(path: string, method: string, body: unknown) {
    setBusy(true);
    setError("");
    try {
      await request(path, { method, body: JSON.stringify(body) }, csrf);
      await onSessionChange();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function rename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!renaming) return;
    const name = String(new FormData(event.currentTarget).get("name") || "").trim();
    if (await call(`/v1/workspaces/${renaming.id}`, "PATCH", { name })) {
      notify("Workspace umbenannt.");
      setRenaming(null);
    }
  }

  async function archive(w: Workspace, archived: boolean) {
    if (
      await call(`/v1/workspaces/${w.id}/archive`, "POST", {
        archived,
        active_workspace_id: active.id,
      })
    )
      notify(archived ? "Workspace archiviert." : "Workspace wiederhergestellt.");
  }

  async function remove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!deleting) return;
    if (
      await call(`/v1/workspaces/${deleting.id}`, "DELETE", {
        confirm_name: typed,
        active_workspace_id: active.id,
      })
    ) {
      notify(`„${deleting.name}“ und alle Daten darin sind gelöscht.`);
      setDeleting(null);
      setTyped("");
    }
  }

  return (
    <>
      <Heading
        title="Workspaces"
        description="Umbenennen, archivieren oder löschen. Gelöschte Workspaces lassen sich nicht wiederherstellen."
      />
      <ErrorNote message={error} />
      <div className="table-wrap" data-testid="workspaces-admin">
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Art</th>
              <th>Status</th>
              <th className="align-right">Aktionen</th>
            </tr>
          </thead>
          <tbody>
            {session.workspaces.map((w) => {
              const isActive = w.id === active.id;
              const owner = w.role === "owner";
              return (
                <tr key={w.id} data-testid={`workspace-row-${w.slug}`}>
                  <td>
                    <strong>{w.name}</strong>
                    {isActive && <span className="muted"> · geöffnet</span>}
                  </td>
                  <td>{kindLabel(w) || <span className="muted">Standard</span>}</td>
                  <td>
                    {w.archived ? <Badge>Archiviert</Badge> : <Badge tone="neutral">Aktiv</Badge>}
                  </td>
                  <td className="align-right row-actions">
                    <button
                      className="button ghost small"
                      disabled={busy || !["owner", "admin"].includes(w.role)}
                      onClick={() => setRenaming(w)}
                    >
                      Umbenennen
                    </button>
                    {w.archived ? (
                      <button
                        className="button ghost small"
                        disabled={busy || !owner}
                        onClick={() => archive(w, false)}
                      >
                        Wiederherstellen
                      </button>
                    ) : (
                      <button
                        className="button ghost small"
                        disabled={busy || !owner || isActive}
                        title={isActive ? "Der geöffnete Workspace kann nicht archiviert werden." : undefined}
                        onClick={() => archive(w, true)}
                      >
                        Archivieren
                      </button>
                    )}
                    <button
                      className="button ghost small danger"
                      disabled={busy || !owner || isActive || total <= 1}
                      title={
                        isActive
                          ? "Der geöffnete Workspace kann nicht gelöscht werden."
                          : total <= 1
                            ? "Der letzte Workspace kann nicht gelöscht werden."
                            : undefined
                      }
                      onClick={() => {
                        setTyped("");
                        setDeleting(w);
                      }}
                    >
                      Löschen
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {renaming && (
        <Modal title="Workspace umbenennen" onClose={() => setRenaming(null)}>
          <form className="modal-form" onSubmit={rename}>
            <label>
              Neuer Name
              <input name="name" defaultValue={renaming.name} minLength={2} maxLength={120} required />
            </label>
            <div className="modal-actions">
              <button type="button" className="button secondary" onClick={() => setRenaming(null)}>
                Abbrechen
              </button>
              <button className="button primary" disabled={busy}>
                Speichern
              </button>
            </div>
          </form>
        </Modal>
      )}
      {deleting && (
        <Modal title="Workspace löschen" onClose={() => setDeleting(null)}>
          <form className="modal-form" onSubmit={remove}>
            <p>
              Alle Firmen, Kontakte, Texte, Bilder und der Verlauf in „{deleting.name}“ werden
              endgültig gelöscht. Zum Bestätigen den Namen eintippen.
            </p>
            <label>
              Name des Workspace
              <input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={deleting.name}
                autoComplete="off"
                aria-label="Name zur Bestätigung"
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="button secondary" onClick={() => setDeleting(null)}>
                Abbrechen
              </button>
              <button className="button danger" disabled={busy || typed.trim() !== deleting.name}>
                Endgültig löschen
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
