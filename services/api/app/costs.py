"""Actual AI costs: price table, cost from the provider's usage field, ledger correction.

Money is kept in micro-USD (1 USD = 1_000_000) so a call that costs a fraction of a cent
is booked as such and never rounded up to a whole cent. A reservation (the cost cap) is
only held while a call runs; afterwards it is replaced by the actual cost. When the
actual cost cannot be known (no usage field, unknown outcome, old booking) the booked
value is flagged `estimated`.

Prices come from the environment / workspace credentials, never from the provider:
  LLM_INPUT_USD_PER_MILLION, LLM_OUTPUT_USD_PER_MILLION              (text)
  IMAGE_TEXT_INPUT_USD_PER_MILLION, IMAGE_IMAGE_INPUT_USD_PER_MILLION,
  IMAGE_OUTPUT_USD_PER_MILLION                                        (images)

CLI: `python -m app.costs` shows the correction, `python -m app.costs --apply` books it.
"""

import math
import sys
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from types import SimpleNamespace

from sqlalchemy import select

from app import credentials
from app.db import now

MICRO_PER_MINOR = 10_000

# Rough output-token counts per image when the provider returned no usage (only used to
# correct old bookings; flagged as estimated). Square 1024 px; other formats ~1.5x.
# "auto" = what the live check on 2026-11-07 returned without a quality parameter
# (quality "low", 196 output tokens).
IMAGE_TOKEN_ESTIMATE = {"low": 196, "medium": 439, "high": 1756, "auto": 196}


def to_minor(micro: int) -> int:
    return math.ceil(max(0, micro) / MICRO_PER_MINOR)


def _price(name: str) -> Decimal | None:
    raw = (credentials.get(name) or "").strip()
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value.is_finite() and value >= 0 else None


def text_prices() -> tuple[Decimal, Decimal] | None:
    i, o = _price("LLM_INPUT_USD_PER_MILLION"), _price("LLM_OUTPUT_USD_PER_MILLION")
    return (i, o) if i is not None and o is not None else None


def image_prices() -> dict | None:
    text_in = _price("IMAGE_TEXT_INPUT_USD_PER_MILLION")
    out = _price("IMAGE_OUTPUT_USD_PER_MILLION")
    if text_in is None or out is None:
        return None
    image_in = _price("IMAGE_IMAGE_INPUT_USD_PER_MILLION")
    return {"text_input": text_in, "image_input": image_in or text_in, "output": out}


def _micro(value: Decimal) -> int:
    # tokens * USD per million tokens = micro-USD
    return int(value.to_integral_value(rounding=ROUND_CEILING))


def text_cost_micro(input_tokens: int, output_tokens: int) -> int | None:
    prices = text_prices()
    if not prices:
        return None
    return _micro(Decimal(input_tokens) * prices[0] + Decimal(output_tokens) * prices[1])


def _int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def image_usage(data: dict) -> dict | None:
    """Normalise the `usage` block of an Images API response (None if absent)."""
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict) or "output_tokens" not in usage:
        return None
    details = usage.get("input_tokens_details") or {}
    total_in = _int(usage.get("input_tokens"))
    image_in = _int(details.get("image_tokens")) if isinstance(details, dict) else 0
    text_in = _int(details.get("text_tokens")) if isinstance(details, dict) else 0
    if not text_in and not image_in:
        text_in = total_in
    return {
        "input_tokens": total_in,
        "text_input_tokens": text_in,
        "image_input_tokens": image_in,
        "output_tokens": _int(usage.get("output_tokens")),
        "size": data.get("size") if isinstance(data.get("size"), str) else "",
        "quality": data.get("quality") if isinstance(data.get("quality"), str) else "",
    }


def image_cost_micro(usage: dict | None) -> int | None:
    prices = image_prices()
    if not usage or not prices:
        return None
    return _micro(
        Decimal(usage["text_input_tokens"]) * prices["text_input"]
        + Decimal(usage["image_input_tokens"]) * prices["image_input"]
        + Decimal(usage["output_tokens"]) * prices["output"]
    )


def image_settlement(usage: dict | None, reservation_minor: int, model: str):
    """Usage object for settle_ai: actual cost if known, else the reservation (estimated)."""
    cost = image_cost_micro(usage)
    estimated = cost is None
    return SimpleNamespace(
        input_tokens=(usage or {}).get("input_tokens", 0),
        output_tokens=(usage or {}).get("output_tokens", 0),
        estimated_cost_microunits=reservation_minor * MICRO_PER_MINOR if estimated else cost,
        estimated=estimated,
        model=model,
        details={"usage": usage or None}
        | (
            {"reason": "Antwort ohne usage-Feld" if not usage else "Bildpreise fehlen in .env"}
            if estimated
            else {}
        ),
    )


def estimate_image_micro(aspect_ratio: str = "square", quality: str = "auto") -> int | None:
    prices = image_prices()
    if not prices:
        return None
    tokens = IMAGE_TOKEN_ESTIMATE.get(quality or "auto", IMAGE_TOKEN_ESTIMATE["auto"])
    if aspect_ratio in ("landscape", "portrait"):
        tokens = math.ceil(tokens * 1.5)
    return _micro(Decimal(tokens) * prices["output"])


# --- ledger correction -------------------------------------------------------------


def corrections(db, ws) -> list[dict]:
    """What each booked event should cost given the stored tokens and the price table."""
    from app.platform_models import Job, UsageEvent

    rows = []
    for event in db.scalars(
        select(UsageEvent).where(UsageEvent.workspace_id == ws).order_by(UsageEvent.created_at)
    ):
        job = db.get(Job, event.job_id)
        unknown_outcome = bool(job and job.status in ("ambiguous",))
        new, estimated, why = event.cost_micro, event.estimated, ""
        if unknown_outcome:
            why = "Ausgang unbekannt, Reservierung bleibt"
            estimated = True
        elif event.provider == "openai_images":
            usage = (event.details or {}).get("usage")
            exact = image_cost_micro(usage) if usage else None
            if exact is not None:
                new, estimated, why = exact, False, "aus gespeicherter usage"
            else:
                guess = estimate_image_micro((job.payload if job else {}).get("aspect_ratio"))
                if guess is not None and event.estimated:
                    new, estimated = guess, True
                    why = "keine usage gespeichert, Schätzung aus Preistabelle"
        elif event.input_tokens or event.output_tokens:
            exact = text_cost_micro(event.input_tokens, event.output_tokens)
            if exact is not None:
                new, estimated, why = exact, False, "aus gespeicherten Tokens"
        rows.append(
            {
                "event": event,
                "old_micro": event.cost_micro,
                "new_micro": new,
                "estimated": estimated,
                "why": why,
            }
        )
    return rows


def recalc_workspace(db, ws, apply: bool = False) -> dict:
    from app.jobs import usage_account

    rows = corrections(db, ws)
    if apply:
        for r in rows:
            e = r["event"]
            if (e.cost_micro, e.estimated) != (r["new_micro"], r["estimated"]):
                e.details = {**(e.details or {}), "corrected_from_micro": e.cost_micro}
            e.cost_micro, e.estimated = r["new_micro"], r["estimated"]
            e.cost_minor = to_minor(r["new_micro"])
        account = usage_account(db, ws)
        period = now().strftime("%Y-%m")
        spent = sum(
            r["new_micro"] for r in rows if r["event"].created_at.strftime("%Y-%m") == period
        )
        if account.period == period:
            account.ai_spent_micro = spent
            account.ai_spent_minor = to_minor(spent)
        db.flush()
    return {
        "events": len(rows),
        "old_micro": sum(r["old_micro"] for r in rows),
        "new_micro": sum(r["new_micro"] for r in rows),
        "estimated": sum(r["estimated"] for r in rows),
        "rows": [
            {
                "job_id": r["event"].job_id,
                "provider": r["event"].provider,
                "tokens": [r["event"].input_tokens, r["event"].output_tokens],
                "old_usd": r["old_micro"] / 1e6,
                "new_usd": r["new_micro"] / 1e6,
                "estimated": r["estimated"],
                "why": r["why"],
            }
            for r in rows
        ],
    }


def summary(account, db, ws) -> dict:
    """Usage numbers for the UI: actual spend vs. held reservations, estimated share."""
    from sqlalchemy import func

    from app.platform_models import UsageEvent

    period = account.period if account else now().strftime("%Y-%m")
    start = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    estimated = int(
        db.scalar(
            select(func.coalesce(func.sum(UsageEvent.cost_micro), 0)).where(
                UsageEvent.workspace_id == ws,
                UsageEvent.estimated.is_(True),
                UsageEvent.created_at >= start,
            )
        )
        or 0
    )
    spent = int(account.ai_spent_micro or 0) if account else 0
    budget = account.ai_budget_minor if account else 500
    reserved = account.ai_reserved_minor if account else 0
    return {
        "period": period,
        "currency": "USD",
        "spent_usd": spent / 1e6,
        "spent_estimated_usd": estimated / 1e6,
        "reserved_usd": reserved / 100,
        "budget_usd": budget / 100,
        "available_usd": max(0, budget * MICRO_PER_MINOR - spent - reserved * MICRO_PER_MINOR)
        / 1e6,
    }


def main(argv: list[str]) -> int:
    from app.db import SessionLocal
    from app.jobs import tenant
    from app.models import Workspace

    apply = "--apply" in argv
    with SessionLocal() as db, db.begin():
        workspaces = list(db.scalars(select(Workspace)))
        for ws in workspaces:
            tenant(db, ws.id)
            token = credentials.bind(ws.id)
            try:
                result = recalc_workspace(db, ws.id, apply=apply)
            finally:
                credentials.unbind(token)
            if not result["events"]:
                continue
            print(
                f"{ws.name}: {result['events']} Buchungen, "
                f"vorher {result['old_micro'] / 1e6:.4f} USD, "
                f"nachher {result['new_micro'] / 1e6:.4f} USD, "
                f"davon {result['estimated']} geschätzt"
            )
            for r in result["rows"]:
                print(
                    f"  {r['provider']:<18} tokens={r['tokens']} "
                    f"{r['old_usd']:.4f} -> {r['new_usd']:.4f} USD"
                    f"{' (geschätzt)' if r['estimated'] else ''} {r['why']}"
                )
        if not apply:
            print("Nur Vorschau. Mit --apply buchen.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
