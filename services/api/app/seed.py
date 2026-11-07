"""Idempotent synthetic local fixtures. Never accepts real customer datasets.

Also makes sure the production workspace "CleanStar" exists and is the default after
login. If an older install did real work inside "CleanStar · Demo" (real OSM companies,
credentials, LinkedIn connection), that workspace is promoted to production in place
(synthetic rows removed) and a fresh, purely synthetic demo workspace is created.
"""

import os

from argon2 import PasswordHasher
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.db import now
from app.models import Audit, Company, Contact, Deal, Membership, Post, User, Workspace

SYNTHETIC_CONTACT_REFS = (
    "deals",
    "campaign_enrollments",
    "campaign_draft_links",
    "message_drafts",
    "consents",
    "notes",
    "suppressions",
    "tasks",
    "lead_profiles",
    "manual_outreach_activities",
    "linkedin_sim_accounts",
    "linkedin_actions",
    "outreach_queue_items",
    "email_messages",
)


def ensure_production(db, user) -> str:
    """Return the production CleanStar workspace id, creating or promoting it."""
    prod = db.scalar(select(Workspace).where(Workspace.slug == "cleanstar"))
    if prod:
        prod.kind = "production"
        return "kept"
    old = db.scalar(select(Workspace).where(Workspace.slug == "cleanstar-demo"))
    real = (
        db.scalar(
            select(Company.id).where(
                Company.workspace_id == old.id, Company.source != "synthetic_demo"
            )
        )
        if old
        else None
    )
    if old and real:
        ws = old.id
        params = {"ws": ws}
        synthetic = "SELECT id FROM contacts WHERE workspace_id = :ws AND source = 'synthetic_demo'"
        for table in SYNTHETIC_CONTACT_REFS:
            db.execute(
                text(
                    f"DELETE FROM {table} WHERE workspace_id = :ws AND contact_id IN ({synthetic})"
                ),
                params,
            )
        db.execute(
            text("DELETE FROM contacts WHERE workspace_id = :ws AND source = 'synthetic_demo'"),
            params,
        )
        db.execute(
            text(
                "DELETE FROM outreach_queue_items WHERE workspace_id = :ws AND company_id IN "
                "(SELECT id FROM companies WHERE workspace_id = :ws AND source = 'synthetic_demo')"
            ),
            params,
        )
        db.execute(
            text("DELETE FROM companies WHERE workspace_id = :ws AND source = 'synthetic_demo'"),
            params,
        )
        demo_posts = (
            "SELECT id FROM social_posts WHERE workspace_id = :ws AND state = 'draft' "
            "AND caption LIKE '%[Demo-Entwurf]%'"
        )
        db.execute(
            text(
                f"DELETE FROM post_revisions WHERE workspace_id = :ws AND post_id IN ({demo_posts})"
            ),
            params,
        )
        db.execute(text(f"DELETE FROM social_posts WHERE id IN ({demo_posts})"), params)
        old.name, old.slug, old.kind = "CleanStar", "cleanstar", "production"
        db.add(
            Audit(
                workspace_id=ws,
                actor_id=user.id,
                kind="workspace_promoted",
                description="Arbeits-Workspace zu „CleanStar“ (produktiv) gemacht; synthetische Demo-Daten entfernt",
                created_at=now(),
            )
        )
        db.flush()
        return "promoted"
    ws = Workspace(name="CleanStar", slug="cleanstar", kind="production")
    db.add(ws)
    db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=user.id, role="owner"))
    return "created"


def main():
    if os.getenv("APP_ENV", "development") not in ("development", "test"):
        raise RuntimeError("Demo seed is development/test only")
    admin = os.getenv(
        "DATABASE_ADMIN_URL",
        "postgresql+psycopg://prospectos:prospectos_dev@127.0.0.1:5432/prospectos",
    )
    with Session(create_engine(admin)) as db, db.begin():
        user = db.scalar(select(User).where(User.email == "demo@prospectos.local"))
        if user is None:
            user = User(
                email="demo@prospectos.local",
                name="Alex Demo",
                password_hash=PasswordHasher().hash(
                    os.getenv("DEMO_PASSWORD", "ProspectDemo!2026")
                ),
            )
            db.add(user)
            db.flush()
        production = ensure_production(db, user)
        # One demo workspace only, named "Demo" (opened via the Demo switch, never default).
        for slug, name in [("cleanstar-demo", "Demo")]:
            existing = db.scalar(select(Workspace).where(Workspace.slug == slug))
            if existing:
                existing.name, existing.kind = name, "demo"
                continue
            ws = Workspace(name=name, slug=slug, kind="demo")
            db.add(ws)
            db.flush()
            db.add(Membership(workspace_id=ws.id, user_id=user.id, role="owner"))
            if slug != "cleanstar-demo":
                continue
            people = [
                ("Mara", "Beispiel", "Geschäftsführerin", "Offenburg", "Büro"),
                ("Jonas", "Demo", "Office Manager", "Offenburg", "Dienstleistung"),
                ("Nora", "Muster", "Facility Managerin", "Kehl", ""),
                ("Emil", "Test", "Einkauf", "Lahr", ""),
                ("Lina", "Beispiel", "Inhaberin", "Ortenau", "Büro"),
                ("Felix", "Demo", "Teamleitung", "Freiburg", ""),
            ]
            for i, (first, last, role, location, industry) in enumerate(people):
                company = Company(
                    workspace_id=ws.id,
                    name=f"Demo {['Nordlicht Büro', 'Freiraum Studio', 'Werkraum', 'Klarblick', 'Raum & Form', 'Westwerk'][i]}",
                    identity=f"seed-{i}",
                    location=location,
                    industry=industry,
                    source="synthetic_demo",
                )
                db.add(company)
                db.flush()
                c = Contact(
                    workspace_id=ws.id,
                    company_id=company.id,
                    first_name=first,
                    last_name=last,
                    job_title=role,
                    location=location,
                    source="synthetic_demo",
                    status="qualified" if i < 2 else "new",
                )
                db.add(c)
                db.flush()
                if i < 2:
                    db.add(
                        Deal(
                            workspace_id=ws.id,
                            contact_id=c.id,
                            title=f"Demo: Büroreinigung · {company.name}",
                            amount=(i + 1) * 125000,
                            stage="qualified" if i == 0 else "proposal",
                        )
                    )
            db.add(
                Post(
                    workspace_id=ws.id,
                    author_id=user.id,
                    caption="Ein guter Arbeitstag beginnt mit einer Umgebung, in der wir uns wohlfühlen.\n\nWas macht für Ihr Team einen angenehmen Arbeitsplatz aus?\n\n[Demo-Entwurf]",
                    state="draft",
                )
            )
            db.add(
                Audit(
                    workspace_id=ws.id,
                    actor_id=user.id,
                    kind="demo_seeded",
                    description="Synthetische Demo-Daten angelegt; keine realen Kontakte oder Geschäftsergebnisse",
                    created_at=now(),
                )
            )
    print(f"Production workspace CleanStar: {production}")
    print("Demo seed ready (idempotent). Local account: demo@prospectos.local")


if __name__ == "__main__":
    main()
