"""Setup check: one traffic light per integration with the concrete next step.

green = configured and confirmed (last connection test or live connection), yellow =
configured but not confirmed / incomplete, red = missing, off = deliberately not
connected yet (mailbox until the Google account is unlocked). Values are never
returned, only whether they exist and where they come from.

`next` is written for the person using the app (no jargon); `tech` carries the
technical detail (env names, scripts) for whoever maintains the installation.
"""

import os
from pathlib import Path

from fastapi import Depends
from sqlalchemy import func, select

from app import credentials, style
from app.db import now


def _tested(db, ws, provider: str) -> str:
    """connected | error | untested | missing from the Integrations page state."""
    from app.integrations import describe

    return describe(db, ws, provider)["status"]


def _item(key, label, light, status, next_step, link="/settings/integrations", detail="", tech=""):
    return {
        "key": key,
        "label": label,
        "light": light,
        "status": status,
        "detail": detail,
        "next": next_step,
        "tech": tech,
        "link": link,
    }


def linkedin(db, ws, user_id=None) -> dict:

    app_ok = bool(
        credentials.get("LINKEDIN_CLIENT_ID")
        and credentials.get("LINKEDIN_CLIENT_SECRET")
        and os.getenv("LINKEDIN_REDIRECT_URI")
    )
    from app.social import linkedin_connection

    connection = linkedin_connection(db, ws, user_id)
    live = bool(connection and connection.expires_at > now())
    can_post = bool(live and "w_member_social" in (connection.scopes or []))
    flag = os.getenv("LINKEDIN_PUBLISHING_APPROVED") == "true"
    if not app_ok:
        return _item(
            "linkedin",
            "LinkedIn",
            "red",
            "Zugangsdaten der LinkedIn-App fehlen",
            "Unter Verbindungen die Client ID und das Secret der LinkedIn-App eintragen.",
        )
    if not live:
        return _item(
            "linkedin",
            "LinkedIn",
            "yellow",
            "Konto nicht verbunden" if not connection else "Verbindung abgelaufen",
            "Unter Verbindungen auf „Mit LinkedIn verbinden“ klicken.",
            tech="ProspectOS dafür über http://localhost:3000 öffnen.",
        )
    days = (connection.expires_at - now()).days
    detail = f"Verbunden, noch {days} Tage gültig. " + (
        "Posten erlaubt." if can_post else "Posten nicht erlaubt."
    )
    if not can_post or not flag:
        return _item(
            "linkedin",
            "LinkedIn",
            "yellow",
            "Verbunden, Posten noch nicht freigeschaltet",
            "Das Posten muss einmalig freigeschaltet werden."
            if can_post
            else "In der LinkedIn-App das Produkt „Share on LinkedIn“ aktivieren und neu verbinden.",
            detail=detail,
            tech="LINKEDIN_PUBLISHING_APPROVED=true in .env" if can_post else "",
        )
    return _item(
        "linkedin",
        "LinkedIn",
        "green",
        "Verbunden, Posten nach Freigabe möglich",
        "Nichts zu tun. Anfragen sendest du selbst in LinkedIn.",
        link="/social/studio",
        detail=detail,
    )


def llm(db, ws) -> dict:
    tested = _tested(db, ws, "openai")
    model = credentials.get("LLM_MODEL")
    if tested == "missing":
        return _item(
            "llm",
            "KI-Texte",
            "red",
            "Zugang zum KI-Anbieter fehlt",
            "Unter Verbindungen den OpenAI-Schlüssel, das Modell und die Preise eintragen.",
        )
    if tested == "connected":
        return _item(
            "llm",
            "KI-Texte",
            "green",
            f"Bestätigt ({model})",
            "Nichts zu tun. Die Kosten siehst du unter Einstellungen → Kosten.",
            link="/operations",
        )
    return _item(
        "llm",
        "KI-Texte",
        "red" if tested == "error" else "yellow",
        "Letzter Test fehlgeschlagen" if tested == "error" else "Eingetragen, noch nicht getestet",
        "Unter Verbindungen bei OpenAI auf „Verbindung testen“ klicken.",
    )


def image(db, ws) -> dict:
    from app.costs import image_prices
    from app.experience import image_requirements

    req = image_requirements()
    if not req["configured"]:
        return _item(
            "image",
            "KI-Bilder",
            "red",
            "Bildmodell oder Kostenobergrenze fehlt",
            "Unter Verbindungen das Bildmodell eintragen.",
            tech="Fehlt: " + ", ".join(req["requirements"]),
        )
    if not image_prices():
        return _item(
            "image",
            "KI-Bilder",
            "yellow",
            "Bildpreise fehlen, Kosten werden nur geschätzt",
            "Die Preise des Bildanbieters in der Konfiguration eintragen lassen.",
            tech="IMAGE_TEXT_INPUT_USD_PER_MILLION und IMAGE_OUTPUT_USD_PER_MILLION in .env",
        )
    tested = _tested(db, ws, "openai")
    light = "green" if tested == "connected" else "yellow"
    return _item(
        "image",
        "KI-Bilder",
        light,
        f"Bereit, höchstens {req['max_cost_minor']} ct pro Bild",
        "Nichts zu tun."
        if light == "green"
        else "Unter Verbindungen die OpenAI-Verbindung testen.",
        link="/content/plan",
    )


def osm() -> dict:
    enabled = os.getenv("OSM_DISCOVERY_ENABLED", "false").lower() == "true"
    contact = credentials.get("OSM_CONTACT", "").strip()
    extract = os.getenv("OSM_EXTRACT_PATH", "").strip()
    has_extract = bool(extract and Path(extract).is_file())
    label = "Firmensuche (OpenStreetMap)"
    if not enabled:
        return _item(
            "osm",
            label,
            "red",
            "Firmensuche ist aus",
            "Die Firmensuche in der Konfiguration einschalten lassen.",
            tech="OSM_DISCOVERY_ENABLED=true in .env (infra/scripts/bootstrap-local.sh)",
        )
    if not contact or contact.endswith("example.invalid"):
        return _item(
            "osm",
            label,
            "yellow",
            "Kontaktangabe fehlt",
            "Unter Verbindungen eine Kontakt-E-Mail für OpenStreetMap eintragen. "
            "Das verlangen deren Regeln.",
            tech="OSM_CONTACT",
        )
    if not has_extract:
        return _item(
            "osm",
            label,
            "yellow",
            "Kartendaten nicht lokal gespeichert",
            "Die Kartendaten einmalig herunterladen lassen. Ohne sie schlägt die Suche oft fehl.",
            tech="infra/scripts/bootstrap-local.sh lädt den Geofabrik-Auszug",
        )
    size = Path(extract).stat().st_size // (1024 * 1024)
    return _item(
        "osm",
        label,
        "green",
        f"Kartendaten lokal gespeichert ({size} MB)",
        "Nichts zu tun.",
        link="/discover",
    )


def brave(db, ws) -> dict:
    tested = _tested(db, ws, "brave")
    label = "Profilsuche (Brave Search)"
    if tested == "missing":
        return _item(
            "brave",
            label,
            "red",
            "Schlüssel fehlt",
            "Unter Verbindungen den Brave-Search-Schlüssel eintragen. Damit findet ProspectOS "
            "passende LinkedIn-Profile.",
        )
    if tested == "connected":
        return _item("brave", label, "green", "Bestätigt", "Nichts zu tun.", link="/today")
    return _item(
        "brave",
        label,
        "red" if tested == "error" else "yellow",
        "Letzter Test fehlgeschlagen" if tested == "error" else "Eingetragen, noch nicht getestet",
        "Unter Verbindungen bei Brave Search auf „Verbindung testen“ klicken.",
    )


def mailbox(db, ws) -> dict:
    from app.email_outreach import Mailbox

    count = db.scalar(select(func.count(Mailbox.id)).where(Mailbox.workspace_id == ws))
    if not count:
        return _item(
            "mailbox",
            "E-Mail-Postfach",
            "off",
            "noch nicht verbunden",
            "Erst wenn das Google-Konto freigeschaltet ist. Bis dahin wird keine E-Mail versendet.",
            tech="Verbindungen → Mailbox: SMTP/IMAP mit App-Passwort",
        )
    return _item(
        "mailbox",
        "E-Mail-Postfach",
        "yellow",
        f"{count} Postfach eingetragen",
        "Unter Verbindungen den Postfach-Test ausführen. Versand nur mit Freigabe.",
    )


def writing_style(db, ws) -> dict:
    s = style.status(db, ws)
    if s["state"] != "ok":
        return _item(
            "style",
            "Schreibstil",
            "yellow",
            "Keine eigenen Texte" if s["state"] == "missing" else "Datei ohne Texte",
            "3 bis 5 eigene Texte hinterlegen, damit die Entwürfe nach dir klingen.",
            link="/settings/outreach",
            tech="data/private/meine-texte.md, Texte mit --- trennen",
        )
    return _item(
        "style",
        "Schreibstil",
        "green" if s["in_sync"] else "yellow",
        f"{s['samples']} eigene Texte",
        "Nichts zu tun."
        if s["in_sync"]
        else "Deine Texte haben sich geändert: „Aus Datei übernehmen“ klicken.",
        link="/settings/outreach",
    )


def external_tools(db, ws):
    """Light for M9 external outreach tools; only shown when the product switch is on."""
    from app.connectors import OutreachConnector, product_enabled, settings_of

    if not product_enabled():
        return None
    settings = settings_of(db, ws)
    if not settings or not settings.enabled:
        return _item(
            "external_tools",
            "Externe Outreach-Tools",
            "off",
            "Aus",
            "Nur bei Bedarf und auf eigene Gefahr einschalten.",
            link="/settings/connectors",
        )
    rows = db.scalars(
        select(OutreachConnector).where(
            OutreachConnector.workspace_id == ws, OutreachConnector.active.is_(True)
        )
    ).all()
    failed = [r.tool for r in rows if r.last_test_ok is False]
    untested = [r.tool for r in rows if r.last_test_ok is None]
    light = "red" if failed else ("yellow" if untested or not rows else "green")
    status = (
        f"Fehler: {', '.join(failed)}"
        if failed
        else (f"Nicht getestet: {', '.join(untested)}" if untested else f"{len(rows)} verbunden")
        if rows
        else "Eingeschaltet, kein Tool verbunden"
    )
    return _item(
        "external_tools",
        "Externe Outreach-Tools (eigene Gefahr)",
        light,
        status,
        "Verbindung testen." if light != "green" else "Nichts zu tun.",
        link="/settings/connectors",
        detail=f"Bestätigt von {settings.acknowledged_name}",
    )


def setup_check(db, ws, user_id=None) -> dict:
    if credentials.is_demo(db, ws):
        items = [
            _item(
                "workspace",
                "Workspace",
                "off",
                "Demo-Workspace",
                "Für echte Arbeit den Demo-Schalter unten links ausschalten.",
                link="/today",
            )
        ]
        return {"items": items, "summary": {"green": 0, "yellow": 0, "red": 0, "off": 1}}
    items = [
        linkedin(db, ws, user_id),
        llm(db, ws),
        image(db, ws),
        osm(),
        brave(db, ws),
        mailbox(db, ws),
        writing_style(db, ws),
    ]
    tools = external_tools(db, ws)
    if tools:
        items.append(tools)
    summary = {k: sum(i["light"] == k for i in items) for k in ("green", "yellow", "red", "off")}
    return {"items": items, "summary": summary}


def register_setup_routes(app, db_session, scope):
    @app.get("/v1/workspaces/{ws}/setup-check")
    def check(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return setup_check(db, ws, member.user_id)
