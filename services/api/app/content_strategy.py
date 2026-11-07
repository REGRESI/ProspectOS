"""Content strategy: goal, audience and approach for every post, campaigns, measured results.

- Every post (and every plan) carries a goal, an audience and a topic. The three
  versions differ in approach, not in wording: A provocative thesis, B personal story,
  C useful tip with numbers. Each version says in one sentence why it fits the goal.
- Campaigns have a start, an end and a goal; posts can belong to one.
- 48 hours after a post went live the app asks for impressions, comments, profile visits
  and inquiries (entered by hand; LinkedIn is never read). Averages per pillar and
  approach show what works, and new suggestions are told about it.
"""

import re
from datetime import date, datetime, timedelta

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now
from app.models import ContentCampaign, Post, TenantMixin

GOALS = {
    "reach": "Reichweite",
    "trust": "Vertrauen aufbauen",
    "leads": "Anfragen gewinnen",
    "partners": "Partner gewinnen",
    "hiring": "Mitarbeiter gewinnen",
}
AUDIENCES = {
    "ortenau_ceo": "Geschäftsführer Ortenau",
    "founders_cleaning": "Gründer und Reinigungsfirmen",
    "ai_entrepreneurs": "Unternehmer und KI-Interessierte",
}
APPROACHES = {
    "A": {
        "label": "Provokante These",
        "brief": "Beginne mit einer klaren, unbequemen These in einem Satz und begründe sie mit "
        "zwei oder drei Beobachtungen. Kein Clickbait, keine Übertreibung, die du nicht belegen kannst.",
    },
    "B": {
        "label": "Persönliche Geschichte",
        "brief": "Erzähle eine konkrete Situation aus deinem Alltag in der Ich-Form mit Anfang, "
        "Wendung und Erkenntnis. Erfinde nichts: wo Details fehlen, setze [eigene Erfahrung].",
    },
    "C": {
        "label": "Nützlicher Tipp mit Zahlen",
        "brief": "Gib einen sofort nutzbaren Tipp in Schritten mit konkreten Zahlen (Minuten, "
        "Euro, Anteile). Nutze nur Zahlen aus den Fakten; sonst [Zahl prüfen] einsetzen.",
    },
}
DEFAULT_PILLARS = [
    "Transparenz in der Reinigungsbranche",
    "Bauen mit KI",
    "Unternehmeralltag",
    "CleanStar-Einblicke",
]
# Fallback "why" per goal and approach when the model leaves the line out.
WHY = {
    "A": "Eine klare These erzeugt Kommentare und Diskussion und damit {goal}.",
    "B": "Eine echte Geschichte zeigt, wer hinter CleanStar steht, und zahlt auf {goal} ein.",
    "C": "Ein Tipp mit Zahlen ist nützlich, wird gespeichert und geteilt und stärkt so {goal}.",
}
METRICS_AFTER = timedelta(hours=48)
STRATEGY_FIELDS = {"goal", "audience", "approach", "pillar", "topic", "campaign_id", "planned_for"}


class PostMetrics(TenantMixin, Base):
    __tablename__ = "post_metrics"
    post_id: Mapped[str] = mapped_column(String(36))
    impressions: Mapped[int] = mapped_column(Integer)
    comments: Mapped[int] = mapped_column(Integer)
    profile_visits: Mapped[int] = mapped_column(Integer)
    inquiries: Mapped[int] = mapped_column(Integer)
    recorded_by: Mapped[str] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "post_id"),
        ForeignKeyConstraint(
            ["workspace_id", "post_id"], ["social_posts.workspace_id", "social_posts.id"]
        ),
    )


def goal_label(key: str | None) -> str:
    return GOALS.get(key or "", key or "")


def audience_label(key: str | None) -> str:
    return AUDIENCES.get(key or "", key or "")


def approach_prompt(approach: str, goal: str | None, audience: str | None) -> str:
    item = APPROACHES[approach]
    return (
        f"Ansatz {approach} ({item['label']}): {item['brief']}\n"
        f"Ziel des Beitrags: {goal_label(goal) or 'nicht angegeben'}. "
        f"Zielgruppe: {audience_label(audience) or 'nicht angegeben'}.\n"
        "Schreibe nach dem Beitrag eine letzte eigene Zeile, die mit 'WARUM:' beginnt: ein Satz, "
        "warum dieser Ansatz zum Ziel passt."
    )


def split_why(text: str, approach: str, goal: str | None) -> tuple[str, str]:
    m = re.search(r"(?:^|\n)\s*WARUM:\s*(.+?)\s*$", text.strip(), re.S | re.I)
    if m:
        why = " ".join(m.group(1).split())[:240]
        return text[: m.start()].strip(), why
    return text.strip(), WHY[approach].format(goal=goal_label(goal) or "dein Ziel")


def post_strategy(post: Post) -> dict:
    return {
        "goal": post.goal,
        "goal_label": goal_label(post.goal),
        "audience": post.audience,
        "audience_label": audience_label(post.audience),
        "approach": post.approach,
        "approach_label": APPROACHES.get(post.approach or "", {}).get("label", ""),
        "pillar": post.pillar,
        "topic": post.topic,
        "campaign_id": post.campaign_id,
        "planned_for": post.planned_for,
    }


def published_at(post: Post):
    if post.published_at:
        return post.published_at
    manual = (post.studio_context or {}).get("manual_publication") or {}
    try:
        return datetime.fromisoformat(manual["at"]) if manual.get("at") else None
    except ValueError:
        return None


def metrics_output(m: PostMetrics | None) -> dict | None:
    if not m:
        return None
    return {
        "impressions": m.impressions,
        "comments": m.comments,
        "profile_visits": m.profile_visits,
        "inquiries": m.inquiries,
        "updated_at": m.updated_at,
    }


def insights(db, ws) -> dict:
    """Averages per pillar and approach from the numbers the user entered."""
    rows = db.execute(
        select(Post, PostMetrics)
        .join(PostMetrics, (PostMetrics.post_id == Post.id) & (PostMetrics.workspace_id == ws))
        .where(Post.workspace_id == ws)
    ).all()

    def group(key):
        out: dict[str, dict] = {}
        for post, m in rows:
            name = key(post)
            if not name:
                continue
            g = out.setdefault(
                name,
                {"posts": 0, "impressions": 0, "comments": 0, "profile_visits": 0, "inquiries": 0},
            )
            g["posts"] += 1
            for field in ("impressions", "comments", "profile_visits", "inquiries"):
                g[field] += getattr(m, field)
        result = []
        for name, g in out.items():
            n = g["posts"]
            result.append(
                {
                    "name": name,
                    "posts": n,
                    "impressions": round(g["impressions"] / n),
                    "comments": round(g["comments"] / n, 1),
                    "profile_visits": round(g["profile_visits"] / n, 1),
                    "inquiries": round(g["inquiries"] / n, 1),
                    # Inquiries weigh most, then comments and profile visits, then reach.
                    "score": round(
                        (
                            g["inquiries"] * 50
                            + g["comments"] * 5
                            + g["profile_visits"] * 2
                            + g["impressions"] / 100
                        )
                        / n,
                        1,
                    ),
                }
            )
        return sorted(result, key=lambda r: -r["score"])

    pillars = group(lambda p: p.pillar)
    approaches = group(
        lambda p: (
            f"{p.approach} {APPROACHES[p.approach]['label']}" if p.approach in APPROACHES else ""
        )
    )
    goals = group(lambda p: goal_label(p.goal))
    return {
        "measured_posts": len(rows),
        "pillars": pillars,
        "approaches": approaches,
        "goals": goals,
        "hint": hint_text(pillars, approaches, len(rows)),
    }


def hint_text(pillars: list[dict], approaches: list[dict], measured: int) -> str:
    if measured < 3:
        return ""
    parts = []
    if pillars and pillars[0]["posts"] >= 2:
        parts.append(f"Säule „{pillars[0]['name']}“")
    if approaches and approaches[0]["posts"] >= 2:
        parts.append(f"Ansatz „{approaches[0]['name']}“")
    if not parts:
        return ""
    return (
        "Bisher funktioniert am besten: "
        + " und ".join(parts)
        + f" (aus {measured} gemessenen Beiträgen)."
    )


def prompt_hint(db, ws) -> str:
    text = insights(db, ws)["hint"]
    return (
        "\nErfahrung aus gemessenen Beiträgen (nur zur Gewichtung, nicht erwähnen): " + text
        if text
        else ""
    )


def due_metrics(db, ws, user_id: str | None = None) -> list[dict]:
    """Posts that went live at least 48 hours ago and have no numbers yet."""
    measured = set(db.scalars(select(PostMetrics.post_id).where(PostMetrics.workspace_id == ws)))
    out = []
    for post in db.scalars(
        select(Post).where(
            Post.workspace_id == ws, Post.state.in_(["published", "published_manually"])
        )
    ):
        at = published_at(post)
        if post.id in measured or not at or at > now() - METRICS_AFTER:
            continue
        if user_id and post.author_id != user_id:
            continue
        out.append(
            {
                "id": post.id,
                "caption": post.caption[:140],
                "published_at": at,
                "pillar": post.pillar,
                "approach": post.approach,
            }
        )
    return sorted(out, key=lambda p: p["published_at"])


def campaign_output(c: ContentCampaign, db=None) -> dict:
    out = {
        "id": c.id,
        "name": c.name,
        "goal": c.goal,
        "goal_label": goal_label(c.goal),
        "audience": c.audience,
        "audience_label": audience_label(c.audience),
        "description": c.description,
        "start_date": c.start_date,
        "end_date": c.end_date,
        "created_at": c.created_at,
    }
    if db is not None:
        posts = db.scalars(
            select(Post)
            .where(Post.workspace_id == c.workspace_id, Post.campaign_id == c.id)
            .order_by(Post.planned_for.asc().nulls_last(), Post.created_at)
        ).all()
        metrics = {
            m.post_id: m
            for m in db.scalars(
                select(PostMetrics).where(
                    PostMetrics.workspace_id == c.workspace_id,
                    PostMetrics.post_id.in_([p.id for p in posts] or [""]),
                )
            )
        }
        from app.main import post_output

        out["posts"] = [
            post_output(p)
            | {
                "placeholder": bool((p.studio_context or {}).get("placeholder")),
                "slot": (p.studio_context or {}).get("slot"),
                "metrics": metrics_output(metrics.get(p.id)),
            }
            for p in posts
        ]
    return out


class CampaignInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=3, max_length=160)
    goal: str
    audience: str
    description: str = Field(default="", max_length=1000)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def valid(self):
        if self.goal not in GOALS:
            raise ValueError("Unbekanntes Ziel")
        if self.audience not in AUDIENCES:
            raise ValueError("Unbekannte Zielgruppe")
        if self.end_date < self.start_date:
            raise ValueError("Das Ende liegt vor dem Start.")
        return self


class SlotsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int = Field(ge=1, le=30)
    # 0 = Monday. Default: the start weekday and every second weekday after it (Mon–Fri).
    weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    pillar: str = Field(default="", max_length=120)
    titles: list[str] = Field(default_factory=list, max_length=30)


class StrategyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    goal: str | None = None
    audience: str | None = None
    approach: str | None = None
    pillar: str | None = Field(default=None, max_length=120)
    topic: str | None = Field(default=None, max_length=300)
    campaign_id: str | None = None
    planned_for: date | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.goal and self.goal not in GOALS:
            raise ValueError("Unbekanntes Ziel")
        if self.audience and self.audience not in AUDIENCES:
            raise ValueError("Unbekannte Zielgruppe")
        if self.approach and self.approach not in APPROACHES:
            raise ValueError("Unbekannter Ansatz")
        return self


class MetricsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    impressions: int = Field(ge=0, le=10_000_000)
    comments: int = Field(ge=0, le=100_000)
    profile_visits: int = Field(ge=0, le=1_000_000)
    inquiries: int = Field(ge=0, le=10_000)


def slot_dates(start: date, end: date, count: int, weekdays: list[int]) -> list[date]:
    days, day = [], start
    while len(days) < count and day <= end + timedelta(days=366):
        if day.weekday() in weekdays:
            days.append(day)
        day += timedelta(days=1)
    return days


def apply_strategy(db, ws, post: Post, body: StrategyInput, fields: set[str], record):
    if "campaign_id" in fields and body.campaign_id:
        record(db, ContentCampaign, ws, body.campaign_id)  # 404 for foreign ids
    for field in fields:
        setattr(post, field, getattr(body, field))


def register_strategy_routes(app, db_session, scope, record, audit):
    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Keine Berechtigung.")

    @app.get("/v1/workspaces/{ws}/content/strategy")
    def strategy(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return {
            "goals": [{"key": k, "label": v} for k, v in GOALS.items()],
            "audiences": [{"key": k, "label": v} for k, v in AUDIENCES.items()],
            "approaches": [
                {"key": k, "label": v["label"], "brief": v["brief"]} for k, v in APPROACHES.items()
            ],
            "pillars": DEFAULT_PILLARS,
            "insights": insights(db, ws),
            "due_metrics": due_metrics(db, ws),
        }

    @app.get("/v1/workspaces/{ws}/content/insights")
    def content_insights(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return insights(db, ws) | {"due": due_metrics(db, ws)}

    @app.get("/v1/workspaces/{ws}/content/campaigns")
    def campaigns(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return {
            "items": [
                campaign_output(c, db)
                for c in db.scalars(
                    select(ContentCampaign)
                    .where(ContentCampaign.workspace_id == ws)
                    .order_by(ContentCampaign.start_date.desc())
                    .limit(50)
                )
            ]
        }

    @app.post("/v1/workspaces/{ws}/content/campaigns", status_code=201)
    def create_campaign(
        ws: str,
        body: CampaignInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        item = ContentCampaign(workspace_id=ws, created_by=member.user_id, **body.model_dump())
        db.add(item)
        db.flush()
        audit(
            db, ws, member.user_id, "content_campaign_created", f"Kampagne „{item.name}“ angelegt"
        )
        return campaign_output(item, db)

    @app.get("/v1/workspaces/{ws}/content/campaigns/{entity_id}")
    def campaign(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        return campaign_output(record(db, ContentCampaign, ws, entity_id), db)

    @app.put("/v1/workspaces/{ws}/content/campaigns/{entity_id}")
    def update_campaign(
        ws: str,
        entity_id: str,
        body: CampaignInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        item = record(db, ContentCampaign, ws, entity_id, True)
        for key, value in body.model_dump().items():
            setattr(item, key, value)
        audit(
            db, ws, member.user_id, "content_campaign_updated", f"Kampagne „{item.name}“ geändert"
        )
        return campaign_output(item, db)

    @app.post("/v1/workspaces/{ws}/content/campaigns/{entity_id}/slots", status_code=201)
    def add_slots(
        ws: str,
        entity_id: str,
        body: SlotsInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        """Placeholder posts with planned days; the user fills in the texts later."""
        authoring(member)
        item = record(db, ContentCampaign, ws, entity_id, True)
        existing = db.scalars(
            select(Post).where(Post.workspace_id == ws, Post.campaign_id == item.id)
        ).all()
        start = max([p.planned_for for p in existing if p.planned_for] or [None]) or None
        start = (start + timedelta(days=1)) if start else item.start_date
        weekdays = (
            [d % 7 for d in body.weekdays]
            if body.weekdays
            else sorted({(start.weekday() + k) % 7 for k in (0, 2, 4)} - {5, 6}) or [0, 2, 4]
        )
        days = slot_dates(start, item.end_date, body.count, weekdays)
        offset = len(existing)
        for i, day in enumerate(days):
            title = body.titles[i] if i < len(body.titles) else ""
            db.add(
                Post(
                    workspace_id=ws,
                    author_id=member.user_id,
                    caption=f"(Text folgt) Teil {offset + i + 1}" + (f": {title}" if title else ""),
                    goal=item.goal,
                    audience=item.audience,
                    pillar=body.pillar or None,
                    topic=title or None,
                    campaign_id=item.id,
                    planned_for=day,
                    studio_context={
                        "placeholder": True,
                        "slot": offset + i + 1,
                        "image_mode": "none",
                    },
                )
            )
        db.flush()
        if days and days[-1] > item.end_date:
            item.end_date = days[-1]
        audit(db, ws, member.user_id, "content_campaign_slots", f"{len(days)} Termine angelegt")
        return campaign_output(item, db)

    @app.put("/v1/workspaces/{ws}/social/posts/{entity_id}/strategy")
    def set_strategy(
        ws: str,
        entity_id: str,
        body: StrategyInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app.main import post_output

        authoring(member)
        post = record(db, Post, ws, entity_id, True)
        apply_strategy(db, ws, post, body, body.model_fields_set, record)
        return post_output(post)

    @app.put("/v1/workspaces/{ws}/social/posts/{entity_id}/metrics")
    def set_metrics(
        ws: str,
        entity_id: str,
        body: MetricsInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        post = record(db, Post, ws, entity_id)
        if post.state not in ("published", "published_manually"):
            raise HTTPException(409, "Zahlen gibt es erst, wenn der Beitrag veröffentlicht ist.")
        item = db.scalar(
            select(PostMetrics).where(
                PostMetrics.workspace_id == ws, PostMetrics.post_id == post.id
            )
        )
        if not item:
            item = PostMetrics(
                workspace_id=ws, post_id=post.id, recorded_by=member.user_id, **body.model_dump()
            )
            db.add(item)
        else:
            for key, value in body.model_dump().items():
                setattr(item, key, value)
            item.recorded_by = member.user_id
        item.updated_at = now()
        db.flush()
        audit(db, ws, member.user_id, "post_metrics_recorded", "Kennzahlen von Hand eingetragen")
        return metrics_output(item) | {"post_id": post.id}

    @app.get("/v1/workspaces/{ws}/social/posts/{entity_id}/metrics")
    def get_metrics(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        post = record(db, Post, ws, entity_id)
        return {
            "post_id": post.id,
            "metrics": metrics_output(
                db.scalar(
                    select(PostMetrics).where(
                        PostMetrics.workspace_id == ws, PostMetrics.post_id == post.id
                    )
                )
            ),
            "due_at": (published_at(post) + METRICS_AFTER) if published_at(post) else None,
        }
