from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas import Strict


class BrandInput(Strict):
    name: str = Field(min_length=1, max_length=120)
    voice: str = Field(default="", max_length=1000)
    audience: str = Field(default="", max_length=1000)
    pillars: list[str] = Field(default_factory=list, max_length=10)
    primary_color: str = Field(default="#4F46E5", pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("pillars")
    @classmethod
    def pillar_limits(cls, value):
        if any(not s.strip() or len(s) > 200 for s in value):
            raise ValueError("Invalid content pillar")
        return value


class TaskInput(Strict):
    title: str = Field(min_length=1, max_length=240)
    contact_id: str | None = None
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("UTC offset required")
        return value


class TaskPatch(Strict):
    state: Literal["open", "done"]


class NoteInput(Strict):
    body: str = Field(min_length=1, max_length=5000)
    contact_id: str | None = None


class CampaignInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(default="", max_length=1000)
    status: Literal["draft", "active", "paused", "completed"] = "draft"
    contact_ids: list[str] = Field(default_factory=list, max_length=100)


class CampaignPatch(Strict):
    status: Literal["draft", "active", "paused", "completed"]


class Budget(Strict):
    ai_budget_minor: int = Field(ge=0, le=1000000)


class SearchInput(Strict):
    query: str = Field(min_length=3, max_length=300)
    provider: Literal["synthetic", "pdl"] = "synthetic"
    city: str = Field(default="", max_length=100)
    country: str = Field(default="germany", min_length=2, max_length=100)
    industry: str = Field(default="", max_length=120)
    min_employees: int | None = Field(default=None, ge=0, le=10000000)
    max_employees: int | None = Field(default=None, ge=1, le=10000000)
    limit: int = Field(default=10, ge=1, le=25)
    license_confirmed: bool = False


class Generation(Strict):
    purpose: Literal["caption", "research", "qualification", "outreach", "reply"]
    prompt: str = Field(min_length=3, max_length=4000)
    contact_id: str | None = None


class ResearchInput(Strict):
    url: str = Field(max_length=2000)
    rights_confirmed: bool = False


class PolicyInput(Strict):
    mode: Literal["manual", "authorized_auto"] = "manual"
    max_posts_daily: int = Field(default=3, ge=1, le=10)


class PublishInput(Strict):
    scheduled_at: datetime | None = None
    automation_authorized: bool = False

    @field_validator("scheduled_at")
    @classmethod
    def aware(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("UTC offset required")
        return value


class ConsentInput(Strict):
    contact_id: str
    evidence: str = Field(min_length=10, max_length=1000)
    legal_basis: Literal["explicit_consent", "verified_statutory_exception"]
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("UTC offset required")
        return value


class SuppressInput(Strict):
    contact_id: str
    reason: str = Field(min_length=3, max_length=200)
