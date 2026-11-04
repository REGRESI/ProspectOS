"""Official social connection and approval-bound publishing; no demo receipts."""

import hashlib
import os
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from app import credentials
from app.db import now
from app.jobs import enqueue
from app.models import Membership, Post
from app.platform_models import Asset, Connection, ContentPolicy, Job, OAuthState, PostMedia
from app.platform_schemas import PolicyInput, PublishInput


def _integrations_url(query: str) -> str:
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    return f"{base}/settings/integrations?linkedin_{query}"


def cipher():
    try:
        return Fernet(os.environ["TOKEN_ENCRYPTION_KEY"].encode())
    except (KeyError, ValueError):
        raise HTTPException(
            503, "Configure a valid TOKEN_ENCRYPTION_KEY before connecting providers."
        ) from None


def publication_context(db, ws, post, member):
    if member.role not in ("owner", "admin"):
        raise HTTPException(403, "Only owner/admin may authorize publication.")
    connection = db.scalar(
        select(Connection).where(Connection.workspace_id == ws, Connection.provider == "linkedin")
    )
    if (
        not connection
        or connection.expires_at <= now()
        or "w_member_social" not in connection.scopes
    ):
        raise HTTPException(409, "LinkedIn not connected or publishing scope unavailable.")
    if os.getenv("LINKEDIN_PUBLISHING_APPROVED") != "true" or not os.getenv("LINKEDIN_API_VERSION"):
        raise HTTPException(
            503, "Official LinkedIn product approval and supported API version required."
        )
    if post.approved_revision != post.version or post.state not in ("approved", "scheduled"):
        raise HTTPException(409, "Current revision must be approved.")
    media = db.scalars(
        select(Asset)
        .join(PostMedia, Asset.id == PostMedia.asset_id)
        .where(PostMedia.post_id == post.id)
    ).all()
    from app.experience import AssetOrigin

    if db.scalar(
        select(AssetOrigin.id).where(
            AssetOrigin.workspace_id == ws,
            AssetOrigin.asset_id.in_([a.id for a in media]),
            AssetOrigin.reviewed.is_(False),
        )
    ):
        raise HTTPException(409, "Generated media review is required.")
    if any(not asset.rights_confirmed or not asset.alt_text for asset in media):
        raise HTTPException(409, "Media rights/alt text missing.")
    try:
        token = cipher().decrypt(connection.encrypted_token.encode()).decode()
    except InvalidToken:
        raise HTTPException(
            409, "Stored credentials cannot be decrypted. Reconnect provider."
        ) from None
    return {
        "token": token,
        "author_urn": connection.author_urn,
        "scopes": connection.scopes,
        "caption": post.caption,
        "asset_keys": [asset.storage_key for asset in media],
        "alt_text": media[0].alt_text if media else post.alt_text,
    }


def prepare_publication(db, job):
    post = db.scalar(select(Post).where(Post.id == job.payload["post_id"]).with_for_update())
    member = db.get(Membership, (job.workspace_id, job.actor_id))
    if (
        not post
        or not member
        or post.version != job.payload["revision"]
        or not post.publish_enabled
    ):
        raise HTTPException(409, "Publication cancelled, changed or actor revoked.")
    policy = db.scalar(
        select(ContentPolicy)
        .where(ContentPolicy.workspace_id == job.workspace_id)
        .with_for_update()
    )
    if not policy:
        raise HTTPException(409, "Publication policy not configured.")
    if job.payload.get("automation_authorized") and policy.mode != "authorized_auto":
        raise HTTPException(409, "Automatic publication authorization was revoked.")
    # Serialize daily quota and account dispatch within this workspace.
    count = db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.workspace_id == job.workspace_id,
            Job.kind == "publish",
            Job.side_effect_started.is_(True),
            Job.dispatched_at >= now().replace(hour=0, minute=0, second=0, microsecond=0),
        )
    )
    if count >= policy.max_posts_daily:
        raise HTTPException(429, "Daily publication limit reached.")
    context = publication_context(db, job.workspace_id, post, member)
    post.state = "publishing"
    return context


def send_publication(context):
    from app.media import private_path
    from app.providers.linkedin import publish_post, upload_image

    image = None
    if context["asset_keys"]:
        image = upload_image(
            context["token"],
            context["author_urn"],
            private_path(context["asset_keys"][0]).read_bytes(),
            "image/jpeg",
            context["scopes"],
        )
    return publish_post(
        context["token"],
        context["author_urn"],
        context["caption"],
        context["scopes"],
        image_urn=image,
        alt_text=context["alt_text"],
    )


def register_social_routes(app, db_session, current_auth, scope, record, audit):
    def admin(member):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Owner/admin required.")

    @app.get("/v1/workspaces/{ws}/social/policy")
    def policy(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        item = db.scalar(select(ContentPolicy).where(ContentPolicy.workspace_id == ws))
        return {
            "mode": item.mode if item else "manual",
            "max_posts_daily": item.max_posts_daily if item else 3,
        }

    @app.put("/v1/workspaces/{ws}/social/policy")
    def update_policy(
        ws: str, body: PolicyInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        admin(member)
        item = db.scalar(
            select(ContentPolicy).where(ContentPolicy.workspace_id == ws).with_for_update()
        )
        if not item:
            item = ContentPolicy(workspace_id=ws)
            db.add(item)
        item.mode = body.mode
        item.max_posts_daily = body.max_posts_daily
        audit(
            db,
            ws,
            member.user_id,
            "content_policy_updated",
            "Publication policy changed; only explicitly approved revisions may publish",
        )
        return body

    @app.post("/v1/workspaces/{ws}/integrations/linkedin/start")
    def start(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        from app.providers.linkedin import authorization_url

        admin(member)
        cipher()
        raw = secrets.token_urlsafe(40)
        state = OAuthState(
            state_hash=hashlib.sha256(raw.encode()).hexdigest(),
            workspace_id=ws,
            user_id=member.user_id,
            expires_at=now() + timedelta(minutes=10),
        )
        db.add(state)
        return {"authorization_url": authorization_url(raw)}

    @app.get("/v1/integrations/linkedin/callback")
    def callback(
        state: str,
        code: str = "",
        error: str = "",
        auth=Depends(current_auth),
        db=Depends(db_session, scope="function"),
    ):
        from app.jobs import tenant
        from app.providers.linkedin import exchange_code

        if len(state) > 200 or len(code) > 2000 or len(error) > 100:
            raise HTTPException(400, "Invalid callback.")
        if error or not code:
            # Member cancelled or LinkedIn refused; nothing stored. Back to the UI.
            reason = "".join(c for c in (error or "missing_code") if c.isalnum() or c == "_")
            return RedirectResponse(_integrations_url("error=" + reason[:60]), status_code=303)
        item = db.scalar(
            select(OAuthState)
            .where(
                OAuthState.state_hash == hashlib.sha256(state.encode()).hexdigest(),
                OAuthState.user_id == auth.user_id,
            )
            .with_for_update()
        )
        if not item or item.consumed or item.expires_at <= now():
            raise HTTPException(400, "Invalid or expired OAuth state.")
        member = db.get(Membership, (item.workspace_id, auth.user_id))
        if not member or member.role not in ("owner", "admin"):
            raise HTTPException(403, "Workspace authorization revoked.")
        tenant(db, item.workspace_id)
        with credentials.workspace(db, item.workspace_id):
            connection = exchange_code(code)
        # Consume state before redirect; no tokens enter logs/browser payloads.
        item.consumed = True
        stored = db.scalar(
            select(Connection)
            .where(Connection.workspace_id == item.workspace_id, Connection.provider == "linkedin")
            .with_for_update()
        )
        if not stored:
            stored = Connection(workspace_id=item.workspace_id, provider="linkedin")
            db.add(stored)
        stored.encrypted_token = cipher().encrypt(connection.access_token.encode()).decode()
        stored.author_urn = connection.author_urn
        stored.scopes = connection.scopes
        stored.expires_at = now() + timedelta(seconds=connection.expires_in)
        audit(
            db,
            item.workspace_id,
            auth.user_id,
            "linkedin_connected",
            "Official OAuth connection established; granted scopes recorded",
        )
        return RedirectResponse(_integrations_url("connected=1"), status_code=303)

    @app.post("/v1/workspaces/{ws}/integrations/linkedin/disconnect")
    def disconnect(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        admin(member)
        item = db.scalar(
            select(Connection)
            .where(Connection.workspace_id == ws, Connection.provider == "linkedin")
            .with_for_update()
        )
        if item:
            db.delete(item)
        # Deletion stops new dispatch. An already dispatched provider call cannot be recalled.
        audit(
            db,
            ws,
            member.user_id,
            "linkedin_disconnected",
            "Local credential removed. Revoke provider authorization in LinkedIn settings if required.",
        )
        return {"status": "disconnected"}

    @app.post("/v1/workspaces/{ws}/social/posts/{entity_id}/publish", status_code=202)
    def publish(
        ws: str,
        entity_id: str,
        body: PublishInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app.platform_routes import job_output

        admin(member)
        post = record(db, Post, ws, entity_id, True)
        publication_context(db, ws, post, member)
        policy = db.scalar(select(ContentPolicy).where(ContentPolicy.workspace_id == ws))
        if not policy:
            policy = ContentPolicy(workspace_id=ws, mode="manual", max_posts_daily=3)
            db.add(policy)
            db.flush()
        if body.automation_authorized and policy.mode != "authorized_auto":
            raise HTTPException(409, "Automatic mode is not authorized.")
        if body.scheduled_at and body.scheduled_at <= now():
            raise HTTPException(422, "Future timestamp required.")
        key = f"publish:{post.id}:{post.version}"
        previous = db.scalar(select(Job).where(Job.workspace_id == ws, Job.idempotency_key == key))
        if previous:
            return job_output(previous)
        post.publish_enabled = True
        post.state = "scheduled"
        post.scheduled_at = body.scheduled_at or now()
        job = enqueue(
            db,
            ws,
            member.user_id,
            "publish",
            {
                "post_id": post.id,
                "revision": post.version,
                "automation_authorized": body.automation_authorized,
            },
            key,
            post.scheduled_at,
        )
        audit(
            db,
            ws,
            member.user_id,
            "publication_authorized",
            f"Explicit publication authorization for revision {post.version}",
        )
        return job_output(job)
