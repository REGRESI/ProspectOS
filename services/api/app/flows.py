"""V3 M2: campaign builder ("Baukasten") with per-contact runs and due tasks in "Heute".

A campaign holds ordered steps. Action steps (LinkedIn task, letter, call, visit, e-mail)
become tasks for a person; ProspectOS never performs them on an external platform. ``wait``
pauses a run for some days; ``condition`` branches on whether the contact reacted.

Each step has a route filter (``any``, ``linkedin``, ``letter``). A run follows the
contact's single active route from M1, so one recipe can carry a LinkedIn path and a
letter path and each contact walks exactly one of them.

Runs keep a cursor (a step position number), not a copy of the steps. Steps are read fresh
every time a run advances, so edits to a running campaign apply from the next due step.
Before every task the channel permission is checked again (objection, legal basis);
a blocked task is shown with its reason instead of silently disappearing.
"""

from datetime import datetime, timedelta

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now
from app.models import Company, Contact, TenantMixin
from app.platform_models import Campaign, Enrollment

STEP_KINDS = {
    "linkedin_task": "LinkedIn-Aufgabe",
    "letter": "Brief",
    "call_task": "Anruf",
    "visit_task": "Besuch vor Ort",
    "email": "E-Mail",
    "wait": "Warten",
    "condition": "Bedingung",
}
ACTION_CHANNEL = {
    "linkedin_task": "linkedin",
    "letter": "letter",
    "call_task": "phone",
    "visit_task": "visit",
    "email": "email",
}
ROUTE_FILTERS = ("any", "linkedin", "letter")
MAX_ITERATIONS = 25

RECIPES = {
    "office_linkedin": {
        "name": "Büro Ortenau mit LinkedIn",
        "goal": "Gespräch über Büro-Unterhaltsreinigung",
        "description": "Mit geprüftem Profil: vernetzen, Nachricht, Follow-up. Ohne Profil: Brief und Besuch.",
        "steps": [
            (
                "linkedin_task",
                "linkedin",
                0,
                "Vernetzen: Profil öffnen, Notiz kopieren, selbst senden",
                "",
            ),
            ("wait", "linkedin", 4, "", ""),
            ("condition", "linkedin", 0, "Reaktion?", ""),
            ("linkedin_task", "linkedin", 0, "Nachricht nach Annahme senden", ""),
            ("wait", "linkedin", 7, "", ""),
            ("linkedin_task", "linkedin", 0, "Kurzes Follow-up", ""),
            ("letter", "letter", 0, "Persönlichen Brief schicken", ""),
            ("wait", "letter", 10, "", ""),
            ("condition", "letter", 0, "Reaktion?", ""),
            ("visit_task", "letter", 0, "Vorbeischauen mit Leistungsmappe", ""),
        ],
    },
    "letter_only": {
        "name": "Ohne LinkedIn: Brief, Besuch, zweiter Brief",
        "goal": "Erstkontakt per Brief für Firmen ohne LinkedIn",
        "description": "Brief mit QR-Code, nach 10 Tagen Besuch, nach 14 Tagen ein zweiter Brief.",
        "steps": [
            ("letter", "any", 0, "Persönlichen Brief schicken", ""),
            ("wait", "any", 10, "", ""),
            ("condition", "any", 0, "Reaktion?", ""),
            ("visit_task", "any", 0, "Vorbeischauen mit Leistungsmappe", ""),
            ("wait", "any", 14, "", ""),
            ("condition", "any", 0, "Reaktion?", ""),
            ("letter", "any", 0, "Zweiten Brief schicken", ""),
        ],
    },
    "after_reply": {
        "name": "Nach Antwort: Termin",
        "goal": "Termin vereinbaren",
        "description": "Anrufen und Termin vereinbaren, nach 2 Tagen nachfassen.",
        "steps": [
            ("call_task", "any", 0, "Anrufen und Termin vereinbaren", ""),
            ("wait", "any", 2, "", ""),
            ("call_task", "any", 0, "Nachfassen, falls noch kein Termin", ""),
        ],
    },
}


class FlowStep(TenantMixin, Base):
    __tablename__ = "flow_steps"
    campaign_id: Mapped[str] = mapped_column(String(36))
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    route: Mapped[str] = mapped_column(String(10), default="any")
    wait_days: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200), default="")
    template: Mapped[str] = mapped_column(String(3000), default="")
    # condition: {"if_reaction": "stop" | <position>, "if_none": "next" | <position>}
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("workspace_id", "campaign_id", "position"),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
        ),
    )


class FlowRun(TenantMixin, Base):
    __tablename__ = "flow_runs"
    campaign_id: Mapped[str] = mapped_column(String(36))
    contact_id: Mapped[str] = mapped_column(String(36))
    cursor: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(20), default="active")
    wait_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[str] = mapped_column(String(300), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("workspace_id", "campaign_id", "contact_id"),
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
    )


class FlowTask(TenantMixin, Base):
    __tablename__ = "flow_tasks"
    run_id: Mapped[str | None] = mapped_column(String(36))
    campaign_id: Mapped[str | None] = mapped_column(String(36))
    contact_id: Mapped[str] = mapped_column(String(36))
    step_position: Mapped[int | None] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(3000), default="")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    state: Mapped[str] = mapped_column(String(20), default="open")
    blocked_reason: Mapped[str] = mapped_column(String(300), default="")
    assignee_id: Mapped[str | None] = mapped_column(String(36))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_by: Mapped[str | None] = mapped_column(String(36))
    note: Mapped[str] = mapped_column(String(1000), default="")
    origin: Mapped[str] = mapped_column(String(30), default="flow")
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["flow_runs.workspace_id", "flow_runs.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "assignee_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "done_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class StepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int = Field(ge=0, le=99)
    kind: str
    route: str = "any"
    wait_days: int = Field(default=0, ge=0, le=180)
    title: str = Field(default="", max_length=200)
    template: str = Field(default="", max_length=3000)
    config: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid(self):
        if self.kind not in STEP_KINDS or self.route not in ROUTE_FILTERS:
            raise ValueError("Unbekannte Schrittart oder Weg")
        if self.kind == "wait" and self.wait_days < 1:
            raise ValueError("Warten braucht mindestens einen Tag")
        if self.kind == "condition":
            reaction = self.config.get("if_reaction", "stop")
            none = self.config.get("if_none", "next")
            for value, word in ((reaction, "stop"), (none, "next")):
                if value != word and not (isinstance(value, int) and 0 <= value <= 99):
                    raise ValueError("Bedingung braucht ein gültiges Sprungziel")
            self.config = {"if_reaction": reaction, "if_none": none}
        elif self.config:
            raise ValueError("Nur Bedingungen haben Einstellungen")
        return self


class FlowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[StepInput] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def unique(self):
        if len({s.position for s in self.steps}) != len(self.steps):
            raise ValueError("Positionen müssen eindeutig sein")
        return self


class RecipeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: str
    name: str = Field(default="", max_length=200)
    contact_ids: list[str] = Field(default_factory=list, max_length=1000)
    # Instead of ids: every contact with this route that is not in another active run.
    audience: str = Field(default="", pattern="^(|routed|linkedin|letter)$")
    start: bool = True


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_ids: list[str] = Field(default_factory=list, max_length=1000)


class DoneInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(default="", max_length=1000)


def steps_of(db, ws, campaign_id) -> list[FlowStep]:
    return list(
        db.scalars(
            select(FlowStep)
            .where(FlowStep.workspace_id == ws, FlowStep.campaign_id == campaign_id)
            .order_by(FlowStep.position)
        )
    )


def has_reaction(db, ws, contact_id, since) -> bool:
    """Any reaction of this contact since ``since`` (all channels)."""
    try:
        from app.reactions import Reaction
    except ImportError:  # before M3: the LinkedIn stage is the only reaction signal
        contact = db.get(Contact, contact_id)
        return bool(contact and contact.outreach_stage in ("replied", "meeting"))

    return bool(
        db.scalar(
            select(Reaction.id).where(
                Reaction.workspace_id == ws,
                Reaction.contact_id == contact_id,
                Reaction.created_at >= since,
            )
        )
    )


def render(template: str, contact: Contact, company: Company | None) -> str:
    values = {
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "company": company.name if company else "",
        "job_title": contact.job_title,
    }
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value or "")
    return out


def _stop(run: FlowRun, reason: str, state="stopped"):
    run.state, run.stop_reason, run.next_due_at, run.wait_until = state, reason[:300], None, None


def advance(db, ws, run: FlowRun, at: datetime | None = None) -> FlowRun:
    """Move a run forward until it waits, has an open task, or ends."""
    from app.multichannel import channel_permissions, suppression_of

    at = at or now()
    if run.state not in ("active", "waiting"):
        return run
    campaign = db.get(Campaign, run.campaign_id)
    if campaign is None or campaign.status in ("paused", "completed"):
        return run
    contact = db.get(Contact, run.contact_id)
    if contact is None:
        _stop(run, "Kontakt gelöscht")
        return run
    if suppression_of(db, ws, contact.id):
        _stop(run, "Widerspruch")
        return run
    if db.scalar(
        select(FlowTask.id).where(
            FlowTask.run_id == run.id, FlowTask.state.in_(["open", "blocked"])
        )
    ):
        return run
    company = db.get(Company, contact.company_id) if contact.company_id else None
    for _ in range(MAX_ITERATIONS):
        step = next(
            (s for s in steps_of(db, ws, run.campaign_id) if s.position >= run.cursor), None
        )
        if step is None:
            _stop(run, "Alle Schritte erledigt", "completed")
            return run
        if step.route != "any" and step.route != contact.channel_route:
            run.cursor = step.position + 1
            continue
        if step.kind == "wait":
            if run.wait_until is None:
                run.wait_until = at + timedelta(days=step.wait_days)
            if at < run.wait_until:
                run.state, run.next_due_at = "waiting", run.wait_until
                return run
            run.wait_until, run.state = None, "active"
            run.cursor = step.position + 1
            continue
        if step.kind == "condition":
            reacted = has_reaction(db, ws, contact.id, run.started_at)
            target = step.config.get("if_reaction" if reacted else "if_none")
            if target == "stop":
                _stop(run, "Reaktion erhalten" if reacted else "Bedingung: Ende")
                return run
            run.cursor = step.position + 1 if target == "next" else int(target)
            if run.cursor <= step.position:
                _stop(run, "Bedingung springt zurück; Lauf beendet, um Schleifen zu vermeiden")
                return run
            continue
        permission = channel_permissions(db, ws, contact)[ACTION_CHANNEL[step.kind]]
        db.add(
            FlowTask(
                workspace_id=ws,
                run_id=run.id,
                campaign_id=run.campaign_id,
                contact_id=contact.id,
                step_position=step.position,
                kind=step.kind,
                title=step.title or STEP_KINDS[step.kind],
                body=render(step.template, contact, company)[:3000],
                due_at=at,
                state="open" if permission["allowed"] else "blocked",
                blocked_reason="" if permission["allowed"] else (permission["reason"] or "")[:300],
                assignee_id=contact.owner_id,
            )
        )
        run.state, run.next_due_at = "active", at
        db.flush()
        return run
    _stop(run, "Zu viele Schritte ohne Aufgabe")
    return run


def tick(db, ws, at=None, limit=500) -> int:
    """Advance runs whose waiting time is over. Called by the worker and lazily by reads."""
    at = at or now()
    runs = db.scalars(
        select(FlowRun)
        .where(
            FlowRun.workspace_id == ws,
            FlowRun.state.in_(["active", "waiting"]),
            (FlowRun.next_due_at.is_(None)) | (FlowRun.next_due_at <= at),
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for run in runs:
        advance(db, ws, run, at)
    return len(runs)


def start_runs(db, ws, campaign: Campaign, contact_ids=None) -> dict:
    stmt = (
        select(Contact)
        .join(Enrollment, Enrollment.contact_id == Contact.id)
        .where(Enrollment.workspace_id == ws, Enrollment.campaign_id == campaign.id)
    )
    if contact_ids:
        stmt = stmt.where(Contact.id.in_(contact_ids))
    started = skipped = 0
    for contact in db.scalars(stmt):
        if db.scalar(
            select(FlowRun.id).where(
                FlowRun.campaign_id == campaign.id, FlowRun.contact_id == contact.id
            )
        ):
            skipped += 1
            continue
        run = FlowRun(
            workspace_id=ws, campaign_id=campaign.id, contact_id=contact.id, started_at=now()
        )
        db.add(run)
        db.flush()
        if contact.channel_route == "none":
            _stop(run, "Kein Weg: weder geprüftes Profil noch Postadresse")
        else:
            advance(db, ws, run)
        started += 1
    if campaign.status == "draft":
        campaign.status = "active"
    return {"started": started, "already_running": skipped}


def stop_runs(db, ws, contact_id, reason) -> int:
    count = 0
    for run in db.scalars(
        select(FlowRun).where(
            FlowRun.workspace_id == ws,
            FlowRun.contact_id == contact_id,
            FlowRun.state.in_(["active", "waiting"]),
        )
    ):
        _stop(run, reason)
        count += 1
    for task in db.scalars(
        select(FlowTask).where(
            FlowTask.workspace_id == ws,
            FlowTask.contact_id == contact_id,
            FlowTask.state.in_(["open", "blocked"]),
            FlowTask.origin == "flow",
        )
    ):
        task.state, task.note = "cancelled", reason[:1000]
    return count


def task_output(db, task: FlowTask, contact: Contact | None = None, company=None) -> dict:
    contact = contact or db.get(Contact, task.contact_id)
    company = (
        company
        if company is not None
        else (db.get(Company, contact.company_id) if contact and contact.company_id else None)
    )
    campaign = db.get(Campaign, task.campaign_id) if task.campaign_id else None
    return {
        "id": task.id,
        "kind": task.kind,
        "kind_label": STEP_KINDS.get(task.kind, task.kind),
        "title": task.title,
        "body": task.body,
        "due_at": task.due_at,
        "state": task.state,
        "blocked_reason": task.blocked_reason,
        "origin": task.origin,
        "assignee_id": task.assignee_id,
        "note": task.note,
        "campaign": {"id": campaign.id, "name": campaign.name} if campaign else None,
        "contact": {
            "id": contact.id,
            "name": f"{contact.first_name} {contact.last_name}".strip(),
            "route": contact.channel_route,
            "linkedin_url": contact.linkedin_url,
            "phone": contact.phone,
        }
        if contact
        else None,
        "company": {"id": company.id, "name": company.name, "location": company.location}
        if company
        else None,
    }


def complete_task(db, ws, task: FlowTask, actor_id: str, state="done", note="") -> None:
    task.state, task.done_at, task.done_by, task.note = state, now(), actor_id, note
    if task.run_id:
        run = db.get(FlowRun, task.run_id)
        if run and run.state in ("active", "waiting"):
            run.cursor = (task.step_position or 0) + 1
            db.flush()
            advance(db, ws, run)


def register_flow_routes(app, db_session, scope, record, audit):
    from app.multichannel import STOP_HOOKS

    STOP_HOOKS["flows"] = stop_runs

    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Bearbeitungsrecht erforderlich.")

    def flow_output(db, ws, campaign):
        steps = steps_of(db, ws, campaign.id)
        runs = db.scalars(select(FlowRun).where(FlowRun.campaign_id == campaign.id)).all()
        open_tasks = db.execute(
            select(FlowTask.step_position, func.count())
            .where(FlowTask.campaign_id == campaign.id, FlowTask.state.in_(["open", "blocked"]))
            .group_by(FlowTask.step_position)
        ).all()
        at_step = dict(open_tasks)
        return {
            "campaign": {
                "id": campaign.id,
                "name": campaign.name,
                "goal": campaign.goal,
                "status": campaign.status,
            },
            "steps": [
                {
                    "id": s.id,
                    "position": s.position,
                    "kind": s.kind,
                    "kind_label": STEP_KINDS[s.kind],
                    "route": s.route,
                    "wait_days": s.wait_days,
                    "title": s.title,
                    "template": s.template,
                    "config": s.config,
                    "open_tasks": at_step.get(s.position, 0),
                    "waiting": sum(
                        1
                        for r in runs
                        if r.state == "waiting"
                        and next((x for x in steps if x.position >= r.cursor), None) is s
                    ),
                }
                for s in steps
            ],
            "runs": {
                state: sum(1 for r in runs if r.state == state)
                for state in ("active", "waiting", "stopped", "completed")
            },
            "stopped": [
                {"contact_id": r.contact_id, "reason": r.stop_reason}
                for r in runs
                if r.state == "stopped"
            ][:50],
            "kinds": STEP_KINDS,
            "notice": "Änderungen gelten ab dem nächsten fälligen Schritt. ProspectOS führt keine "
            "Schritte auf LinkedIn oder per Post selbst aus; jede Aktion ist eine Aufgabe für dich.",
        }

    @app.get("/v1/workspaces/{ws}/flow-recipes")
    def recipes(ws: str, member=Depends(scope)):
        return {
            "items": [
                {
                    "id": key,
                    "name": r["name"],
                    "description": r["description"],
                    "steps": [
                        {
                            "kind": k,
                            "kind_label": STEP_KINDS[k],
                            "route": route,
                            "wait_days": d,
                            "title": t,
                        }
                        for k, route, d, t, _ in r["steps"]
                    ],
                }
                for key, r in RECIPES.items()
            ]
        }

    @app.post("/v1/workspaces/{ws}/campaigns/from-recipe", status_code=201)
    def from_recipe(
        ws: str, body: RecipeInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        recipe = RECIPES.get(body.recipe)
        if recipe is None:
            raise HTTPException(404, "Rezept nicht gefunden.")
        campaign = Campaign(workspace_id=ws, name=body.name or recipe["name"], goal=recipe["goal"])
        db.add(campaign)
        db.flush()
        for position, (kind, route, days, title, template) in enumerate(recipe["steps"]):
            db.add(
                FlowStep(
                    workspace_id=ws,
                    campaign_id=campaign.id,
                    position=position * 10,
                    kind=kind,
                    route=route,
                    wait_days=days,
                    title=title,
                    template=template,
                    config={"if_reaction": "stop", "if_none": "next"}
                    if kind == "condition"
                    else {},
                )
            )
        contact_ids = list(dict.fromkeys(body.contact_ids))
        if not contact_ids and body.audience:
            from app.platform_models import Suppression

            busy = select(FlowRun.contact_id).where(
                FlowRun.workspace_id == ws, FlowRun.state.in_(["active", "waiting"])
            )
            blocked = select(Suppression.contact_id).where(Suppression.workspace_id == ws)
            stmt = select(Contact.id).where(
                Contact.workspace_id == ws,
                Contact.id.not_in(busy),
                Contact.id.not_in(blocked),
            )
            stmt = (
                stmt.where(Contact.channel_route != "none")
                if body.audience == "routed"
                else stmt.where(Contact.channel_route == body.audience)
            )
            contact_ids = list(db.scalars(stmt.order_by(Contact.created_at).limit(200)))
        for contact_id in contact_ids:
            record(db, Contact, ws, contact_id)
            db.add(Enrollment(workspace_id=ws, campaign_id=campaign.id, contact_id=contact_id))
        db.flush()
        started = start_runs(db, ws, campaign) if body.start and contact_ids else {"started": 0}
        audit(
            db, ws, member.user_id, "campaign_from_recipe", f"Kampagne aus Rezept {recipe['name']}"
        )
        return flow_output(db, ws, campaign) | {"started": started}

    @app.get("/v1/workspaces/{ws}/flow-campaigns")
    def flow_campaigns(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        with_steps = select(FlowStep.campaign_id).where(FlowStep.workspace_id == ws)
        rows = db.scalars(
            select(Campaign)
            .where(Campaign.workspace_id == ws, Campaign.id.in_(with_steps))
            .order_by(Campaign.created_at.desc())
            .limit(100)
        ).all()
        stats = {}
        for campaign_id, state, count in db.execute(
            select(FlowRun.campaign_id, FlowRun.state, func.count())
            .where(FlowRun.workspace_id == ws)
            .group_by(FlowRun.campaign_id, FlowRun.state)
        ):
            stats.setdefault(campaign_id, {})[state] = count
        return {
            "items": [
                {
                    "id": c.id,
                    "name": c.name,
                    "goal": c.goal,
                    "status": c.status,
                    "runs": stats.get(c.id, {}),
                }
                for c in rows
            ]
        }

    @app.get("/v1/workspaces/{ws}/campaigns/{entity_id}/flow")
    def read_flow(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        return flow_output(db, ws, record(db, Campaign, ws, entity_id))

    @app.put("/v1/workspaces/{ws}/campaigns/{entity_id}/flow")
    def write_flow(
        ws: str,
        entity_id: str,
        body: FlowInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        campaign = record(db, Campaign, ws, entity_id, True)
        if campaign.status == "completed":
            raise HTTPException(409, "Abgeschlossene Kampagnen lassen sich nicht mehr ändern.")
        positions = {s.position for s in body.steps}
        for s in body.steps:
            for value in (s.config or {}).values():
                if isinstance(value, int) and value not in positions:
                    raise HTTPException(422, f"Sprungziel {value} existiert nicht.")
        for step in steps_of(db, ws, campaign.id):
            db.delete(step)
        db.flush()
        for s in body.steps:
            db.add(FlowStep(workspace_id=ws, campaign_id=campaign.id, **s.model_dump()))
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "flow_saved",
            "Kampagnen-Ablauf gespeichert; gilt ab dem nächsten Schritt",
        )
        return flow_output(db, ws, campaign)

    @app.post("/v1/workspaces/{ws}/campaigns/{entity_id}/flow/start")
    def start(
        ws: str,
        entity_id: str,
        body: StartInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        campaign = record(db, Campaign, ws, entity_id, True)
        if not steps_of(db, ws, campaign.id):
            raise HTTPException(409, "Zuerst Schritte anlegen.")
        if campaign.status in ("paused", "completed"):
            raise HTTPException(409, "Kampagne ist pausiert oder abgeschlossen.")
        result = start_runs(db, ws, campaign, body.contact_ids or None)
        audit(db, ws, member.user_id, "flow_started", f"{result['started']} Läufe gestartet")
        return flow_output(db, ws, campaign) | {"started": result}

    @app.get("/v1/workspaces/{ws}/flow-tasks")
    def tasks(
        ws: str,
        due: str = "today",
        mine: bool = False,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if due not in ("today", "all"):
            raise HTTPException(422, "due muss today oder all sein.")
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "flow-tick:" + ws},
        )
        tick(db, ws)
        stmt = select(FlowTask).where(
            FlowTask.workspace_id == ws, FlowTask.state.in_(["open", "blocked"])
        )
        if due == "today":
            end = now().replace(hour=23, minute=59, second=59)
            stmt = stmt.where(FlowTask.due_at <= end)
        if mine:
            stmt = stmt.where(
                (FlowTask.assignee_id == member.user_id) | (FlowTask.assignee_id.is_(None))
            )
        rows = db.scalars(
            stmt.order_by(FlowTask.state, FlowTask.due_at, FlowTask.id).limit(200)
        ).all()
        return {
            "items": [task_output(db, t) for t in rows],
            "counts": {
                "open": sum(t.state == "open" for t in rows),
                "blocked": sum(t.state == "blocked" for t in rows),
            },
        }

    @app.post("/v1/workspaces/{ws}/flow-tasks/{entity_id}/done")
    def done(
        ws: str,
        entity_id: str,
        body: DoneInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        task = record(db, FlowTask, ws, entity_id, True)
        if task.state != "open":
            raise HTTPException(
                409,
                "Aufgabe ist nicht offen."
                if task.state != "blocked"
                else f"Gesperrt: {task.blocked_reason}",
            )
        complete_task(db, ws, task, member.user_id, "done", body.note)
        audit(
            db,
            ws,
            member.user_id,
            "flow_task_done",
            f"{STEP_KINDS.get(task.kind, task.kind)} erledigt (selbst gemeldet)",
        )
        return task_output(db, task)

    @app.post("/v1/workspaces/{ws}/flow-tasks/{entity_id}/skip")
    def skip(
        ws: str,
        entity_id: str,
        body: DoneInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        task = record(db, FlowTask, ws, entity_id, True)
        if task.state not in ("open", "blocked"):
            raise HTTPException(409, "Aufgabe ist nicht offen.")
        complete_task(db, ws, task, member.user_id, "skipped", body.note)
        audit(db, ws, member.user_id, "flow_task_skipped", "Schritt übersprungen")
        return task_output(db, task)


def tick_all() -> int:
    """Worker entry: advance due runs in every workspace (each in its own transaction)."""
    from app.db import SessionLocal
    from app.jobs import tenant
    from app.models import Workspace

    with SessionLocal() as db:
        workspaces = list(db.scalars(select(Workspace.id)))
    total = 0
    for ws in workspaces:
        with SessionLocal() as db, db.begin():
            tenant(db, ws)
            total += tick(db, ws)
    return total
