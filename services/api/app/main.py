import hashlib
import json
import logging
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

from app import credentials
from app.commercial import register_commercial_routes
from app.db import SessionLocal, now, uid
from app.entitlements import remaining
from app.experience import register_experience_routes, register_provider_tests
from app.identity import auth_settings, register_identity_routes
from app.imports import parse_csv
from app.journeys import company_listing, register_journey_routes
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
from app.observability import BodyLimitMiddleware
from app.platform_models import Asset, Brand, PostMedia, PostRevision
from app.platform_routes import register_platform_routes
from app.providers.ai import ProviderError
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
from app.social import register_social_routes
from app.studio import register_studio_routes


@asynccontextmanager
async def lifespan(app):
    from app.runtime import validate_runtime

    validate_runtime()
    yield


app = FastAPI(title="ProspectOS local pilot", version="0.1.0", lifespan=lifespan)
app.add_middleware(BodyLimitMiddleware)
request_logger = logging.getLogger("prospectos.requests")
request_logger.setLevel(logging.INFO)
if not request_logger.handlers:
    request_logger.addHandler(logging.StreamHandler())
request_logger.propagate = False
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
async def workspace_credentials(request, call_next):
    # Lazy per-request binding; values load only after `scope` authorized the member.
    parts = request.url.path.split("/")
    ws = parts[3] if len(parts) > 3 and parts[1:3] == ["v1", "workspaces"] else None
    token = credentials.bind(ws)
    try:
        return await call_next(request)
    finally:
        credentials.unbind(token)


@app.middleware("http")
async def security_headers(request, call_next):
    request_id = uid()
    request.state.request_id = request_id
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        response = problem(
            500, "internal_error", "Internal operation failed. Use the request ID for support."
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-Id"] = request_id
    route = request.scope.get("route")
    request_logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "route": getattr(route, "path", "unmatched"),
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
        )
    )
    return response


def db_session():
    with SessionLocal() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def current_auth(request: Request, db: Session = Depends(db_session, scope="function")):
    raw = request.cookies.get("prospectos_session", "")
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    auth = db.get(AuthSession, token_hash)
    if auth is None or auth.expires_at <= now():
        raise HTTPException(401, "Bitte anmelden.")
    user = db.get(User, auth.user_id)
    settings = auth_settings()
    if not user or (
        settings.mode == "supabase"
        and (
            auth.auth_provider != "supabase"
            or not user.auth_subject
            or not user.auth_subject.startswith(settings.issuer + ":")
        )
    ):
        raise HTTPException(401, "Verified external identity required.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not secrets.compare_digest(csrf, auth.csrf_token):
            raise HTTPException(403, "Sicherheitsprüfung fehlgeschlagen. Bitte neu laden.")
    return auth


def scope(
    ws: str,
    request: Request,
    auth=Depends(current_auth),
    db: Session = Depends(db_session, scope="function"),
):
    member = db.get(Membership, (ws, auth.user_id))
    if member is None:
        raise HTTPException(404, "Workspace nicht gefunden.")
    read_only_post = request.method == "POST" and request.url.path.endswith(
        ("/leads/query", "/discovery/interpret")
    )
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and not read_only_post
        and member.role
        not in (
            "owner",
            "admin",
            "editor",
            "approver",
        )
    ):
        raise HTTPException(403, "Diese Rolle hat nur Lesezugriff.")
    # Approvers can review, but cannot modify contacts, ICP or authored content.
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and not read_only_post
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
    # Production first (default after login), then user-created, demo examples last.
    order = {"production": 0, "standard": 1, "demo": 2}
    workspaces = sorted(
        workspaces,
        key=lambda r: (r[0].archived_at is not None, order.get(r[0].kind, 1), r[0].name),
    )
    return {
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "csrf_token": auth.csrf_token,
        "workspaces": [
            {
                "id": w.id,
                "name": w.name,
                "slug": w.slug,
                "role": role,
                "kind": w.kind,
                "archived": w.archived_at is not None,
            }
            for w, role in workspaces
        ],
    }


@app.post("/v1/auth/demo")
def login(
    body: Login,
    request: Request,
    response: Response,
    db: Session = Depends(db_session, scope="function"),
):
    if auth_settings().mode != "demo":
        raise HTTPException(403, "Demo authentication is disabled.")
    key = request.client.host if request.client else "local"
    attempts = login_attempts[key]
    while attempts and attempts[0] < time.monotonic() - 60:
        attempts.popleft()
    # 10 per minute; the isolated E2E stack raises it because every spec signs in.
    if len(attempts) >= int(os.getenv("LOGIN_ATTEMPTS_PER_MINUTE", "10")):
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
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        path="/",
    )
    return auth_payload(db, auth)


@app.get("/v1/me")
def me(auth=Depends(current_auth), db: Session = Depends(db_session, scope="function")):
    return auth_payload(db, auth)


@app.post("/v1/auth/logout")
def logout(
    response: Response,
    auth=Depends(current_auth),
    db: Session = Depends(db_session, scope="function"),
):
    db.delete(auth)
    response.delete_cookie("prospectos_session", path="/")
    return {"ok": True}


@app.get("/v1/workspaces")
def workspaces(auth=Depends(current_auth), db: Session = Depends(db_session, scope="function")):
    return {"items": auth_payload(db, auth)["workspaces"]}


@app.post("/v1/workspaces", status_code=201)
def new_workspace(
    body: WorkspaceInput,
    auth=Depends(current_auth),
    db: Session = Depends(db_session, scope="function"),
):
    workspace = Workspace(name=body.name, slug="workspace-" + uid()[:8], kind=body.kind)
    db.add(workspace)
    db.flush()
    db.add(Membership(workspace_id=workspace.id, user_id=auth.user_id, role="owner"))
    return {
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "role": "owner",
        "kind": workspace.kind,
        "archived": False,
    }


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
    } | {
        "company": company.name if company else "",
        "company_id": contact.company_id,
        "score": score(contact, company, icp),
        "outreach_stage": contact.outreach_stage or "new",
        "linkedin_status": contact.linkedin_status or "unchecked",
        "linkedin_reason": contact.linkedin_reason or "",
        "owner_id": contact.owner_id,
    }


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
    stage: str = "",
    sort: str = "-created",
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
    stmt = select(Contact).where(Contact.workspace_id == ws)
    if stage:
        stmt = stmt.where(Contact.outreach_stage == stage)
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
    desc = sort.startswith("-")
    key = sort.lstrip("-")
    columns = {
        "name": func.lower(Contact.last_name + " " + Contact.first_name),
        "company": select(func.lower(Company.name))
        .where(Company.id == Contact.company_id)
        .scalar_subquery(),
        "location": func.lower(Contact.location),
        "stage": Contact.outreach_stage,
        "created": Contact.created_at,
    }
    if key not in columns:
        raise HTTPException(422, "Unbekannte Sortierung.")
    order = columns[key].desc().nullslast() if desc else columns[key].asc().nullslast()
    items, total = paginate(db, stmt.order_by(order, Contact.id), page, limit)
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
def get_contact(
    ws: str,
    entity_id: str,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
    c = record(db, Contact, ws, entity_id)
    return contact_output(
        c, db.get(Company, c.company_id) if c.company_id else None, profile(db, ws)
    )


@app.post("/v1/workspaces/{ws}/contacts", status_code=201)
def create_contact(
    ws: str,
    body: ContactInput,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
    remaining(db, ws, "contacts")
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
    db: Session = Depends(db_session, scope="function"),
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
    ws: str,
    entity_id: str,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
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
    db: Session = Depends(db_session, scope="function"),
):
    return company_listing(db, ws, page, limit)


@app.get("/v1/workspaces/{ws}/icp")
def get_icp(ws: str, member=Depends(scope), db: Session = Depends(db_session, scope="function")):
    return profile(db, ws)


@app.put("/v1/workspaces/{ws}/icp")
def put_icp(
    ws: str,
    body: ICPInput,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
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
    db: Session = Depends(db_session, scope="function"),
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
    ws: str,
    entity_id: str,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
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
    capacity = remaining(db, ws, "contacts", require_slot=False)
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
        if created >= capacity:
            raise HTTPException(402, "Workspace contact limit exceeded; import rolled back.")
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
    ws: str,
    entity_id: str,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
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
def dashboard(ws: str, member=Depends(scope), db: Session = Depends(db_session, scope="function")):
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
    db: Session = Depends(db_session, scope="function"),
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
    search: str = "",
    stage: str = "",
    sort: str = "created",
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
    if (
        len(search) > 200
        or sort not in ("created", "amount", "title")
        or stage
        and stage
        not in ("new", "qualified", "contacted", "conversation", "proposal", "won", "lost")
    ):
        raise HTTPException(422, "Invalid pipeline filters.")
    stmt = select(Deal).where(Deal.workspace_id == ws)
    if search:
        stmt = stmt.where(
            Deal.title.ilike("%" + search.replace("%", "\\%").replace("_", "\\_") + "%")
        )
    if stage:
        stmt = stmt.where(Deal.stage == stage)
    filtered = stmt.subquery()
    open_value = db.scalar(
        select(func.coalesce(func.sum(filtered.c.amount), 0)).where(
            filtered.c.stage.not_in(["won", "lost"])
        )
    )
    won_value = db.scalar(
        select(func.coalesce(func.sum(filtered.c.amount), 0)).where(filtered.c.stage == "won")
    )
    order = {
        "created": Deal.created_at.desc(),
        "amount": Deal.amount.desc(),
        "title": Deal.title.asc(),
    }[sort]
    items, total = paginate(db, stmt.order_by(order, Deal.id), page, limit)
    return {
        "items": [deal_output(d) for d in items],
        "total": total,
        "page": page,
        "limit": limit,
        "open_value": open_value,
        "won_value": won_value,
    }


@app.post("/v1/workspaces/{ws}/deals", status_code=201)
def create_deal(
    ws: str,
    body: DealInput,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
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
    db: Session = Depends(db_session, scope="function"),
):
    deal = record(db, Deal, ws, entity_id, True)
    deal.stage = body.stage
    audit(db, ws, member.user_id, "deal_stage_changed", "Deal-Phase aktualisiert: " + body.stage)
    return deal_output(deal)


def post_output(p):
    from sqlalchemy.orm import object_session

    from app.content_strategy import post_strategy

    db = object_session(p)
    assets = (
        list(db.scalars(select(PostMedia.asset_id).where(PostMedia.post_id == p.id))) if db else []
    )
    return (
        {
            key: getattr(p, key)
            for key in (
                "id",
                "brand_id",
                "provider_post_id",
                "publish_enabled",
                "caption",
                "alt_text",
                "state",
                "version",
                "approved_revision",
                "scheduled_at",
                "created_at",
            )
        }
        | {"asset_ids": assets, "studio_context": p.studio_context, "author_id": p.author_id}
        | post_strategy(p)
    )


@app.get("/v1/workspaces/{ws}/social/posts")
def posts(
    ws: str,
    page: int = 1,
    limit: int = 100,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
    items, total = paginate(
        db,
        select(Post).where(Post.workspace_id == ws).order_by(Post.created_at.desc()),
        page,
        limit,
    )
    return {"items": [post_output(p) for p in items], "total": total, "page": page, "limit": limit}


@app.post("/v1/workspaces/{ws}/social/posts", status_code=201)
def create_post(
    ws: str,
    body: PostInput,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
    validate_post_refs(db, ws, body)
    if body.campaign_id:
        from app.content_strategy import ContentCampaign as Campaign

        record(db, Campaign, ws, body.campaign_id)
    if "studio_context" not in body.model_fields_set:
        body.studio_context.image_mode = "manual" if body.asset_ids else "none"
    p = Post(workspace_id=ws, author_id=member.user_id, **body.model_dump(exclude={"asset_ids"}))
    db.add(p)
    db.flush()
    replace_post_media(db, ws, p, body.asset_ids)
    audit(db, ws, member.user_id, "post_created", "Beitragsentwurf angelegt")
    return post_output(p)


@app.patch("/v1/workspaces/{ws}/social/posts/{entity_id}")
def edit_post(
    ws: str,
    entity_id: str,
    body: PostPatch,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
    p = record(db, Post, ws, entity_id, True)
    if p.version != body.version:
        raise HTTPException(409, "Beitrag wurde zwischenzeitlich geändert.")
    if p.state == "publishing":
        raise HTTPException(409, "Publication in progress; wait for provider reconciliation.")
    validate_post_refs(db, ws, body, previous=p)
    from app.content_strategy import STRATEGY_FIELDS
    from app.content_strategy import ContentCampaign as Campaign
    from app.voice_learning import record_edit

    # Every change to a draft is kept (original and the user's version) for the profile.
    record_edit(db, ws, member.user_id, "post", p.id, p.caption, body.caption)
    if body.campaign_id and "campaign_id" in body.model_fields_set:
        record(db, Campaign, ws, body.campaign_id)
    for field in STRATEGY_FIELDS & body.model_fields_set:
        setattr(p, field, getattr(body, field))
    if (p.studio_context or {}).get("placeholder") and not body.caption.startswith("(Text folgt)"):
        p.studio_context = {k: v for k, v in (p.studio_context or {}).items() if k != "placeholder"}
    p.caption, p.alt_text, p.brand_id = body.caption, body.alt_text, body.brand_id
    if "studio_context" in body.model_fields_set:
        p.studio_context = body.studio_context.model_dump()
    p.version += 1
    if p.state != "draft":
        p.state = "needs_review"
    p.approved_revision, p.scheduled_at = None, None
    p.publish_enabled = False
    replace_post_media(db, ws, p, body.asset_ids)
    audit(
        db,
        ws,
        member.user_id,
        "post_edited",
        "Beitrag geändert; bisherige Freigabe und Planung ungültig",
    )
    return post_output(p)


@app.post("/v1/workspaces/{ws}/social/posts/{entity_id}/submit-review")
def review_post(
    ws: str,
    entity_id: str,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
    p = record(db, Post, ws, entity_id, True)
    if p.state not in ("draft", "needs_review"):
        raise HTTPException(409, "Beitrag ist bereits freigegeben oder geplant.")
    p.state = "needs_review"
    audit(db, ws, member.user_id, "post_review_requested", "Beitrag zur Prüfung eingereicht")
    return post_output(p)


@app.post("/v1/workspaces/{ws}/social/posts/{entity_id}/approve")
def approve_post(
    ws: str,
    entity_id: str,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
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
    db: Session = Depends(db_session, scope="function"),
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
        "revision": d.revision,
        "subject": d.subject,
        "state": d.state,
        "send_allowed": False,
        "reason": "Kein automatischer LinkedIn-Versand. E-Mail erfordert getrennte Freigabe, geprüfte Quelle, gültigen Nachweis und ungesperrten Empfänger.",
    }


@app.post("/v1/workspaces/{ws}/outreach/drafts")
def create_draft(
    ws: str,
    body: DraftInput,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
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
    db: Session = Depends(db_session, scope="function"),
):
    items, total = paginate(
        db,
        select(Draft).where(Draft.workspace_id == ws).order_by(Draft.created_at.desc()),
        page,
        limit,
    )
    return {"items": [draft_output(d) for d in items], "total": total, "page": page, "limit": limit}


@app.get("/v1/workspaces/{ws}/integrations")
def integrations(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
    from app.experience import image_requirements
    from app.platform_models import Connection

    images = image_requirements()
    connected = db.scalar(
        select(Connection).where(
            Connection.workspace_id == ws,
            Connection.provider == "linkedin",
            Connection.user_id == member.user_id,
            Connection.expires_at > now(),
        )
    )
    return {
        "items": [
            {
                "name": "LinkedIn",
                "connect_available": bool(
                    credentials.get("LINKEDIN_CLIENT_ID")
                    and credentials.get("LINKEDIN_CLIENT_SECRET")
                    and os.getenv("LINKEDIN_REDIRECT_URI")
                    and os.getenv("TOKEN_ENCRYPTION_KEY")
                ),
                "publish_available": bool(
                    connected
                    and "w_member_social" in connected.scopes
                    and os.getenv("LINKEDIN_PUBLISHING_APPROVED") == "true"
                    and os.getenv("LINKEDIN_API_VERSION")
                ),
                "scopes": connected.scopes if connected else [],
                "status": "connected" if connected else "not_configured",
                "reason": "Verbunden. Posten geht nur, wenn LinkedIn es für deine App freigegeben hat."
                if connected
                else "Noch nicht verbunden. Posten ist erst nach der Verbindung möglich.",
            },
            {
                "name": "KI-Text",
                "status": "configured"
                if credentials.get("LLM_API_KEY") and credentials.get("LLM_MODEL")
                else "not_configured",
                "reason": "Eingerichtet. Texte entstehen nur mit Quellen und im Rahmen deines Budgets."
                if credentials.get("LLM_API_KEY")
                else "Noch kein KI-Anbieter eingerichtet.",
            },
            {
                "name": "KI-Bilder",
                "status": "configured" if images["configured"] else "not_configured",
                "reason": "Eingerichtet. Jedes Bild prüfst du, bevor es verwendet wird."
                if images["configured"]
                else "Noch nicht eingerichtet. Es fehlt: " + ", ".join(images["requirements"]),
            },
            {
                "name": "Firmensuche mit Lizenz",
                "status": "configured"
                if os.getenv("PDL_API_KEY") and os.getenv("PDL_LICENSE_APPROVED") == "true"
                else "not_configured",
                "reason": "Optional. Braucht einen Vertrag mit einem Datenanbieter. OpenStreetMap funktioniert ohne.",
            },
            {
                "name": "Stripe",
                "status": "configured" if os.getenv("STRIPE_SECRET_KEY") else "not_configured",
                "reason": "Zahlungen, nur im Testmodus.",
            },
        ]
    }


@app.post("/v1/workspaces/{ws}/discovery/runs")
def discovery(
    ws: str, body: Topic, member=Depends(scope), db: Session = Depends(db_session, scope="function")
):
    from app.providers.discovery import SyntheticDemoProvider

    if os.getenv("APP_ENV", "development") not in ("development", "test"):
        raise HTTPException(403, "Synthetic discovery is development-only.")

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
    ws: str,
    entity_id: str,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
    run = record(db, Discovery, ws, entity_id, True)
    if run.status == "imported":
        return {"created": 0, "status": "imported"}
    capacity = (
        remaining(db, ws, "contacts", require_slot=False)
        if any(r.get("source") == "synthetic_demo" for r in run.results)
        else 0
    )
    created = 0
    for row in run.results:
        if row.get("source") != "synthetic_demo":
            identity = row.get("source", "licensed") + ":" + row["external_key"]
            existing = db.scalar(
                select(Company.id).where(Company.workspace_id == ws, Company.identity == identity)
            )
            if not existing:
                company = make_company(
                    db,
                    ws,
                    row["company"],
                    row.get("location", ""),
                    identity,
                    row.get("source", "licensed"),
                )
                company.industry = row.get("industry", "")
                company.website = row.get("website")
                company.provenance = {
                    k: row.get(k)
                    for k in ("source_url", "license", "observed_at", "confidence", "allowed_uses")
                }
                created += 1
            continue
        key = hashlib.sha256(("synthetic_demo:" + row["external_key"]).encode()).hexdigest()
        if db.scalar(
            select(Contact.id).where(Contact.workspace_id == ws, Contact.import_key == key)
        ):
            continue
        if created >= capacity:
            raise HTTPException(402, "Workspace contact limit exceeded.")
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
        f"{created} Discovery-Datensätze mit Herkunft übernommen; keine Marketingfreigabe",
    )
    return {"created": created, "status": run.status}


@app.get("/health/live")
def live():
    return {"status": "ok", "mode": os.getenv("APP_ENV", "development")}


@app.get("/health/ready")
def ready(db: Session = Depends(db_session, scope="function")):
    db.execute(text("SELECT 1 FROM contacts LIMIT 0"))
    version = db.scalar(text("SELECT current_user"))
    return {"status": "ready", "database": "connected", "role": version}


@app.post("/v1/workspaces/{ws}/social/posts/{entity_id}/cancel")
def cancel_post(
    ws: str,
    entity_id: str,
    member=Depends(scope),
    db: Session = Depends(db_session, scope="function"),
):
    p = record(db, Post, ws, entity_id, True)
    if p.state != "scheduled":
        raise HTTPException(409, "Nur geplante Termine können aufgehoben werden.")
    p.state, p.scheduled_at = "approved", None
    p.publish_enabled = False
    audit(db, ws, member.user_id, "post_unscheduled", "Redaktionellen Termin aufgehoben")
    return post_output(p)


def validate_post_refs(db, ws, body, previous=None):
    from app.experience import AssetOrigin
    from app.studio import VoiceProfile

    # A deleted voice can remain as historical attribution on an existing draft.
    prior_voice = (previous.studio_context or {}).get("voice_profile_id") if previous else None
    if body.studio_context.voice_profile_id and body.studio_context.voice_profile_id != prior_voice:
        record(db, VoiceProfile, ws, body.studio_context.voice_profile_id)
    if body.studio_context.generation_job_id:
        from app.platform_models import Job

        job = record(db, Job, ws, body.studio_context.generation_job_id)
        if job.kind != "social_text" or job.status != "succeeded":
            raise HTTPException(422, "Erfolgreichen Textauftrag auswählen.")
    if body.brand_id:
        record(db, Brand, ws, body.brand_id)
    for asset_id in body.asset_ids:
        asset = record(db, Asset, ws, asset_id)
        origin = db.scalar(
            select(AssetOrigin).where(
                AssetOrigin.workspace_id == ws, AssetOrigin.asset_id == asset.id
            )
        )
        if origin and not origin.reviewed:
            raise HTTPException(409, "Review generated image before using it in a post.")
        if not asset.rights_confirmed or not asset.alt_text:
            raise HTTPException(422, "Asset rights and alt text required.")


def replace_post_media(db, ws, post, asset_ids):
    for media in db.scalars(select(PostMedia).where(PostMedia.post_id == post.id)):
        db.delete(media)
    db.flush()
    for asset_id in asset_ids:
        db.add(PostMedia(workspace_id=ws, post_id=post.id, asset_id=asset_id))
    db.add(
        PostRevision(
            workspace_id=ws,
            post_id=post.id,
            revision=post.version,
            snapshot={
                "caption": post.caption,
                "alt_text": post.alt_text,
                "brand_id": post.brand_id,
                "asset_ids": asset_ids,
                "studio_context": post.studio_context,
            },
        )
    )
    db.flush()


register_identity_routes(app, db_session, current_auth, scope, auth_payload, audit)

register_platform_routes(app, db_session, scope, record, paginate, audit)
register_social_routes(app, db_session, current_auth, scope, record, audit)

register_commercial_routes(app, db_session, scope, record, audit)


@app.exception_handler(ProviderError)
async def provider_error(request, exc):
    return problem(503, exc.code, "Provider operation unavailable: " + exc.code)


register_experience_routes(app, db_session, scope, record, paginate, audit, contact_output, profile)

register_journey_routes(app, db_session, scope, record, paginate, audit, contact_output, profile)

register_provider_tests(app, db_session, scope, audit)


register_studio_routes(app, db_session, scope, record, paginate, audit)

from app.sales_agent import register_sales_agent_routes  # noqa: E402

register_sales_agent_routes(app, db_session, scope, record, paginate, audit)

from app.linkedin_channel import register_linkedin_channel_routes  # noqa: E402

register_linkedin_channel_routes(app, db_session, scope, record, paginate, audit)

from app.integrations import register_integration_routes  # noqa: E402

register_integration_routes(app, db_session, scope, audit)

from app.research_flow import register_research_routes  # noqa: E402

register_research_routes(app, db_session, scope, record, audit)

from app.ranking import register_ranking_routes  # noqa: E402

register_ranking_routes(app, db_session, scope, record, audit)

from app.today import register_today_routes  # noqa: E402

register_today_routes(app, db_session, scope, record, audit)

from app.style import register_style_routes  # noqa: E402

register_style_routes(app, db_session, scope, audit)

from app.setup_check import register_setup_routes  # noqa: E402

register_setup_routes(app, db_session, scope)

from app.workspace_admin import register_workspace_admin_routes  # noqa: E402

register_workspace_admin_routes(app, db_session, scope, audit)

from app.email_outreach import register_email_routes  # noqa: E402

register_email_routes(app, db_session, scope, record, audit)

from app.content_plan import register_content_routes  # noqa: E402

register_content_routes(app, db_session, scope, record, audit)
from app.content_plan import register_content_apply  # noqa: E402

register_content_apply(app, db_session, scope, record, audit)

from app.agent import register_agent_routes  # noqa: E402

register_agent_routes(app, db_session, scope, record, audit)

from app.profile_check import register_profile_routes  # noqa: E402

register_profile_routes(app, db_session, scope, audit)

from app.content_strategy import register_strategy_routes  # noqa: E402

register_strategy_routes(app, db_session, scope, record, audit)

from app.voice_learning import register_voice_learning_routes  # noqa: E402

register_voice_learning_routes(app, db_session, scope, record, audit)

from app.team import register_team_routes  # noqa: E402

register_team_routes(app, db_session, scope, audit)
