"""Setup check: one traffic light per integration with the concrete next step.

green = configured and confirmed (last connection test or live connection), yellow =
configured but not confirmed / incomplete, red = missing, off = deliberately not
connected yet (mailbox until the Google account is unlocked). Values are never
returned, only whether they exist and where they come from.
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


def _item(key, label, light, status, next_step, link="/settings/integrations", detail=""):
    return {
        "key": key,
        "label": label,
        "light": light,
        "status": status,
        "detail": detail,
        "next": next_step,
        "link": link,
    }


def linkedin(db, ws) -> dict:
    from app.platform_models import Connection

    app_ok = bool(
        credentials.get("LINKEDIN_CLIENT_ID")
        and credentials.get("LINKEDIN_CLIENT_SECRET")
        and os.getenv("LINKEDIN_REDIRECT_URI")
    )
    connection = db.scalar(
        select(Connection).where(Connection.workspace_id == ws, Connection.provider == "linkedin")
    )
    live = bool(connection and connection.expires_at > now())
    can_post = bool(live and "w_member_social" in (connection.scopes or []))
    flag = os.getenv("LINKEDIN_PUBLISHING_APPROVED") == "true"
    if not app_ok:
        return _item(
            "linkedin",
            "LinkedIn",
            "red",
            "App-Zugangsdaten fehlen",
            "Client ID und Secret der LinkedIn-App unter Integrationen eintragen.",
        )
    if not live:
        return _item(
            "linkedin",
            "LinkedIn",
            "yellow",
            "App eingetragen, Konto nicht verbunden" if not connection else "Verbindung abgelaufen",
            "Integrationen → „Offiziell mit LinkedIn verbinden“ (ProspectOS über http://localhost:3000 öffnen).",
        )
    days = (connection.expires_at - now()).days
    detail = f"Verbunden, Token noch {days} Tage gültig. " + (
        "Posten erlaubt (w_member_social)." if can_post else "Posten nicht gewährt."
    )
    if not can_post or not flag:
        return _item(
            "linkedin",
            "LinkedIn",
            "yellow",
            "Verbunden, Posten noch nicht freigeschaltet",
            "LINKEDIN_PUBLISHING_APPROVED=true setzen"
            if can_post
            else "Produkt „Share on LinkedIn“ aktivieren und neu verbinden.",
            detail=detail,
        )
    return _item(
        "linkedin",
        "LinkedIn",
        "green",
        "Verbunden, Posten nach Freigabe möglich",
        "Probe-Post im Social Studio vorbereiten. Anfragen sendest du selbst in LinkedIn.",
        link="/social/studio",
        detail=detail,
    )


def llm(db, ws) -> dict:
    tested = _tested(db, ws, "openai")
    model = credentials.get("LLM_MODEL")
    if tested == "missing":
        return _item(
            "llm",
            "KI-Text (LLM)",
            "red",
            "API-Key, Modell oder Tokenpreise fehlen",
            "OpenAI-Key, Textmodell und Preise unter Integrationen eintragen.",
        )
    if tested == "connected":
        return _item(
            "llm",
            "KI-Text (LLM)",
            "green",
            f"Bestätigt ({model})",
            "Nichts zu tun. Kosten stehen unter Aufträge & Budget.",
            link="/operations",
        )
    return _item(
        "llm",
        "KI-Text (LLM)",
        "red" if tested == "error" else "yellow",
        "Letzter Test fehlgeschlagen" if tested == "error" else "Eingetragen, nicht getestet",
        "Integrationen → OpenAI → „Verbindung testen“.",
    )


def image(db, ws) -> dict:
    from app.experience import image_requirements

    req = image_requirements()
    if not req["configured"]:
        return _item(
            "image",
            "KI-Bilder",
            "red",
            "Fehlt: " + ", ".join(req["requirements"]),
            "Bildmodell unter Integrationen und IMAGE_MAX_COST_USD_CENTS in .env setzen.",
        )
    tested = _tested(db, ws, "openai")
    light = "green" if tested == "connected" else "yellow"
    return _item(
        "image",
        "KI-Bilder",
        light,
        f"Bereit ({credentials.get('IMAGE_MODEL')}, max. {req['max_cost_minor']} ct pro Bild)",
        "Bild zu einem Plan-Post erzeugen und prüfen."
        if light == "green"
        else "OpenAI-Verbindung testen.",
        link="/content/plan",
    )


def osm() -> dict:
    enabled = os.getenv("OSM_DISCOVERY_ENABLED", "false").lower() == "true"
    contact = credentials.get("OSM_CONTACT", "").strip()
    extract = os.getenv("OSM_EXTRACT_PATH", "").strip()
    has_extract = bool(extract and Path(extract).is_file())
    if not enabled:
        return _item(
            "osm",
            "OpenStreetMap",
            "red",
            "Firmensuche aus",
            "OSM_DISCOVERY_ENABLED=true in .env (infra/scripts/bootstrap-local.sh setzt es).",
        )
    if not contact or contact.endswith("example.invalid"):
        return _item(
            "osm",
            "OpenStreetMap",
            "yellow",
            "Kontaktangabe fehlt",
            "OSM_CONTACT (E-Mail oder URL) unter Integrationen eintragen; Pflicht der OSM-Richtlinie.",
        )
    if not has_extract:
        return _item(
            "osm",
            "OpenStreetMap",
            "yellow",
            "Kein lokaler Auszug, nutzt öffentliches Overpass",
            "infra/scripts/bootstrap-local.sh laden lassen (Geofabrik-Auszug), öffentliches Overpass lehnt Automatik oft ab.",
        )
    size = Path(extract).stat().st_size // (1024 * 1024)
    return _item(
        "osm",
        "OpenStreetMap",
        "green",
        f"Lokaler Geofabrik-Auszug ({size} MB)",
        "Nichts zu tun. Auszug gelegentlich aktualisieren.",
        link="/discover",
    )


def brave(db, ws) -> dict:
    tested = _tested(db, ws, "brave")
    if tested == "missing":
        return _item(
            "brave",
            "Brave Search",
            "red",
            "API-Key fehlt",
            "Brave-Search-API-Key unter Integrationen eintragen (für LinkedIn-Profil-Kandidaten).",
        )
    if tested == "connected":
        return _item(
            "brave",
            "Brave Search",
            "green",
            "Bestätigt",
            "Nichts zu tun. Treffer werden nicht gespeichert.",
            link="/today",
        )
    return _item(
        "brave",
        "Brave Search",
        "red" if tested == "error" else "yellow",
        "Letzter Test fehlgeschlagen" if tested == "error" else "Eingetragen, nicht getestet",
        "Integrationen → Brave Search → „Verbindung testen“.",
    )


def mailbox(db, ws) -> dict:
    from app.email_outreach import Mailbox

    count = db.scalar(select(func.count(Mailbox.id)).where(Mailbox.workspace_id == ws))
    if not count:
        return _item(
            "mailbox",
            "Mailbox (E-Mail)",
            "off",
            "noch nicht verbunden",
            "Erst wenn das Google-Konto freigeschaltet ist: unter Integrationen → Mailbox SMTP/IMAP "
            "mit App-Passwort eintragen. Bis dahin wird keine E-Mail versendet.",
        )
    return _item(
        "mailbox",
        "Mailbox (E-Mail)",
        "yellow",
        f"{count} Mailbox eingetragen",
        "Mailbox-Test unter Integrationen ausführen; Versand nur mit Rechtsgrundlage und Freigabe.",
    )


def writing_style(db, ws) -> dict:
    s = style.status(db, ws)
    if s["state"] != "ok":
        return _item(
            "style",
            "Schreibstil",
            "yellow",
            "Keine eigenen Texte" if s["state"] == "missing" else "Datei ohne Texte",
            "3 bis 5 eigene Texte in data/private/meine-texte.md einfügen, dann übernehmen.",
            link="/content/plan",
        )
    return _item(
        "style",
        "Schreibstil",
        "green" if s["in_sync"] else "yellow",
        f"{s['samples']} eigene Texte",
        "Nichts zu tun." if s["in_sync"] else "Datei geändert: „Aus Datei übernehmen“ klicken.",
        link="/content/plan",
    )


def setup_check(db, ws) -> dict:
    if credentials.is_demo(db, ws):
        items = [
            _item(
                "workspace",
                "Workspace",
                "off",
                "Demo-Workspace",
                "Für echte Arbeit den Workspace „CleanStar“ wählen.",
                link="/overview",
            )
        ]
        return {"items": items, "summary": {"green": 0, "yellow": 0, "red": 0, "off": 1}}
    items = [
        linkedin(db, ws),
        llm(db, ws),
        image(db, ws),
        osm(),
        brave(db, ws),
        mailbox(db, ws),
        writing_style(db, ws),
    ]
    summary = {k: sum(i["light"] == k for i in items) for k in ("green", "yellow", "red", "off")}
    return {"items": items, "summary": summary}


def register_setup_routes(app, db_session, scope):
    @app.get("/v1/workspaces/{ws}/setup-check")
    def check(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return setup_check(db, ws)
