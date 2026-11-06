"""M8: job agent ("Auftrags-Agent") and morning autopilot.

An instruction such as "Finde 200 Firmen in meiner Region, recherchiere sie, priorisiere
sie und bereite eine Kampagne vor" is parsed deterministically into steps that reuse the
existing workflows (discovery → import → website research → AI profiles → ranking →
contacts from Impressum → campaign → today queue). The plan shows costs before anything
runs; execution starts only after confirmation and runs as a chain of durable
``agent_step`` jobs that wait for the sub-jobs they started.

Nothing leaves ProspectOS through the agent: no LinkedIn sends, no e-mails, no posts.
Those keep their own human approvals. The autopilot only repeats confirmed internal steps
once per day (after ``hour`` Europe/Berlin) for workspaces that enabled it.
"""

import math
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, object_session

from app import credentials
from app.db import Base, SessionLocal, now
from app.models import Company, Membership, TenantMixin, Workspace
from app.platform_models import Job

TZ = ZoneInfo("Europe/Berlin")
STEP_LABELS = {
    "discover": "Firmen suchen",
    "import": "Firmen übernehmen (ohne Dubletten)",
    "research": "Websites und Impressum recherchieren",
    "profile": "KI-Kurzprofile erstellen",
    "rank": "Bewerten und priorisieren",
    "contacts": "Ansprechpartner aus Impressum übernehmen",
    "campaign": "Kampagne vorbereiten",
    "today": "Tagesliste „Heute“ füllen",
}
# "Ortenaukreis" as autopilot area: one town per day with a small radius, so the whole
# district is covered over the weeks without repeating the same OSM search.
ROTATION = [
    "Offenburg", "Lahr", "Kehl", "Achern", "Oberkirch", "Gengenbach", "Haslach im Kinzigtal",
    "Ettenheim", "Wolfach", "Zell am Harmersbach", "Renchen", "Willstätt", "Friesenheim",
    "Hausach", "Appenweier", "Neuried", "Schutterwald", "Rheinau",
]  # fmt: skip
AREA_NAMES = ("ortenaukreis", "ortenau")
WAIT_SECONDS = 15
MAX_WAIT_MINUTES = 90


class AgentRun(TenantMixin, Base):
    __tablename__ = "agent_runs"
    created_by: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20), default="manual")
    instruction: Mapped[str] = mapped_column(String(1000))
    plan: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    progress: Mapped[list] = mapped_column(JSON, default=list)
    estimate_minor: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_at = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "created_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class AutopilotSettings(TenantMixin, Base):
    __tablename__ = "autopilot_settings"
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    plan: Mapped[dict] = mapped_column(JSON)
    hour: Mapped[int] = mapped_column(Integer, default=6)
    last_run_on = mapped_column(Date, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "updated_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class InstructionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction: str = Field(min_length=5, max_length=1000)


class AutopilotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    place: str = Field(default="", max_length=120)
    radius_km: int = Field(default=30, ge=1, le=50)
    new_companies: int = Field(default=30, ge=5, le=200)
    research: int = Field(default=20, ge=0, le=100)
    profiles: int = Field(default=0, ge=0, le=50)
    hour: int = Field(default=6, ge=0, le=23)
    # Upper bound for paid AI steps per run, in USD cents (free steps are not limited).
    budget_minor: int = Field(default=50, ge=0, le=5000)


# ---- planning --------------------------------------------------------------------------


def icp_region(db, ws) -> str:
    """A region term from the ICP locations (e.g. "Ortenaukreis") used to disambiguate."""
    from app.journeys import ICPProfile

    icp = db.scalar(
        select(ICPProfile)
        .where(ICPProfile.workspace_id == ws)
        .order_by(ICPProfile.created_at.desc())
    )
    for loc in (icp.profile or {}).get("locations", []) if icp else []:
        if re.search(r"(kreis|landkreis|region)$", loc, re.I) and " " not in loc.strip():
            return loc
    return ""


def default_place(db, ws) -> str:
    from app.journeys import ICPProfile

    icp = db.scalar(
        select(ICPProfile)
        .where(ICPProfile.workspace_id == ws)
        .order_by(ICPProfile.created_at.desc())
    )
    locations = (icp.profile or {}).get("locations", []) if icp else []
    return locations[0] if locations else ""


def parse_instruction(text_in: str, fallback_place: str) -> dict:
    t = text_in.casefold()
    count = re.search(r"(\d{1,4})\s*(?:neue\s+)?(?:firmen|unternehmen|betriebe|leads|kontakte)", t)
    radius = re.search(r"(\d{1,3})\s*km", t)
    place = re.search(
        r"(?:um|in|bei|rund um|im raum|umkreis von \d+\s*km um)\s+([A-ZÄÖÜ][\wäöüß\-]+(?:\s+[A-ZÄÖÜ][\wäöüß\-]+)?)",
        text_in,
    )
    chosen_place = (
        place.group(1)
        if place and place.group(1).casefold() not in ("meiner", "der", "unserer")
        else ""
    )
    steps = []
    if re.search(r"find|such|sammel|lade|neue firmen|neue unternehmen", t):
        steps += ["discover", "import"]
    if "recherch" in t:
        steps.append("research")
    if re.search(r"ki-profil|kurzprofil|profil", t):
        steps.append("profile")
    if re.search(r"priorisier|bewert|rangliste|ranking|qualifizier", t):
        steps.append("rank")
    if re.search(r"kampagne|ansprache|outreach", t):
        steps += ["contacts", "campaign"]
    if re.search(r"linkedin|heute|tagesliste|tagesansicht", t):
        steps += ["contacts", "today"]
    if not steps:
        steps = ["discover", "import", "research", "rank"]
    if "research" in steps and "rank" not in steps:
        steps.append("rank")
    order = list(STEP_LABELS)
    steps = sorted(dict.fromkeys(steps), key=order.index)
    n = min(int(count.group(1)), 200) if count else 100
    return {
        "place": chosen_place or fallback_place,
        "radius_km": min(int(radius.group(1)), 50) if radius else 30,
        "companies": n,
        "research": min(n, 100),
        "profiles": min(n, 20) if "profile" in steps else 0,
        "steps": steps,
        "provider": "northdata" if "north data" in t or "handelsregister" in t else "osm",
    }


def estimate(plan: dict) -> dict:
    """Cost estimate in USD cents from configured token prices; free sources are 0."""
    lines = []
    total = 0
    for step in plan["steps"]:
        cost, note = 0, "kostenlos"
        if step == "discover":
            note = (
                "OpenStreetMap: kostenlos (ODbL)"
                if plan["provider"] == "osm"
                else "North Data: Abrechnung je Firma laut Vertrag"
            )
        if step == "research":
            note = f"{plan['research']} Websites, kostenlos, ca. {max(1, plan['research'] * 8 // 60)} Min."
        if step == "profile":
            try:
                inp = float(credentials.get("LLM_INPUT_USD_PER_MILLION") or "nan")
                out = float(credentials.get("LLM_OUTPUT_USD_PER_MILLION") or "nan")
                per = (4000 * inp + 500 * out) / 1_000_000 * 100
                cost = math.ceil(per * plan["profiles"]) if math.isfinite(per) else 0
                note = f"{plan['profiles']} Profile × ca. {per:.2f} ct (Schätzung, 4.000 Input-/500 Output-Tokens)"
            except ValueError:
                note = "KI-Preise nicht konfiguriert"
        total += cost
        lines.append({"step": step, "label": STEP_LABELS[step], "cost_minor": cost, "note": note})
    return {"lines": lines, "total_minor": total}


def budgeted(plan: dict, budget_minor: int, remaining_minor: int | None) -> dict:
    """Fit paid steps into the per-run budget and the workspace AI budget."""
    plan = dict(plan)
    limit = budget_minor if remaining_minor is None else min(budget_minor, remaining_minor)
    est = estimate(plan)
    if est["total_minor"] <= limit:
        return plan | {"budget_note": ""}
    line = next((x for x in est["lines"] if x["step"] == "profile"), None)
    per = (line["cost_minor"] / max(1, plan.get("profiles") or 1)) if line else 0
    fit = int(limit // per) if per else 0
    plan["profiles"] = max(0, min(plan.get("profiles", 0), fit))
    if plan["profiles"] == 0:
        plan["steps"] = [s for s in plan["steps"] if s != "profile"]
    plan["budget_note"] = (
        f"Budget {limit / 100:.2f} USD: KI-Profile auf {plan['profiles']} begrenzt"
        if plan["profiles"]
        else f"Budget {limit / 100:.2f} USD reicht nicht für KI-Profile; nur kostenlose Schritte"
    )
    return plan


def todays_area(plan: dict, cursor: int) -> dict:
    if (plan.get("place") or "").strip().casefold() not in AREA_NAMES:
        return dict(plan)
    town = ROTATION[cursor % len(ROTATION)]
    return dict(plan) | {
        "place": town,
        "radius_km": min(plan.get("radius_km", 12), 12),
        "area": plan["place"],
    }


def ledger(db, ws, run) -> dict:
    """Actual AI cost of the run from the usage ledger (UsageEvent per job)."""
    from app.platform_models import UsageEvent

    ids = [j for p in (run.progress or []) for j in p.get("jobs", [])]
    actual = 0
    if ids:
        actual = sum(
            db.scalars(
                select(UsageEvent.cost_minor).where(
                    UsageEvent.workspace_id == ws, UsageEvent.job_id.in_(ids)
                )
            )
        )
    return {
        "estimate_minor": run.estimate_minor,
        "actual_minor": actual,
        "budget_minor": (run.plan or {}).get("budget_minor"),
        "note": (run.plan or {}).get("budget_note", ""),
    }


def _progress(plan: dict) -> list:
    return [
        {"step": s, "label": STEP_LABELS[s], "status": "pending", "detail": "", "jobs": []}
        for s in plan["steps"]
    ]


# ---- execution -------------------------------------------------------------------------


def _discovery_payload(plan: dict) -> dict:
    from app.journeys import SearchFilters
    from app.providers.osm import resolve_categories
    from app.ranking import TEMPLATES

    industries = TEMPLATES["office_cleaning_ortenau"]["profile"]["industries"]
    criteria = SearchFilters.model_validate(
        {
            "provider": plan["provider"],
            "country": "germany",
            "city": plan["place"],
            "region": plan.get("region", ""),
            "radius_km": plan["radius_km"],
            "industries": industries,
            "max_results": plan["companies"],
            "exclude_customers": True,
        }
    )
    categories, _ = resolve_categories(industries)
    payload = {
        "query": f"Agent: {plan['place']} {plan['radius_km']} km",
        "provider": plan["provider"],
        "country": "germany",
        "city": plan["place"],
        "industry": "",
        "min_employees": None,
        "max_employees": None,
        "limit": plan["companies"],
        "criteria": criteria.model_dump(),
        "warnings": [],
    }
    if plan["provider"] == "osm":
        payload["osm"] = {
            # City + ICP region disambiguates homonyms (Lahr/Schwarzwald vs. Lahr/Eifel).
            "place": ", ".join(filter(None, [plan["place"], plan.get("region", "")])),
            "radius_km": plan["radius_km"],
            "categories": categories,
            "keywords": [],
        }
    else:
        from app.providers.northdata import segment_codes

        payload["northdata"] = {
            "address": plan["place"],
            "radius_km": plan["radius_km"],
            "categories": categories,
            "segment_codes": segment_codes(categories),
            "keywords": "",
        }
    return payload


def _jobs_done(db, ws, ids) -> tuple[bool, dict]:
    if not ids:
        return True, {}
    jobs = db.scalars(select(Job).where(Job.workspace_id == ws, Job.id.in_(ids))).all()
    counts: dict = {}
    for j in jobs:
        counts[j.status] = counts.get(j.status, 0) + 1
    done = all(j.status in ("succeeded", "failed", "dead", "ambiguous", "cancelled") for j in jobs)
    return done, counts


def ensure_hooks():
    """The worker never imports app.main; route registration fills journeys.HOOKS."""
    from app.journeys import HOOKS

    if "import_discovery_results" not in HOOKS:
        import app.main  # noqa: F401


def run_step(db, job) -> dict:
    """Run one step in a savepoint; an unexpected error marks the run failed (visible)."""
    try:
        with db.begin_nested():
            return _run_step(db, job)
    except HTTPException:
        raise
    except Exception as exc:  # never leave a run stuck in "running"
        run = db.scalar(
            select(AgentRun)
            .where(AgentRun.workspace_id == job.workspace_id, AgentRun.id == job.payload["run_id"])
            .with_for_update()
        )
        if run:
            progress = [dict(p) for p in run.progress]
            for p in progress:
                if p["status"] in ("pending", "running"):
                    p.update(status="failed", detail=f"Interner Fehler: {type(exc).__name__}")
                    break
            run.progress, run.status, run.finished_at = progress, "failed", now()
        return {"failed": type(exc).__name__}


def _run_step(db, job) -> dict:
    """One agent_step: start or check the current step, then schedule the next one."""
    from app.jobs import enqueue

    ws = job.workspace_id
    run = db.scalar(
        select(AgentRun)
        .where(AgentRun.workspace_id == ws, AgentRun.id == job.payload["run_id"])
        .with_for_update()
    )
    if not run or run.status != "running":
        return {"skipped": True}
    progress = [dict(p) for p in run.progress]
    index = next((i for i, p in enumerate(progress) if p["status"] in ("pending", "running")), None)
    if index is None:
        run.status, run.finished_at = "done", now()
        return {"done": True}
    step = progress[index]
    plan = dict(run.plan)
    actor = run.created_by
    state = dict(plan.get("_state") or {})

    def finish(detail, status="done"):
        step.update(status=status, detail=detail[:500], finished_at=now().isoformat())

    def wait_or(ids, on_done):
        done, counts = _jobs_done(db, ws, ids)
        started = datetime.fromisoformat(step.get("started_at") or now().isoformat())
        if done:
            on_done(counts)
        elif now() - started > timedelta(minutes=MAX_WAIT_MINUTES):
            finish(f"Zeitlimit erreicht: {counts}", "failed")
        else:
            step["detail"] = f"läuft: {counts}"

    if step["status"] == "pending":
        step.update(status="running", started_at=now().isoformat())
        if step["step"] == "discover":
            sub = enqueue(db, ws, actor, "discovery", _discovery_payload(plan))
            step["jobs"] = [sub.id]
        elif step["step"] == "research":
            from app.journeys import CompanyFact, ICPProfile
            from app.ranking import rank_company

            icp = db.scalar(
                select(ICPProfile)
                .where(ICPProfile.workspace_id == ws)
                .order_by(ICPProfile.created_at.desc())
            )
            companies = db.scalars(
                select(Company).where(Company.workspace_id == ws, Company.website.is_not(None))
            ).all()
            # Websites that failed recently (robots.txt, DNS, guard) are not retried for
            # 30 days; hidden companies (Autohaus, Konzernfiliale …) are not researched.
            failed_recently = {
                (j.payload or {}).get("company_id")
                for j in db.scalars(
                    select(Job).where(
                        Job.workspace_id == ws,
                        Job.kind == "research",
                        Job.status.in_(["failed", "dead"]),
                        Job.created_at >= now() - timedelta(days=30),
                    )
                )
            }
            todo = [
                c
                for c in companies
                if not (c.provenance or {}).get("website_research") and c.id not in failed_recently
            ]
            if icp:
                facts: dict = {}
                for f in db.scalars(select(CompanyFact).where(CompanyFact.workspace_id == ws)):
                    facts.setdefault(f.company_id, []).append(f)
                ranks = {c.id: rank_company(c, facts.get(c.id, []), icp.profile) for c in todo}
                todo = [c for c in todo if not ranks[c.id]["excluded"]]
                todo.sort(key=lambda c: -ranks[c.id]["priority"])
            state["research_skipped_failed"] = len(failed_recently)
            ids = []
            for c in todo[: plan["research"]]:
                sub = enqueue(
                    db,
                    ws,
                    actor,
                    "research",
                    {"mode": "site", "url": c.website, "company_id": c.id},
                    key=f"site-research:{c.id}:{now().date().isoformat()}",
                )
                ids.append(sub.id)
            step["jobs"] = ids
        elif step["step"] == "profile":
            from app.jobs import reserve_ai
            from app.research_flow import profile_prompt_and_sources

            ids = []
            researched = db.scalars(
                select(Job)
                .where(Job.workspace_id == ws, Job.kind == "research", Job.status == "succeeded")
                .order_by(Job.created_at.desc())
                .limit(500)
            ).all()
            seen = set()
            for r in researched:
                cid = r.payload.get("company_id")
                if (
                    cid in seen
                    or not isinstance(r.result, dict)
                    or not r.result.get("pages")
                    or len(ids) >= plan["profiles"]
                ):
                    continue
                seen.add(cid)
                try:
                    prompt, sources, urls = profile_prompt_and_sources(r.result)
                    reservation = reserve_ai(db, ws, prompt + "".join(s["text"] for s in sources))
                except HTTPException as exc:
                    step["detail"] = str(exc.detail)[:200]
                    break
                sub = enqueue(
                    db,
                    ws,
                    actor,
                    "company_profile",
                    {
                        "prompt": prompt,
                        "sources": sources,
                        "source_urls": urls,
                        "company_id": cid,
                        "purpose": "company_profile",
                        "reservation_minor": reservation,
                    },
                )
                ids.append(sub.id)
            step["jobs"] = ids
        # Steps without sub-jobs complete immediately below.
    if step["status"] == "running":
        kind = step["step"]
        if kind == "discover":

            def on_discover(counts):
                sub = db.get(Job, step["jobs"][0])
                if sub.status != "succeeded":
                    finish(f"Suche fehlgeschlagen: {sub.last_error}", "failed")
                    return
                state["run_id"] = sub.result["run_id"]
                finish(f"{len(sub.result.get('results', []))} Treffer")

            wait_or(step["jobs"], on_discover)
        elif kind == "import":
            from app.journeys import HOOKS

            ensure_hooks()

            member = db.get(Membership, (ws, actor))
            from app.journeys import Discovery

            discovery = db.scalar(
                select(Discovery).where(
                    Discovery.workspace_id == ws, Discovery.id == state.get("run_id")
                )
            )
            rows = HOOKS["normalized_results"](db, ws, discovery) if discovery else []
            keys = [r["key"] for r in rows if not r["imported"] and not r["duplicate_of"]]
            totals = {"companies": 0, "linked_duplicates": 0, "facts": 0}
            for i in range(0, len(keys), 100):
                res = HOOKS["import_discovery_results"](
                    db, ws, discovery.id, keys[i : i + 100], member
                )
                for k in totals:
                    totals[k] += res.get(k, 0)
            dup = sum(1 for r in rows if r["duplicate_of"])
            state["imported"] = totals
            finish(
                f"{totals['companies']} neue Firmen, {dup} Dubletten erkannt, {totals['facts']} belegte Fakten"
            )
        elif kind in ("research", "profile"):
            wait_or(
                step["jobs"],
                lambda counts: finish(
                    f"{counts.get('succeeded', 0)} erfolgreich, {sum(counts.values()) - counts.get('succeeded', 0)} ohne Ergebnis"
                ),
            )
        elif kind == "rank":
            from app.journeys import CompanyFact, ICPProfile
            from app.ranking import TEMPLATES, rank_company

            icp = db.scalar(
                select(ICPProfile)
                .where(ICPProfile.workspace_id == ws)
                .order_by(ICPProfile.created_at.desc())
            )
            profile = icp.profile if icp else TEMPLATES["office_cleaning_ortenau"]["profile"]
            facts: dict = {}
            for f in db.scalars(select(CompanyFact).where(CompanyFact.workspace_id == ws)):
                facts.setdefault(f.company_id, []).append(f)
            stmt = select(Company).where(Company.workspace_id == ws)
            scope_label = "alle Firmen"
            if "discover" in plan["steps"] and run.confirmed_at:
                # Focus contacts/campaign on what this run found (new or linked duplicates).
                fresh = list(db.scalars(stmt.where(Company.created_at >= run.confirmed_at)))
                if fresh:
                    stmt = stmt.where(Company.id.in_([c.id for c in fresh]))
                    scope_label = "Firmen dieses Laufs"
            ranked = sorted(
                (rank_company(c, facts.get(c.id, []), profile) for c in db.scalars(stmt)),
                key=lambda r: (-r["priority"], r["name"]),
            )
            ranked = [r for r in ranked if not r["excluded"]]
            state["top"] = [
                {
                    k: r[k]
                    for k in ("company_id", "name", "location", "priority", "reason", "sources")
                }
                for r in ranked[:20]
            ]
            finish(
                f"{len(ranked)} {scope_label} bewertet; Top: {', '.join(r['name'] for r in ranked[:3])}"
            )
        elif kind == "contacts":
            from app.today import contacts_from_impressum

            ids = [t["company_id"] for t in state.get("top", [])] or []
            created = contacts_from_impressum(db, ws, ids, 100)
            state["contacts_created"] = created
            finish(f"{created} Ansprechpartner aus Impressum/Register übernommen")
        elif kind == "campaign":
            from app.journeys import CampaignStep
            from app.models import Contact
            from app.platform_models import Campaign, Enrollment

            campaign = Campaign(
                workspace_id=ws,
                name=f"Agent {datetime.now(TZ):%d.%m.%Y}: {plan['place']}"[:200],
                goal=run.instruction[:1000],
            )
            db.add(campaign)
            db.flush()
            templates = [
                (
                    0,
                    0,
                    "linkedin_manual",
                    "Kontaktanfrage über die Tagesansicht „Heute“ (Notiz ≤ 200 Zeichen).",
                ),
                (
                    1,
                    0,
                    "email",
                    "Guten Tag {name},\n\nwir übernehmen die Büro-Unterhaltsreinigung für Unternehmen in {city}. {evidence}\n\nHätten Sie Interesse an einer unverbindlichen Besichtigung?",
                ),
                (
                    2,
                    5,
                    "email",
                    "Guten Tag {name},\n\nich wollte kurz nachhaken, ob eine Besichtigung für {company} interessant ist.",
                ),
            ]
            for pos, delay, channel, tpl in templates:
                db.add(
                    CampaignStep(
                        workspace_id=ws,
                        campaign_id=campaign.id,
                        position=pos,
                        delay_days=delay,
                        channel=channel,
                        template=tpl,
                    )
                )
            company_ids = [t["company_id"] for t in state.get("top", [])]
            contacts = (
                db.scalars(
                    select(Contact).where(
                        Contact.workspace_id == ws, Contact.company_id.in_(company_ids)
                    )
                ).all()
                if company_ids
                else []
            )
            for contact in contacts:
                db.add(Enrollment(workspace_id=ws, campaign_id=campaign.id, contact_id=contact.id))
            state["campaign_id"] = campaign.id
            finish(
                f"Kampagne „{campaign.name}“ mit {len(contacts)} Kontakten und 3 Schritten (LinkedIn manuell, 2 E-Mails – Versand nur mit Rechtsgrundlage und Freigabe)"
            )
        elif kind == "today":
            from app.today import build_queue, sender_for

            result = build_queue(db, ws, actor, sender_for(db, ws))
            state["today"] = result["created"]
            c = result["created"]
            finish(
                f"Tagesliste (Limit {result['daily_limit']}): {c['connect']} Anfragen, "
                f"{c['message']} Nachrichten, {c['followup'] + c.get('followup2', 0)} Follow-ups "
                "vorbereitet. Bitte in „Heute“ prüfen und freigeben."
            )
    run.progress = progress
    # New dict objects so SQLAlchemy detects the JSON change (in-place edits are invisible).
    run.plan = {**plan, "_state": dict(state)}
    remaining = [p for p in progress if p["status"] in ("pending", "running")]
    if any(p["status"] == "failed" for p in progress):
        run.status, run.finished_at = "failed", now()
        return {"failed": step["step"]}
    if not remaining:
        run.status, run.finished_at = "done", now()
        return {"done": True}
    delay = WAIT_SECONDS if step["status"] == "running" else 0
    enqueue(
        db,
        ws,
        actor,
        "agent_step",
        {"run_id": run.id},
        key=f"agent:{run.id}:{now().isoformat()}",
        available_at=now() + timedelta(seconds=delay),
    )
    return {"step": step["step"], "status": step["status"]}


def start_run(db, ws, run: AgentRun):
    from app.jobs import enqueue

    run.status, run.confirmed_at = "running", now()
    run.progress = _progress(run.plan)
    enqueue(db, ws, run.created_by, "agent_step", {"run_id": run.id}, key=f"agent:{run.id}:start")


def run_output(run: AgentRun) -> dict:
    state = (run.plan or {}).get("_state", {})
    return {
        "id": run.id,
        "kind": run.kind,
        "instruction": run.instruction,
        "plan": {k: v for k, v in (run.plan or {}).items() if k != "_state"},
        "estimate": estimate(run.plan) if run.plan.get("steps") else None,
        "status": run.status,
        "progress": run.progress,
        "results": {
            "imported": state.get("imported"),
            "top": state.get("top", [])[:10],
            "contacts_created": state.get("contacts_created"),
            "campaign_id": state.get("campaign_id"),
            "today": state.get("today"),
        },
        "ledger": ledger(object_session(run), run.workspace_id, run)
        if object_session(run)
        else None,
        "created_at": run.created_at,
        "confirmed_at": run.confirmed_at,
        "finished_at": run.finished_at,
    }


def autopilot_tick() -> int:
    """Called by the worker loop; creates at most one autopilot run per workspace per day."""
    started = 0
    local = datetime.now(TZ)
    with SessionLocal() as db:
        workspaces = list(db.scalars(select(Workspace.id)))
    for ws in workspaces:
        with SessionLocal() as db, db.begin():
            db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws})
            settings = db.scalar(
                select(AutopilotSettings)
                .where(AutopilotSettings.workspace_id == ws)
                .with_for_update(skip_locked=True)
            )
            if (
                not settings
                or not settings.enabled
                or local.hour < settings.hour
                or settings.last_run_on == local.date()
            ):
                continue
            member = db.get(Membership, (ws, settings.updated_by))
            if not member or member.role not in ("owner", "admin"):
                settings.enabled = False  # authorization revoked
                continue
            from app.jobs import usage_account

            cursor = int((settings.plan or {}).get("_cursor", 0))
            plan = todays_area({k: v for k, v in settings.plan.items() if k != "_cursor"}, cursor)
            account = usage_account(db, ws)
            plan = budgeted(
                plan,
                int(plan.get("budget_minor", 50)),
                account.ai_budget_minor - account.ai_spent_minor - account.ai_reserved_minor,
            )
            settings.plan = {**settings.plan, "_cursor": cursor + 1}
            run = AgentRun(
                workspace_id=ws,
                created_by=settings.updated_by,
                kind="autopilot",
                instruction="Morgen-Autopilot",
                plan=plan,
                estimate_minor=estimate(plan)["total_minor"],
            )
            db.add(run)
            db.flush()
            start_run(db, ws, run)
            settings.last_run_on = local.date()
            started += 1
    return started


def register_agent_routes(app, db_session, scope, record, audit):
    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Keine Berechtigung.")

    @app.post("/v1/workspaces/{ws}/agent/plan", status_code=201)
    def plan(
        ws: str,
        body: InstructionInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        parsed = parse_instruction(body.instruction, default_place(db, ws))
        parsed["region"] = icp_region(db, ws)
        if not parsed["place"]:
            raise HTTPException(
                422,
                "Bitte einen Ort nennen (z. B. „um Offenburg“) oder ein ICP-Profil mit Region anlegen.",
            )
        if parsed["provider"] == "northdata":
            from app.providers.northdata import enabled

            if not enabled():
                parsed["provider"] = "osm"
        run = AgentRun(
            workspace_id=ws,
            created_by=member.user_id,
            instruction=body.instruction,
            plan=parsed,
            estimate_minor=estimate(parsed)["total_minor"],
            progress=_progress(parsed),
        )
        db.add(run)
        db.flush()
        return run_output(run)

    @app.post("/v1/workspaces/{ws}/agent/runs/{entity_id}/confirm")
    def confirm(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        run = record(db, AgentRun, ws, entity_id, True)
        if run.status != "planned":
            raise HTTPException(409, "Auftrag wurde bereits gestartet.")
        start_run(db, ws, run)
        audit(
            db,
            ws,
            member.user_id,
            "agent_confirmed",
            f"Auftrag bestätigt: {', '.join(run.plan['steps'])}",
        )
        return run_output(run)

    @app.post("/v1/workspaces/{ws}/agent/runs/{entity_id}/cancel")
    def cancel(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        run = record(db, AgentRun, ws, entity_id, True)
        if run.status in ("planned", "running"):
            run.status, run.finished_at = "cancelled", now()
        return run_output(run)

    @app.get("/v1/workspaces/{ws}/agent/runs")
    def runs(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return {
            "items": [
                run_output(r)
                for r in db.scalars(
                    select(AgentRun)
                    .where(AgentRun.workspace_id == ws)
                    .order_by(AgentRun.created_at.desc())
                    .limit(20)
                )
            ]
        }

    @app.get("/v1/workspaces/{ws}/agent/runs/{entity_id}")
    def run(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        return run_output(record(db, AgentRun, ws, entity_id))

    @app.get("/v1/workspaces/{ws}/agent/autopilot")
    def get_autopilot(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        from app.jobs import usage_account

        s = db.scalar(select(AutopilotSettings).where(AutopilotSettings.workspace_id == ws))
        account = usage_account(db, ws)
        budget = {
            "workspace_budget_minor": account.ai_budget_minor,
            "spent_minor": account.ai_spent_minor,
            "reserved_minor": account.ai_reserved_minor,
            "period": account.period,
        }
        if not s:
            return {
                "enabled": False,
                "plan": None,
                "hour": 6,
                "last_run_on": None,
                "budget": budget,
                "rotation": ROTATION,
            }
        recent = db.scalars(
            select(AgentRun)
            .where(AgentRun.workspace_id == ws, AgentRun.kind == "autopilot")
            .order_by(AgentRun.created_at.desc())
            .limit(7)
        ).all()
        return {
            "enabled": s.enabled,
            "plan": {k: v for k, v in (s.plan or {}).items() if k != "_cursor"},
            "hour": s.hour,
            "last_run_on": s.last_run_on,
            "next_area": todays_area(s.plan or {}, int((s.plan or {}).get("_cursor", 0)))["place"],
            "budget": budget,
            "rotation": ROTATION,
            "recent": [
                {
                    "id": r.id,
                    "status": r.status,
                    "place": (r.plan or {}).get("place"),
                    "created_at": r.created_at,
                    "ledger": ledger(db, ws, r),
                }
                for r in recent
            ],
        }

    @app.put("/v1/workspaces/{ws}/agent/autopilot")
    def put_autopilot(
        ws: str,
        body: AutopilotInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Nur Owner/Admin aktivieren den Autopiloten.")
        place = body.place or default_place(db, ws)
        if body.enabled and not place:
            raise HTTPException(422, "Ort für den Autopiloten angeben.")
        steps = (
            ["discover", "import"]
            + (["research"] if body.research else [])
            + (["profile"] if body.profiles else [])
            + ["rank", "contacts", "today"]
        )
        plan = {
            "place": place,
            "region": icp_region(db, ws),
            "radius_km": body.radius_km,
            "companies": body.new_companies,
            "research": body.research,
            "profiles": body.profiles,
            "steps": steps,
            "provider": "osm",
            "budget_minor": body.budget_minor,
        }
        s = db.scalar(
            select(AutopilotSettings).where(AutopilotSettings.workspace_id == ws).with_for_update()
        )
        if s and (s.plan or {}).get("_cursor") is not None:
            plan["_cursor"] = s.plan["_cursor"]
        if not s:
            s = AutopilotSettings(workspace_id=ws, updated_by=member.user_id, plan=plan)
            db.add(s)
        s.enabled, s.plan, s.hour, s.updated_by = body.enabled, plan, body.hour, member.user_id
        audit(
            db,
            ws,
            member.user_id,
            "autopilot_updated",
            f"Morgen-Autopilot {'aktiv' if body.enabled else 'aus'} ({place}, {body.hour} Uhr)",
        )
        return {
            "enabled": s.enabled,
            "plan": plan,
            "hour": s.hour,
            "last_run_on": s.last_run_on,
            "estimate": estimate(plan),
            "next_area": todays_area(plan, int(plan.get("_cursor", 0)))["place"],
        }


__all__ = ["AgentRun", "AutopilotSettings", "autopilot_tick", "run_step", "os"]
