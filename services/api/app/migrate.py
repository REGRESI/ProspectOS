"""Local-only role provisioning followed by versioned Alembic migrations."""

import os
import subprocess

from sqlalchemy import create_engine, text


def main():
    if os.getenv("APP_ENV", "development") not in ("development", "test"):
        raise RuntimeError("Local role provisioning is disabled outside development/test")
    admin = os.getenv(
        "DATABASE_ADMIN_URL",
        "postgresql+psycopg://prospectos:prospectos_dev@127.0.0.1:5432/prospectos",
    )
    password = os.getenv("DB_APP_PASSWORD", "prospectos_app_dev")
    engine = create_engine(admin)
    # Values are bound through PostgreSQL format(), never interpolated into SQL.
    with engine.begin() as db:
        exists = db.scalar(text("SELECT 1 FROM pg_roles WHERE rolname='prospectos_app'"))
        if not exists:
            statement = db.scalar(
                text(
                    "SELECT format('CREATE ROLE prospectos_app LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS', CAST(:p AS text))"
                ),
                {"p": password},
            )
            db.execute(text(statement))
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    with engine.begin() as db:
        db.execute(text("GRANT USAGE ON SCHEMA public TO prospectos_app"))
        db.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO prospectos_app"
            )
        )
        db.execute(text("REVOKE UPDATE, DELETE ON audit_events FROM prospectos_app"))
        db.execute(text("REVOKE ALL ON alembic_version FROM prospectos_app"))
    print("Schema upgraded; application role uses RLS and cannot mutate audit history.")


if __name__ == "__main__":
    main()
