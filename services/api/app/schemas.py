from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class WorkspaceInput(Strict):
    name: str = Field(min_length=2, max_length=120)
    # "demo" = synthetic examples only (used by browser tests); never offered in the UI.
    kind: Literal["standard", "demo"] = "standard"


class ContactInput(Strict):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(default="", max_length=120)
    company: str = Field(default="", max_length=240)
    job_title: str = Field(default="", max_length=240)
    location: str = Field(default="", max_length=240)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=80)
    linkedin_url: str | None = Field(default=None, max_length=500)
    status: Literal["new", "qualified", "contacted", "archived"] = "new"
    version: int = 1

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        if value and ("@" not in value or " " in value):
            raise ValueError("Ungültige E-Mail")
        return value or None

    @field_validator("linkedin_url")
    @classmethod
    def linkedin_valid(cls, value):
        from app.imports import normalize_url

        return normalize_url(value)


class ICPInput(Strict):
    name: str = Field(min_length=1, max_length=120)
    locations: list[str] = Field(max_length=30)
    roles: list[str] = Field(max_length=30)
    industries: list[str] = Field(max_length=30)
    weights: dict[str, int]

    @model_validator(mode="after")
    def valid_weights(self):
        if (
            set(self.weights) != {"location", "role", "industry"}
            or any(w < 0 or w > 100 for w in self.weights.values())
            or sum(self.weights.values()) != 100
        ):
            raise ValueError(
                "Gewichte müssen Region, Rolle und Branche enthalten und zusammen 100 ergeben."
            )
        if any(
            not term.strip() or len(term) > 120
            for group in (self.locations, self.roles, self.industries)
            for term in group
        ):
            raise ValueError("ICP-Begriffe dürfen nicht leer oder länger als 120 Zeichen sein.")
        return self


Stage = Literal["new", "qualified", "contacted", "conversation", "proposal", "won", "lost"]


class DealInput(Strict):
    title: str = Field(min_length=1, max_length=200)
    contact_id: str | None = None
    amount: int = Field(default=0, ge=0, le=10**12)
    stage: Stage = "new"


class DealPatch(Strict):
    stage: Stage


class StudioContext(Strict):
    image_mode: Literal["none", "manual", "auto", "random", "ai"] = "none"
    voice_profile_id: str | None = Field(default=None, max_length=36)
    generation_job_id: str | None = Field(default=None, max_length=36)


class PostInput(Strict):
    studio_context: StudioContext = Field(default_factory=StudioContext)
    brand_id: str | None = None
    asset_ids: list[str] = Field(default_factory=list, max_length=1)
    caption: str = Field(min_length=1, max_length=3000)
    alt_text: str = Field(default="", max_length=1000)
    # Content strategy (app.content_strategy): goal, audience, approach A/B/C, pillar.
    goal: Literal["reach", "trust", "leads", "partners", "hiring"] | None = None
    audience: Literal["ortenau_ceo", "founders_cleaning", "ai_entrepreneurs"] | None = None
    approach: Literal["A", "B", "C"] | None = None
    pillar: str | None = Field(default=None, max_length=120)
    topic: str | None = Field(default=None, max_length=300)
    campaign_id: str | None = Field(default=None, max_length=36)
    planned_for: date | None = None


class PostPatch(PostInput):
    version: int = Field(ge=1)


class Schedule(Strict):
    scheduled_at: datetime

    @field_validator("scheduled_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Zeit mit explizitem UTC-Offset erforderlich (Sommer-/Winterzeit).")
        return value


class Topic(Strict):
    topic: str = Field(min_length=3, max_length=300)


class DraftInput(Strict):
    contact_id: str
