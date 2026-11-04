"use client";
import { CampaignEmail } from "./email-outreach";
import { FormEvent, useCallback, useState } from "react";
import { ArrowRight, ExternalLink, FileText, MessageSquare, Plus, ShieldCheck, Users } from "lucide-react";
import { request, dateTime } from "@/lib/api";
import type { Page } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Empty, ErrorNote, Heading, Modal, Spinner } from "./ui";
import type { JourneyProps, Lead, LeadFilters, Campaign, Draft } from "./journey-types";
import { initialLeadFilters } from "./journey-types";
import { CampaignAgent } from "./sales-agent";
import { useOptionalData } from "./journey-shared";
import { LeadProfile } from "./lead-database";

export type SequenceStep = {
  id?: string;
  position: number;
  delay_days: number;
  channel: "linkedin_manual" | "email";
  template: string;
  requires_approval?: boolean;
};

export type CampaignContext = {
  campaign: Campaign;
  sequence: SequenceStep[];
  audience: (Lead & { journey_status: string })[];
  drafts: Draft[];
  activities: {
    id: string;
    description: string;
    kind: string;
    created_at: string;
  }[];
  counts: {
    waiting: number;
    approved: number;
    completed: number;
    replied: number;
    suppressed: number;
  };
};

export function OutreachWorkbench(
  props: JourneyProps & { initialCampaignId?: string },
) {
  const { base, write, notify, onChange, revision, csrf, initialCampaignId } =
    props;
  const [active, setActive] = useState(initialCampaignId || "");
  const [tab, setTab] = useState<"campaign" | "inbox">(
    initialCampaignId ? "campaign" : "inbox",
  );
  const [create, setCreate] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [localRevision, setLocalRevision] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [leadId, setLeadId] = useState<string | null>(null);
  const campaigns = useData<Page<Campaign>>(
    `${base}/campaigns?limit=100`,
    revision + localRevision,
  );
  const workspace = useOptionalData<CampaignContext>(
    active ? `${base}/campaigns/${active}/workspace` : null,
    revision + localRevision,
  );
  const inbox = useData<Page<Draft>>(
    `${base}/outreach/inbox?limit=100`,
    revision + localRevision,
  );
  const contacts = useData<Page<Lead>>(`${base}/contacts?limit=100`, revision);
  const segments = useData<
    Page<{ id: string; name: string; filters: LeadFilters }>
  >(`${base}/segments?limit=100`, revision);
  const refresh = () => {
    setLocalRevision((v) => v + 1);
    onChange();
  };
  const closeCreate = useCallback(() => setCreate(false), []);
  async function createCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const form = new FormData(event.currentTarget);
      let ids = form.getAll("contacts").map(String);
      const segment = segments.data?.items.find(
        (s) => s.id === form.get("segment"),
      );
      if (segment) {
        const selection = await request<Page<Lead>>(
          `${base}/leads/query`,
          {
            method: "POST",
            body: JSON.stringify({
              ...initialLeadFilters,
              ...segment.filters,
              page: 1,
              limit: 100,
            }),
          },
          csrf,
        );
        ids = selection.items.map((c) => c.id);
      }
      const campaign = await write<Campaign>("/campaigns", {
        name: String(form.get("name")),
        goal: String(form.get("goal") || ""),
        status: "draft",
        contact_ids: ids,
      });
      setActive(campaign.id);
      setCreate(false);
      setTab("campaign");
      refresh();
      notify("Kampagne mit ausgewählter Zielgruppe angelegt.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function approve(item: Draft) {
    setBusy(true);
    setError("");
    try {
      await write(`/outreach/drafts/${item.id}/approve`);
      refresh();
      notify(
        "Aktuelle Nachrichtenrevision freigegeben. Es wurde nichts versendet.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function handoff(contactId: string, kind: string) {
    setBusy(true);
    setError("");
    try {
      await write("/outreach/handoffs", {
        contact_id: contactId,
        ...(active ? { campaign_id: active } : {}),
        kind,
        note: "Manuell im Outreach-Workspace dokumentiert.",
      });
      refresh();
      notify("Manueller Status als Selbstauskunft gespeichert.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const current = workspace.data;
  return (
    <>
      <Heading
        title="Outreach-Workspace"
        description="Zielgruppe, Sequenz, Entwürfe und manuelle Gespräche in einem durchgängigen Ablauf."
      >
        <button className="button primary" onClick={() => setCreate(true)}>
          <Plus size={16} /> Neue Kampagne
        </button>
      </Heading>
      <div className="tabs journey-tabs">
        <button
          className={`tab ${tab === "campaign" ? "active" : ""}`}
          onClick={() => setTab("campaign")}
        >
          Kampagnen & Sequenzen
        </button>
        <button
          className={`tab ${tab === "inbox" ? "active" : ""}`}
          onClick={() => setTab("inbox")}
        >
          Entwürfe & Freigaben <Badge>{inbox.data?.total || 0}</Badge>
        </button>
      </div>
      <ErrorNote
        message={error || campaigns.error || workspace.error || inbox.error}
      />
      <div className="info-note">
        <ShieldCheck size={18} />
        <p>
          <strong>Manueller Übergabepunkt.</strong> LinkedIn bleibt ein
          manueller Handoff. Ein Kontaktstatus ist keine Werbeeinwilligung.
          E-Mail benötigt geprüfte Herkunft, gültigen Nachweis, Freigabe,
          Provider und eine letzte Sperrlistenprüfung.
        </p>
      </div>
      {tab === "inbox" ? (
        <section className="panel">
          <div className="panel-head">
            <h2>Zentraler Posteingang für Entwürfe</h2>
            <Badge>Kein Versand durch Entwurf</Badge>
          </div>
          {inbox.loading ? (
            <div className="loading-block">
              <Spinner />
            </div>
          ) : inbox.data?.items.length ? (
            <div className="journey-draft-inbox">
              {inbox.data.items.map((item) => (
                <article
                  className="journey-draft-card outreach-card"
                  key={item.id}
                >
                  <div className="section-title">
                    <h3>
                      {item.contact
                        ? `${item.contact.first_name} ${item.contact.last_name}`
                        : "Kontaktentwurf"}
                    </h3>
                    <Badge
                      tone={
                        item.approved_revision === item.revision
                          ? "green"
                          : "neutral"
                      }
                    >
                      {item.approved_revision === item.revision
                        ? "Freigegeben"
                        : "Prüfung erforderlich"}
                    </Badge>
                  </div>
                  <small>
                    {item.campaign?.name || "Ohne Kampagnenzuordnung"} ·
                    Revision {item.revision}
                  </small>
                  <p className="journey-draft-text">{item.content}</p>
                  {item.blocked_reasons?.map((reason, i) => (
                    <p className="small muted" key={i}>
                      {reason}
                    </p>
                  ))}
                  <div className="form-actions">
                    <button
                      className="button secondary small"
                      onClick={() => setDraft(item)}
                    >
                      Prüfen & bearbeiten
                    </button>
                    <button
                      className="button secondary small"
                      onClick={() => setLeadId(item.contact_id)}
                    >
                      Kontaktprofil
                    </button>
                    {item.state === "draft" && (
                      <button
                        className="button primary small"
                        disabled={busy}
                        onClick={() => approve(item)}
                      >
                        Revision freigeben
                      </button>
                    )}
                    {item.contact?.linkedin_url && (
                      <a
                        className="button secondary small"
                        href={item.contact.linkedin_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={() =>
                          handoff(item.contact_id, "profile_opened")
                        }
                      >
                        LinkedIn manuell öffnen <ExternalLink size={13} />
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              icon={MessageSquare}
              title="Noch keine Entwürfe zur Prüfung"
              description="Wähle eine Kampagne, ergänze ihre Sequenz und erstelle nachvollziehbare Entwürfe."
            />
          )}
        </section>
      ) : (
        <div className="journey-outreach-layout">
          <aside className="panel">
            <div className="panel-head">
              <h2>Kampagnen</h2>
              <Badge>{campaigns.data?.total || 0}</Badge>
            </div>
            <div className="journey-campaign-list">
              {campaigns.data?.items.length ? (
                campaigns.data.items.map((item) => (
                  <button
                    className={`journey-campaign-item ${active === item.id ? "active" : ""}`}
                    key={item.id}
                    onClick={() => setActive(item.id)}
                  >
                    <strong>{item.name}</strong>
                    <span>
                      {item.contacts} Kontakte{" "}
                      <Badge>
                        {(
                          {
                            draft: "Entwurf",
                            active: "Aktiv",
                            paused: "Pausiert",
                            completed: "Abgeschlossen",
                          } as Record<string, string>
                        )[item.status] || item.status}
                      </Badge>
                    </span>
                  </button>
                ))
              ) : (
                <p className="muted">
                  Beginne mit einer klaren Zielgruppe und einem Gesprächsziel.
                </p>
              )}
            </div>
          </aside>
          <div>
            {!active ? (
              <section className="panel">
                <Empty
                  icon={Users}
                  title="Eine Kampagne auswählen"
                  description="Definiere Ziel und Publikum, plane deine Sequenz und prüfe jeden Nachrichtenentwurf."
                >
                  <button
                    className="button primary"
                    onClick={() => setCreate(true)}
                  >
                    Erste Kampagne anlegen
                  </button>
                </Empty>
              </section>
            ) : workspace.loading ? (
              <section className="panel loading-block">
                <Spinner />
              </section>
            ) : (
              current && (
                <>
                  <section className="panel journey-campaign-summary">
                    <div className="panel-head">
                      <div>
                        <h2>{current.campaign.name}</h2>
                        <p>
                          {current.campaign.goal ||
                            "Noch kein Gesprächsziel hinterlegt."}
                        </p>
                      </div>
                      <select
                        aria-label="Kampagnenstatus"
                        value={current.campaign.status}
                        disabled={busy}
                        onChange={async (e) => {
                          setBusy(true);
                          try {
                            await write(
                              `/campaigns/${active}`,
                              { status: e.target.value },
                              "PATCH",
                            );
                            refresh();
                          } catch (error) {
                            setError((error as Error).message);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        <option value="draft">Entwurf</option>
                        <option value="active">Aktiv</option>
                        <option value="paused">Pausiert</option>
                        <option value="completed">Abgeschlossen</option>
                      </select>
                    </div>
                    <div className="journey-progress-counts">
                      {[
                        ["waiting", "Wartend"],
                        ["approved", "Freigegeben"],
                        ["completed", "Manuell erledigt"],
                        ["replied", "Antwort notiert"],
                        ["suppressed", "Gesperrt"],
                      ].map(([key, label]) => (
                        <div key={key}>
                          <strong>
                            {
                              current.counts[
                                key as keyof CampaignContext["counts"]
                              ]
                            }
                          </strong>
                          <small>{label}</small>
                        </div>
                      ))}
                    </div>
                  </section>
                  <SequenceEditor
                    key={`${active}:${localRevision}`}
                    steps={current.sequence}
                    channel={current.campaign.channel || "linkedin_manual"}
                    busy={busy}
                    onSave={async (channel, steps) => {
                      setBusy(true);
                      setError("");
                      try {
                        await write(
                          `/campaigns/${active}/sequence`,
                          { channel, steps },
                          "PUT",
                        );
                        refresh();
                        notify(
                          "Sequenz gespeichert. Keine Nachrichten versendet.",
                        );
                      } catch (error) {
                        setError((error as Error).message);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  />
                  <CampaignAgent
                    {...props}
                    campaignId={active}
                    onRefresh={refresh}
                  />
                  <CampaignEmail
                    base={props.base}
                    write={props.write}
                    campaignId={active}
                  />
                  <section className="panel">
                    <div className="panel-head">
                      <div>
                        <h2>Zielgruppe & Kontaktreise</h2>
                        <p>
                          Jeder manuelle Status ist als Selbstauskunft
                          gekennzeichnet.
                        </p>
                      </div>
                      <button
                        className="button primary small"
                        disabled={
                          busy ||
                          !current.audience.length ||
                          ["paused", "completed"].includes(
                            current.campaign.status,
                          )
                        }
                        onClick={async () => {
                          setBusy(true);
                          try {
                            const result = await write<{
                              created: number;
                              duplicates: number;
                              notice: string;
                            }>(`/campaigns/${active}/generate-drafts`);
                            refresh();
                            notify(
                              result.notice ||
                                `${result.created} Entwürfe erstellt, ${result.duplicates} bereits vorhanden.`,
                            );
                          } catch (error) {
                            setError((error as Error).message);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        <FileText size={14} /> Entwürfe aus Sequenz erstellen
                      </button>
                    </div>
                    {current.audience.length ? (
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Kontakt</th>
                              <th>Unternehmen</th>
                              <th>Status</th>
                              <th>Manuellen Verlauf dokumentieren</th>
                            </tr>
                          </thead>
                          <tbody>
                            {current.audience.map((lead) => (
                              <tr key={lead.id}>
                                <td>
                                  <button
                                    className="journey-link"
                                    onClick={() => setLeadId(lead.id)}
                                  >
                                    {lead.first_name} {lead.last_name}
                                  </button>
                                </td>
                                <td>{lead.company || "—"}</td>
                                <td>
                                  <Badge>{lead.journey_status}</Badge>
                                </td>
                                <td>
                                  <select
                                    aria-label={`Manueller Verlauf für ${lead.first_name} ${lead.last_name}`}
                                    value=""
                                    disabled={busy}
                                    onChange={(e) =>
                                      handoff(lead.id, e.target.value)
                                    }
                                  >
                                    <option value="">
                                      Aktion als Selbstauskunft notieren
                                    </option>
                                    <option value="profile_opened">
                                      Profil geöffnet
                                    </option>
                                    <option value="connection_requested">
                                      Kontaktanfrage manuell gestellt
                                    </option>
                                    <option value="connected">
                                      Verbindung manuell bestätigt
                                    </option>
                                    <option value="message_sent_manually">
                                      Nachricht selbst gesendet
                                    </option>
                                    <option value="replied">
                                      Antwort selbst erfasst
                                    </option>
                                    <option value="followup_due">
                                      Follow-up erforderlich
                                    </option>
                                  </select>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <Empty
                        icon={Users}
                        title="Noch keine Kontakte zugeordnet"
                        description="Öffne die Kontaktdatenbank und ordne ausgewählte Kontakte per Sammelaktion zu."
                      />
                    )}
                  </section>
                  <section className="panel">
                    <div className="panel-head">
                      <h2>Entwürfe dieser Kampagne</h2>
                      <button
                        className="button secondary small"
                        onClick={() => setTab("inbox")}
                      >
                        Zur Freigabe-Inbox <ArrowRight size={13} />
                      </button>
                    </div>
                    <div className="journey-draft-inbox">
                      {current.drafts.length ? (
                        current.drafts.map((item) => (
                          <article
                            className="journey-draft-card outreach-card"
                            key={item.id}
                          >
                            <div className="section-title">
                              <h3>
                                {current.audience.find(
                                  (c) => c.id === item.contact_id,
                                )?.first_name || "Nachricht"}
                              </h3>
                              <Badge
                                tone={
                                  item.approved_revision === item.revision
                                    ? "green"
                                    : "neutral"
                                }
                              >
                                {item.approved_revision === item.revision
                                  ? "Freigegeben"
                                  : "Entwurf"}
                              </Badge>
                            </div>
                            <p className="journey-draft-text">{item.content}</p>
                            <div className="form-actions">
                              <button
                                className="button secondary small"
                                onClick={() => setDraft(item)}
                              >
                                Entwurf prüfen
                              </button>
                              {item.state === "draft" && (
                                <button
                                  className="button primary small"
                                  disabled={busy}
                                  onClick={() => approve(item)}
                                >
                                  Revision freigeben
                                </button>
                              )}
                            </div>
                          </article>
                        ))
                      ) : (
                        <p className="muted">
                          Die Sequenz liefert Vorlagen. Erst die bewusste
                          Erstellung legt Kontaktentwürfe an.
                        </p>
                      )}
                    </div>
                  </section>
                  <section className="panel">
                    <div className="panel-head">
                      <h2>Kommunikationsverlauf</h2>
                    </div>
                    <div className="journey-timeline">
                      {current.activities.length ? (
                        current.activities.map((item) => (
                          <article key={item.id}>
                            <p>{item.description}</p>
                            <small>
                              {dateTime(item.created_at)} · {item.kind}
                            </small>
                          </article>
                        ))
                      ) : (
                        <p className="muted">
                          Noch keine manuellen Aktivitäten dokumentiert.
                        </p>
                      )}
                    </div>
                  </section>
                </>
              )
            )}
          </div>
        </div>
      )}
      {create && (
        <Modal title="Kampagne anlegen" onClose={closeCreate} wide>
          <form className="modal-body" onSubmit={createCampaign}>
            <div className="form-grid">
              <label>
                Kampagnenname
                <input name="name" required maxLength={200} />
              </label>
              <label>
                Gesprächsziel
                <input name="goal" maxLength={1000} />
              </label>
            </div>
            <label>
              Gespeichertes Segment
              <select name="segment">
                <option value="">Kontakte unten manuell auswählen</option>
                {segments.data?.items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="small muted">
              Bis zu 100 ausgewählte Kontakte. Bei einem Segment wird der
              aktuelle Filterstand übernommen.
            </p>
            <div className="journey-audience-picker">
              {contacts.data?.items.map((lead) => (
                <label className="checkbox-line" key={lead.id}>
                  <input type="checkbox" name="contacts" value={lead.id} />
                  <span>
                    {lead.first_name} {lead.last_name}
                    <small>
                      {lead.company || lead.job_title || "Keine Firmendaten"}
                    </small>
                  </span>
                </label>
              ))}
            </div>
            <ErrorNote message={error} />
            <div className="form-actions">
              <button
                type="button"
                className="button secondary"
                onClick={closeCreate}
              >
                Abbrechen
              </button>
              <button className="button primary" disabled={busy}>
                Kampagne anlegen
              </button>
            </div>
          </form>
        </Modal>
      )}
      {draft && (
        <DraftReview
          item={draft}
          write={write}
          onClose={() => setDraft(null)}
          onSaved={() => {
            setDraft(null);
            refresh();
            notify("Entwurf gespeichert. Vorherige Freigabe ist ungültig.");
          }}
        />
      )}
      {leadId && (
        <LeadProfile
          {...props}
          contactId={leadId}
          onClose={() => setLeadId(null)}
          onUpdated={refresh}
        />
      )}
    </>
  );
}

export function SequenceEditor({
  steps,
  channel,
  busy,
  onSave,
}: {
  steps: SequenceStep[];
  channel: "linkedin_manual" | "email";
  busy: boolean;
  onSave: (
    channel: "linkedin_manual" | "email",
    steps: SequenceStep[],
  ) => Promise<void>;
}) {
  const [selectedChannel, setSelectedChannel] = useState(channel);
  const [items, setItems] = useState<SequenceStep[]>(
    steps.length
      ? steps
      : [
          {
            position: 1,
            delay_days: 0,
            channel,
            template:
              "Hallo {{first_name}},\n\nwelche Themen beschäftigen Ihr Team bei {{company}} aktuell?",
          },
        ],
  );
  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Geplante Gesprächssequenz</h2>
          <p>
            Vorlagen sind Planungshilfen. Kein Schritt sendet automatisch eine
            LinkedIn-Nachricht.
          </p>
        </div>
        <select
          aria-label="Kampagnenkanal"
          value={selectedChannel}
          onChange={(e) => setSelectedChannel(e.target.value as typeof channel)}
        >
          <option value="linkedin_manual">LinkedIn · manuell</option>
          <option value="email">E-Mail · Policy-Prüfung erforderlich</option>
        </select>
      </div>
      <div className="journey-sequence">
        <p className="small muted">
          Verfügbare Variablen:{" "}
          {"{{first_name}}, {{last_name}}, {{company}}, {{job_title}}, {{evidence}}"}.
          {"{{evidence}}"} wird nur bei „Mit Belegen personalisieren“ mit bis zu
          zwei zitierten Unternehmensangaben gefüllt. Unbekannte Fakten werden
          nicht ergänzt.
        </p>
        {items.map((step, index) => (
          <article className="journey-sequence-step" key={index}>
            <span className="journey-step-number">{index + 1}</span>
            <div>
              <div className="section-title">
                <h3>
                  {index === 0 ? "Erste Nachricht" : `Follow-up ${index}`}
                </h3>
                <Badge>Freigabe erforderlich</Badge>
              </div>
              <label>
                Warten in Tagen
                <input
                  type="number"
                  min={0}
                  max={90}
                  value={step.delay_days}
                  onChange={(e) =>
                    setItems((old) =>
                      old.map((s, i) =>
                        i === index
                          ? { ...s, delay_days: Number(e.target.value) }
                          : s,
                      ),
                    )
                  }
                />
              </label>
              <label>
                Nachrichtenvorlage
                <textarea
                  rows={4}
                  value={step.template}
                  onChange={(e) =>
                    setItems((old) =>
                      old.map((s, i) =>
                        i === index ? { ...s, template: e.target.value } : s,
                      ),
                    )
                  }
                  maxLength={3000}
                />
              </label>
              {items.length > 1 && (
                <button
                  className="button secondary small"
                  onClick={() =>
                    setItems((old) => old.filter((_, i) => i !== index))
                  }
                >
                  Schritt entfernen
                </button>
              )}
            </div>
          </article>
        ))}
        <div className="form-actions">
          <button
            className="button secondary"
            disabled={items.length >= 8 || busy}
            onClick={() =>
              setItems((old) => [
                ...old,
                {
                  position: old.length + 1,
                  delay_days: 3,
                  channel: selectedChannel,
                  template:
                    "Hallo {{first_name}},\n\nich möchte mich noch einmal zu meiner vorherigen Nachricht melden.",
                },
              ])
            }
          >
            Schritt ergänzen
          </button>
          <button
            className="button primary"
            disabled={busy || items.some((s) => !s.template.trim())}
            onClick={() =>
              onSave(
                selectedChannel,
                items.map((s, i) => ({
                  position: i + 1,
                  delay_days: s.delay_days,
                  channel: selectedChannel,
                  template: s.template,
                })),
              )
            }
          >
            Sequenz speichern
          </button>
        </div>
      </div>
    </section>
  );
}

export function DraftReview({
  item,
  write,
  onClose,
  onSaved,
}: {
  item: Draft;
  write: JourneyProps["write"];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [content, setContent] = useState(item.content);
  const [subject, setSubject] = useState(
    item.subject || "Gespräch vorbereiten",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal title="Nachrichtenrevision prüfen" onClose={onClose} wide>
      <form
        className="modal-body"
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          try {
            await write(
              `/outreach/drafts/${item.id}`,
              { content, subject, revision: item.revision },
              "PATCH",
            );
            onSaved();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Badge>
          Revision {item.revision} ·{" "}
          {item.source === "offline"
            ? "Offline-Vorlage"
            : item.source || "Benutzereingabe"}
        </Badge>
        <label>
          Betreff / interner Nachrichtentitel
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            required
            maxLength={200}
          />
        </label>
        <label>
          Nachrichteninhalt
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={8}
            required
            maxLength={3000}
          />
        </label>
        <p className="small muted">
          Speichern erhöht die Revision und hebt bestehende Freigaben auf. Eine
          Freigabe versendet keine Nachricht.
        </p>
        <ErrorNote message={error} />
        <div className="form-actions">
          <button type="button" className="button secondary" onClick={onClose}>
            Abbrechen
          </button>
          <button className="button primary" disabled={busy}>
            Revision speichern
          </button>
        </div>
      </form>
    </Modal>
  );
}
