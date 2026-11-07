"""Incremental MVP domain models; all customer-owned records remain tenant-scoped."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now
from app.models import TenantMixin


class Asset(TenantMixin, Base):
    __tablename__ = "assets"
    title: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(String(2000), default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    rights_note: Mapped[str] = mapped_column(String(1000), default="")
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    content_type: Mapped[str] = mapped_column(String(80))
    size: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    alt_text: Mapped[str] = mapped_column(String(1000))
    rights_confirmed: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)


class Brand(TenantMixin, Base):
    __tablename__ = "brands"
    name: Mapped[str] = mapped_column(String(120))
    voice: Mapped[str] = mapped_column(String(1000), default="")
    audience: Mapped[str] = mapped_column(String(1000), default="")
    pillars: Mapped[list] = mapped_column(JSON, default=list)
    primary_color: Mapped[str] = mapped_column(String(7), default="#4F46E5")
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)


class PostMedia(TenantMixin, Base):
    __tablename__ = "post_media"
    post_id: Mapped[str] = mapped_column(String(36))
    asset_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("workspace_id", "post_id", "asset_id"),
        ForeignKeyConstraint(
            ["workspace_id", "post_id"],
            ["social_posts.workspace_id", "social_posts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["workspace_id", "asset_id"], ["assets.workspace_id", "assets.id"]),
    )


class PostRevision(TenantMixin, Base):
    __tablename__ = "post_revisions"
    post_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int]
    snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("workspace_id", "post_id", "revision"),
        ForeignKeyConstraint(
            ["workspace_id", "post_id"], ["social_posts.workspace_id", "social_posts.id"]
        ),
    )


class Job(TenantMixin, Base):
    __tablename__ = "jobs"
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(150))
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(120))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    side_effect_started: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "idempotency_key"),
        Index("job_pending", "workspace_id", "status", "available_at"),
    )


class UsageAccount(TenantMixin, Base):
    __tablename__ = "usage_accounts"
    ai_budget_minor: Mapped[int] = mapped_column(default=500)
    ai_spent_minor: Mapped[int] = mapped_column(default=0)
    ai_reserved_minor: Mapped[int] = mapped_column(default=0)
    # Exact actual spend in micro-USD; ai_spent_minor is its rounded-up mirror.
    ai_spent_micro: Mapped[int] = mapped_column(BigInteger, default=0)
    period: Mapped[str] = mapped_column(String(7), default=lambda: now().strftime("%Y-%m"))
    __table_args__ = (UniqueConstraint("workspace_id"),)


class UsageEvent(TenantMixin, Base):
    __tablename__ = "usage_events"
    job_id: Mapped[str] = mapped_column(String(36))
    provider: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_minor: Mapped[int] = mapped_column(default=0)
    # Actual cost (micro-USD) from the provider's usage field and the price table.
    cost_micro: Mapped[int] = mapped_column(BigInteger, default=0)
    # The cost cap held while the call ran; released when the actual cost is booked.
    reserved_minor: Mapped[int] = mapped_column(default=0)
    # True when the actual cost is unknown (no usage field, unknown outcome, old booking).
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    model: Mapped[str] = mapped_column(String(120), default="")
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (
        UniqueConstraint("workspace_id", "job_id"),
        ForeignKeyConstraint(["workspace_id", "job_id"], ["jobs.workspace_id", "jobs.id"]),
    )


class Task(TenantMixin, Base):
    __tablename__ = "tasks"
    title: Mapped[str] = mapped_column(String(240))
    contact_id: Mapped[str | None] = mapped_column(String(36))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(20), default="open")
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"]
        ),
    )


class Note(TenantMixin, Base):
    __tablename__ = "notes"
    body: Mapped[str] = mapped_column(String(5000))
    contact_id: Mapped[str | None] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"]
        ),
    )


class Campaign(TenantMixin, Base):
    __tablename__ = "campaigns"
    name: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)


class Enrollment(TenantMixin, Base):
    __tablename__ = "campaign_enrollments"
    campaign_id: Mapped[str] = mapped_column(String(36))
    contact_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("workspace_id", "campaign_id", "contact_id"),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"], ["campaigns.workspace_id", "campaigns.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"]
        ),
    )


class Consent(TenantMixin, Base):
    __tablename__ = "consents"
    contact_id: Mapped[str] = mapped_column(String(36))
    channel: Mapped[str] = mapped_column(String(20), default="email")
    evidence: Mapped[str] = mapped_column(String(1000))
    legal_basis: Mapped[str] = mapped_column(String(60))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)
    country: Mapped[str] = mapped_column(String(2), default="DE")
    evidence_url: Mapped[str | None] = mapped_column(String(2000))
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"]
        ),
    )


class Suppression(TenantMixin, Base):
    __tablename__ = "suppressions"
    contact_id: Mapped[str] = mapped_column(String(36))
    reason: Mapped[str] = mapped_column(String(200))
    __table_args__ = (
        UniqueConstraint("workspace_id", "contact_id"),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"]
        ),
    )


class Connection(TenantMixin, Base):
    __tablename__ = "connections"
    provider: Mapped[str] = mapped_column(String(40))
    encrypted_token: Mapped[str] = mapped_column(String(6000))
    author_urn: Mapped[str] = mapped_column(String(300))
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # One LinkedIn connection per user (migration 0021).
    user_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", "user_id"),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="connection_member",
            ondelete="CASCADE",
        ),
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed: Mapped[bool] = mapped_column(default=False)


class ContentPolicy(TenantMixin, Base):
    __tablename__ = "content_policies"
    mode: Mapped[str] = mapped_column(String(20), default="manual")
    max_posts_daily: Mapped[int] = mapped_column(default=3)
    __table_args__ = (UniqueConstraint("workspace_id"),)


class BillingAccount(TenantMixin, Base):
    __tablename__ = "billing_accounts"
    customer_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    subscription_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(40), default="trial")
    plan: Mapped[str] = mapped_column(String(40), default="trial")
    __table_args__ = (UniqueConstraint("workspace_id"),)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(150), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IntegrationCredential(TenantMixin, Base):
    """Encrypted per-workspace provider settings; the API only ever returns masks."""

    __tablename__ = "integration_credentials"
    provider: Mapped[str] = mapped_column(String(40))
    ciphertext: Mapped[str] = mapped_column(String(8000))
    masked: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="untested")
    last_error: Mapped[str] = mapped_column(String(200), default="")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider"),
        ForeignKeyConstraint(
            ["workspace_id", "updated_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )
