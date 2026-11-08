"""V3 M4: personal letters for companies without LinkedIn.

Layout follows DIN 5008 form B on A4: letterhead 45 mm, address field 85 x 45 mm at
20 mm from the left (5 lines return-address zone + 9 lines address zone), information
block at 125 mm, fold marks at 105 mm and 210 mm, punch mark at 148.5 mm, subject below
the address field, one page. CleanStar look: colours, Instrument Sans/Serif (SIL OFL,
licences in ``app/assets/brand/cleanstar``) and logo.

Each company gets one reference code. The QR code points to ``<public base>/r/<code>``
when ProspectOS is reachable from the internet, otherwise directly to the target page
with ``?ref=<code>``; a code that later appears in an inquiry is matched in the inbox.

Letters are drafts until approved; only approved letters go into the print PDF. Marking a
batch as printed completes the matching campaign tasks. A print-and-mail service is an
adapter behind a switch that is off; no provider is called (see ``PRINT_SERVICE_OPTIONS``).
"""

import os
import re
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from app import style
from app.db import Base, now
from app.models import Company, Contact, TenantMixin

ASSETS = Path(__file__).parent / "assets" / "brand" / "cleanstar"
BRAND = {
    "ink": "#0b1220",
    "night": "#0a1a33",
    "blue": "#1a4fe0",
    "sky": "#0086f6",
    "muted": "#4a5566",
    "line": "#d9e0e8",
}
MAX_BATCH = 200
PRINT_SERVICE_OPTIONS = [
    {
        "name": "Pingen",
        "note": "Schweizer Anbieter mit REST-API, Druck und Versand auch in Deutschland. Preise und "
        "API-Bedingungen vor Aktivierung auf pingen.com prüfen.",
    },
    {
        "name": "LetterXpress",
        "note": "Deutscher Anbieter (Druck in Deutschland) mit API. Konditionen und Datenschutzvertrag "
        "(AVV) vor Aktivierung prüfen.",
    },
    {
        "name": "Deutsche Post E-POST Mailer / Dialogpost",
        "note": "Brief bzw. Werbesendung über die Post; Schnittstellen und Mindestmengen beim Anbieter klären.",
    },
]
DEFAULT_BODY = (
    "{evidence}Wir sind {sender_company} und kümmern uns um {offer} in {region}. "
    "Für Sie haben wir einen kostenlosen Reinigungs-Check vorbereitet: Wir schauen uns Ihre "
    "Räume an und Sie bekommen ein festes Angebot. Ohne Verpflichtung.\n\n"
    "Scannen Sie einfach den QR-Code unten. Oder rufen Sie mich direkt an."
)


class LetterSettings(TenantMixin, Base):
    __tablename__ = "letter_settings"
    sender_name: Mapped[str] = mapped_column(String(80), default="")
    sender_company: Mapped[str] = mapped_column(String(80), default="")
    sender_street: Mapped[str] = mapped_column(String(120), default="")
    sender_city: Mapped[str] = mapped_column(String(120), default="")
    sender_phone: Mapped[str] = mapped_column(String(40), default="")
    sender_email: Mapped[str] = mapped_column(String(120), default="")
    sender_web: Mapped[str] = mapped_column(String(120), default="")
    qr_target_url: Mapped[str] = mapped_column(String(500), default="")
    qr_caption: Mapped[str] = mapped_column(String(120), default="Kostenloser Reinigungs-Check")
    subject: Mapped[str] = mapped_column(String(120), default="Ihr kostenloser Reinigungs-Check")
    body_template: Mapped[str] = mapped_column(String(3000), default=DEFAULT_BODY)
    closing: Mapped[str] = mapped_column(String(80), default="Viele Grüße")
    print_service_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("workspace_id"),)


class Letter(TenantMixin, Base):
    __tablename__ = "letters"
    contact_id: Mapped[str] = mapped_column(String(36))
    company_id: Mapped[str | None] = mapped_column(String(36))
    task_id: Mapped[str | None] = mapped_column(String(36))
    code: Mapped[str] = mapped_column(String(20))
    recipient: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(3000))
    qr_url: Mapped[str] = mapped_column(String(600))
    state: Mapped[str] = mapped_column(String(20), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    approved_by: Mapped[str | None] = mapped_column(String(36))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "company_id"], ["companies.workspace_id", "companies.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "approved_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sender_name: str = Field(default="", max_length=80)
    sender_company: str = Field(default="", max_length=80)
    sender_street: str = Field(default="", max_length=120)
    sender_city: str = Field(default="", max_length=120)
    sender_phone: str = Field(default="", max_length=40)
    sender_email: str = Field(default="", max_length=120)
    sender_web: str = Field(default="", max_length=120)
    qr_target_url: str = Field(default="", max_length=500)
    qr_caption: str = Field(default="Kostenloser Reinigungs-Check", max_length=120)
    subject: str = Field(default="Ihr kostenloser Reinigungs-Check", min_length=3, max_length=120)
    body_template: str = Field(default=DEFAULT_BODY, min_length=20, max_length=3000)
    closing: str = Field(default="Viele Grüße", min_length=2, max_length=80)


class PrepareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_ids: list[str] = Field(default_factory=list, max_length=MAX_BATCH)
    from_tasks: bool = False


class EditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=20, max_length=3000)
    revision: int


class IdsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(default_factory=list, max_length=MAX_BATCH)
    all_approved: bool = False


# ---- fonts and drawing --------------------------------------------------------------


@lru_cache(maxsize=1)
def fonts() -> dict:
    """Register the CleanStar fonts once; fall back to Helvetica if conversion fails."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont as ReportFont

    try:
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer

        def ttf(font):
            font.flavor = None
            out = BytesIO()
            font.save(out)
            out.seek(0)
            return out

        sans = ASSETS / "instrument-sans-latin-wght.woff2"
        for name, weight in (("CS-Sans", 400), ("CS-Sans-Bold", 600)):
            pdfmetrics.registerFont(
                ReportFont(
                    name, ttf(instancer.instantiateVariableFont(TTFont(sans), {"wght": weight}))
                )
            )
        pdfmetrics.registerFont(
            ReportFont("CS-Serif", ttf(TTFont(ASSETS / "instrument-serif-subset.woff2")))
        )
        return {"sans": "CS-Sans", "bold": "CS-Sans-Bold", "serif": "CS-Serif", "brand": True}
    except Exception:
        return {
            "sans": "Helvetica",
            "bold": "Helvetica-Bold",
            "serif": "Times-Roman",
            "brand": False,
        }


def split_address(value: str) -> list[str]:
    """'Testweg 1, 77652 Offenburg' -> ['Testweg 1', '77652 Offenburg']."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) >= 2 and re.match(r"^\d{5}\b", parts[-1]):
        return [", ".join(parts[:-1]), parts[-1]]
    return parts[:3]


def salutation(contact: Contact) -> str:
    # Gender-neutral: never guess "Herr"/"Frau" from a first name.
    name = f"{contact.first_name} {contact.last_name}".strip()
    if contact.first_name and contact.last_name and not contact.last_name.endswith("(synthetisch)"):
        return f"Guten Tag {name},"
    return "Sehr geehrte Damen und Herren,"


def _wrap(canvas, text, font, size, width):
    from reportlab.pdfbase.pdfmetrics import stringWidth

    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for word in paragraph.split():
            trial = f"{current} {word}".strip()
            if stringWidth(trial, font, size) <= width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def draw_letter(
    canvas, letter: "Letter", settings: "LetterSettings", contact: Contact, draft: bool
):
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import mm

    f = fonts()
    height = 297 * mm
    ink, blue, muted, line = (HexColor(BRAND[k]) for k in ("ink", "blue", "muted", "line"))

    def y(from_top_mm):
        return height - from_top_mm * mm

    # Letterhead (45 mm): CleanStar logo (only for a CleanStar sender) or the sender name,
    # sender details right, thin brand rule.
    logo = ASSETS / "logo-cropped.png"
    if logo.exists() and "cleanstar" in (settings.sender_company or "").casefold():
        canvas.drawImage(str(logo), 20 * mm, y(33), 62 * mm, 62 * mm * 227 / 841, mask="auto")
    else:
        canvas.setFillColor(ink)
        canvas.setFont(f["serif"], 20)
        canvas.drawString(20 * mm, y(28), settings.sender_company or "Absender")
    canvas.setFont(f["sans"], 8.5)
    canvas.setFillColor(muted)
    info = [
        x
        for x in (
            settings.sender_street,
            settings.sender_city,
            settings.sender_phone,
            settings.sender_email,
            settings.sender_web,
        )
        if x
    ]
    for i, text in enumerate(info[:5]):
        canvas.drawRightString(190 * mm, y(16 + i * 4.2), text)
    canvas.setStrokeColor(blue)
    canvas.setLineWidth(1.2)
    canvas.line(20 * mm, y(42), 190 * mm, y(42))

    # Fold and punch marks on the left edge.
    canvas.setStrokeColor(muted)
    canvas.setLineWidth(0.3)
    for mark in (105, 210):
        canvas.line(3 * mm, y(mark), 8 * mm, y(mark))
    canvas.line(3 * mm, y(148.5), 10 * mm, y(148.5))

    # Address field: return-address zone (17.7 mm) + address zone (27.3 mm) at 45 mm.
    canvas.setFont(f["sans"], 7)
    sender_line = " · ".join(
        x for x in (settings.sender_company, settings.sender_street, settings.sender_city) if x
    )
    canvas.drawString(20 * mm, y(45 + 14), sender_line[:95])
    canvas.setFillColor(ink)
    canvas.setFont(f["sans"], 10.5)
    for i, text in enumerate(letter.recipient[:6]):
        canvas.drawString(20 * mm, y(45 + 17.7 + 4.5 + i * 4.6), text[:48])

    # Information block.
    canvas.setFont(f["sans"], 8.5)
    canvas.setFillColor(muted)
    canvas.drawString(125 * mm, y(55), "Datum")
    canvas.drawString(125 * mm, y(63), "Ihr Code")
    canvas.setFillColor(ink)
    canvas.setFont(f["sans"], 10)
    canvas.drawString(125 * mm, y(59), now().strftime("%d.%m.%Y"))
    canvas.drawString(125 * mm, y(67), letter.code)

    # Subject and body (one page; text is cut off with a note, never a second page).
    canvas.setFont(f["bold"], 12)
    canvas.drawString(25 * mm, y(98.5), letter.subject)
    body = (
        f"{salutation(contact)}\n\n{letter.body}\n\n{settings.closing}\n\n\n{settings.sender_name}"
    )
    canvas.setFont(f["sans"], 10.5)
    top, limit, leading = 110, 238, 5.2
    lines = _wrap(canvas, body, f["sans"], 10.5, 165 * mm)
    for i, text in enumerate(lines):
        pos = top + i * leading
        if pos > limit:
            canvas.setFillColor(muted)
            canvas.drawString(25 * mm, y(pos), "[Text gekürzt: maximal eine Seite]")
            break
        canvas.drawString(25 * mm, y(pos), text)

    # QR code with caption, bottom right.
    size = 28 * mm
    widget = QrCodeWidget(letter.qr_url, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, canvas, 162 * mm, y(272))
    canvas.setFont(f["bold"], 9)
    canvas.setFillColor(ink)
    canvas.drawRightString(158 * mm, y(255), settings.qr_caption)
    canvas.setFont(f["sans"], 8)
    canvas.setFillColor(muted)
    canvas.drawRightString(
        158 * mm, y(259.5), "QR-Code scannen oder Code bei Ihrer Anfrage angeben:"
    )
    canvas.drawRightString(158 * mm, y(263.5), letter.code)

    # Footer.
    canvas.setStrokeColor(line)
    canvas.line(20 * mm, y(280), 190 * mm, y(280))
    canvas.setFont(f["sans"], 7)
    canvas.drawString(20 * mm, y(284), " · ".join([settings.sender_company, *info])[:160])
    if draft:
        canvas.saveState()
        canvas.setFillColor(HexColor("#bd455b"))
        canvas.setFont(f["bold"], 9)
        canvas.drawString(125 * mm, y(75), "ENTWURF, nicht freigegeben")
        canvas.restoreState()
    canvas.showPage()


def render_pdf(db, ws, letters: list["Letter"], draft_mark=True) -> bytes:
    from reportlab.pdfgen import canvas as pdf

    settings = get_settings(db, ws)
    out = BytesIO()
    c = pdf.Canvas(out, pagesize=(595.2756, 841.8898))
    c.setTitle("Briefe" if len(letters) > 1 else letters[0].subject)
    c.setAuthor(settings.sender_company or "ProspectOS")
    for letter in letters:
        contact = db.get(Contact, letter.contact_id)
        draw_letter(c, letter, settings, contact, draft_mark and letter.state == "draft")
    c.save()
    return out.getvalue()


def render_labels(letters: list["Letter"]) -> bytes:
    """Zweckform 3474 layout: 3 x 8 labels of 70 x 37 mm on A4, no margins."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdf

    f = fonts()
    out = BytesIO()
    c = pdf.Canvas(out, pagesize=(595.2756, 841.8898))
    c.setTitle("Adressetiketten")
    for index, letter in enumerate(letters):
        slot = index % 24
        if index and slot == 0:
            c.showPage()
        col, row = slot % 3, slot // 3
        x = col * 70 * mm + 6 * mm
        top = 297 * mm - row * 37 * mm - 10 * mm
        c.setFont(f["sans"], 9.5)
        for i, text in enumerate(letter.recipient[:5]):
            c.drawString(x, top - i * 4.6 * mm, text[:40])
    c.showPage()
    c.save()
    return out.getvalue()


# ---- data ---------------------------------------------------------------------------


def get_settings(db, ws) -> LetterSettings:
    item = db.scalar(select(LetterSettings).where(LetterSettings.workspace_id == ws))
    if item is None:
        from app.today import get_settings as outreach_settings

        base = outreach_settings(db, ws)
        item = LetterSettings(
            workspace_id=ws,
            sender_name=base.sender_name,
            sender_company=base.sender_company,
        )
        db.add(item)
        db.flush()
    return item


def qr_url(settings: LetterSettings, code: str) -> str:
    from app.reactions import with_ref

    public = os.getenv("PUBLIC_WEB_URL", "").rstrip("/")
    if public.startswith("https://"):
        return f"{public}/r/{code}"
    if settings.qr_target_url:
        return with_ref(settings.qr_target_url, code)
    raise HTTPException(
        409,
        "Für den QR-Code fehlt ein Ziel: Zielseite in den Brief-Einstellungen angeben "
        "(oder ProspectOS öffentlich über https erreichbar machen).",
    )


def compose_letter(db, ws, contact: Contact, settings: LetterSettings, task_id=None) -> "Letter":
    from app.multichannel import channel_permissions, points_of
    from app.reactions import code_for
    from app.sales_agent import evidence_sentence, ranked_facts
    from app.today import get_settings as outreach_settings

    permission = channel_permissions(db, ws, contact)["letter"]
    if not permission["allowed"]:
        raise HTTPException(409, f"Brief nicht möglich: {permission['reason']}")
    company = db.get(Company, contact.company_id) if contact.company_id else None
    if company is None:
        raise HTTPException(409, "Ein Brief braucht eine Firma mit Adresse.")
    postal = next(p for p in points_of(db, ws, contact.id) if p.channel == "postal")
    name = f"{contact.first_name} {contact.last_name}".strip()
    recipient = [
        company.name,
        *([f"z. Hd. {name}"] if contact.first_name else []),
        *split_address(postal.value),
    ]
    facts = [
        f
        for f in ranked_facts(db, ws, company.id)
        if f.field not in ("Adresse", "Adresse (Impressum)")
    ]
    evidence = (evidence_sentence(facts[0], company) + " ") if facts else ""
    base = outreach_settings(db, ws)
    body = settings.body_template
    for key, value in {
        "evidence": evidence,
        "company": company.name,
        "sender_company": settings.sender_company or base.sender_company or "wir",
        "offer": base.offer,
        "region": base.region,
        "first_name": contact.first_name,
    }.items():
        body = body.replace("{" + key + "}", value or "")
    ref = code_for(db, ws, company.id, settings.qr_target_url)
    return Letter(
        workspace_id=ws,
        contact_id=contact.id,
        company_id=company.id,
        task_id=task_id,
        code=ref.code,
        recipient=recipient,
        subject=settings.subject,
        body=style.clean(body)[:3000],
        qr_url=qr_url(settings, ref.code),
        state="draft",
    )


def letter_output(db, letter: Letter) -> dict:
    contact = db.get(Contact, letter.contact_id)
    return {
        "id": letter.id,
        "contact": {"id": contact.id, "name": f"{contact.first_name} {contact.last_name}".strip()}
        if contact
        else None,
        "recipient": letter.recipient,
        "subject": letter.subject,
        "body": letter.body,
        "code": letter.code,
        "qr_url": letter.qr_url,
        "state": letter.state,
        "revision": letter.revision,
        "task_id": letter.task_id,
        "approved_at": letter.approved_at,
        "printed_at": letter.printed_at,
        "style_issues": style.violations(letter.body),
        "created_at": letter.created_at,
    }


def register_letter_routes(app, db_session, scope, record, audit):
    from app.flows import FlowTask, complete_task

    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Bearbeitungsrecht erforderlich.")

    def settings_out(s: LetterSettings):
        return {k: getattr(s, k) for k in SettingsInput.model_fields} | {
            "print_service_enabled": s.print_service_enabled,
            "fonts": "CleanStar (Instrument Sans/Serif)"
            if fonts()["brand"]
            else "Ersatzschrift (Helvetica)",
        }

    def selected(db, ws, body: IdsInput, states):
        if body.all_approved:
            rows = db.scalars(
                select(Letter)
                .where(Letter.workspace_id == ws, Letter.state.in_(states))
                .order_by(Letter.created_at)
                .limit(MAX_BATCH)
            ).all()
        else:
            rows = [record(db, Letter, ws, i) for i in dict.fromkeys(body.ids)]
        if not rows:
            raise HTTPException(409, "Keine passenden Briefe ausgewählt.")
        if any(r.state not in states for r in rows):
            raise HTTPException(409, "Nur freigegebene Briefe gehen in den Druck.")
        return rows

    @app.get("/v1/workspaces/{ws}/letters/settings")
    def read_settings(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return settings_out(get_settings(db, ws))

    @app.put("/v1/workspaces/{ws}/letters/settings")
    def write_settings(
        ws: str,
        body: SettingsInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app.reactions import safe_target

        authoring(member)
        item = get_settings(db, ws)
        data = body.model_dump()
        data["qr_target_url"] = safe_target(data["qr_target_url"])
        for key, value in data.items():
            setattr(item, key, value)
        audit(db, ws, member.user_id, "letter_settings", "Brief-Einstellungen gespeichert")
        return settings_out(item)

    @app.get("/v1/workspaces/{ws}/letters")
    def list_letters(
        ws: str, state: str = "", member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        stmt = select(Letter).where(Letter.workspace_id == ws)
        if state:
            stmt = stmt.where(Letter.state == state)
        rows = db.scalars(stmt.order_by(Letter.created_at.desc()).limit(300)).all()
        counts = {}
        for row in db.scalars(select(Letter.state).where(Letter.workspace_id == ws)):
            counts[row] = counts.get(row, 0) + 1
        open_tasks = db.scalar(
            select(func_count())
            .select_from(FlowTask)
            .where(FlowTask.workspace_id == ws, FlowTask.kind == "letter", FlowTask.state == "open")
        )
        return {
            "items": [letter_output(db, r) for r in rows],
            "counts": counts,
            "open_letter_tasks": open_tasks,
            "print_service": {"enabled": False, "options": PRINT_SERVICE_OPTIONS},
        }

    @app.post("/v1/workspaces/{ws}/letters/prepare", status_code=201)
    def prepare(
        ws: str, body: PrepareInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        settings = get_settings(db, ws)
        pairs = []
        if body.from_tasks:
            for task in db.scalars(
                select(FlowTask)
                .where(
                    FlowTask.workspace_id == ws, FlowTask.kind == "letter", FlowTask.state == "open"
                )
                .limit(MAX_BATCH)
            ):
                pairs.append((task.contact_id, task.id))
        pairs += [(cid, None) for cid in body.contact_ids]
        created, skipped = [], []
        for contact_id, task_id in pairs:
            contact = record(db, Contact, ws, contact_id)
            if db.scalar(
                select(Letter.id).where(
                    Letter.workspace_id == ws,
                    Letter.contact_id == contact.id,
                    Letter.state.in_(["draft", "approved"]),
                )
            ):
                skipped.append({"contact_id": contact.id, "reason": "Offener Brief vorhanden"})
                continue
            try:
                letter = compose_letter(db, ws, contact, settings, task_id)
            except HTTPException as exc:
                if exc.status_code == 409 and "QR-Code" in str(exc.detail):
                    raise
                skipped.append({"contact_id": contact.id, "reason": str(exc.detail)})
                continue
            db.add(letter)
            db.flush()
            created.append(letter_output(db, letter))
        audit(db, ws, member.user_id, "letters_prepared", f"{len(created)} Briefentwürfe erstellt")
        return {"created": created, "skipped": skipped}

    @app.patch("/v1/workspaces/{ws}/letters/{entity_id}")
    def edit(
        ws: str,
        entity_id: str,
        body: EditInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        letter = record(db, Letter, ws, entity_id, True)
        if letter.revision != body.revision or letter.state not in ("draft", "approved"):
            raise HTTPException(409, "Brief wurde inzwischen geändert oder ist schon gedruckt.")
        letter.subject, letter.body = body.subject, style.clean(body.body)
        letter.revision += 1
        letter.state, letter.approved_by, letter.approved_at = "draft", None, None
        return letter_output(db, letter)

    @app.post("/v1/workspaces/{ws}/letters/{entity_id}/approve")
    def approve(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if member.role not in ("owner", "admin", "editor", "approver"):
            raise HTTPException(403, "Freigaberecht erforderlich.")
        letter = record(db, Letter, ws, entity_id, True)
        if letter.state != "draft":
            raise HTTPException(409, "Nur Entwürfe können freigegeben werden.")
        from app.multichannel import suppression_of

        if suppression_of(db, ws, letter.contact_id):
            raise HTTPException(409, "Widerspruch: Brief darf nicht verschickt werden.")
        letter.state, letter.approved_by, letter.approved_at = "approved", member.user_id, now()
        audit(
            db,
            ws,
            member.user_id,
            "letter_approved",
            f"Brief Revision {letter.revision} freigegeben",
        )
        return letter_output(db, letter)

    @app.get("/v1/workspaces/{ws}/letters/{entity_id}/pdf")
    def one_pdf(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        letter = record(db, Letter, ws, entity_id)
        return Response(
            render_pdf(db, ws, [letter]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="brief-{letter.code}.pdf"'},
        )

    @app.post("/v1/workspaces/{ws}/letters/print-pdf")
    def print_pdf(
        ws: str, body: IdsInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        rows = selected(db, ws, body, ("approved",))
        from app.multichannel import suppression_of

        blocked = [r for r in rows if suppression_of(db, ws, r.contact_id)]
        if blocked:
            raise HTTPException(
                409, f"{len(blocked)} Empfänger haben widersprochen; Auswahl prüfen."
            )
        return Response(
            render_pdf(db, ws, rows, draft_mark=False),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="briefe-druck.pdf"'},
        )

    @app.post("/v1/workspaces/{ws}/letters/labels-pdf")
    def labels_pdf(
        ws: str, body: IdsInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        rows = selected(db, ws, body, ("approved", "printed"))
        return Response(
            render_labels(rows),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="adressetiketten-3474.pdf"'},
        )

    @app.post("/v1/workspaces/{ws}/letters/mark-printed")
    def mark_printed(
        ws: str, body: IdsInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        rows = selected(db, ws, body, ("approved",))
        completed = 0
        for letter in rows:
            letter.state, letter.printed_at = "printed", now()
            if letter.task_id:
                task = db.get(FlowTask, letter.task_id)
                if task and task.workspace_id == ws and task.state == "open":
                    complete_task(
                        db, ws, task, member.user_id, "done", "Brief gedruckt (selbst gemeldet)"
                    )
                    completed += 1
        audit(
            db, ws, member.user_id, "letters_printed", f"{len(rows)} Briefe als gedruckt markiert"
        )
        return {"printed": len(rows), "tasks_completed": completed}

    @app.post("/v1/workspaces/{ws}/letters/send-print-service")
    def send_print_service(ws: str, member=Depends(scope)):
        raise HTTPException(
            403,
            "Druck-und-Versand-Dienst ist ausgeschaltet. Anbieter, Vertrag (AVV) und Kosten müssen "
            "vor einer Aktivierung geprüft werden; bis dahin Sammel-PDF drucken.",
        )


def func_count():
    from sqlalchemy import func

    return func.count()
