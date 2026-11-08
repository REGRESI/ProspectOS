import os

from sqlalchemy import create_engine

from alembic import context
from app import (
    experience,  # noqa: F401
    flows,  # noqa: F401
    identity,  # noqa: F401
    journeys,  # noqa: F401
    letters,  # noqa: F401
    linkedin_channel,  # noqa: F401
    multichannel,  # noqa: F401
    reactions,  # noqa: F401
    sales_agent,  # noqa: F401
    studio,  # noqa: F401
    team_mode,  # noqa: F401
)
from app.models import Base

url = os.getenv(
    "DATABASE_ADMIN_URL", "postgresql+psycopg://prospectos:prospectos_dev@127.0.0.1:5432/prospectos"
)
with create_engine(url).connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
