"""Server-side resource limits; billing status never invents paid product capabilities."""

import os

from fastapi import HTTPException
from sqlalchemy import func, select, text

from app.models import Contact
from app.platform_models import Asset, BillingAccount


def limits(db, ws):
    account = db.scalar(select(BillingAccount).where(BillingAccount.workspace_id == ws))
    subscribed = bool(
        account and account.status in ("active", "trialing") and account.plan == "test_subscription"
    )
    prefix = "SUBSCRIPTION" if subscribed else "TRIAL"
    contacts = int(os.getenv(prefix + "_MAX_CONTACTS", "100000" if subscribed else "10000"))
    assets = int(os.getenv(prefix + "_MAX_ASSETS", "1000" if subscribed else "100"))
    if not 1 <= contacts <= 1000000 or not 1 <= assets <= 10000:
        raise RuntimeError("Invalid resource limit configuration")
    return {"max_contacts": contacts, "max_assets": assets, "ai_budget_managed_separately": True}


def remaining(db, ws, resource, require_slot=True):
    if resource not in ("contacts", "assets"):
        raise ValueError("Unknown resource")
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": "limit:" + resource + ":" + ws},
    )
    model = Contact if resource == "contacts" else Asset
    count = db.scalar(select(func.count()).select_from(model).where(model.workspace_id == ws))
    capacity = limits(db, ws)["max_" + resource] - count
    if capacity <= 0 and require_slot:
        raise HTTPException(402, "Workspace " + resource + " limit reached.")
    return capacity
