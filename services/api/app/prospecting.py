"""Deterministic deduplication and company-level ICP fit for discovery results.

Every decision carries a human-readable reason. Nothing is inferred that the source did
not report: missing size/need data stays "unknown" and is counted against the score.
"""

from urllib.parse import urlsplit

from sqlalchemy import select

from app.models import Company
from app.providers.osm import normalize_name


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlsplit(url if "://" in url else "https://" + url).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def place_key(location: str | None) -> str:
    return " ".join((location or "").casefold().split())


class DuplicateIndex:
    """Existing workspace companies keyed by provider identity, domain and name+place."""

    def __init__(self, db, ws):
        rows = db.execute(
            select(Company.id, Company.name, Company.identity, Company.website, Company.location)
            .where(Company.workspace_id == ws)
            .limit(50000)
        ).all()
        self.identity, self.domain, self.name_place = {}, {}, {}
        for row in rows:
            ref = {"company_id": row.id, "name": row.name}
            self.identity[row.identity] = ref
            if domain := domain_of(row.website):
                self.domain.setdefault(domain, ref)
            name = normalize_name(row.name)
            if name:
                self.name_place.setdefault((name, place_key(row.location)), ref)

    def match(self, identity: str, website: str | None, name: str, location: str | None):
        if identity in self.identity:
            return self.identity[identity] | {
                "reason": "identity",
                "explanation": "Gleiche Anbieter-ID bereits importiert.",
            }
        if (domain := domain_of(website)) and domain in self.domain:
            return self.domain[domain] | {
                "reason": "domain",
                "explanation": f"Gleiche Website-Domain ({domain}) wie ein bestehendes Unternehmen.",
            }
        key = (normalize_name(name), place_key(location))
        if key[0] and key[1] and key in self.name_place:
            return self.name_place[key] | {
                "reason": "name_location",
                "explanation": "Gleicher normalisierter Firmenname am gleichen Ort (Rechtsform ignoriert).",
            }
        return None


def _matches(value: str, terms: list[str]) -> bool:
    value = (value or "").casefold()
    return bool(value) and any(t.casefold() in value or value in t.casefold() for t in terms if t)


def company_fit_score(row: dict, profile: dict, criteria: dict | None = None) -> dict:
    """Score a company record. Role is not applicable to a company without a contact
    person and is excluded from the denominator; the result is normalized to 0–100 and
    the exclusion is disclosed. Unknown size/needs remain in the denominator (score 0)."""
    criteria = criteria or {}
    weights = profile.get("weights", {})
    factors, missing = [], []

    # Region: within the confirmed search radius, or textual ICP location match.
    w = weights.get("location", 0)
    distance, radius = row.get("distance_km"), criteria.get("radius_km")
    location = row.get("location") or ""
    if isinstance(distance, (int, float)) and radius:
        inside = distance <= radius
        factors.append(
            {
                "name": "Region",
                "points": w if inside else 0,
                "max_points": w,
                "reason": f"{distance:.1f} km vom Suchzentrum (Radius {radius} km)"
                + (f", Ort: {location}" if location else ""),
                "evidence": row.get("source_url"),
            }
        )
    elif location:
        hit = _matches(location, profile.get("locations", []))
        factors.append(
            {
                "name": "Region",
                "points": w if hit else 0,
                "max_points": w,
                "reason": ("Übereinstimmung mit ICP-Region: " if hit else "Keine ICP-Region: ")
                + location,
                "evidence": row.get("source_url"),
            }
        )
    else:
        missing.append("Region")
        factors.append(
            {
                "name": "Region",
                "points": 0,
                "max_points": w,
                "reason": "Keine Ortsangabe – unbekannt",
            }
        )

    w = weights.get("industry", 0)
    industry = row.get("industry") or ""
    category = row.get("osm_category") or ""
    terms = profile.get("industries", []) + criteria.get("industries", [])
    if industry or category:
        hit = _matches(industry, terms) or _matches(category, terms)
        factors.append(
            {
                "name": "Branche",
                "points": w if hit else 0,
                "max_points": w,
                "reason": ("Branche passt: " if hit else "Branche passt nicht zum ICP: ")
                + " / ".join(x for x in (industry, category) if x),
                "evidence": row.get("source_url"),
            }
        )
    else:
        missing.append("Branche")
        factors.append(
            {
                "name": "Branche",
                "points": 0,
                "max_points": w,
                "reason": "Keine Branchenangabe – unbekannt",
            }
        )

    w = weights.get("size", 0)
    count = row.get("employee_count")
    if w:
        known = type(count) is int and count >= 0
        fit = (
            known
            and (profile.get("min_employees") is None or count >= profile["min_employees"])
            and (profile.get("max_employees") is None or count <= profile["max_employees"])
        )
        if not known:
            missing.append("Unternehmensgröße")
        factors.append(
            {
                "name": "Unternehmensgröße",
                "points": w if fit else 0,
                "max_points": w,
                "reason": f"Anbieterangabe: {count} Mitarbeitende"
                if known
                else "Quelle liefert keine Größe – unbekannt",
            }
        )
    elif type(count) is not int:
        missing.append("Unternehmensgröße")

    w = weights.get("needs", 0)
    if w:
        missing.append("Belegter Bedarf")
        factors.append(
            {
                "name": "Belegter Bedarf",
                "points": 0,
                "max_points": w,
                "reason": "Kein belegter Bedarf – unbekannt",
            }
        )

    role_weight = weights.get("role", 0)
    excluded = _matches(
        industry, profile.get("excluded_industries", []) + criteria.get("excluded_industries", [])
    )
    if excluded:
        factors.append(
            {
                "name": "Branchenausschluss",
                "points": 0,
                "max_points": 0,
                "reason": "Branche ist explizit ausgeschlossen.",
            }
        )
    applicable = sum(f["max_points"] for f in factors)
    earned = sum(f["points"] for f in factors)
    value = 0 if excluded or not applicable else round(earned * 100 / applicable)
    if not row.get("website"):
        missing.append("Website")
    return {
        "value": value,
        "factors": factors,
        "missing_data": missing + ["Ansprechpartner", "Kaufabsicht"],
        "not_applicable": [{"name": "Entscheiderrolle", "max_points": role_weight}]
        if role_weight
        else [],
        "notice": "Firmen-Fit (normalisiert ohne Rollenfaktor, da kein Ansprechpartner vorliegt). "
        "Keine Kaufwahrscheinlichkeit; unbekannte Angaben zählen 0 Punkte.",
    }
