"""Durable PostgreSQL queue. Broker state, leases and results survive process restarts."""

import math
import os
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, text

from app.db import SessionLocal, now, uid
from app.models import Audit, Discovery, Membership, Post, Workspace
from app.platform_models import Job, UsageAccount, UsageEvent


def tenant(db, workspace):
    db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": workspace})


def enqueue(db, ws, actor, kind, payload, key=None, available_at=None):
    key = key or uid()
    existing = db.scalar(select(Job).where(Job.workspace_id == ws, Job.idempotency_key == key))
    if existing:
        return existing
    item = Job(
        workspace_id=ws,
        actor_id=actor,
        kind=kind,
        payload=payload,
        idempotency_key=key,
        available_at=available_at or now(),
    )
    db.add(item)
    db.flush()
    return item


def usage_account(db, ws):
    # Serialize creation and reservations across web/worker instances.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": "usage:" + ws}
    )
    account = db.scalar(
        select(UsageAccount).where(UsageAccount.workspace_id == ws).with_for_update()
    )
    if not account:
        account = UsageAccount(workspace_id=ws)
        db.add(account)
        db.flush()
    period = now().strftime("%Y-%m")
    if account.period != period and account.ai_reserved_minor == 0:
        account.period = period
        account.ai_spent_minor = 0
    return account


def reserve_ai(db, ws, prompt, multiplier=1):
    # UTF-8 byte count is a conservative token bound; completion tokens are capped by the provider.
    try:
        input_price = float(os.environ["LLM_INPUT_USD_PER_MILLION"])
        output_price = float(os.environ["LLM_OUTPUT_USD_PER_MILLION"])
        if not all(math.isfinite(v) and v >= 0 for v in (input_price, output_price)):
            raise ValueError()
    except (KeyError, ValueError):
        raise HTTPException(
            503, "Configure explicit LLM token prices before paid generation."
        ) from None
    bound = len(prompt.encode()) + 4096
    maximum = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1500"))
    reserved = (
        max(1, math.ceil((bound * input_price + maximum * output_price) / 10000)) * multiplier
    )
    account = usage_account(db, ws)
    if account.ai_spent_minor + account.ai_reserved_minor + reserved > account.ai_budget_minor:
        raise HTTPException(402, "Workspace AI budget exceeded.")
    account.ai_reserved_minor += reserved
    return reserved


def settle_ai(db, job, cost=0, usage=None):
    reservation = job.payload.get("reservation_minor", 0)
    if not reservation:
        return
    existing = db.scalar(select(UsageEvent).where(UsageEvent.job_id == job.id))
    if existing:
        return
    account = usage_account(db, job.workspace_id)
    account.ai_reserved_minor = max(0, account.ai_reserved_minor - reservation)
    account.ai_spent_minor += cost
    db.add(
        UsageEvent(
            workspace_id=job.workspace_id,
            job_id=job.id,
            provider="openai_images" if job.kind == "social_image" else "openai_compatible",
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cost_minor=cost,
        )
    )


def claim(ws):
    with SessionLocal() as db, db.begin():
        tenant(db, ws)
        expired = db.scalars(
            select(Job)
            .where(Job.workspace_id == ws, Job.status == "running", Job.lease_until < now())
            .with_for_update(skip_locked=True)
        ).all()
        for job in expired:
            if job.side_effect_started:
                job.status = "ambiguous"
                job.last_error = "lease_expired_after_dispatch"
                # Charge reserved maximum when outcome is unknown, never treat as free.
                settle_ai(db, job, job.payload.get("reservation_minor", 0))
            else:
                job.status = "retry" if job.attempts < job.max_attempts else "failed"
                job.last_error = "lease_expired"
                if job.status == "failed":
                    settle_ai(db, job)
        job = db.scalar(
            select(Job)
            .where(
                Job.workspace_id == ws,
                Job.status.in_(["queued", "retry"]),
                Job.available_at <= now(),
            )
            .order_by(Job.available_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return None
        job.status = "running"
        job.attempts += 1
        job.lease_until = now() + timedelta(minutes=5)
        return job.id, job.attempts


def dispatch(db, job):
    """Local transactional handlers. All required actor and tenant checks run again."""
    member = db.get(Membership, (job.workspace_id, job.actor_id))
    if not member or member.role not in ("owner", "admin", "editor"):
        raise HTTPException(403, "job_actor_permission_revoked")
    if job.kind == "import":
        from app.main import commit_import

        return commit_import(job.workspace_id, job.payload["import_id"], member, db)
    if job.kind == "discovery":
        from app.providers.discovery import SyntheticDemoProvider
        from app.providers.licensed import CompanySearchFilters, search_companies

        if job.payload["provider"] == "synthetic":
            if os.getenv("APP_ENV", "development") not in ("development", "test"):
                raise HTTPException(403, "synthetic_provider_disabled")
            rows = [
                r.model_dump()
                for r in SyntheticDemoProvider().search(
                    job.payload["query"], job.payload.get("limit", 5)
                )
            ]
            notice = "Synthetische Beispieldaten, keine recherchierten Suchtreffer."
        else:
            candidates = search_companies(
                CompanySearchFilters(
                    **{
                        k: v
                        for k, v in job.payload.items()
                        if k in ("city", "country", "industry", "min_employees", "max_employees")
                    }
                ),
                job.payload.get("limit", 10),
            )
            rows = [r.model_dump(mode="json") for r in candidates]
            notice = "Lizenzanbieter: Quellen und Nutzungsrechte vor Übernahme prüfen."
        if job.payload.get("criteria"):
            from app.journeys import apply_discovery_criteria

            rows, warnings = apply_discovery_criteria(
                db, job.workspace_id, rows, job.payload["criteria"]
            )
        else:
            warnings = []
        run = Discovery(workspace_id=job.workspace_id, query=job.payload["query"], results=rows)
        db.add(run)
        db.flush()
        return {"run_id": run.id, "results": rows, "notice": notice, "warnings": warnings}
    if job.kind == "ai":
        from app.providers.ai import generate_text

        result = generate_text(job.payload["prompt"], job.payload.get("sources", []))
        cost = math.ceil(result.estimated_cost_microunits / 10000)
        settle_ai(db, job, cost, result)
        return result.model_dump(mode="json") | {
            "verified": False,
            "purpose": job.payload["purpose"],
        }
    if job.kind == "research":
        from app.providers.research import research_company

        return research_company(job.payload["url"]).model_dump(mode="json")
    raise HTTPException(422, "unknown_job_type")


def execute_one(ws):
    selected = claim(ws)
    if not selected:
        return False
    job_id, attempt = selected
    try:
        with SessionLocal() as db, db.begin():
            tenant(db, ws)
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job.status != "running" or job.attempts != attempt:
                return True
            member = db.get(Membership, (ws, job.actor_id))
            if not member or member.role not in ("owner", "admin", "editor"):
                raise HTTPException(403, "job_actor_permission_revoked")
            if job.kind == "publish":
                from app.social import prepare_publication

                # Mark dispatch durably before making a provider request; crashed requests are ambiguous.
                context = prepare_publication(db, job)
                job.side_effect_started = True
                job.dispatched_at = now()
            elif job.kind == "email":
                from app.commercial import prepare_email

                context = prepare_email(db, job)
                job.side_effect_started = True
                job.dispatched_at = now()
            elif job.kind in ("social_text", "social_image", "social_reply"):
                from app.experience import validate_generation_config

                validate_generation_config(job)
                job.side_effect_started = True
                job.dispatched_at = now()
                context = None
            elif job.kind == "discovery" and job.payload.get("provider") == "pdl":
                job.side_effect_started = True
                job.dispatched_at = now()
                context = None
            elif job.kind == "ai":
                # A timed-out paid request may have incurred cost. Never blindly retry it.
                job.side_effect_started = True
                job.dispatched_at = now()
                context = None
            else:
                result = dispatch(db, job)
                job.status = "succeeded"
                job.result = result
                job.last_error = None
                db.add(
                    Audit(
                        workspace_id=ws,
                        actor_id=job.actor_id,
                        kind="job_completed",
                        description=f"{job.kind}: completed",
                    )
                )
                return True
        if job.kind == "publish":
            from app.social import send_publication

            result = send_publication(context)
            usage = None
        elif job.kind == "email":
            from app.commercial import send_authorized_email

            result = send_authorized_email(context, job_id)
            usage = None
        elif job.kind == "discovery":
            with SessionLocal() as db, db.begin():
                tenant(db, ws)
                result = dispatch(db, db.get(Job, job_id))
            usage = None
        elif job.kind in ("social_text", "social_image", "social_reply"):
            from app.experience import external_generation

            result, usage = external_generation(job)
        else:
            from app.providers.ai import generate_text

            usage = generate_text(job.payload["prompt"], job.payload.get("sources", []))
            result = usage.model_dump(mode="json") | {
                "verified": False,
                "purpose": job.payload["purpose"],
            }
        with SessionLocal() as db, db.begin():
            tenant(db, ws)
            current = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if current.attempts != attempt:
                return True
            if current.kind in ("social_text", "social_image", "social_reply"):
                from app.experience import finalize_generation

                result = finalize_generation(db, current, result)
            current.status = "succeeded"
            current.result = result
            current.last_error = None
            if usage:
                settle_ai(db, current, math.ceil(usage.estimated_cost_microunits / 10000), usage)
            if current.kind == "email":
                from app.models import Draft

                draft = db.get(Draft, current.payload["draft_id"])
                if draft:
                    draft.state = "accepted"
            if current.kind == "publish":
                post = db.scalar(
                    select(Post).where(Post.id == current.payload["post_id"]).with_for_update()
                )
                post.state = "published"
                post.provider_post_id = result["id"]
                post.published_at = now()
            db.add(
                Audit(
                    workspace_id=ws,
                    actor_id=current.actor_id,
                    kind="job_completed",
                    description=f"{current.kind}: completed",
                )
            )
    except Exception as exc:
        from app.providers.ai import ProviderError

        if isinstance(exc, HTTPException):
            code = str(exc.detail)[:100]
            retry = False
            ambiguous = False
        elif isinstance(exc, ProviderError):
            code = exc.code
            retry = exc.retryable
            ambiguous = exc.ambiguous
        else:
            code = "internal_job_failure"
            retry = False
            ambiguous = False
        with SessionLocal() as db, db.begin():
            tenant(db, ws)
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job.attempts != attempt:
                return True
            if not isinstance(exc, (HTTPException, ProviderError)) and job.side_effect_started:
                ambiguous = True
            # Never retry an uncertain external side effect.
            job.status = (
                "ambiguous"
                if ambiguous
                else (
                    "retry"
                    if retry and not job.side_effect_started and job.attempts < job.max_attempts
                    else "failed"
                )
            )
            job.last_error = code
            job.available_at = now() + timedelta(seconds=min(300, 2**job.attempts * 5))
            if job.status in ("failed", "ambiguous"):
                settle_ai(
                    db,
                    job,
                    job.payload.get("reservation_minor", 0) if job.side_effect_started else 0,
                )
            if job.kind == "email":
                from app.models import Draft

                draft = db.get(Draft, job.payload["draft_id"])
                if draft and draft.state == "sending":
                    draft.state = "ambiguous" if job.status == "ambiguous" else "failed"
            if job.kind == "publish":
                post = db.get(Post, job.payload["post_id"])
                if post and post.state == "publishing":
                    post.state = "failed"
            db.add(
                Audit(
                    workspace_id=ws,
                    actor_id=job.actor_id,
                    kind="job_failed",
                    description=f"{job.kind}: {code}",
                )
            )
    return True


def run_once():
    with SessionLocal() as db:
        workspaces = list(db.scalars(select(Workspace.id).order_by(Workspace.id)))
    return sum(execute_one(ws) for ws in workspaces)
