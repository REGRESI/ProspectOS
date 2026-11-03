"""Connected prospecting workflows layered on the existing tenant-safe MVP.

Read-only query endpoints use explicit validated filters, never executable query text.
All synthetic and provider-reported data retains its provenance and uncertainty.
"""

import hashlib
import os
import re
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy import (
    JSON,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    cast,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now
from app.entitlements import remaining
from app.jobs import enqueue
from app.models import (
    Company,
    Contact,
    Deal,
    Discovery,
    Draft,
    ImportJob,
    Membership,
    TenantMixin,
)
from app.platform_models import Campaign, Consent, Enrollment, Note, Suppression, Task
from app.schemas import Strict
from app.scoring import score


class LeadProfile(TenantMixin, Base):
    __tablename__ = "lead_profiles"
    contact_id: Mapped[str] = mapped_column(String(36))
    owner_id: Mapped[str | None] = mapped_column(String(36))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (
        UniqueConstraint("workspace_id", "contact_id"),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "owner_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class Segment(TenantMixin, Base):
    __tablename__ = "saved_segments"
    name: Mapped[str] = mapped_column(String(120))
    filters: Mapped[dict] = mapped_column(JSON)


class SavedSearch(TenantMixin, Base):
    __tablename__ = "saved_searches"
    name: Mapped[str] = mapped_column(String(120))
    briefing: Mapped[str] = mapped_column(String(2000), default="")
    filters: Mapped[dict] = mapped_column(JSON)


class ICPProfile(TenantMixin, Base):
    __tablename__ = "intelligence_profiles"
    name: Mapped[str] = mapped_column(String(120))
    profile: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(default=1)


class CompanyProfile(TenantMixin, Base):
    __tablename__ = "company_profiles"
    company_id: Mapped[str] = mapped_column(String(36))
    is_customer: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        UniqueConstraint("workspace_id", "company_id"),
        ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            ondelete="CASCADE",
        ),
    )


class CompanyFact(TenantMixin, Base):
    __tablename__ = "company_facts"
    company_id: Mapped[str] = mapped_column(String(36))
    field: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(String(1000))
    source_url: Mapped[str] = mapped_column(String(2000))
    confidence: Mapped[str] = mapped_column(String(30), default="user_reported")
    source_kind: Mapped[str] = mapped_column(String(40), default="manual")
    source_id: Mapped[str | None] = mapped_column(String(64))
    actor_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "actor_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="company_fact_actor",
        ),
    )


class GeocodeCache(TenantMixin, Base):
    """Per-workspace cache of OSM Nominatim results (usage policy requires caching)."""

    __tablename__ = "geocode_cache"
    query_key: Mapped[str] = mapped_column(String(300))
    latitude: Mapped[float]
    longitude: Mapped[float]
    display_name: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str] = mapped_column(String(300))
    __table_args__ = (UniqueConstraint("workspace_id", "query_key"),)


class CampaignConfig(TenantMixin, Base):
    __tablename__ = "campaign_configs"
    campaign_id: Mapped[str] = mapped_column(String(36))
    channel: Mapped[str] = mapped_column(String(30), default="linkedin_manual")
    __table_args__ = (
        UniqueConstraint("workspace_id", "campaign_id"),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
        ),
    )


class CampaignStep(TenantMixin, Base):
    __tablename__ = "campaign_sequence_steps"
    campaign_id: Mapped[str] = mapped_column(String(36))
    position: Mapped[int]
    delay_days: Mapped[int] = mapped_column(default=0)
    channel: Mapped[str] = mapped_column(String(30), default="linkedin_manual")
    template: Mapped[str] = mapped_column(String(3000))
    __table_args__ = (
        UniqueConstraint("workspace_id", "campaign_id", "position"),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
        ),
    )


class CampaignDraft(TenantMixin, Base):
    __tablename__ = "campaign_draft_links"
    campaign_id: Mapped[str] = mapped_column(String(36))
    contact_id: Mapped[str] = mapped_column(String(36))
    draft_id: Mapped[str] = mapped_column(String(36))
    step_position: Mapped[int] = mapped_column(default=0)
    __table_args__ = (
        UniqueConstraint("workspace_id", "campaign_id", "contact_id", "step_position"),
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
        ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["message_drafts.workspace_id", "message_drafts.id"],
            ondelete="CASCADE",
        ),
    )


class ManualActivity(TenantMixin, Base):
    __tablename__ = "manual_outreach_activities"
    contact_id: Mapped[str] = mapped_column(String(36))
    campaign_id: Mapped[str | None] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(String(1000), default="")
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "actor_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class LeadQuery(Strict):
    search: str = Field(default="", max_length=240)
    statuses: list[str] = Field(default_factory=list, max_length=4)
    sources: list[str] = Field(default_factory=list, max_length=20)
    company_id: str | None = None
    location: str = Field(default="", max_length=240)
    job_title: str = Field(default="", max_length=240)
    tags: list[str] = Field(default_factory=list, max_length=20)
    owner_id: str | None = None
    has_email: str = "any"
    min_score: int = Field(default=0, ge=0, le=100)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=25, ge=1, le=100)
    sort: str = "created"
    direction: str = "desc"
    icp_id: str | None = None

    @model_validator(mode="after")
    def valid_choices(self):
        if (
            set(self.statuses) - {"new", "qualified", "contacted", "archived"}
            or self.has_email not in ("any", "present", "missing")
            or self.sort not in ("name", "created", "score")
            or self.direction not in ("asc", "desc")
        ):
            raise ValueError("Invalid query filter")
        if any(not tag.strip() or len(tag) > 50 for tag in self.tags):
            raise ValueError("Invalid tag")
        return self


class BulkInput(Strict):
    contact_ids: list[str] = Field(min_length=1, max_length=100)
    status: str | None = None
    tags_add: list[str] = Field(default_factory=list, max_length=20)
    tags_remove: list[str] = Field(default_factory=list, max_length=20)
    owner_id: str | None = None
    campaign_id: str | None = None

    @model_validator(mode="after")
    def validate_values(self):
        if self.status is not None and self.status not in (
            "new",
            "qualified",
            "contacted",
            "archived",
        ):
            raise ValueError("Invalid status")
        if any(not s.strip() or len(s) > 50 for s in self.tags_add + self.tags_remove):
            raise ValueError("Invalid tag")
        return self


class SegmentInput(Strict):
    name: str = Field(min_length=1, max_length=120)
    filters: LeadQuery = Field(default_factory=LeadQuery)


class SearchFilters(Strict):
    provider: str = "synthetic"
    country: str = Field(default="germany", max_length=100)
    region: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    radius_km: int | None = Field(default=None, ge=1, le=500)
    industries: list[str] = Field(default_factory=list, max_length=20)
    excluded_industries: list[str] = Field(default_factory=list, max_length=20)
    min_employees: int | None = Field(default=None, ge=0, le=10000000)
    max_employees: int | None = Field(default=None, ge=1, le=10000000)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    job_titles: list[str] = Field(default_factory=list, max_length=20)
    seniority: list[str] = Field(default_factory=list, max_length=20)
    exclude_customers: bool = True
    max_results: int = Field(default=10, ge=1, le=50)
    license_confirmed: bool = False

    @model_validator(mode="after")
    def valid(self):
        if self.provider not in ("synthetic", "pdl", "osm"):
            raise ValueError("Unknown provider")
        if self.provider == "osm" and self.radius_km is not None and self.radius_km > 50:
            raise ValueError("OSM radius is limited to 50 km")
        if (
            self.min_employees is not None
            and self.max_employees is not None
            and self.min_employees > self.max_employees
        ):
            raise ValueError("Invalid employee range")
        if any(
            not s.strip() or len(s) > 120
            for group in (
                self.industries,
                self.excluded_industries,
                self.keywords,
                self.job_titles,
                self.seniority,
            )
            for s in group
        ):
            raise ValueError("Invalid search term")
        return self


class SearchDefinition(Strict):
    name: str = Field(min_length=1, max_length=120)
    briefing: str = Field(default="", max_length=2000)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class Briefing(Strict):
    briefing: str = Field(min_length=3, max_length=2000)


class ConfirmSearch(Strict):
    confirmed: bool = False
    license_confirmed: bool = False


class SelectedResults(Strict):
    keys: list[str] = Field(min_length=1, max_length=100)


class SequenceStepInput(Strict):
    position: int = Field(ge=0, le=9)
    delay_days: int = Field(default=0, ge=0, le=90)
    channel: str = "linkedin_manual"
    template: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def valid_template(self):
        if self.channel not in ("linkedin_manual", "email"):
            raise ValueError("Unsupported channel")
        variables = set(re.findall(r"\{([^{}]+)\}", self.template))
        if variables - {"first_name", "last_name", "company", "job_title", "evidence"}:
            raise ValueError("Unsupported template variable")
        return self


class SequenceInput(Strict):
    channel: str = "linkedin_manual"
    steps: list[SequenceStepInput] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def valid(self):
        if self.channel not in ("linkedin_manual", "email") or len(
            {s.position for s in self.steps}
        ) != len(self.steps):
            raise ValueError("Invalid sequence")
        return self


class GenerateDrafts(Strict):
    template: str | None = Field(default=None, max_length=3000)


class HandoffInput(Strict):
    contact_id: str
    campaign_id: str | None = None
    kind: str
    note: str = Field(default="", max_length=1000)

    @field_validator("kind")
    @classmethod
    def supported(cls, value):
        if value not in (
            "profile_opened",
            "connection_requested",
            "connected",
            "message_sent_manually",
            "replied",
            "followup_due",
        ):
            raise ValueError("Unsupported manual activity")
        return value


class IntelligenceProfileInput(Strict):
    name: str = Field(min_length=1, max_length=120)
    locations: list[str] = Field(default_factory=list, max_length=30)
    roles: list[str] = Field(default_factory=list, max_length=30)
    industries: list[str] = Field(default_factory=list, max_length=30)
    excluded_industries: list[str] = Field(default_factory=list, max_length=30)
    min_employees: int | None = Field(default=None, ge=0)
    max_employees: int | None = Field(default=None, ge=1)
    needs: list[str] = Field(default_factory=list, max_length=30)
    required_fields: list[str] = Field(default_factory=list, max_length=20)
    optional_fields: list[str] = Field(default_factory=list, max_length=20)
    weights: dict[str, int] = Field(
        default_factory=lambda: {"location": 35, "role": 35, "industry": 30, "size": 0, "needs": 0}
    )

    @model_validator(mode="after")
    def valid(self):
        if (
            set(self.weights) - {"location", "role", "industry", "size", "needs"}
            or set(self.weights) < {"location", "role", "industry"}
            or sum(self.weights.values()) != 100
            or any(v < 0 or v > 100 for v in self.weights.values())
        ):
            raise ValueError("Weights must sum to100")
        if (
            self.min_employees is not None
            and self.max_employees is not None
            and self.min_employees > self.max_employees
        ):
            raise ValueError("Invalid size range")
        allowed = {"email", "phone", "company", "job_title", "location", "linkedin_url"}
        if (set(self.required_fields) | set(self.optional_fields)) - allowed:
            raise ValueError("Unknown field")
        if any(
            not value.strip() or len(value) > 120
            for group in (
                self.locations,
                self.roles,
                self.industries,
                self.excluded_industries,
                self.needs,
            )
            for value in group
        ):
            raise ValueError("Invalid criterion")
        return self


def completeness(values: dict):
    missing = [key for key, value in values.items() if value is None or value == ""]
    total = len(values)
    return {
        "present": total - len(missing),
        "total": total,
        "percent": round((total - len(missing)) * 100 / total) if total else 0,
        "missing": missing,
    }


def _pattern(value):
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _profile(db, ws, icp_id, legacy_profile):
    if not icp_id:
        return legacy_profile(db, ws)
    item = db.scalar(
        select(ICPProfile).where(ICPProfile.workspace_id == ws, ICPProfile.id == icp_id)
    )
    if not item:
        raise HTTPException(404, "ICP profile not found.")
    return item.profile


def explained_score(contact, company, profile):
    result = score(contact, company, profile)
    if not any(profile.get("weights", {}).get(k) for k in ("size", "needs")) and not profile.get(
        "excluded_industries"
    ):
        return result
    factors = list(result["factors"])
    missing = list(result["missing_data"])
    evidence = (company.provenance or {}) if company else {}
    count = evidence.get("employee_count")
    known_size = isinstance(count, int) and not isinstance(count, bool) and count >= 0
    size_fit = (
        known_size
        and (profile.get("min_employees") is None or count >= profile["min_employees"])
        and (profile.get("max_employees") is None or count <= profile["max_employees"])
    )
    maximum = profile.get("weights", {}).get("size", 0)
    if maximum:
        factors.append(
            {
                "name": "Unternehmensgröße",
                "points": maximum if size_fit else 0,
                "max_points": maximum,
                "reason": f"Anbieterangabe: {count} Mitarbeitende"
                if known_size
                else "Keine belegte Größenangabe – unbekannt",
            }
        )
    known_needs = evidence.get("business_needs")
    known_needs = known_needs if isinstance(known_needs, list) else []
    need_fit = any(
        needle.casefold() in str(value).casefold()
        for needle in profile.get("needs", [])
        for value in known_needs
    )
    maximum = profile.get("weights", {}).get("needs", 0)
    if maximum:
        factors.append(
            {
                "name": "Belegter Bedarf",
                "points": maximum if need_fit else 0,
                "max_points": maximum,
                "reason": "Gemeldete Bedarfsangabe passt; Quelle prüfen"
                if known_needs
                else "Kein belegter Bedarf – unbekannt",
            }
        )
    excluded = bool(
        company
        and company.industry
        and any(
            x.casefold() in company.industry.casefold()
            for x in profile.get("excluded_industries", [])
        )
    )
    if excluded:
        factors.append(
            {
                "name": "Branchenausschluss",
                "points": 0,
                "max_points": 0,
                "reason": "Bekannte Branchenangabe entspricht einem expliziten Ausschluss.",
            }
        )
    result.update(
        value=0 if excluded else sum(f["points"] for f in factors),
        factors=factors,
        missing_data=[x for x in missing if not (x == "Unternehmensgröße" and known_size)],
    )
    return result


def contact_extended(db, contact, company, profile, metadata=None):
    metadata = metadata or db.scalar(
        select(LeadProfile).where(LeadProfile.contact_id == contact.id)
    )
    values = {
        k: getattr(contact, k)
        for k in (
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
    }
    values.update(
        company=company.name if company else "",
        company_id=contact.company_id,
        tags=metadata.tags if metadata else [],
        owner_id=metadata.owner_id if metadata else None,
        score=explained_score(contact, company, profile),
        completeness=completeness(
            {
                "company": company.name if company else None,
                "job_title": contact.job_title,
                "location": contact.location,
                "email": contact.email,
                "phone": contact.phone,
                "linkedin_url": contact.linkedin_url,
            }
        ),
        provenance={"source": contact.source, "reviewed": contact.source_reviewed},
    )
    return values


def company_listing(db, ws, page=1, limit=25, search=""):
    if page < 1 or not 1 <= limit <= 100:
        raise HTTPException(422, "Invalid pagination.")
    counts = (
        select(Contact.company_id, func.count().label("contact_count"))
        .where(Contact.workspace_id == ws)
        .group_by(Contact.company_id)
        .subquery()
    )
    deals = (
        select(Contact.company_id, func.count(Deal.id).label("deal_count"))
        .join(Deal, Deal.contact_id == Contact.id)
        .where(Contact.workspace_id == ws, Deal.workspace_id == ws)
        .group_by(Contact.company_id)
        .subquery()
    )
    stmt = (
        select(
            Company, func.coalesce(counts.c.contact_count, 0), func.coalesce(deals.c.deal_count, 0)
        )
        .outerjoin(counts, counts.c.company_id == Company.id)
        .outerjoin(deals, deals.c.company_id == Company.id)
        .where(Company.workspace_id == ws)
    )
    if search:
        stmt = stmt.where(
            or_(
                Company.name.ilike(_pattern(search)),
                Company.location.ilike(_pattern(search)),
                Company.industry.ilike(_pattern(search)),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(
        stmt.order_by(Company.name, Company.id).offset((page - 1) * limit).limit(limit)
    ).all()
    return {
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "location": c.location,
                "industry": c.industry,
                "source": c.source,
                "website": c.website,
                "provenance": c.provenance,
                "contact_count": count,
                "deal_count": deal_count,
                "completeness": completeness(
                    {"location": c.location, "industry": c.industry, "website": c.website}
                ),
            }
            for c, count, deal_count in rows
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


def _activity_output(item):
    return {
        k: getattr(item, k)
        for k in ("id", "kind", "note", "contact_id", "campaign_id", "created_at")
    } | {"verification": "self_reported"}


def _draft_output(db, draft):
    contact = db.get(Contact, draft.contact_id)
    link = db.scalar(select(CampaignDraft).where(CampaignDraft.draft_id == draft.id))
    campaign = db.get(Campaign, link.campaign_id) if link else None
    blocked = []
    if draft.approved_revision != draft.revision:
        blocked.append("Aktuelle Revision ist nicht freigegeben.")
    if db.scalar(select(Suppression.id).where(Suppression.contact_id == draft.contact_id)):
        blocked.append("Kontakt ist gesperrt.")
    if contact is None or not contact.email:
        blocked.append("Keine E-Mail bekannt.")
    if contact is None or not contact.source_reviewed:
        blocked.append("Quellenrechte sind noch nicht geprüft.")
    consent = db.scalar(
        select(Consent.id)
        .where(
            Consent.contact_id == draft.contact_id,
            Consent.revoked.is_(False),
            Consent.expires_at > now(),
        )
        .limit(1)
    )
    if not consent:
        blocked.append("Kein gültiger Werbekontakt-Nachweis dokumentiert.")
    return {
        k: getattr(draft, k)
        for k in (
            "id",
            "contact_id",
            "content",
            "subject",
            "revision",
            "state",
            "approved_revision",
            "source",
            "created_at",
        )
    } | {
        "contact": {
            "id": contact.id,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "linkedin_url": contact.linkedin_url,
        }
        if contact
        else None,
        "campaign": {"id": campaign.id, "name": campaign.name} if campaign else None,
        "campaign_id": campaign.id if campaign else None,
        "blocked_reasons": blocked,
        "send_allowed": False,
        "manual_handoff_only": True,
    }


def register_journey_routes(
    app, db_session, scope, record, paginate, audit, contact_output, legacy_profile
):
    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Bearbeitungsrecht erforderlich.")

    def profile_for(db, ws, icp_id=None):
        return _profile(db, ws, icp_id, legacy_profile)

    def output_contacts(db, rows, ws, icp_id=None):
        companies = {
            c.id: c
            for c in db.scalars(
                select(Company).where(
                    Company.workspace_id == ws,
                    Company.id.in_([row.company_id for row in rows if row.company_id]),
                )
            )
        }
        metadata = {
            m.contact_id: m
            for m in db.scalars(
                select(LeadProfile).where(
                    LeadProfile.workspace_id == ws,
                    LeadProfile.contact_id.in_([row.id for row in rows]),
                )
            )
        }
        profile = profile_for(db, ws, icp_id)
        return [
            contact_extended(db, row, companies.get(row.company_id), profile, metadata.get(row.id))
            for row in rows
        ]

    def lead_stmt(ws, body):
        stmt = (
            select(Contact)
            .outerjoin(Company, Company.id == Contact.company_id)
            .outerjoin(LeadProfile, LeadProfile.contact_id == Contact.id)
            .where(Contact.workspace_id == ws)
        )
        if body.search:
            term = _pattern(body.search)
            stmt = stmt.where(
                or_(
                    Contact.first_name.ilike(term),
                    Contact.last_name.ilike(term),
                    Contact.job_title.ilike(term),
                    Company.name.ilike(term),
                    Contact.location.ilike(term),
                )
            )
        if body.statuses:
            stmt = stmt.where(Contact.status.in_(body.statuses))
        if body.sources:
            stmt = stmt.where(Contact.source.in_(body.sources))
        if body.company_id:
            stmt = stmt.where(Contact.company_id == body.company_id)
        if body.location:
            stmt = stmt.where(Contact.location.ilike(_pattern(body.location)))
        if body.job_title:
            stmt = stmt.where(Contact.job_title.ilike(_pattern(body.job_title)))
        if body.tags:
            stmt = stmt.where(cast(LeadProfile.tags, JSONB).contains(body.tags))
        if body.owner_id:
            stmt = stmt.where(
                LeadProfile.owner_id.is_(None)
                if body.owner_id == "unassigned"
                else LeadProfile.owner_id == body.owner_id
            )
        if body.has_email == "present":
            stmt = stmt.where(Contact.email.is_not(None), Contact.email != "")
        elif body.has_email == "missing":
            stmt = stmt.where(or_(Contact.email.is_(None), Contact.email == ""))
        return stmt

    @app.post("/v1/workspaces/{ws}/leads/query")
    def query_leads(
        ws: str, body: LeadQuery, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        stmt = lead_stmt(ws, body)
        if body.sort == "score" or body.min_score:
            # Scores are explainable domain logic. Bound materialization while preserving exact totals.
            total = db.scalar(select(func.count()).select_from(stmt.subquery()))
            if total > 20000:
                raise HTTPException(
                    422,
                    "Für die Score-Sortierung bitte die Suche auf höchstens 20.000 Kontakte eingrenzen.",
                )
            rows = db.scalars(stmt.order_by(Contact.id)).all()
            items = output_contacts(db, rows, ws, body.icp_id)
            items = [item for item in items if item["score"]["value"] >= body.min_score]
            if body.sort == "score":
                items.sort(
                    key=lambda x: (x["score"]["value"], x["id"]), reverse=body.direction == "desc"
                )
            elif body.sort == "name":
                items.sort(
                    key=lambda x: (x["last_name"].casefold(), x["first_name"].casefold(), x["id"]),
                    reverse=body.direction == "desc",
                )
            else:
                items.sort(
                    key=lambda x: (x["created_at"], x["id"]), reverse=body.direction == "desc"
                )
            total = len(items)
            items = items[(body.page - 1) * body.limit : body.page * body.limit]
        else:
            order = (
                (Contact.last_name, Contact.first_name, Contact.id)
                if body.sort == "name"
                else (Contact.created_at, Contact.id)
            )
            rows, total = paginate(
                db,
                stmt.order_by(
                    *(
                        column.desc() if body.direction == "desc" else column.asc()
                        for column in order
                    )
                ),
                body.page,
                body.limit,
            )
            items = output_contacts(db, rows, ws, body.icp_id)
        return {"items": items, "total": total, "page": body.page, "limit": body.limit}

    @app.post("/v1/workspaces/{ws}/leads/bulk")
    def bulk_leads(
        ws: str, body: BulkInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        ids = set(body.contact_ids)
        rows = db.scalars(
            select(Contact)
            .where(Contact.workspace_id == ws, Contact.id.in_(ids))
            .order_by(Contact.id)
            .with_for_update()
        ).all()
        if len(rows) != len(ids):
            raise HTTPException(
                404, "Mindestens ein Kontakt ist nicht in diesem Workspace vorhanden."
            )
        if body.owner_id and not db.get(Membership, (ws, body.owner_id)):
            raise HTTPException(422, "Zuständige Person gehört nicht zum Workspace.")
        if body.campaign_id:
            record(db, Campaign, ws, body.campaign_id, True)
        enrolled = 0
        for contact in rows:
            meta = db.scalar(
                select(LeadProfile).where(LeadProfile.contact_id == contact.id).with_for_update()
            )
            if not meta:
                meta = LeadProfile(workspace_id=ws, contact_id=contact.id, tags=[])
                db.add(meta)
            tags = set(meta.tags or []) | {s.strip() for s in body.tags_add}
            tags -= {s.strip() for s in body.tags_remove}
            if len(tags) > 50:
                raise HTTPException(422, "Höchstens 50 Tags pro Kontakt.")
            meta.tags = sorted(tags, key=str.casefold)
            if "owner_id" in body.model_fields_set:
                meta.owner_id = body.owner_id
            if body.status:
                contact.status = body.status
            contact.version += 1
            if body.campaign_id and not db.scalar(
                select(Enrollment.id).where(
                    Enrollment.campaign_id == body.campaign_id, Enrollment.contact_id == contact.id
                )
            ):
                db.add(
                    Enrollment(workspace_id=ws, campaign_id=body.campaign_id, contact_id=contact.id)
                )
                enrolled += 1
        audit(
            db,
            ws,
            member.user_id,
            "leads_bulk_updated",
            f"{len(rows)} Kontakte aktualisiert; {enrolled} Kampagnenzuordnungen erstellt",
        )
        return {"updated": len(rows), "enrolled": enrolled}

    @app.get("/v1/workspaces/{ws}/segments")
    def segments(
        ws: str,
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        rows, total = paginate(
            db,
            select(Segment).where(Segment.workspace_id == ws).order_by(Segment.created_at.desc()),
            page,
            limit,
        )
        return {
            "items": [
                {"id": r.id, "name": r.name, "filters": r.filters, "created_at": r.created_at}
                for r in rows
            ],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @app.post("/v1/workspaces/{ws}/segments", status_code=201)
    def create_segment(
        ws: str, body: SegmentInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        if body.filters.company_id:
            record(db, Company, ws, body.filters.company_id)
        if body.filters.icp_id:
            record(db, ICPProfile, ws, body.filters.icp_id)
        item = Segment(
            workspace_id=ws,
            name=body.name,
            filters=body.filters.model_dump(exclude={"page", "limit"}),
        )
        db.add(item)
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "segment_created",
            "Validierte Kontaktfilter als Segment gespeichert",
        )
        return {
            "id": item.id,
            "name": item.name,
            "filters": item.filters,
            "created_at": item.created_at,
        }

    @app.get("/v1/workspaces/{ws}/contacts/{entity_id}/context")
    def contact_context(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        contact = record(db, Contact, ws, entity_id)
        company = db.get(Company, contact.company_id) if contact.company_id else None
        extended = contact_extended(db, contact, company, profile_for(db, ws))
        campaigns = db.scalars(
            select(Campaign)
            .join(Enrollment, Enrollment.campaign_id == Campaign.id)
            .where(Enrollment.contact_id == contact.id)
            .order_by(Campaign.created_at.desc())
            .limit(100)
        ).all()
        notes = db.scalars(
            select(Note)
            .where(Note.contact_id == contact.id)
            .order_by(Note.created_at.desc())
            .limit(100)
        ).all()
        tasks = db.scalars(
            select(Task)
            .where(Task.contact_id == contact.id)
            .order_by(Task.created_at.desc())
            .limit(100)
        ).all()
        drafts = db.scalars(
            select(Draft)
            .where(Draft.contact_id == contact.id)
            .order_by(Draft.created_at.desc())
            .limit(100)
        ).all()
        activities = db.scalars(
            select(ManualActivity)
            .where(ManualActivity.contact_id == contact.id)
            .order_by(ManualActivity.created_at.desc())
            .limit(100)
        ).all()
        return {
            "contact": extended,
            "company": {
                "id": company.id,
                "name": company.name,
                "location": company.location,
                "website": company.website,
                "industry": company.industry,
                "source": company.source,
                "provenance": company.provenance,
            }
            if company
            else None,
            "notes": [_columns(r, ("id", "body", "contact_id", "created_at")) for r in notes],
            "tasks": [_columns(r, ("id", "title", "due_at", "state", "contact_id")) for r in tasks],
            "drafts": [_draft_output(db, r) for r in drafts],
            "campaigns": [_columns(r, ("id", "name", "status", "goal")) for r in campaigns],
            "activities": [_activity_output(r) for r in activities],
            "missing_fields": extended["completeness"]["missing"],
        }

    @app.get("/v1/workspaces/{ws}/companies/summary")
    def companies_summary(
        ws: str,
        search: str = "",
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        return company_listing(db, ws, page, limit, search)

    @app.get("/v1/workspaces/{ws}/companies/{entity_id}")
    def company_detail(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        company = record(db, Company, ws, entity_id)
        contacts = db.scalars(
            select(Contact)
            .where(Contact.company_id == company.id)
            .order_by(Contact.last_name, Contact.id)
            .limit(100)
        ).all()
        contact_ids = select(Contact.id).where(Contact.company_id == company.id)
        deals = db.scalars(
            select(Deal)
            .where(Deal.contact_id.in_(contact_ids))
            .order_by(Deal.created_at.desc())
            .limit(100)
        ).all()
        tasks = db.scalars(
            select(Task)
            .where(Task.contact_id.in_(contact_ids))
            .order_by(Task.created_at.desc())
            .limit(100)
        ).all()
        notes = db.scalars(
            select(Note)
            .where(Note.contact_id.in_(contact_ids))
            .order_by(Note.created_at.desc())
            .limit(100)
        ).all()
        research = db.scalars(
            select(CompanyFact)
            .where(CompanyFact.company_id == company.id)
            .order_by(CompanyFact.created_at.desc())
            .limit(100)
        ).all()
        activities = db.scalars(
            select(ManualActivity)
            .where(ManualActivity.contact_id.in_(contact_ids))
            .order_by(ManualActivity.created_at.desc())
            .limit(100)
        ).all()
        meta = db.scalar(select(CompanyProfile).where(CompanyProfile.company_id == company.id))
        summary = _columns(
            company, ("id", "name", "location", "industry", "source", "website", "provenance")
        ) | {
            "contact_count": db.scalar(
                select(func.count()).select_from(Contact).where(Contact.company_id == company.id)
            ),
            "deal_count": db.scalar(
                select(func.count()).select_from(Deal).where(Deal.contact_id.in_(contact_ids))
            ),
            "is_customer": bool(meta and meta.is_customer),
            "completeness": completeness(
                {
                    "location": company.location,
                    "industry": company.industry,
                    "website": company.website,
                }
            ),
        }
        return {
            "company": summary,
            "contacts": output_contacts(db, contacts, ws),
            "contacts_total": summary["contact_count"],
            "deals": [_columns(r, ("id", "title", "contact_id", "amount", "stage")) for r in deals],
            "notes": [_columns(r, ("id", "body", "contact_id", "created_at")) for r in notes],
            "tasks": [_columns(r, ("id", "title", "contact_id", "due_at", "state")) for r in tasks],
            "research": [
                _columns(r, ("id", "field", "value", "source_url", "confidence", "created_at"))
                for r in research
            ],
            "activities": [_activity_output(r) for r in activities],
        }

    @app.get("/v1/workspaces/{ws}/imports/history")
    def import_history(
        ws: str,
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        rows, total = paginate(
            db,
            select(ImportJob)
            .where(ImportJob.workspace_id == ws)
            .order_by(ImportJob.created_at.desc()),
            page,
            limit,
        )
        return {
            "items": [
                {
                    "id": r.id,
                    "status": r.status,
                    "created_at": r.created_at,
                    "total": r.data.get("total", 0),
                    "summary": r.summary,
                    "headers": r.data.get("headers", []),
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @app.get("/v1/workspaces/{ws}/imports/{entity_id}/report")
    def import_report(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        item = record(db, ImportJob, ws, entity_id)
        errors = [
            {"row": r.get("row"), "errors": r.get("errors", [])}
            for r in item.data.get("rows", [])
            if r.get("errors")
        ]
        return {
            "id": item.id,
            "status": item.status,
            "summary": item.summary,
            "errors": errors[:100],
            "total": item.data.get("total", 0),
            "notice": "Rohdaten werden nach Commit entfernt; der Bericht enthält keine Kontaktwerte.",
        }

    @app.post("/v1/workspaces/{ws}/discovery/interpret")
    def interpret(
        ws: str, body: Briefing, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        suggested = SearchFilters().model_dump()
        found = []
        city = re.search(r"\b(?:in|bei|um|Raum)\s+([A-ZÄÖÜ][\wÄÖÜäöüß-]+)", body.briefing)
        if city:
            suggested["city"] = city.group(1)
            found.append("city")
        employees = re.search(
            r"(\d+)\s*[-–]\s*(\d+)\s*(?:Mitarbeit|Beschäftigt|employees)", body.briefing, re.I
        )
        if employees:
            low, high = map(int, employees.groups())
            if 0 <= low <= high <= 10000000:
                suggested.update(min_employees=low, max_employees=high)
                found += ["min_employees", "max_employees"]
        radius = re.search(r"\b(\d{1,3})\s*km\b", body.briefing, re.I)
        if radius and 1 <= int(radius.group(1)) <= 500:
            suggested["radius_km"] = int(radius.group(1))
            found.append("radius_km")
        for value in ("Geschäftsführer", "Office Management", "Facility Management", "CEO"):
            if value.casefold() in body.briefing.casefold():
                suggested["job_titles"].append(value)
        if suggested["job_titles"]:
            found.append("job_titles")
        from app.providers.osm import CATEGORIES
        from app.providers.osm import enabled as osm_enabled

        words = {w.casefold() for w in re.findall(r"[\wÄÖÜäöüß-]+", body.briefing)}
        for label, spec in CATEGORIES.items():
            if (
                any(alias in words for alias in spec["aliases"])
                and label not in suggested["industries"]
            ):
                suggested["industries"].append(label)
        if suggested["industries"]:
            found.append("industries")
        if osm_enabled() and (suggested["city"] or suggested["region"]):
            suggested["provider"] = "osm"
            found.append("provider")
        return {
            "suggested_filters": suggested,
            "interpretation": {
                "method": "deterministic_suggestions",
                "unparsed": body.briefing,
                "recognized_fields": found,
                "requires_confirmation": True,
            },
            "warnings": [
                "Regelbasierte Vorschläge sind keine validierten Suchkriterien. Prüfe Land, Region, Branche und die vollständigen Filter vor dem Start.",
                "Personen-/Radiusfilter werden nur angewandt, wenn der Anbieter diese Funktion unterstützt.",
            ],
        }

    @app.get("/v1/workspaces/{ws}/discovery/providers")
    def discovery_providers(ws: str, member=Depends(scope)):
        from app.providers.osm import ATTRIBUTION, CATEGORIES
        from app.providers.osm import enabled as osm_enabled

        development = os.getenv("APP_ENV", "development") in ("development", "test")
        pdl = bool(os.getenv("PDL_API_KEY")) and os.getenv("PDL_LICENSE_APPROVED") == "true"
        return {
            "items": [
                {
                    "id": "osm",
                    "label": "OpenStreetMap (Orte & Firmen)",
                    "available": osm_enabled(),
                    "reason": None
                    if osm_enabled()
                    else "OSM_DISCOVERY_ENABLED=true und OSM_CONTACT konfigurieren.",
                    "supports": ["city", "region", "radius_km", "industries", "keywords"],
                    "unsupported": ["employee_range", "job_titles", "seniority", "contacts"],
                    "license": "ODbL 1.0",
                    "attribution": ATTRIBUTION,
                    "cost": "Kostenlos; öffentliche Infrastruktur mit Nutzungsgrenzen",
                },
                {
                    "id": "pdl",
                    "label": "People Data Labs (lizenziert)",
                    "available": pdl,
                    "reason": None if pdl else "Lizenz, Referenz und API-Schlüssel erforderlich.",
                    "supports": ["country", "city", "industries", "employee_range"],
                    "unsupported": ["radius_km", "job_titles", "seniority"],
                    "license": "Vertragsabhängig",
                    "cost": "Kostenpflichtig je Abfrage",
                },
                {
                    "id": "synthetic",
                    "label": "Synthetische Demo",
                    "available": development,
                    "reason": None if development else "Nur in Entwicklung/Test.",
                    "supports": [],
                    "unsupported": ["alle Filter – feste Beispieldaten"],
                    "license": "Synthetisch",
                    "cost": "Keine",
                },
            ],
            "osm_categories": [
                {"label": label, "tags": [f"{k}={v}" for k, v in spec["tags"]]}
                for label, spec in CATEGORIES.items()
            ],
        }

    @app.get("/v1/workspaces/{ws}/discovery/searches")
    def searches(
        ws: str,
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        rows, total = paginate(
            db,
            select(SavedSearch)
            .where(SavedSearch.workspace_id == ws)
            .order_by(SavedSearch.created_at.desc()),
            page,
            limit,
        )
        return {
            "items": [
                _columns(r, ("id", "name", "briefing", "filters", "created_at")) for r in rows
            ],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @app.post("/v1/workspaces/{ws}/discovery/searches", status_code=201)
    def save_search(
        ws: str,
        body: SearchDefinition,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        item = SavedSearch(
            workspace_id=ws,
            name=body.name,
            briefing=body.briefing,
            filters=body.filters.model_dump(),
        )
        db.add(item)
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "discovery_search_saved",
            "Explizite Suchkriterien gespeichert; kein Anbieteraufruf ausgelöst",
        )
        return _columns(item, ("id", "name", "briefing", "filters", "created_at"))

    @app.post("/v1/workspaces/{ws}/discovery/searches/{entity_id}/run", status_code=202)
    def run_search(
        ws: str,
        entity_id: str,
        body: ConfirmSearch,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app.platform_routes import job_output

        search = record(db, SavedSearch, ws, entity_id)
        criteria = SearchFilters.model_validate(search.filters)
        if not body.confirmed:
            raise HTTPException(
                422, "Die vorgeschlagenen Suchfilter müssen ausdrücklich bestätigt werden."
            )
        if criteria.provider == "synthetic" and os.getenv("APP_ENV", "development") not in (
            "development",
            "test",
        ):
            raise HTTPException(403, "Synthetische Daten sind in Produktion deaktiviert.")
        if criteria.provider == "pdl" and (
            not (body.license_confirmed or criteria.license_confirmed)
            or os.getenv("PDL_LICENSE_APPROVED") != "true"
            or not os.getenv("PDL_API_KEY")
        ):
            raise HTTPException(503, "Anbieterzugang und geprüfte Lizenz/Nutzungsrechte fehlen.")
        warnings = []
        osm_fields = {}
        if criteria.provider == "osm":
            from app.providers.osm import enabled, resolve_categories

            if not enabled():
                raise HTTPException(
                    503,
                    "OpenStreetMap-Suche ist nicht aktiviert (OSM_DISCOVERY_ENABLED und OSM_CONTACT erforderlich).",
                )
            if not (criteria.city or criteria.region):
                raise HTTPException(422, "Für die OSM-Suche Ort oder Region angeben.")
            categories, unmapped = resolve_categories(criteria.industries)
            if not categories and not criteria.keywords:
                raise HTTPException(
                    422,
                    "Mindestens eine OSM-abbildbare Branche oder ein Namens-Schlüsselwort angeben.",
                )
            if unmapped:
                warnings.append(
                    "Nicht auf OSM-Kategorien abbildbar und nicht angewandt: " + ", ".join(unmapped)
                )
            if criteria.min_employees is not None or criteria.max_employees is not None:
                warnings.append(
                    "OpenStreetMap enthält keine Mitarbeiterzahlen; Größenfilter wird nicht angewandt."
                )
            osm_fields = {
                "place": criteria.city or criteria.region,
                "radius_km": criteria.radius_km or 10,
                "categories": categories,
                "keywords": criteria.keywords,
            }
            if criteria.radius_km is None:
                warnings.append("Kein Radius angegeben; Standard 10 km angewandt.")
        elif criteria.radius_km is not None:
            warnings.append(
                "Radius wird von diesem Company-Adapter nicht unterstützt und nicht angewandt."
            )
        if criteria.job_titles or criteria.seniority:
            warnings.append(
                "Personenrollen/Seniorität sind im Company-Adapter nicht suchbar. Keine Personenrecherche wird behauptet."
            )
        payload = {
            "query": search.briefing or search.name,
            "provider": criteria.provider,
            "country": criteria.country,
            "city": criteria.city,
            "industry": criteria.industries[0] if criteria.industries else "",
            "min_employees": criteria.min_employees,
            "max_employees": criteria.max_employees,
            "limit": criteria.max_results,
            "search_id": search.id,
            "criteria": criteria.model_dump(),
            "warnings": warnings,
        } | ({"osm": osm_fields} if osm_fields else {})
        audit(
            db,
            ws,
            member.user_id,
            "discovery_search_queued",
            "Bestätigte Suche eingeplant; Anbietergrenzen werden offengelegt",
        )
        return job_output(enqueue(db, ws, member.user_id, "discovery", payload)) | {
            "warnings": warnings,
            "applied_filters": {
                k: payload[k]
                for k in ("country", "city", "industry", "min_employees", "max_employees")
            },
        }

    def normalized_results(db, ws, run, icp_id=None):
        from app.prospecting import DuplicateIndex, company_fit_score, domain_of

        profile = profile_for(db, ws, icp_id)
        index = DuplicateIndex(db, ws)
        criteria = run.criteria or {}
        output = []
        for position, row in enumerate(run.results):
            source = str(row.get("source") or "unknown")
            external = str(row.get("external_key") or position)
            key = hashlib.sha256((source + "\0" + external).encode()).hexdigest()
            kind = "person" if row.get("first_name") else "company"
            identity = external if source == "synthetic_demo" else source + ":" + external
            match = index.match(
                identity, row.get("website"), row.get("company", ""), row.get("location")
            )
            company_id = match["company_id"] if match and match["reason"] == "identity" else None
            fingerprint = hashlib.sha256((source + ":" + external).encode()).hexdigest()
            known_contact = (
                db.scalar(
                    select(Contact.id).where(
                        Contact.workspace_id == ws, Contact.import_key == fingerprint
                    )
                )
                if kind == "person"
                else None
            )
            domain = domain_of(row.get("website"))
            if kind == "company":
                fit = company_fit_score(row, profile, criteria)
            else:
                fit = explained_score(
                    SimpleNamespace(
                        location=row.get("location", ""), job_title=row.get("job_title", "")
                    ),
                    SimpleNamespace(
                        industry=row.get("industry", ""),
                        provenance={"employee_count": row.get("employee_count")},
                    ),
                    profile,
                )
            missing = completeness(
                {
                    "location": row.get("location"),
                    "industry": row.get("industry"),
                    "domain": domain,
                    "role": row.get("job_title"),
                }
                if kind == "person"
                else {
                    "location": row.get("location"),
                    "industry": row.get("industry"),
                    "domain": domain,
                    "address": row.get("address"),
                }
            )
            output.append(
                {
                    "key": key,
                    "entity_kind": kind,
                    "company": row.get("company", ""),
                    "first_name": row.get("first_name"),
                    "last_name": row.get("last_name"),
                    "location": row.get("location", ""),
                    "address": row.get("address", ""),
                    "industry": row.get("industry", ""),
                    "job_title": row.get("job_title"),
                    "domain": domain,
                    "website": row.get("website"),
                    "distance_km": row.get("distance_km"),
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                    "source": source,
                    "source_url": row.get("source_url"),
                    "attribution": row.get("attribution"),
                    "observed_at": row.get("observed_at"),
                    "last_verified_at": None,
                    "confidence": row.get("confidence", "unverified"),
                    "license": row.get("license"),
                    "score": fit,
                    "completeness": missing,
                    "imported": bool(known_contact if kind == "person" else company_id),
                    "duplicate_of": match if match and match["reason"] != "identity" else None,
                    "company_id": company_id or (match["company_id"] if match else None),
                    "contact_id": known_contact,
                    "_row": row,
                }
            )
        return output

    @app.get("/v1/workspaces/{ws}/discovery/runs/{entity_id}/results")
    def results(
        ws: str,
        entity_id: str,
        page: int = 1,
        limit: int = 25,
        sort: str = "name",
        direction: str = "asc",
        search: str = "",
        entity_kind: str = "all",
        icp_id: str | None = None,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if (
            page < 1
            or not 1 <= limit <= 100
            or sort not in ("name", "score")
            or direction not in ("asc", "desc")
            or entity_kind not in ("all", "company", "person")
        ):
            raise HTTPException(422, "Invalid results filter.")
        run = record(db, Discovery, ws, entity_id)
        rows = normalized_results(db, ws, run, icp_id)
        if entity_kind != "all":
            rows = [r for r in rows if r["entity_kind"] == entity_kind]
        if search:
            rows = [
                r
                for r in rows
                if search.casefold()
                in " ".join(
                    str(r.get(k) or "")
                    for k in ("company", "first_name", "last_name", "location", "industry")
                ).casefold()
            ]
        rows.sort(
            key=(lambda r: (r["score"]["value"], r["key"]))
            if sort == "score"
            else (lambda r: (r["company"].casefold(), r["last_name"] or "", r["key"])),
            reverse=direction == "desc",
        )
        total = len(rows)
        rows = rows[(page - 1) * limit : page * limit]
        return {
            "items": [{k: v for k, v in r.items() if k != "_row"} for r in rows],
            "total": total,
            "page": page,
            "limit": limit,
            "notice": "Quellenangaben und Scoring sind keine Marketingfreigabe. Synthetische Einträge sind nicht recherchiert.",
            "meta": run.meta or {},
            "duplicates": sum(1 for r in rows if r["duplicate_of"]),
        }

    @app.post("/v1/workspaces/{ws}/discovery/runs/{entity_id}/import-selected")
    def import_selected(
        ws: str,
        entity_id: str,
        body: SelectedResults,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "discovery-import:" + ws},
        )
        run = record(db, Discovery, ws, entity_id, True)
        rows = normalized_results(db, ws, run)
        keys = set(body.keys)
        available = {r["key"]: r for r in rows}
        if keys - set(available):
            raise HTTPException(422, "Ausgewählte Ergebnisse gehören nicht zu diesem Suchlauf.")
        selected = [available[key] for key in sorted(keys)]
        capacity = (
            remaining(db, ws, "contacts", require_slot=False)
            if any(r["entity_kind"] == "person" and not r["imported"] for r in selected)
            else 0
        )
        created = duplicates = companies = contacts = linked = facts = 0
        for result in selected:
            if result["imported"]:
                duplicates += 1
                continue
            if result["duplicate_of"] and result["entity_kind"] == "company":
                # Probable duplicate: never create a second company. Attach the new source's
                # evidence to the existing record without overwriting its fields.
                existing = record(db, Company, ws, result["duplicate_of"]["company_id"])
                facts += record_source_facts(db, ws, existing, result["_row"], member.user_id)
                linked += 1
                continue
            row = result["_row"]
            source = result["source"]
            external = str(row.get("external_key"))
            if (
                not isinstance(row.get("external_key"), str)
                or not row["external_key"]
                or not isinstance(row.get("company"), str)
                or not row["company"].strip()
            ):
                raise HTTPException(422, "Result has no stable provider identity/company name.")
            if source == "synthetic_demo" and os.getenv("APP_ENV", "development") not in (
                "development",
                "test",
            ):
                raise HTTPException(403, "Synthetische Imports sind in Produktion deaktiviert.")
            identity = external if source == "synthetic_demo" else source + ":" + external
            company = db.scalar(
                select(Company).where(Company.workspace_id == ws, Company.identity == identity)
            )
            if company is None:
                company = Company(
                    workspace_id=ws,
                    name=row.get("company") or "Unbenanntes Unternehmen",
                    identity=identity,
                    location=row.get("location") or "",
                    industry=row.get("industry") or "",
                    website=row.get("website"),
                    source=source,
                    provenance={
                        k: row.get(k)
                        for k in (
                            "source_url",
                            "license",
                            "observed_at",
                            "confidence",
                            "allowed_uses",
                            "employee_count",
                            "attribution",
                            "address",
                            "latitude",
                            "longitude",
                            "osm_category",
                        )
                    },
                )
                db.add(company)
                db.flush()
                companies += 1
                facts += record_source_facts(db, ws, company, row, member.user_id)
            if result["entity_kind"] == "person":
                if contacts >= capacity:
                    raise HTTPException(
                        402, "Workspace-Kontaktlimit überschritten; Import wurde zurückgenommen."
                    )
                if not row.get("first_name"):
                    raise HTTPException(
                        422, "Ein Personenresultat benötigt einen tatsächlich gelieferten Namen."
                    )
                fingerprint = hashlib.sha256((source + ":" + external).encode()).hexdigest()
                db.add(
                    Contact(
                        workspace_id=ws,
                        company_id=company.id,
                        import_key=fingerprint,
                        source=source,
                        first_name=row["first_name"],
                        last_name=row.get("last_name") or "",
                        job_title=row.get("job_title") or "",
                        location=row.get("location") or "",
                        email=None,
                        phone=None,
                        linkedin_url=None,
                    )
                )
                contacts += 1
            created += 1
        db.flush()
        if all(r["imported"] or r["key"] in keys for r in rows):
            run.status = "imported"
        audit(
            db,
            ws,
            member.user_id,
            "discovery_selected_imported",
            f"{created} ausgewählte Datensätze übernommen; {duplicates} Dubletten übersprungen; "
            f"{linked} wahrscheinliche Dubletten mit bestehenden Unternehmen verknüpft",
        )
        return {
            "created": created,
            "duplicates": duplicates,
            "companies": companies,
            "contacts": contacts,
            "linked_duplicates": linked,
            "facts": facts,
        }

    def campaign_workspace_data(db, ws, campaign):
        config = db.scalar(select(CampaignConfig).where(CampaignConfig.campaign_id == campaign.id))
        steps = db.scalars(
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign.id)
            .order_by(CampaignStep.position)
        ).all()
        audience = db.scalars(
            select(Contact)
            .join(Enrollment, Enrollment.contact_id == Contact.id)
            .where(Enrollment.campaign_id == campaign.id)
            .order_by(Contact.last_name, Contact.id)
        ).all()
        links = db.scalars(
            select(CampaignDraft).where(CampaignDraft.campaign_id == campaign.id)
        ).all()
        draft_ids = [link.draft_id for link in links]
        drafts = (
            db.scalars(
                select(Draft).where(Draft.id.in_(draft_ids)).order_by(Draft.created_at.desc())
            ).all()
            if draft_ids
            else []
        )
        activities = db.scalars(
            select(ManualActivity)
            .where(ManualActivity.campaign_id == campaign.id)
            .order_by(ManualActivity.created_at.desc())
            .limit(100)
        ).all()
        suppressed = set(
            db.scalars(
                select(Suppression.contact_id).where(
                    Suppression.contact_id.in_([c.id for c in audience])
                )
            )
        )
        draft_by_contact = {}
        for draft in drafts:
            draft_by_contact.setdefault(draft.contact_id, []).append(draft)
        activities_by_contact = {}
        for activity in activities:
            activities_by_contact.setdefault(activity.contact_id, []).append(activity.kind)
        counts = {key: 0 for key in ("waiting", "approved", "completed", "replied", "suppressed")}
        output = output_contacts(db, audience, ws)
        for contact in output:
            kinds = activities_by_contact.get(contact["id"], [])
            selected_drafts = draft_by_contact.get(contact["id"], [])
            state = (
                "suppressed"
                if contact["id"] in suppressed
                else (
                    "replied"
                    if "replied" in kinds
                    else (
                        "completed"
                        if "message_sent_manually" in kinds
                        else (
                            "approved"
                            if any(
                                d.approved_revision == d.revision
                                and d.state in ("approved", "queued", "accepted")
                                for d in selected_drafts
                            )
                            else "waiting"
                        )
                    )
                )
            )
            contact["journey_status"] = state
            counts[state] += 1
        return {
            "campaign": _columns(campaign, ("id", "name", "goal", "status"))
            | {
                "channel": config.channel if config else "linkedin_manual",
                "contacts": len(audience),
            },
            "sequence": [
                _columns(s, ("id", "position", "delay_days", "channel", "template"))
                | {"requires_approval": True, "execution": "planned_only"}
                for s in steps
            ],
            "audience": output,
            "drafts": [_draft_output(db, d) for d in drafts],
            "activities": [_activity_output(a) for a in activities],
            "counts": counts,
            "notice": "Sequenzzeiten sind Planung. Keine Kontaktanfrage oder LinkedIn-DM wird automatisch versendet. Manuelle Aktivitäten sind selbst gemeldet; Verbindungen sind kein Werbeeinverständnis.",
        }

    @app.get("/v1/workspaces/{ws}/campaigns/{entity_id}/workspace")
    def campaign_workspace(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        campaign = record(db, Campaign, ws, entity_id)
        return campaign_workspace_data(db, ws, campaign)

    @app.put("/v1/workspaces/{ws}/campaigns/{entity_id}/sequence")
    def save_sequence(
        ws: str,
        entity_id: str,
        body: SequenceInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        campaign = record(db, Campaign, ws, entity_id, True)
        if campaign.status == "completed":
            raise HTTPException(409, "Abgeschlossene Kampagnen können nicht verändert werden.")
        config = db.scalar(
            select(CampaignConfig)
            .where(CampaignConfig.campaign_id == campaign.id)
            .with_for_update()
        )
        if config is None:
            config = CampaignConfig(workspace_id=ws, campaign_id=campaign.id)
            db.add(config)
        config.channel = body.channel
        for step in db.scalars(select(CampaignStep).where(CampaignStep.campaign_id == campaign.id)):
            db.delete(step)
        db.flush()
        for step in body.steps:
            db.add(CampaignStep(workspace_id=ws, campaign_id=campaign.id, **step.model_dump()))
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "campaign_sequence_saved",
            "Geplante Kampagnensequenz gespeichert; jede Nachricht benötigt eigene Freigabe",
        )
        return campaign_workspace_data(db, ws, campaign)

    @app.post("/v1/workspaces/{ws}/campaigns/{entity_id}/generate-drafts")
    def generate_campaign_drafts(
        ws: str,
        entity_id: str,
        body: GenerateDrafts,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        campaign = record(db, Campaign, ws, entity_id, True)
        if campaign.status in ("paused", "completed"):
            raise HTTPException(409, "Kampagne ist pausiert oder abgeschlossen.")
        rows = db.scalars(
            select(Contact)
            .join(Enrollment, Enrollment.contact_id == Contact.id)
            .where(Enrollment.campaign_id == campaign.id)
        ).all()
        if len(rows) > 1000:
            raise HTTPException(
                422, "Für die Entwurfserzeugung Zielgruppe auf höchstens 1.000 Kontakte begrenzen."
            )
        steps = db.scalars(
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign.id)
            .order_by(CampaignStep.position)
        ).all()
        if body.template:
            validated = SequenceStepInput(position=0, template=body.template)
            templates = [(0, validated.template)]
        elif steps:
            templates = [(step.position, step.template) for step in steps]
        else:
            templates = [
                (
                    0,
                    "Hallo {first_name},\n\n"
                    + (campaign.goal or "Besteht Interesse an einem Gespräch?"),
                )
            ]
        created = duplicates = 0
        companies = {
            c.id: c
            for c in db.scalars(
                select(Company).where(
                    Company.id.in_([row.company_id for row in rows if row.company_id])
                )
            )
        }
        for contact in rows:
            if db.scalar(select(Suppression.id).where(Suppression.contact_id == contact.id)):
                continue
            values = {
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "job_title": contact.job_title,
                "company": companies[contact.company_id].name
                if contact.company_id in companies
                else "",
            }
            for position, template in templates:
                if db.scalar(
                    select(CampaignDraft.id).where(
                        CampaignDraft.campaign_id == campaign.id,
                        CampaignDraft.contact_id == contact.id,
                        CampaignDraft.step_position == position,
                    )
                ):
                    duplicates += 1
                    continue
                content = re.sub(
                    r"\{(first_name|last_name|company|job_title|evidence)\}",
                    lambda match, values=values: values.get(match.group(1), ""),
                    template.replace("{{", "{").replace("}}", "}"),
                )
                content += "\n\n[Vorlagenentwurf – manuell prüfen. Kein KI-Anbieter aufgerufen; nichts versendet.]"
                if len(content) > 3000:
                    raise HTTPException(
                        422,
                        "Personalisierter Entwurf ist länger als 3.000 Zeichen. Vorlage kürzen.",
                    )
                draft = Draft(
                    workspace_id=ws,
                    contact_id=contact.id,
                    content=content,
                    subject=campaign.name[:200],
                    source="offline",
                    state="draft",
                )
                db.add(draft)
                db.flush()
                db.add(
                    CampaignDraft(
                        workspace_id=ws,
                        campaign_id=campaign.id,
                        contact_id=contact.id,
                        draft_id=draft.id,
                        step_position=position,
                    )
                )
                created += 1
        audit(
            db,
            ws,
            member.user_id,
            "campaign_attributed_drafts_generated",
            f"{created} nachvollziehbare Vorlagenentwürfe erstellt; {duplicates} vorhandene Entwürfe erhalten",
        )
        return {
            "created": created,
            "duplicates": duplicates,
            "notice": "Vorlagenentwürfe mit belegten Kontaktfeldern, keine KI-Ausgabe. Keine Nachricht wurde versendet.",
        }

    @app.get("/v1/workspaces/{ws}/outreach/inbox")
    def approval_inbox(
        ws: str,
        state: str = "",
        campaign_id: str | None = None,
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        stmt = select(Draft).where(Draft.workspace_id == ws)
        if state:
            stmt = stmt.where(Draft.state == state)
        if campaign_id:
            record(db, Campaign, ws, campaign_id)
            stmt = stmt.join(CampaignDraft, CampaignDraft.draft_id == Draft.id).where(
                CampaignDraft.campaign_id == campaign_id
            )
        rows, total = paginate(db, stmt.order_by(Draft.created_at.desc(), Draft.id), page, limit)
        return {
            "items": [_draft_output(db, draft) for draft in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @app.post("/v1/workspaces/{ws}/outreach/handoffs", status_code=201)
    def handoff(
        ws: str, body: HandoffInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        contact = record(db, Contact, ws, body.contact_id)
        if body.campaign_id:
            record(db, Campaign, ws, body.campaign_id)
            if not db.scalar(
                select(Enrollment.id).where(
                    Enrollment.campaign_id == body.campaign_id, Enrollment.contact_id == contact.id
                )
            ):
                raise HTTPException(422, "Kontakt ist dieser Kampagne nicht zugeordnet.")
        item = ManualActivity(workspace_id=ws, actor_id=member.user_id, **body.model_dump())
        db.add(item)
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "manual_outreach_recorded",
            f"Manual handoff: {body.kind}; selbst gemeldet, nicht vom Anbieter bestätigt",
        )
        return _activity_output(item)

    @app.get("/v1/workspaces/{ws}/icp-profiles")
    def intelligence_profiles(
        ws: str,
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        rows, total = paginate(
            db,
            select(ICPProfile)
            .where(ICPProfile.workspace_id == ws)
            .order_by(ICPProfile.created_at.desc()),
            page,
            limit,
        )
        return {
            "items": [
                {"id": r.id, **r.profile, "version": r.version, "created_at": r.created_at}
                for r in rows
            ],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @app.post("/v1/workspaces/{ws}/icp-profiles", status_code=201)
    def create_profile(
        ws: str,
        body: IntelligenceProfileInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        item = ICPProfile(workspace_id=ws, name=body.name, profile=body.model_dump())
        db.add(item)
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "icp_profile_created",
            "Wiederverwendbares ICP-Profil erstellt; unbekannte Angaben bleiben unbekannt",
        )
        return {
            "id": item.id,
            **item.profile,
            "version": item.version,
            "created_at": item.created_at,
        }

    @app.get("/v1/workspaces/{ws}/icp-profiles/{entity_id}")
    def get_profile(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        item = record(db, ICPProfile, ws, entity_id)
        return {
            "id": item.id,
            **item.profile,
            "version": item.version,
            "created_at": item.created_at,
        }

    @app.put("/v1/workspaces/{ws}/icp-profiles/{entity_id}")
    def update_profile(
        ws: str,
        entity_id: str,
        body: IntelligenceProfileInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        item = record(db, ICPProfile, ws, entity_id, True)
        item.profile = body.model_dump()
        item.name = body.name
        item.version += 1
        audit(
            db,
            ws,
            member.user_id,
            "icp_profile_updated",
            f"ICP-Profil auf Revision {item.version} aktualisiert",
        )
        return {
            "id": item.id,
            **item.profile,
            "version": item.version,
            "created_at": item.created_at,
        }


SOURCE_FACT_FIELDS = (
    ("address", "Adresse"),
    ("industry", "Kategorie"),
    ("osm_category", "OSM-Tag"),
    ("website", "Website"),
    ("opening_hours", "Öffnungszeiten"),
    ("employee_count", "Mitarbeitende (Anbieterangabe)"),
)


def record_source_facts(db, ws, company, row, actor_id):
    """Persist provider-reported fields as cited facts. Idempotent per field+source."""
    source_url = str(row.get("source_url") or "")[:2000]
    if not source_url:
        return 0
    existing = {
        (f.field, f.source_url)
        for f in db.scalars(
            select(CompanyFact).where(
                CompanyFact.workspace_id == ws, CompanyFact.company_id == company.id
            )
        )
    }
    created = 0
    for key, label in SOURCE_FACT_FIELDS:
        value = row.get(key)
        if value is None or value == "" or (label, source_url) in existing:
            continue
        db.add(
            CompanyFact(
                workspace_id=ws,
                company_id=company.id,
                field=label,
                value=str(value)[:1000],
                source_url=source_url,
                confidence=str(row.get("confidence") or "provider_reported")[:30],
                source_kind=str(row.get("source") or "provider")[:40],
                source_id=hashlib.sha256(source_url.encode()).hexdigest()[:32],
                actor_id=actor_id,
            )
        )
        created += 1
    db.flush()
    return created


def apply_discovery_criteria(db, ws, rows, criteria):
    """Bounded post-filtering of known provider fields; absence is never fabricated."""
    warnings = []
    if criteria.get("provider") == "synthetic":
        return rows, ["Synthetische Beispiele sind keine Treffer für die Suchkriterien."]
    customers = (
        list(
            db.scalars(
                select(Company)
                .join(
                    CompanyProfile,
                    (CompanyProfile.workspace_id == Company.workspace_id)
                    & (CompanyProfile.company_id == Company.id),
                )
                .where(Company.workspace_id == ws, CompanyProfile.is_customer.is_(True))
            )
        )
        if criteria.get("exclude_customers")
        else []
    )
    won_companies = (
        list(
            db.scalars(
                select(Company)
                .join(
                    Contact,
                    (Contact.workspace_id == Company.workspace_id)
                    & (Contact.company_id == Company.id),
                )
                .join(
                    Deal,
                    (Deal.workspace_id == Contact.workspace_id) & (Deal.contact_id == Contact.id),
                )
                .where(Company.workspace_id == ws, Deal.stage == "won")
            )
        )
        if criteria.get("exclude_customers")
        else []
    )
    identities = {c.identity.casefold() for c in customers + won_companies}
    domains = {urlsplit(c.website).hostname for c in customers + won_companies if c.website}
    upstream_geo = criteria.get("provider") == "osm"
    output = []
    for row in rows:
        industry = str(row.get("industry") or "").casefold()
        if any(term.casefold() in industry for term in criteria.get("excluded_industries", [])):
            continue
        if (
            not upstream_geo
            and criteria.get("industries")
            and not any(term.casefold() in industry for term in criteria["industries"])
        ):
            continue
        if (
            not upstream_geo
            and criteria.get("region")
            and criteria["region"].casefold() not in str(row.get("location") or "").casefold()
        ):
            continue
        text_value = " ".join(
            str(row.get(k) or "") for k in ("company", "industry", "website", "description")
        ).casefold()
        if criteria.get("keywords") and not any(
            term.casefold() in text_value for term in criteria["keywords"]
        ):
            continue
        identity = str(row.get("source", "")) + ":" + str(row.get("external_key", ""))
        domain = urlsplit(row["website"]).hostname if row.get("website") else None
        if identity.casefold() in identities or (domain and domain in domains):
            continue
        output.append(row)
    if (
        criteria.get("region")
        or criteria.get("keywords")
        or len(criteria.get("industries", [])) > 1
    ):
        warnings.append(
            "Region, Schlüsselwörter und zusätzliche Branchen werden auf der begrenzten Anbieterantwort geprüft; keine vollständige Marktdeckung."
        )
    return output, warnings


def _columns(item, keys):
    return {key: getattr(item, key) for key in keys}
