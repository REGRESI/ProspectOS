"""Validate migrations and tests in a disposable local database.
Run: cd services/api && uv run python ../../infra/scripts/validate_database.py
Requires a development admin URL with CREATE DATABASE permission.
"""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    if os.getenv("APP_ENV", "development") not in ("development", "test"):
        raise RuntimeError("Disposable validation is development/test only")
    admin = make_url(
        os.getenv(
            "DATABASE_ADMIN_URL",
            "postgresql+psycopg://prospectos:prospectos_dev@127.0.0.1:5432/prospectos",
        )
    )
    runtime = make_url(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://prospectos_app:prospectos_app_dev@127.0.0.1:5432/prospectos",
        )
    )
    name = "prospectos_validation_" + uuid4().hex[:10]
    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text("CREATE DATABASE " + name))
    env = os.environ.copy()
    env.update(
        DATABASE_ADMIN_URL=admin.set(database=name).render_as_string(hide_password=False),
        DATABASE_URL=runtime.set(database=name).render_as_string(hide_password=False),
        APP_ENV="test",
    )
    cwd = Path(__file__).resolve().parents[2] / "services" / "api"
    try:
        commands = [
            [sys.executable, "-m", "app.migrate"],
            ["alembic", "downgrade", "base"],
            [sys.executable, "-m", "app.migrate"],
            [sys.executable, "-m", "app.seed"],
            [sys.executable, "-m", "app.seed"],
            ["pytest", "-q", *sys.argv[1:]],
        ]
        for command in commands:
            subprocess.run(command, env=env, cwd=cwd, check=True)
    finally:
        with engine.connect() as connection:
            connection.execute(text("DROP DATABASE " + name + " WITH (FORCE)"))
        engine.dispose()


if __name__ == "__main__":
    main()
