from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now, uid


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    auth_subject: Mapped[str | None] = mapped_column(String(500), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    auth_provider: Mapped[str] = mapped_column(String(20), default="demo")
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(100), unique=True)


class Membership(Base):
    __tablename__ = "memberships"
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")


class TenantMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Company(TenantMixin, Base):
    __tablename__ = "companies"
    name: Mapped[str] = mapped_column(String(240))
    website: Mapped[str | None] = mapped_column(String(2000))
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    identity: Mapped[str] = mapped_column(String(500))
    location: Mapped[str] = mapped_column(String(240), default="")
    industry: Mapped[str] = mapped_column(String(120), default="")
    source: Mapped[str] = mapped_column(String(100), default="user_entry")
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "identity"),
    )


class Contact(TenantMixin, Base):
    __tablename__ = "contacts"
    company_id: Mapped[str | None] = mapped_column(String(36))
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120), default="")
    job_title: Mapped[str] = mapped_column(String(240), default="")
    location: Mapped[str] = mapped_column(String(240), default="")
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(80))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    source_reviewed: Mapped[bool] = mapped_column(default=False)
    import_key: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="new")
    source: Mapped[str] = mapped_column(String(100), default="user_entry")
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "linkedin_url"),
        UniqueConstraint("workspace_id", "import_key"),
        ForeignKeyConstraint(
            ["workspace_id", "company_id"], ["companies.workspace_id", "companies.id"]
        ),
        Index("contact_workspace_name", "workspace_id", "last_name", "first_name"),
    )


class ImportJob(TenantMixin, Base):
    __tablename__ = "import_jobs"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="validated")
    data: Mapped[dict] = mapped_column(JSON)
    journal: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class ICP(TenantMixin, Base):
    __tablename__ = "icp_profiles"
    profile: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("workspace_id"),)


class Audit(TenantMixin, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))


class Deal(TenantMixin, Base):
    __tablename__ = "deals"
    title: Mapped[str] = mapped_column(String(200))
    contact_id: Mapped[str | None] = mapped_column(String(36))
    amount: Mapped[int] = mapped_column(BigInteger, default=0)
    stage: Mapped[str] = mapped_column(String(30), default="new")
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"]
        ),
    )


class Post(TenantMixin, Base):
    __tablename__ = "social_posts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "brand_id"],
            ["brands.workspace_id", "brands.id"],
            name="post_brand_tenant",
        ),
    )
    brand_id: Mapped[str | None] = mapped_column(String(36))
    publish_enabled: Mapped[bool] = mapped_column(default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_post_id: Mapped[str | None] = mapped_column(String(300))
    studio_context: Mapped[dict] = mapped_column(JSON, default=dict)
    caption: Mapped[str] = mapped_column(String(3000))
    alt_text: Mapped[str] = mapped_column(String(1000), default="")
    state: Mapped[str] = mapped_column(String(30), default="draft")
    version: Mapped[int] = mapped_column(default=1)
    approved_revision: Mapped[int | None]
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Draft(TenantMixin, Base):
    __tablename__ = "message_drafts"
    revision: Mapped[int] = mapped_column(default=1)
    approved_revision: Mapped[int | None]
    subject: Mapped[str] = mapped_column(String(200), default="")
    state: Mapped[str] = mapped_column(String(30), default="draft")
    contact_id: Mapped[str] = mapped_column(String(36))
    content: Mapped[str] = mapped_column(String(3000))
    source: Mapped[str] = mapped_column(String(40), default="offline")
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"], ["contacts.workspace_id", "contacts.id"]
        ),
    )


class Discovery(TenantMixin, Base):
    __tablename__ = "discovery_runs"
    query: Mapped[str] = mapped_column(String(300))
    results: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="completed")


# Register additive domain tables for migration metadata and test cleanup.
from app import platform_models as _platform_models  # noqa: E402,F401
