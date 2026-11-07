"""Synthetic screenshot data for the isolated E2E stack only (docs/design screenshots).

Every company and person is invented ("Fiktiv", "Beispiel", example.test domains), so
screenshots can live in Git without real contacts. Refuses to run outside the E2E stack.

  docker compose -f docker-compose.e2e.yml -p prospectos-e2e exec api python -m app.design_fixture
"""

import os
import sys
from datetime import timedelta

from sqlalchemy import select, text

from app.db import SessionLocal, now
from app.models import Company, Contact, Membership, Post, User, Workspace

COMPANIES = [
    # name, osm category, location, website (example.test = fictional), with contact
    (
        "Zahnarztpraxis Dr. Fiktiv",
        "amenity=dentist",
        "Offenburg",
        "zahnarzt-fiktiv.example.test",
        True,
    ),
    (
        "Steuerberatung Beispiel & Partner",
        "office=tax_advisor",
        "Offenburg",
        "stb-beispiel.example.test",
        True,
    ),
    ("Kanzlei Muster Rechtsanwälte", "office=lawyer", "Lahr", "kanzlei-muster.example.test", True),
    (
        "Werbeagentur Fiktiv Blau",
        "office=advertising_agency",
        "Kehl",
        "fiktiv-blau.example.test",
        True,
    ),
    (
        "Hausverwaltung Beispielhof",
        "office=property_management",
        "Achern",
        "beispielhof.example.test",
        True,
    ),
    (
        "Kita Sonnenfiktiv",
        "amenity=kindergarten",
        "Offenburg",
        "kita-sonnenfiktiv.example.test",
        True,
    ),
    (
        "Physiotherapie Beispielwerk",
        "healthcare=physiotherapist",
        "Oberkirch",
        "physio-beispielwerk.example.test",
        True,
    ),
    (
        "Architekturbüro Fiktivraum",
        "office=architect",
        "Gengenbach",
        "fiktivraum.example.test",
        True,
    ),
    (
        "Praxis für Ergotherapie Muster",
        "healthcare=occupational_therapist",
        "Lahr",
        "ergo-muster.example.test",
        False,
    ),
    (
        "Notariat Beispielstadt",
        "office=notary",
        "Offenburg",
        "notariat-beispiel.example.test",
        False,
    ),
    ("IT-Service Fiktiv GmbH", "office=it", "Kehl", "it-fiktiv.example.test", False),
    ("Versicherungsbüro Muster", "office=insurance", "Achern", "", False),
    ("Immobilien Beispiel Makler", "office=estate_agent", "Offenburg", "", False),
    (
        "Kinderarztpraxis Fiktiv",
        "amenity=doctors",
        "Haslach",
        "kinderarzt-fiktiv.example.test",
        False,
    ),
    ("Agentur Musterwerk", "office=company", "Offenburg", "andere-domain.example.test", False),
    ("Autohaus Fiktiv", "shop=car", "Offenburg", "autohaus-fiktiv.example.test", False),
    ("Maschinenbau Beispiel AG", "office=company", "Lahr", "", False),
]
PEOPLE = [
    ("Mara", "Fiktiv", "Praxisinhaberin"),
    ("Jonas", "Beispiel", "Steuerberater, Partner"),
    ("Nora", "Muster", "Rechtsanwältin"),
    ("Emil", "Fiktiv", "Geschäftsführer"),
    ("Lina", "Beispiel", "Verwalterin"),
    ("Paula", "Muster", "Kita-Leitung"),
    ("Felix", "Beispiel", "Inhaber"),
    ("Clara", "Fiktiv", "Büroleitung"),
]
POSTS = [
    ("Alltag", "Warum ein sauberes Wartezimmer Vertrauen schafft"),
    ("Region", "Drei Dinge, die Büros in der Ortenau gerade beschäftigen"),
    ("Tipps", "So bleibt die Teeküche ohne Aufwand ordentlich"),
    ("Alltag", "Ein Morgen mit unserem Team in Offenburg"),
    ("Region", "Was Kitas bei der Reinigung wirklich brauchen"),
    ("Tipps", "Checkliste: Reinigung in der Kanzlei vor dem Mandantentermin"),
]


def main() -> int:
    if os.getenv("E2E_STACK") != "true":
        print("Nur im isolierten E2E-Stack erlaubt.", file=sys.stderr)
        return 1
    from app.ranking import TEMPLATES
    from app.today import build_queue, get_settings, sender_for

    with SessionLocal() as db, db.begin():
        ws = db.scalar(select(Workspace).where(Workspace.kind == "production"))
        user = db.scalar(select(User).where(User.email == "demo@prospectos.local"))
        db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws.id})
        if db.scalar(select(Company.id).where(Company.workspace_id == ws.id)):
            print("Daten schon vorhanden.")
            return 0
        assert db.get(Membership, (ws.id, user.id))
        from app.journeys import ICPProfile, IntelligenceProfileInput

        template = TEMPLATES["office_cleaning_ortenau"]
        data = IntelligenceProfileInput.model_validate(
            {"name": template["name"], **template["profile"]}
        )
        db.add(ICPProfile(workspace_id=ws.id, name=data.name, profile=data.model_dump()))
        made = []
        for i, (name, category, location, site, with_contact) in enumerate(COMPANIES):
            company = Company(
                workspace_id=ws.id,
                name=name,
                identity=f"design-fixture-{i}",
                location=location,
                industry="",
                website=f"https://{site}" if site else None,
                source="osm",
                provenance={"osm_category": category, "synthetic": True},
                created_at=now() - timedelta(days=i % 5),
            )
            db.add(company)
            db.flush()
            made.append((company, with_contact))
        for (company, _), person in zip([m for m in made if m[1]], PEOPLE, strict=False):
            first, last, role = person
            db.add(
                Contact(
                    workspace_id=ws.id,
                    company_id=company.id,
                    first_name=first,
                    last_name=last,
                    job_title=role,
                    location=company.location,
                    source="synthetic_demo",
                )
            )
        settings = get_settings(db, ws.id)
        db.add(settings)
        settings.daily_limit = 7
        settings.sender_name = "Alex"
        settings.sender_company = "CleanStar"
        db.flush()
        build_queue(db, ws.id, user.id, sender_for(db, ws.id))
        from app.content_plan import ContentPlan
        from app.db import uid

        items = []
        for i, (pillar, topic) in enumerate(POSTS):
            post = Post(
                workspace_id=ws.id,
                author_id=user.id,
                caption=f"{topic}.\n\nEin kurzer Beispieltext für den Screenshot. Fiktiv.",
                state=["approved", "needs_review", "needs_review", "draft", "draft", "draft"][i],
                studio_context={
                    "source": "content_plan",
                    "pillar": pillar,
                    "topic": topic,
                    "variants": [
                        f"{topic}. Variante A, fiktiver Beispieltext.",
                        f"{topic}. Variante B, fiktiver Beispieltext.",
                    ],
                    "image_idea": "Helles, aufgeräumtes Büro",
                    "synthetic": True,
                },
            )
            db.add(post)
            db.flush()
            items.append(
                {
                    "id": uid(),
                    "week": 1 + i // 3,
                    "day": ["Mo", "Mi", "Fr"][i % 3],
                    "pillar": pillar,
                    "topic": topic,
                    "hook": "Ein Satz, der neugierig macht",
                    "format": "Text mit Bild",
                    "status": "drafted" if i < 4 else "planned",
                    "post_id": post.id if i < 4 else None,
                }
            )
        db.add(
            ContentPlan(
                workspace_id=ws.id,
                name="CleanStar · 2 Wochen",
                goal="Sichtbarkeit bei Büro- und Praxisleitungen",
                audience="Büro- und Praxisleitungen in der Ortenau",
                pillars=["Alltag", "Region", "Tipps"],
                cadence=3,
                weeks=2,
                status="ready",
                storyline="Saubere Räume als ruhiger Hintergrund für gute Arbeit.",
                items=items,
                created_by=user.id,
            )
        )
    print("Synthetische Screenshot-Daten angelegt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
