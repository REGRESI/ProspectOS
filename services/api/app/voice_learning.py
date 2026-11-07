"""A writing profile per user that learns from edits and feedback.

- Every change a user makes to a draft is stored (original and their version).
- "Klingt nach mir" / "Klingt nicht nach mir" with an optional reason.
- From both, rules in plain language are derived deterministically (shorter, no emojis,
  words the user always deletes …). The user can edit, switch off or add rules; edited
  rules become their own and are never overwritten. Dismissed rules do not come back.
- Posts by other people that the user likes are kept separately as style references.
  They guide rhythm and tone only and are never copied.

Rules and references go into every new suggestion of that user.
"""

import re
import secrets
from collections import Counter

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ForeignKeyConstraint, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now
from app.models import Post, TenantMixin

LEARNED_KEYS = ("rules", "dismissed", "personal", "learned_at")
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿]")
STOP = set(
    """aber alle allem allen aller alles als also auch auf aus bei beim bin bis bist dann das
    dass dein deine dem den der des dich die dies diese diesem diesen dieser doch dort du durch
    ein eine einem einen einer eines euch euer für hab habe haben hat hatte hier ich ihr ihre
    im in ist ja jede jedem jeden jeder jetzt kann kein keine man mein meine mich mit muss nach
    nicht noch nur ob oder ohne sehr sein seine sich sie sind so soll sondern über um und uns
    unser unter viel vom von vor war was weil wenn wer wie wir wird wo zu zum zur sowie damit
    mehr immer schon heute wieder einfach dabei denn gibt geht""".split()
)


class DraftEdit(TenantMixin, Base):
    __tablename__ = "draft_edits"
    kind: Mapped[str] = mapped_column(String(20))
    ref_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(String(36))
    original: Mapped[str] = mapped_column(String(3000))
    edited: Mapped[str] = mapped_column(String(3000))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class VoiceFeedback(TenantMixin, Base):
    __tablename__ = "voice_feedback"
    post_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str] = mapped_column(String(36))
    verdict: Mapped[str] = mapped_column(String(3))
    reason: Mapped[str] = mapped_column(String(500), default="")
    text: Mapped[str] = mapped_column(String(3000))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "post_id"], ["social_posts.workspace_id", "social_posts.id"]
        ),
    )


class Inspiration(TenantMixin, Base):
    __tablename__ = "style_inspirations"
    user_id: Mapped[str] = mapped_column(String(36))
    author: Mapped[str] = mapped_column(String(120), default="")
    text: Mapped[str] = mapped_column(String(3000))
    note: Mapped[str] = mapped_column(String(500), default="")
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


# ---- recording -------------------------------------------------------------------------


def record_edit(db, ws, user_id, kind, ref_id, original: str, edited: str) -> bool:
    """Store a user's change to a draft. Placeholders and no-op edits are ignored."""
    original, edited = (original or "").strip(), (edited or "").strip()
    if not original or not edited or original == edited or original.startswith("(Text folgt)"):
        return False
    db.add(
        DraftEdit(
            workspace_id=ws,
            kind=kind,
            ref_id=ref_id,
            user_id=user_id,
            original=original[:3000],
            edited=edited[:3000],
        )
    )
    return True


# ---- derivation ------------------------------------------------------------------------


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-zäöüß]{4,}", text.casefold()) if w not in STOP]


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _avg_words(text: str) -> float:
    sentences = _sentences(text)
    return sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0


def derive_rules(edits: list[tuple[str, str]], feedback: list[tuple[str, str]]) -> list[dict]:
    """Plain-language rules with a key and the evidence they come from."""
    rules: list[dict] = []
    n = len(edits)

    def add(key, text, evidence):
        rules.append({"key": key, "text": text, "evidence": evidence})

    if n >= 2:
        ratios = [len(b) / max(len(a), 1) for a, b in edits]
        avg = sum(ratios) / n
        if avg <= 0.85:
            add(
                "shorter",
                f"Schreib kürzer. Du kürzt Entwürfe im Schnitt um {round((1 - avg) * 100)} %.",
                f"aus {n} Änderungen",
            )
        elif avg >= 1.15:
            add(
                "longer",
                f"Es darf ausführlicher sein. Du ergänzt Entwürfe im Schnitt um {round((avg - 1) * 100)} %.",
                f"aus {n} Änderungen",
            )
        sent = [(_avg_words(a), _avg_words(b)) for a, b in edits]
        if sum(b for _, b in sent) <= 0.8 * sum(a for a, _ in sent):
            add("short_sentences", "Kurze Sätze. Du teilst lange Sätze auf.", f"aus {n} Änderungen")
    with_emoji = [(a, b) for a, b in edits if EMOJI.search(a)]
    if with_emoji and sum(not EMOJI.search(b) for _, b in with_emoji) >= max(
        1, len(with_emoji) * 0.6
    ):
        add("no_emoji", "Keine Emojis.", f"in {len(with_emoji)} Entwürfen entfernt")
    with_tags = [(a, b) for a, b in edits if "#" in a]
    if with_tags and sum(b.count("#") < a.count("#") for a, b in with_tags) >= max(
        1, len(with_tags) * 0.6
    ):
        add(
            "fewer_hashtags",
            "Keine oder höchstens zwei Hashtags.",
            f"in {len(with_tags)} Entwürfen gekürzt",
        )
    with_bang = [(a, b) for a, b in edits if "!" in a]
    if with_bang and sum(b.count("!") < a.count("!") for a, b in with_bang) >= max(
        1, len(with_bang) * 0.6
    ):
        add("no_exclamation", "Keine Ausrufezeichen.", f"in {len(with_bang)} Entwürfen entfernt")
    removed, added = Counter(), Counter()
    for a, b in edits:
        wa, wb = set(_words(a)), set(_words(b))
        removed.update(wa - wb)
        added.update(wb - wa)
    gone = [w for w, c in removed.most_common(8) if c >= 2]
    if gone:
        add(
            "avoid_words",
            "Vermeide diese Wörter: " + ", ".join(gone[:6]) + ".",
            "du streichst sie immer wieder",
        )
    liked = [w for w, c in added.most_common(8) if c >= 2]
    if liked:
        add(
            "own_words",
            "Du verwendest gern: " + ", ".join(liked[:6]) + ".",
            "du ergänzt sie immer wieder",
        )

    def address(text):
        t = f" {text.casefold()} "
        return (
            len(re.findall(r"\b(sie|ihnen|ihr(?:e|en)?)\b", t))
            if re.search(r"\b(ihnen|haben sie|können sie)\b", t)
            else 0,
            len(re.findall(r"\b(du|dich|dir|dein\w*)\b", t)),
        )

    if n >= 2:
        to_sie = sum(
            address(a)[1] > 0 and address(b)[0] > 0 and address(b)[1] == 0 for a, b in edits
        )
        to_du = sum(
            address(a)[0] > 0 and address(b)[1] > 0 and address(b)[0] == 0 for a, b in edits
        )
        if to_sie >= 2:
            add("address_sie", "Sprich die Leser mit Sie an.", f"in {to_sie} Entwürfen geändert")
        elif to_du >= 2:
            add("address_du", "Sprich die Leser mit Du an.", f"in {to_du} Entwürfen geändert")
        questions = sum(not a.rstrip().endswith("?") and b.rstrip().endswith("?") for a, b in edits)
        if questions >= 2:
            add(
                "end_question",
                "Schließe mit einer offenen Frage.",
                f"in {questions} Entwürfen ergänzt",
            )
    for verdict, reason in feedback:
        reason = " ".join((reason or "").split())[:200]
        if not reason:
            continue
        key = ("fb_no_" if verdict == "no" else "fb_yes_") + re.sub(r"\W+", "_", reason.casefold())[
            :40
        ]
        text = f"Nicht: {reason}" if verdict == "no" else f"Gut so: {reason}"
        add(key, text, "aus deiner Rückmeldung")
    return rules


def merge_rules(current: list[dict], derived: list[dict], dismissed: list[str]) -> list[dict]:
    """Keep the user's own and edited rules; refresh automatic ones; never revive dismissed."""
    keep = [r for r in current if r.get("source") in ("manual", "edited")]
    kept_keys = {r.get("key") for r in keep}
    state = {r.get("key"): r for r in current}
    out = list(keep)
    for rule in derived:
        if rule["key"] in dismissed or rule["key"] in kept_keys:
            continue
        old = state.get(rule["key"])
        out.append(
            {
                "id": old["id"] if old else secrets.token_hex(6),
                "key": rule["key"],
                "text": rule["text"],
                "evidence": rule["evidence"],
                "source": "auto",
                "active": old.get("active", True) if old else True,
            }
        )
    return out


def rules_prompt(voice: dict) -> str:
    rules = [r["text"] for r in voice.get("rules") or [] if r.get("active", True)]
    inspirations = voice.get("inspirations") or []
    out = ""
    if rules:
        out += "\nGelernte Regeln des Verfassers (immer beachten): " + " | ".join(rules)
    if inspirations:
        out += (
            "\nStil-Vorbilder (Posts anderer Leute, die dem Verfasser gefallen; nur Rhythmus und "
            "Aufbau, niemals Inhalte, Formulierungen oder Fakten übernehmen): "
            + " ||| ".join(t[:800] for t in inspirations[:3])
        )
    return out


# ---- personal profile ------------------------------------------------------------------


def personal_profile(db, ws, user_id, create=False):
    from app.studio import VoiceInput, VoiceProfile

    for item in db.scalars(
        select(VoiceProfile)
        .where(VoiceProfile.workspace_id == ws, VoiceProfile.actor_id == user_id)
        .order_by(VoiceProfile.created_at)
    ):
        if (item.settings or {}).get("personal"):
            return item
    if not create:
        return None
    from app.models import User

    user = db.get(User, user_id)
    item = VoiceProfile(
        workspace_id=ws,
        actor_id=user_id,
        name=f"Schreibprofil {user.name if user else ''}".strip(),
        settings=VoiceInput(name="Mein Schreibprofil").model_dump()
        | {"personal": True, "rules": [], "dismissed": []},
    )
    db.add(item)
    db.flush()
    return item


def snapshot_extras(db, ws, user_id) -> dict:
    """Rules and style references of a user for a generation snapshot."""
    profile = personal_profile(db, ws, user_id)
    inspirations = [
        i.text
        for i in db.scalars(
            select(Inspiration)
            .where(Inspiration.workspace_id == ws, Inspiration.user_id == user_id)
            .order_by(Inspiration.created_at.desc())
            .limit(3)
        )
    ]
    return {
        "rules": (profile.settings or {}).get("rules", []) if profile else [],
        "inspirations": inspirations,
    }


def relearn(db, ws, user_id) -> dict:
    profile = personal_profile(db, ws, user_id, create=True)
    edits = [
        (e.original, e.edited)
        for e in db.scalars(
            select(DraftEdit)
            .where(DraftEdit.workspace_id == ws, DraftEdit.user_id == user_id)
            .order_by(DraftEdit.created_at.desc())
            .limit(100)
        )
    ]
    feedback = [
        (f.verdict, f.reason)
        for f in db.scalars(
            select(VoiceFeedback)
            .where(VoiceFeedback.workspace_id == ws, VoiceFeedback.user_id == user_id)
            .order_by(VoiceFeedback.created_at.desc())
            .limit(50)
        )
    ]
    settings = dict(profile.settings or {})
    settings["rules"] = merge_rules(
        settings.get("rules", []), derive_rules(edits, feedback), settings.get("dismissed", [])
    )
    settings["learned_at"] = now().isoformat()
    profile.settings = settings
    profile.version += 1
    return profile_output(db, ws, profile, user_id)


def profile_output(db, ws, profile, user_id) -> dict:
    edits = db.scalars(
        select(DraftEdit)
        .where(DraftEdit.workspace_id == ws, DraftEdit.user_id == user_id)
        .order_by(DraftEdit.created_at.desc())
        .limit(10)
    ).all()
    feedback = db.scalars(
        select(VoiceFeedback)
        .where(VoiceFeedback.workspace_id == ws, VoiceFeedback.user_id == user_id)
        .order_by(VoiceFeedback.created_at.desc())
        .limit(10)
    ).all()
    counts = {
        "edits": len(
            db.scalars(
                select(DraftEdit.id).where(
                    DraftEdit.workspace_id == ws, DraftEdit.user_id == user_id
                )
            ).all()
        ),
        "yes": sum(f.verdict == "yes" for f in feedback),
        "no": sum(f.verdict == "no" for f in feedback),
    }
    settings = profile.settings or {}
    return {
        "id": profile.id,
        "version": profile.version,
        "name": profile.name,
        "rules": settings.get("rules", []),
        "learned_at": settings.get("learned_at"),
        "counts": counts,
        "recent_edits": [
            {
                "id": e.id,
                "kind": e.kind,
                "original": e.original,
                "edited": e.edited,
                "created_at": e.created_at,
            }
            for e in edits
        ],
        "recent_feedback": [
            {
                "id": f.id,
                "verdict": f.verdict,
                "reason": f.reason,
                "text": f.text[:200],
                "created_at": f.created_at,
            }
            for f in feedback
        ],
        "inspirations": [
            {
                "id": i.id,
                "author": i.author,
                "text": i.text,
                "note": i.note,
                "created_at": i.created_at,
            }
            for i in db.scalars(
                select(Inspiration)
                .where(Inspiration.workspace_id == ws, Inspiration.user_id == user_id)
                .order_by(Inspiration.created_at.desc())
                .limit(50)
            )
        ],
    }


# ---- routes ----------------------------------------------------------------------------


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    verdict: str = Field(pattern="^(yes|no)$")
    reason: str = Field(default="", max_length=500)
    post_id: str | None = None
    text: str = Field(default="", max_length=3000)


class RuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=3, max_length=300)
    active: bool = True


class RulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str | None = Field(default=None, min_length=3, max_length=300)
    active: bool | None = None


class InspirationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    author: str = Field(default="", max_length=120)
    text: str = Field(min_length=20, max_length=3000)
    note: str = Field(default="", max_length=500)


def register_voice_learning_routes(app, db_session, scope, record, audit):
    base = "/v1/workspaces/{ws}/writing-profile"

    @app.get(base)
    def my_profile(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        profile = personal_profile(db, ws, member.user_id, create=True)
        return profile_output(db, ws, profile, member.user_id)

    @app.post(base + "/relearn")
    def relearn_route(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return relearn(db, ws, member.user_id)

    @app.post(base + "/feedback", status_code=201)
    def feedback(
        ws: str,
        body: FeedbackInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        text = body.text
        if body.post_id:
            post = record(db, Post, ws, body.post_id)
            text = text or post.caption
        if not text:
            raise HTTPException(422, "Text fehlt.")
        db.add(
            VoiceFeedback(
                workspace_id=ws,
                post_id=body.post_id,
                user_id=member.user_id,
                verdict=body.verdict,
                reason=body.reason,
                text=text[:3000],
            )
        )
        db.flush()
        result = relearn(db, ws, member.user_id)
        audit(db, ws, member.user_id, "voice_feedback", "Rückmeldung zum Schreibstil gespeichert")
        return result

    @app.post(base + "/rules", status_code=201)
    def add_rule(
        ws: str, body: RuleInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        profile = personal_profile(db, ws, member.user_id, create=True)
        settings = dict(profile.settings or {})
        settings["rules"] = [
            *settings.get("rules", []),
            {
                "id": secrets.token_hex(6),
                "key": "manual_" + secrets.token_hex(4),
                "text": body.text,
                "evidence": "von dir",
                "source": "manual",
                "active": body.active,
            },
        ]
        profile.settings, profile.version = settings, profile.version + 1
        return profile_output(db, ws, profile, member.user_id)

    @app.patch(base + "/rules/{rule_id}")
    def edit_rule(
        ws: str,
        rule_id: str,
        body: RulePatch,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        profile = personal_profile(db, ws, member.user_id, create=True)
        settings = dict(profile.settings or {})
        rules = [dict(r) for r in settings.get("rules", [])]
        rule = next((r for r in rules if r["id"] == rule_id), None)
        if not rule:
            raise HTTPException(404, "Regel nicht gefunden.")
        if body.text is not None and body.text != rule["text"]:
            rule["text"] = body.text
            if rule["source"] == "auto":
                rule["source"] = "edited"
        if body.active is not None:
            rule["active"] = body.active
        settings["rules"] = rules
        profile.settings, profile.version = settings, profile.version + 1
        return profile_output(db, ws, profile, member.user_id)

    @app.delete(base + "/rules/{rule_id}")
    def delete_rule(
        ws: str, rule_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        profile = personal_profile(db, ws, member.user_id, create=True)
        settings = dict(profile.settings or {})
        rule = next((r for r in settings.get("rules", []) if r["id"] == rule_id), None)
        if not rule:
            raise HTTPException(404, "Regel nicht gefunden.")
        settings["rules"] = [r for r in settings["rules"] if r["id"] != rule_id]
        if rule.get("source") != "manual":
            settings["dismissed"] = sorted({*settings.get("dismissed", []), rule["key"]})
        profile.settings, profile.version = settings, profile.version + 1
        return profile_output(db, ws, profile, member.user_id)

    @app.post(base + "/inspirations", status_code=201)
    def add_inspiration(
        ws: str,
        body: InspirationInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        db.add(Inspiration(workspace_id=ws, user_id=member.user_id, **body.model_dump()))
        db.flush()
        profile = personal_profile(db, ws, member.user_id, create=True)
        return profile_output(db, ws, profile, member.user_id)

    @app.delete(base + "/inspirations/{entity_id}")
    def delete_inspiration(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        item = record(db, Inspiration, ws, entity_id, True)
        if item.user_id != member.user_id:
            raise HTTPException(404, "Nicht gefunden.")
        db.delete(item)
        db.flush()
        profile = personal_profile(db, ws, member.user_id, create=True)
        return profile_output(db, ws, profile, member.user_id)
