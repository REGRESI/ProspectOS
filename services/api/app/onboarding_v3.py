"""V3 M6: guided start in five steps (company, area, audience, LinkedIn, first campaign).

Each step's state is derived from data that already exists, so the guide never claims a
step is done that is not: sender set, region set, an ICP profile exists, a LinkedIn
connection exists for this person (or the step was explicitly skipped), a campaign with
steps exists. Writes go to the existing settings tables.
"""

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.db import now


class CompanyStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender_company: str = Field(min_length=2, max_length=80)
    sender_name: str = Field(min_length=2, max_length=80)
    offer: str = Field(min_length=3, max_length=120)
    address_form: str = Field(default="sie", pattern="^(sie|du)$")


class AreaStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: str = Field(min_length=2, max_length=60)
    places: list[str] = Field(default_factory=list, max_length=40)


def status(db, ws, user_id) -> dict:
    from app.experience import WorkspaceSetup
    from app.flows import FlowStep
    from app.journeys import ICPProfile
    from app.platform_models import Connection
    from app.today import get_settings

    settings = get_settings(db, ws)
    setup = db.scalar(select(WorkspaceSetup).where(WorkspaceSetup.workspace_id == ws))
    skipped = set(setup.completed_steps or []) if setup else set()
    linked = db.scalar(
        select(func.count(Connection.id)).where(
            Connection.workspace_id == ws,
            Connection.provider == "linkedin",
            Connection.user_id == user_id,
        )
    )
    steps = [
        {
            "key": "company",
            "title": "Deine Firma",
            "done": bool(settings.sender_company and settings.sender_name),
            "summary": f"{settings.sender_company} · {settings.offer}"
            if settings.sender_company
            else "",
        },
        {
            "key": "area",
            "title": "Dein Gebiet",
            "done": bool(setup and setup.region),
            "summary": setup.region if setup else "",
        },
        {
            "key": "audience",
            "title": "Deine Zielgruppe",
            "done": bool(
                db.scalar(select(func.count(ICPProfile.id)).where(ICPProfile.workspace_id == ws))
            ),
            "summary": "",
        },
        {
            "key": "linkedin",
            "title": "LinkedIn verbinden",
            "done": bool(linked) or "linkedin" in skipped,
            "summary": "verbunden" if linked else ("übersprungen" if "linkedin" in skipped else ""),
        },
        {
            "key": "campaign",
            "title": "Erste Kampagne",
            "done": bool(
                db.scalar(select(func.count(FlowStep.id)).where(FlowStep.workspace_id == ws))
            ),
            "summary": "",
        },
    ]
    done = sum(s["done"] for s in steps)
    return {
        "steps": steps,
        "done": done,
        "total": len(steps),
        "next": next((s["key"] for s in steps if not s["done"]), None),
        "settings": {
            "sender_company": settings.sender_company,
            "sender_name": settings.sender_name,
            "offer": settings.offer,
            "address_form": settings.address_form,
            "region": settings.region,
        },
    }


def _setup(db, ws):
    from app.experience import WorkspaceSetup

    item = db.scalar(
        select(WorkspaceSetup).where(WorkspaceSetup.workspace_id == ws).with_for_update()
    )
    if item is None:
        item = WorkspaceSetup(workspace_id=ws, completed_steps=[])
        db.add(item)
    return item


def register_onboarding_v3_routes(app, db_session, scope, audit):
    def admin(member):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Den Start richtet Owner oder Admin ein.")

    @app.get("/v1/workspaces/{ws}/start")
    def read_start(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return status(db, ws, member.user_id)

    @app.put("/v1/workspaces/{ws}/start/company")
    def company(
        ws: str, body: CompanyStep, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        from app.letters import get_settings as letter_settings
        from app.today import get_settings

        admin(member)
        settings = get_settings(db, ws)
        db.add(settings)  # get_settings returns an unsaved default when none exists
        settings.sender_company, settings.sender_name = body.sender_company, body.sender_name
        settings.offer, settings.address_form = body.offer, body.address_form
        settings.updated_by = member.user_id
        letters = letter_settings(db, ws)
        letters.sender_company = letters.sender_company or body.sender_company
        letters.sender_name = letters.sender_name or body.sender_name
        setup = _setup(db, ws)
        setup.business = setup.business or f"{body.sender_company}: {body.offer}"
        audit(db, ws, member.user_id, "start_company", "Geführter Start: Firma gespeichert")
        db.flush()
        return status(db, ws, member.user_id)

    @app.put("/v1/workspaces/{ws}/start/area")
    def area(
        ws: str, body: AreaStep, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        from app.team_mode import member_settings
        from app.today import get_settings

        admin(member)
        settings = get_settings(db, ws)
        db.add(settings)
        settings.region = body.region
        setup = _setup(db, ws)
        places = [p.strip()[:60] for p in body.places if p.strip()]
        setup.region = ", ".join([body.region, *places])[:200]
        if places:
            mine = member_settings(db, ws, member.user_id)
            mine.territory, mine.updated_at = places, now()
        audit(db, ws, member.user_id, "start_area", "Geführter Start: Gebiet gespeichert")
        db.flush()
        return status(db, ws, member.user_id)

    @app.post("/v1/workspaces/{ws}/start/linkedin/skip")
    def skip_linkedin(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        admin(member)
        setup = _setup(db, ws)
        setup.completed_steps = list(dict.fromkeys([*(setup.completed_steps or []), "linkedin"]))
        db.flush()
        return status(db, ws, member.user_id)
