"""Shared startup invariants for both HTTP and worker processes."""

import os

from sqlalchemy import text

from app.db import SessionLocal
from app.identity import auth_settings


def validate_runtime():
    auth_settings()
    if os.getenv("APP_ENV") == "production" and os.getenv("DATABASE_ADMIN_URL"):
        raise RuntimeError("Runtime must not receive database administrator credentials")
    with SessionLocal() as db:
        role = db.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")
        ).one()
        owns = db.scalar(
            text(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner=current_user"
            )
        )
        if role.rolsuper or role.rolbypassrls or owns:
            raise RuntimeError("Runtime DB role must be a non-owner without SUPERUSER/BYPASSRLS")
