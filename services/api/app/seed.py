"""Idempotent synthetic local fixtures. Never accepts real customer datasets."""

import os

from argon2 import PasswordHasher
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import now
from app.models import Audit, Company, Contact, Deal, Membership, Post, User, Workspace


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
        for slug, name in [
            ("cleanstar-demo", "CleanStar · Demo"),
            ("studio-demo", "Studio · Demo"),
        ]:
            if db.scalar(select(Workspace).where(Workspace.slug == slug)):
                continue
            ws = Workspace(name=name, slug=slug)
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
    print("Demo seed ready (idempotent). Local account: demo@prospectos.local")


if __name__ == "__main__":
    main()
