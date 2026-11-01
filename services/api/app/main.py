import hashlib
import json
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal, now, uid
from app.imports import parse_csv
from app.models import (
    ICP,
    Audit,
    AuthSession,
    Company,
    Contact,
    Deal,
    Discovery,
    Draft,
    ImportJob,
    Membership,
    Post,
    User,
    Workspace,
)
from app.schemas import (
    ContactInput,
    DealInput,
    DealPatch,
    DraftInput,
    ICPInput,
    Login,
    PostInput,
    PostPatch,
    Schedule,
    Topic,
    WorkspaceInput,
)
from app.scoring import DEFAULT_ICP, score


@asynccontextmanager
async def lifespan(app):
    if os.getenv("APP_ENV", "development") not in ("development", "test"):
        raise RuntimeError(
            "Production auth is not implemented. Demo server refuses production startup."
        )
    with SessionLocal() as db:
        role = db.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")
        ).one()
        owns = db.scalar(
            text(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename='contacts' AND tableowner=current_user"
            )
        )
        if role.rolsuper or role.rolbypassrls or owns:
            raise RuntimeError("Runtime DB role must be a non-owner without SUPERUSER/BYPASSRLS")
    yield


app = FastAPI(title="ProspectOS local pilot", version="0.1.0", lifespan=lifespan)
password_hasher = PasswordHasher()
login_attempts = defaultdict(deque)
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))


def problem(status, code, message, details=None):
    return JSONResponse(
        status_code=status, content={"code": code, "message": message, "details": details}
    )


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return problem(exc.status_code, f"http_{exc.status_code}", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not echo input/password/file contents.
    return problem(
        422,
        "validation",
        "Bitte Eingaben prüfen.",
        [{"field": list(e["loc"]), "message": e["msg"]} for e in exc.errors()],
    )


@app.exception_handler(IntegrityError)
async def conflict_error(request, exc):
    return problem(409, "conflict", "Datensatz existiert bereits oder wird noch verwendet.")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-Id"] = uid()
    return response


def db_session():
    with SessionLocal() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def current_auth(request: Request, db: Session = Depends(db_session)):
    raw = request.cookies.get("prospectos_session", "")
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    auth = db.get(AuthSession, token_hash)
    if auth is None or auth.expires_at <= now():
        raise HTTPException(401, "Bitte anmelden.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not secrets.compare_digest(csrf, auth.csrf_token):
            raise HTTPException(403, "Sicherheitsprüfung fehlgeschlagen. Bitte neu laden.")
    return auth


def scope(ws: str, request: Request, auth=Depends(current_auth), db: Session = Depends(db_session)):
    member = db.get(Membership, (ws, auth.user_id))
    if member is None:
        raise HTTPException(404, "Workspace nicht gefunden.")
    if request.method not in ("GET", "HEAD", "OPTIONS") and member.role not in (
        "owner",
        "admin",
        "editor",
        "approver",
    ):
        raise HTTPException(403, "Diese Rolle hat nur Lesezugriff.")
    # Approvers can review, but cannot modify contacts, ICP or authored content.
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and member.role == "approver"
        and not request.url.path.endswith(("/approve", "/reject"))
    ):
        raise HTTPException(403, "Diese Rolle darf nur Freigaben bearbeiten.")
    db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws})
    return member


def audit(db, ws, actor, kind, description):
    db.add(Audit(workspace_id=ws, actor_id=actor, kind=kind, description=description))


def auth_payload(db, auth):
    user = db.get(User, auth.user_id)
    workspaces = db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Workspace.id == Membership.workspace_id)
        .where(Membership.user_id == user.id)
    ).all()
    return {
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "csrf_token": auth.csrf_token,
        "workspaces": [
            {"id": w.id, "name": w.name, "slug": w.slug, "role": role} for w, role in workspaces
        ],
    }


@app.post("/v1/auth/demo")
def login(body: Login, request: Request, response: Response, db: Session = Depends(db_session)):
    key = request.client.host if request.client else "local"
    attempts = login_attempts[key]
    while attempts and attempts[0] < time.monotonic() - 60:
        attempts.popleft()
    if len(attempts) >= 10:
        raise HTTPException(429, "Zu viele Anmeldeversuche. Bitte eine Minute warten.")
    attempts.append(time.monotonic())
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    try:
        password_hasher.verify(user.password_hash if user else DUMMY_HASH, body.password)
    except VerificationError:
        raise HTTPException(401, "E-Mail oder Passwort falsch.") from None
    if not user:
        raise HTTPException(401, "E-Mail oder Passwort falsch.")
    raw = secrets.token_urlsafe(40)
    auth = AuthSession(
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=now() + timedelta(hours=8),
    )
    db.add(auth)
    response.set_cookie(
        "prospectos_session",
        raw,
        max_age=8 * 3600,
        httponly=True,
        samesite="strict",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        path="/",
    )
    return auth_payload(db, auth)


@app.get("/v1/me")
def me(auth=Depends(current_auth), db: Session = Depends(db_session)):
    return auth_payload(db, auth)


@app.post("/v1/auth/logout")
def logout(response: Response, auth=Depends(current_auth), db: Session = Depends(db_session)):
    db.delete(auth)
    response.delete_cookie("prospectos_session", path="/")
    return {"ok": True}


@app.get("/v1/workspaces")
def workspaces(auth=Depends(current_auth), db: Session = Depends(db_session)):
    return {"items": auth_payload(db, auth)["workspaces"]}


@app.post("/v1/workspaces", status_code=201)
def new_workspace(
    body: WorkspaceInput, auth=Depends(current_auth), db: Session = Depends(db_session)
):
    workspace = Workspace(name=body.name, slug="workspace-" + uid()[:8])
    db.add(workspace)
    db.flush()
    db.add(Membership(workspace_id=workspace.id, user_id=auth.user_id, role="owner"))
    return {"id": workspace.id, "name": workspace.name, "slug": workspace.slug, "role": "owner"}


def record(db, model, ws, entity_id, lock=False):
    stmt = select(model).where(model.workspace_id == ws, model.id == entity_id)
    item = db.scalar(stmt.with_for_update() if lock else stmt)
    if not item:
        raise HTTPException(404, "Datensatz nicht gefunden.")
    return item


def paginate(db, stmt, page, limit):
    if page < 1 or not 1 <= limit <= 100:
        raise HTTPException(422, "Seite ab 1, Seitengröße zwischen 1 und 100.")
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    return db.scalars(stmt.offset((page - 1) * limit).limit(limit)).all(), total


def profile(db, ws):
    item = db.scalar(select(ICP).where(ICP.workspace_id == ws))
    return item.profile if item else DEFAULT_ICP


def contact_output(contact, company, icp):
    return {
        key: getattr(contact, key)
        for key in (
            "id",
            "first_name",
            "last_name",
            "job_title",
            "location",
            "email",
            "phone",
            "linkedin_url",
            "status",
            "source",
            "version",
            "created_at",
        )
    } | {"company": company.name if company else "", "score": score(contact, company, icp)}


def make_company(db, ws, name, location="", identity=None, source="user_entry"):
    if not name:
        return None
    if identity:
        existing = db.scalar(
            select(Company).where(Company.workspace_id == ws, Company.identity == identity)
        )
        if existing:
            return existing
    company = Company(
        workspace_id=ws, name=name, location=location, identity=identity or uid(), source=source
    )
    db.add(company)
    db.flush()
    return company


@app.get("/v1/workspaces/{ws}/contacts")
def contacts(
    ws: str,
    search: str = "",
    page: int = 1,
    limit: int = 25,
    status: str = "",
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    stmt = select(Contact).where(Contact.workspace_id == ws)
    if search:
        pattern = "%" + search.replace("%", "\\%").replace("_", "\\_") + "%"
        company_ids = select(Company.id).where(Company.name.ilike(pattern))
        stmt = stmt.where(
            or_(
                Contact.first_name.ilike(pattern),
                Contact.last_name.ilike(pattern),
                Contact.job_title.ilike(pattern),
                Contact.location.ilike(pattern),
                Contact.company_id.in_(company_ids),
            )
        )
    if status:
        stmt = stmt.where(Contact.status == status)
    items, total = paginate(db, stmt.order_by(Contact.created_at.desc(), Contact.id), page, limit)
    company_ids = {c.company_id for c in items if c.company_id}
    companies = (
        {c.id: c for c in db.scalars(select(Company).where(Company.id.in_(company_ids)))}
        if company_ids
        else {}
    )
    icp = profile(db, ws)
    return {
        "items": [contact_output(c, companies.get(c.company_id), icp) for c in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@app.get("/v1/workspaces/{ws}/contacts/{entity_id}")
def get_contact(ws: str, entity_id: str, member=Depends(scope), db: Session = Depends(db_session)):
    c = record(db, Contact, ws, entity_id)
    return contact_output(
        c, db.get(Company, c.company_id) if c.company_id else None, profile(db, ws)
    )


@app.post("/v1/workspaces/{ws}/contacts", status_code=201)
def create_contact(
    ws: str, body: ContactInput, member=Depends(scope), db: Session = Depends(db_session)
):
    company = make_company(db, ws, body.company, body.location)
    c = Contact(
        workspace_id=ws,
        company_id=company.id if company else None,
        **body.model_dump(exclude={"company", "version"}),
    )
    db.add(c)
    db.flush()
    audit(db, ws, member.user_id, "contact_created", "Kontakt manuell angelegt")
    return contact_output(c, company, profile(db, ws))


@app.patch("/v1/workspaces/{ws}/contacts/{entity_id}")
def update_contact(
    ws: str,
    entity_id: str,
    body: ContactInput,
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    c = record(db, Contact, ws, entity_id, True)
    if c.version != body.version:
        raise HTTPException(409, "Kontakt wurde zwischenzeitlich geändert. Bitte neu laden.")
    company = db.get(Company, c.company_id) if c.company_id else None
    if (company.name if company else "") != body.company:
        company = make_company(db, ws, body.company, body.location)
        c.company_id = company.id if company else None
    for key, value in body.model_dump(exclude={"company", "version"}).items():
        setattr(c, key, value)
    c.version += 1
    audit(db, ws, member.user_id, "contact_updated", "Kontakt aktualisiert")
    return contact_output(c, company, profile(db, ws))


@app.delete("/v1/workspaces/{ws}/contacts/{entity_id}")
def delete_contact(
    ws: str, entity_id: str, member=Depends(scope), db: Session = Depends(db_session)
):
    c = record(db, Contact, ws, entity_id, True)
    if db.scalar(select(Deal.id).where(Deal.contact_id == c.id).limit(1)):
        raise HTTPException(
            409, "Kontakt ist mit einem Deal verknüpft. Zuerst Zuordnung entfernen."
        )
    for draft in db.scalars(select(Draft).where(Draft.contact_id == c.id)):
        db.delete(draft)
    db.flush()
    db.delete(c)
    audit(db, ws, member.user_id, "contact_deleted", "Kontakt und zugehörige Entwürfe gelöscht")
    return {"ok": True}


@app.get("/v1/workspaces/{ws}/companies")
def companies(
    ws: str,
    page: int = 1,
    limit: int = 25,
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    items, total = paginate(
        db, select(Company).where(Company.workspace_id == ws).order_by(Company.name), page, limit
    )
    return {
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "location": c.location,
                "industry": c.industry,
                "source": c.source,
            }
            for c in items
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@app.get("/v1/workspaces/{ws}/icp")
def get_icp(ws: str, member=Depends(scope), db: Session = Depends(db_session)):
    return profile(db, ws)


@app.put("/v1/workspaces/{ws}/icp")
def put_icp(ws: str, body: ICPInput, member=Depends(scope), db: Session = Depends(db_session)):
    item = db.scalar(select(ICP).where(ICP.workspace_id == ws).with_for_update())
    if item:
        item.profile = body.model_dump()
    else:
        db.add(ICP(workspace_id=ws, profile=body.model_dump()))
    audit(
        db,
        ws,
        member.user_id,
        "icp_updated",
        "ICP aktualisiert; Scores werden anhand aktueller Regeln berechnet",
    )
    return body


@app.post("/v1/workspaces/{ws}/imports/preview")
def preview_import(
    ws: str,
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    try:
        mapping_dict = json.loads(mapping) if mapping else None
        if mapping_dict is not None and (
            not isinstance(mapping_dict, dict)
            or any(
                k
                not in (
                    "first_name",
                    "last_name",
                    "company",
                    "job_title",
                    "email",
                    "phone",
                    "location",
                    "linkedin_url",
                    "company_url",
                )
                or not isinstance(v, str)
                for k, v in mapping_dict.items()
            )
        ):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, "Ungültige Spaltenzuordnung.") from None
    payload = file.file.read(3 * 1024 * 1024 + 1)
    headers, used_mapping, rows = parse_csv(payload, mapping_dict)
    urls = {
        r[0]
        for r in db.execute(
            select(Contact.linkedin_url).where(
                Contact.workspace_id == ws, Contact.linkedin_url.is_not(None)
            )
        )
    }
    keys = set(
        db.scalars(
            select(Contact.import_key).where(
                Contact.workspace_id == ws, Contact.import_key.is_not(None)
            )
        )
    )
    for row in rows:
        row["duplicate"] = (
            row["duplicate"] or row.get("linkedin_url") in urls or row["import_key"] in keys
        )
    data = {
        "headers": headers,
        "mapping": used_mapping,
        "rows": rows,
        "total": len(rows),
        "valid": sum(not r["errors"] for r in rows),
        "invalid": sum(bool(r["errors"]) for r in rows),
        "duplicates": sum(r["duplicate"] for r in rows),
    }
    job = ImportJob(workspace_id=ws, owner_id=member.user_id, data=data)
    db.add(job)
    db.flush()
    return {
        "id": job.id,
        **data,
        "rows": rows[:100],
        "notice": "Quelle: Nutzer-Upload, nicht extern verifiziert. Kein Nachweis für Werbekontakt.",
    }


@app.post("/v1/workspaces/{ws}/imports/{entity_id}/commit")
def commit_import(
    ws: str, entity_id: str, member=Depends(scope), db: Session = Depends(db_session)
):
    # Serialize import commits per tenant, including duplicate previews from concurrent tabs.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:ws, 0))"), {"ws": ws})
    job = record(db, ImportJob, ws, entity_id, True)
    if job.owner_id != member.user_id and member.role not in ("owner", "admin"):
        raise HTTPException(403, "Import gehört einem anderen Benutzer.")
    if job.status == "completed":
        return job.summary
    if job.status != "validated":
        raise HTTPException(409, "Import kann nicht erneut übernommen werden.")
    created, duplicates, invalid, journal = 0, 0, 0, []
    for row in job.data["rows"]:
        if row["errors"]:
            invalid += 1
            continue
        cond = Contact.import_key == row["import_key"]
        if row.get("linkedin_url"):
            cond = or_(cond, Contact.linkedin_url == row["linkedin_url"])
        if db.scalar(select(Contact.id).where(Contact.workspace_id == ws, cond)):
            duplicates += 1
            continue
        company = make_company(
            db, ws, row["company"], row["location"], row.get("company_url"), "csv_upload"
        )
        c = Contact(
            workspace_id=ws,
            company_id=company.id if company else None,
            source="csv_upload",
            import_key=row["import_key"],
            **{
                k: row.get(k) or (None if k in ("email", "phone", "linkedin_url") else "")
                for k in (
                    "first_name",
                    "last_name",
                    "job_title",
                    "location",
                    "email",
                    "phone",
                    "linkedin_url",
                )
            },
        )
        db.add(c)
        db.flush()
        journal.append({"id": c.id, "version": c.version})
        created += 1
    job.journal = journal
    job.status = "completed"
    job.summary = {
        "created": created,
        "duplicates": duplicates,
        "invalid": invalid,
        "status": job.status,
    }
    # Raw CSV staging data is discarded after commit; the minimal journal supports rollback.
    job.data = {
        "total": job.data["total"],
        "headers": job.data["headers"],
        "mapping": job.data["mapping"],
    }
    audit(
        db,
        ws,
        member.user_id,
        "lead_imported",
        f"CSV-Import: {created} Kontakte, {duplicates} Dubletten, {invalid} Fehler",
    )
    return job.summary


@app.post("/v1/workspaces/{ws}/imports/{entity_id}/rollback")
def rollback_import(
    ws: str, entity_id: str, member=Depends(scope), db: Session = Depends(db_session)
):
    job = record(db, ImportJob, ws, entity_id, True)
    if job.owner_id != member.user_id and member.role not in ("owner", "admin"):
        raise HTTPException(403, "Keine Berechtigung für diesen Import.")
    if job.status == "rolled_back":
        return job.summary
    if job.status not in ("completed", "rollback_partial"):
        raise HTTPException(409, "Nur abgeschlossene Importe können zurückgenommen werden.")
    deleted, conflicts, remaining = 0, [], []
    for entry in job.journal:
        c = db.scalar(select(Contact).where(Contact.id == entry["id"]).with_for_update())
        if c is None:
            continue
        used = db.scalar(select(Deal.id).where(Deal.contact_id == c.id).limit(1)) or db.scalar(
            select(Draft.id).where(Draft.contact_id == c.id).limit(1)
        )
        if c.version != entry["version"] or used:
            conflicts.append(c.id)
            remaining.append(entry)
        else:
            db.delete(c)
            deleted += 1
    job.journal = remaining
    job.status = "rollback_partial" if conflicts else "rolled_back"
    job.summary = {"deleted": deleted, "conflicts": conflicts, "status": job.status}
    audit(
        db,
        ws,
        member.user_id,
        "import_rollback",
        f"Import-Rücknahme: {deleted} Kontakte gelöscht, {len(conflicts)} Konflikte. Unternehmen bleiben erhalten.",
    )
    return job.summary


@app.get("/v1/workspaces/{ws}/dashboard")
def dashboard(ws: str, member=Depends(scope), db: Session = Depends(db_session)):
    def count(model, *conditions):
        return db.scalar(
            select(func.count()).select_from(model).where(model.workspace_id == ws, *conditions)
        )

    events = db.scalars(
        select(Audit).where(Audit.workspace_id == ws).order_by(Audit.created_at.desc()).limit(8)
    ).all()
    return {
        "contacts": count(Contact),
        "companies": count(Company),
        "qualified": count(Contact, Contact.status == "qualified"),
        "deals": count(Deal, Deal.stage.not_in(["won", "lost"])),
        "pipeline_value": db.scalar(
            select(func.coalesce(func.sum(Deal.amount), 0)).where(
                Deal.workspace_id == ws, Deal.stage.not_in(["won", "lost"])
            )
        ),
        "posts": count(Post),
        "activities": [event_output(e) for e in events],
    }


def event_output(e):
    return {"id": e.id, "kind": e.kind, "description": e.description, "created_at": e.created_at}


@app.get("/v1/workspaces/{ws}/audit")
def events(
    ws: str,
    page: int = 1,
    limit: int = 25,
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    items, total = paginate(
        db,
        select(Audit).where(Audit.workspace_id == ws).order_by(Audit.created_at.desc()),
        page,
        limit,
    )
    return {"items": [event_output(e) for e in items], "total": total, "page": page, "limit": limit}


def deal_output(d):
    return {
        "id": d.id,
        "title": d.title,
        "contact_id": d.contact_id,
        "amount": d.amount,
        "stage": d.stage,
    }


@app.get("/v1/workspaces/{ws}/deals")
def deals(
    ws: str,
    page: int = 1,
    limit: int = 100,
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    items, total = paginate(
        db,
        select(Deal).where(Deal.workspace_id == ws).order_by(Deal.created_at.desc()),
        page,
        limit,
    )
    return {"items": [deal_output(d) for d in items], "total": total, "page": page, "limit": limit}


@app.post("/v1/workspaces/{ws}/deals", status_code=201)
def create_deal(ws: str, body: DealInput, member=Depends(scope), db: Session = Depends(db_session)):
    if body.contact_id:
        record(db, Contact, ws, body.contact_id)
    deal = Deal(workspace_id=ws, **body.model_dump())
    db.add(deal)
    db.flush()
    audit(db, ws, member.user_id, "deal_created", "Deal angelegt (manuelle Angaben)")
    return deal_output(deal)


@app.patch("/v1/workspaces/{ws}/deals/{entity_id}")
def change_deal(
    ws: str,
    entity_id: str,
    body: DealPatch,
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    deal = record(db, Deal, ws, entity_id, True)
    deal.stage = body.stage
    audit(db, ws, member.user_id, "deal_stage_changed", "Deal-Phase aktualisiert: " + body.stage)
    return deal_output(deal)


def post_output(p):
    return {
        key: getattr(p, key)
        for key in (
            "id",
            "caption",
            "alt_text",
            "state",
            "version",
            "approved_revision",
            "scheduled_at",
            "created_at",
        )
    }


@app.get("/v1/workspaces/{ws}/social/posts")
def posts(
    ws: str,
    page: int = 1,
    limit: int = 100,
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    items, total = paginate(
        db,
        select(Post).where(Post.workspace_id == ws).order_by(Post.created_at.desc()),
        page,
        limit,
    )
    return {"items": [post_output(p) for p in items], "total": total, "page": page, "limit": limit}


@app.post("/v1/workspaces/{ws}/social/posts", status_code=201)
def create_post(ws: str, body: PostInput, member=Depends(scope), db: Session = Depends(db_session)):
    p = Post(workspace_id=ws, author_id=member.user_id, **body.model_dump())
    db.add(p)
    db.flush()
    audit(db, ws, member.user_id, "post_created", "Beitragsentwurf angelegt")
    return post_output(p)


@app.patch("/v1/workspaces/{ws}/social/posts/{entity_id}")
def edit_post(
    ws: str,
    entity_id: str,
    body: PostPatch,
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    p = record(db, Post, ws, entity_id, True)
    if p.version != body.version:
        raise HTTPException(409, "Beitrag wurde zwischenzeitlich geändert.")
    p.caption, p.alt_text = body.caption, body.alt_text
    p.version += 1
    if p.state != "draft":
        p.state = "needs_review"
    p.approved_revision, p.scheduled_at = None, None
    audit(
        db,
        ws,
        member.user_id,
        "post_edited",
        "Beitrag geändert; bisherige Freigabe und Planung ungültig",
    )
    return post_output(p)


@app.post("/v1/workspaces/{ws}/social/posts/{entity_id}/submit-review")
def review_post(ws: str, entity_id: str, member=Depends(scope), db: Session = Depends(db_session)):
    p = record(db, Post, ws, entity_id, True)
    if p.state not in ("draft", "needs_review"):
        raise HTTPException(409, "Beitrag ist bereits freigegeben oder geplant.")
    p.state = "needs_review"
    audit(db, ws, member.user_id, "post_review_requested", "Beitrag zur Prüfung eingereicht")
    return post_output(p)


@app.post("/v1/workspaces/{ws}/social/posts/{entity_id}/approve")
def approve_post(ws: str, entity_id: str, member=Depends(scope), db: Session = Depends(db_session)):
    if member.role not in ("owner", "admin", "approver"):
        raise HTTPException(403, "Freigabe erfordert Owner-, Admin- oder Approver-Rolle.")
    p = record(db, Post, ws, entity_id, True)
    if p.state != "needs_review":
        raise HTTPException(409, "Beitrag muss zuerst zur Prüfung eingereicht werden.")
    # Local pilot policy: owner/admin may approve own drafts; editors never can.
    p.state, p.approved_revision = "approved", p.version
    audit(
        db,
        ws,
        member.user_id,
        "post_approved",
        f"Beitragsrevision {p.version} explizit freigegeben",
    )
    return post_output(p)


@app.post("/v1/workspaces/{ws}/social/posts/{entity_id}/schedule")
def schedule_post(
    ws: str,
    entity_id: str,
    body: Schedule,
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    p = record(db, Post, ws, entity_id, True)
    if p.state not in ("approved", "scheduled") or p.approved_revision != p.version:
        raise HTTPException(409, "Aktuelle Revision muss freigegeben sein.")
    if body.scheduled_at <= now():
        raise HTTPException(422, "Bitte Zeitpunkt in der Zukunft wählen.")
    p.scheduled_at = body.scheduled_at.astimezone(UTC)
    p.state = "scheduled"
    audit(
        db,
        ws,
        member.user_id,
        "post_scheduled",
        "Redaktionell eingeplant. Keine automatische Veröffentlichung; LinkedIn nicht verbunden.",
    )
    return post_output(p)


@app.post("/v1/workspaces/{ws}/social/captions/generate")
def captions(ws: str, body: Topic, member=Depends(scope)):
    return {
        "provider": "offline",
        "notice": "Demo-Vorschlag: Kein KI-Anbieter verbunden.",
        "variants": [
            f"Was bedeutet {body.topic} für Ihren Arbeitsalltag?\n\nWir möchten Erfahrungen und offene Fragen sammeln. Was ist Ihnen dabei wichtig?",
            f"Ein Thema, über das wir sprechen sollten: {body.topic}.\n\nWelche Herausforderungen begegnen Ihnen? Teilen Sie Ihre Perspektive.",
            f"Neue Perspektiven auf {body.topic}.\n\nGute Zusammenarbeit beginnt mit Zuhören. Worauf kommt es für Ihr Team an?",
        ],
    }


def draft_output(d):
    return {
        "id": d.id,
        "contact_id": d.contact_id,
        "content": d.content,
        "source": d.source,
        "send_allowed": False,
        "reason": "Kein Versand implementiert. Öffentliche Profildaten sind kein Werbekontakt-Nachweis.",
    }


@app.post("/v1/workspaces/{ws}/outreach/drafts")
def create_draft(
    ws: str, body: DraftInput, member=Depends(scope), db: Session = Depends(db_session)
):
    c = record(db, Contact, ws, body.contact_id)
    d = Draft(
        workspace_id=ws,
        contact_id=c.id,
        content=f"Hallo {c.first_name} {c.last_name},\n\nich würde mich gerne zum Thema Ihres Arbeitsalltags austauschen. Besteht Interesse an einem Gespräch?\n\n[Demo-Entwurf – bitte Anlass und rechtliche Grundlage selbst prüfen.]",
    )
    db.add(d)
    db.flush()
    audit(db, ws, member.user_id, "draft_generated", "Offline-Entwurf erstellt. Nichts versendet.")
    return draft_output(d)


@app.get("/v1/workspaces/{ws}/outreach/drafts")
def drafts(
    ws: str,
    page: int = 1,
    limit: int = 25,
    member=Depends(scope),
    db: Session = Depends(db_session),
):
    items, total = paginate(
        db,
        select(Draft).where(Draft.workspace_id == ws).order_by(Draft.created_at.desc()),
        page,
        limit,
    )
    return {"items": [draft_output(d) for d in items], "total": total, "page": page, "limit": limit}


@app.get("/v1/workspaces/{ws}/integrations")
def integrations(ws: str, member=Depends(scope)):
    return {
        "items": [
            {"name": name, "status": "not_configured", "reason": reason}
            for name, reason in [
                ("LinkedIn", "OAuth und Freigaben fehlen. Veröffentlichung nicht implementiert."),
                ("KI-Text", "Nur deterministische Offline-Vorschläge; kein KI-Anbieter verbunden."),
                (
                    "Lead Discovery",
                    "Nur synthetischer Demo-Anbieter; keine Recherche echter Unternehmen.",
                ),
                ("Stripe", "Abrechnung nicht implementiert; keine Zahlungen möglich."),
            ]
        ]
    }


@app.post("/v1/workspaces/{ws}/discovery/runs")
def discovery(ws: str, body: Topic, member=Depends(scope), db: Session = Depends(db_session)):
    from app.providers.discovery import SyntheticDemoProvider

    rows = [candidate.model_dump() for candidate in SyntheticDemoProvider().search(body.topic)]
    run = Discovery(workspace_id=ws, query=body.topic, results=rows)
    db.add(run)
    db.flush()
    return {
        "id": run.id,
        "status": run.status,
        "results": rows,
        "notice": "Beispieldaten: Diese Unternehmen sind synthetisch und wurden nicht recherchiert.",
    }


@app.post("/v1/workspaces/{ws}/discovery/runs/{entity_id}/import")
def import_discovery(
    ws: str, entity_id: str, member=Depends(scope), db: Session = Depends(db_session)
):
    run = record(db, Discovery, ws, entity_id, True)
    if run.status == "imported":
        return {"created": 0, "status": "imported"}
    created = 0
    for row in run.results:
        key = hashlib.sha256(("synthetic_demo:" + row["external_key"]).encode()).hexdigest()
        if db.scalar(
            select(Contact.id).where(Contact.workspace_id == ws, Contact.import_key == key)
        ):
            continue
        company = make_company(
            db, ws, row["company"], row["location"], row["external_key"], "synthetic_demo"
        )
        db.add(
            Contact(
                workspace_id=ws,
                company_id=company.id,
                import_key=key,
                source="synthetic_demo",
                **{k: row[k] for k in ("first_name", "last_name", "job_title", "location")},
            )
        )
        created += 1
    run.status = "imported"
    audit(
        db,
        ws,
        member.user_id,
        "lead_discovered",
        f"{created} synthetische Demo-Kontakte importiert; keine echte Recherche",
    )
    return {"created": created, "status": run.status}


@app.get("/health/live")
def live():
    return {"status": "ok", "mode": "development"}


@app.get("/health/ready")
def ready(db: Session = Depends(db_session)):
    db.execute(text("SELECT 1 FROM contacts LIMIT 0"))
    version = db.scalar(text("SELECT current_user"))
    return {"status": "ready", "database": "connected", "role": version}


@app.post("/v1/workspaces/{ws}/social/posts/{entity_id}/cancel")
def cancel_post(ws: str, entity_id: str, member=Depends(scope), db: Session = Depends(db_session)):
    p = record(db, Post, ws, entity_id, True)
    if p.state != "scheduled":
        raise HTTPException(409, "Nur geplante Termine können aufgehoben werden.")
    p.state, p.scheduled_at = "approved", None
    audit(db, ws, member.user_id, "post_unscheduled", "Redaktionellen Termin aufgehoben")
    return post_output(p)
