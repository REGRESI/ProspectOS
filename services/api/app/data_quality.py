"""Data quality for the CleanStar pilot.

1. Website ↔ company plausibility. A website found in OSM (or entered) is only trusted
   when the company name plausibly belongs to the domain or to the firm named in the
   Impressum. Otherwise the check is stored as a cited fact ("Website-Abgleich") and the
   Impressum facts are kept as *unbestätigt* instead of being silently adopted: they do
   not count for ranking completeness, do not create contacts and are shown flagged.
2. Target segments for office cleaning in Offenburg/Ortenau. Every company gets one
   segment with a tier (A sehr gut … C schwach, X ausgeblendet) from its OSM category,
   industry and name. Konzernfilialen (OSM brand/operator, known chains, Impressum seat
   outside the region) are hidden like Autohäuser and Industrie, with the reason shown.

Everything here is deterministic and explainable; nothing is invented. Segment and
check results are recomputed from stored facts, never from model guesses.
"""

import re
import unicodedata
from urllib.parse import urlsplit

from sqlalchemy import select

from app.journeys import CompanyFact
from app.models import Company

CHECK_FIELD = "Website-Abgleich"
CHECK_KIND = "data_quality"
UNCONFIRMED = "unbestätigt"

LEGAL = {
    "gmbh", "mbh", "ag", "kg", "kgaa", "co", "ug", "ohg", "gbr", "ek", "ev", "eg", "se",
    "partg", "partgmbb", "mbb", "ltd", "inc", "haftungsbeschraenkt", "gesellschaft",
}  # fmt: skip
GENERIC = {
    "und", "der", "die", "das", "den", "fuer", "von", "vom", "zum", "zur", "am", "im", "in",
    "an", "bei", "mit", "the", "and", "of", "dr", "med", "dent", "prof", "dipl", "ing",
    "praxis", "gemeinschaftspraxis", "kanzlei", "buero", "office", "partner", "partnerschaft",
    "rechtsanwalt", "rechtsanwaelte", "rechtsanwaeltin", "anwaltskanzlei", "steuerberater",
    "steuerberaterin", "steuerberatung", "steuerkanzlei", "zahnarzt", "zahnaerztin",
    "zahnarztpraxis", "arzt", "aerztin", "allgemeinmedizin", "physiotherapie", "service",
    "services", "gruppe", "group", "center", "centrum", "zentrum", "haus", "autohaus",
    "agentur", "versicherung", "versicherungen", "immobilien", "hausverwaltung", "notar",
    "notariat", "architekt", "architekten", "ingenieurbuero", "beratung", "consulting",
    "kindergarten", "kita", "offenburg", "lahr", "kehl", "achern", "oberkirch", "ortenau",
    "gengenbach", "baden", "schwarzwald", "germany", "deutschland", "www", "home", "info",
}  # fmt: skip
STOP = LEGAL | GENERIC

# Chains and branch networks whose local office is no buyer of office cleaning.
CHAINS = (
    "sparkasse", "volksbank", "raiffeisenbank", "commerzbank", "deutsche bank", "postbank",
    "targobank", "santander", "hypovereinsbank", "aok", "kkh", "barmer", "techniker krankenkasse",
    "dak", "ikk", "deutsche post", "dhl", "telekom", "vodafone", "o2", "1&1", "fielmann",
    "apollo", "tüv", "dekra", "adac", "kfz-zulassung", "agentur für arbeit", "jobcenter",
    "deutsche rentenversicherung", "finanzamt", "polizei", "mcdonald", "burger king",
)  # fmt: skip

# (key, label, tier, osm categories, industries, name keywords)
SEGMENTS = [
    ("tax", "Steuerberatung", "A", ("office=tax_advisor", "office=accountant"), ("Steuerberatung",), ("steuerber", "steuerkanzlei", "buchhaltung", "lohnbuero")),
    ("law", "Kanzlei / Notariat", "A", ("office=lawyer", "office=notary"), ("Rechtsberatung",), ("rechtsanw", "kanzlei", "notar", "anwaltsk")),
    ("practice", "Arzt-/Zahnarzt-/Therapiepraxis", "A", ("amenity=doctors", "amenity=dentist", "healthcare=physiotherapist", "healthcare=doctor", "healthcare=dentist"), (), ("praxis", "zahnarzt", "physio", "ergotherap", "logopaed", "heilpraktik")),
    ("agency", "Agentur", "A", ("office=advertising_agency", "office=graphic_design"), ("Agentur / Marketing",), ("agentur", "werbung", "design", "marketing", "medien")),
    ("property", "Hausverwaltung", "A", ("office=property_management",), ("Hausverwaltung",), ("hausverwaltung", "immobilienverwaltung", "wohnungsverwaltung", "weg-verwaltung")),
    ("childcare", "Kita / Kinderbetreuung", "A", ("amenity=kindergarten", "amenity=childcare"), ("Kita / Kinderbetreuung",), ("kita", "kindergarten", "kindertages", "kinderhaus", "krippe")),
    ("office", "Büro / Dienstleistung", "B", ("office=company", "office=consulting", "office=coworking"), ("Büro / Dienstleistung",), ("buero", "beratung", "consult")),
    ("estate", "Immobilienmakler", "B", ("office=estate_agent",), ("Immobilien",), ("immobilien", "makler")),
    ("architect", "Architektur / Ingenieurbüro", "B", ("office=architect", "office=engineer", "office=surveyor"), ("Architektur & Ingenieurwesen",), ("architekt", "ingenieur", "planung", "vermessung")),
    ("it", "IT-Büro", "B", ("office=it", "office=telecommunication"), ("IT & Software",), ("software", "edv", "it-")),
    ("insurance", "Versicherungs-/Finanzbüro", "B", ("office=insurance", "office=financial_advisor"), ("Versicherung & Finanzen",), ("versicherung", "finanzberat", "vermoegens")),
    ("public", "Öffentliche Verwaltung", "C", ("office=government", "amenity=townhall"), ("Öffentliche Verwaltung",), ("rathaus", "landratsamt", "verwaltung", "amt ")),
    ("clinic", "Klinik / MVZ", "C", ("amenity=clinic", "amenity=hospital"), (), ("klinik", "klinikum", "mvz", "krankenhaus")),
    ("bank", "Bank / Finanzinstitut", "C", ("office=financial", "amenity=bank"), (), ("bank",)),
    ("repair", "Reparatur / Werkstatt", "C", ("craft=electronics_repair",), (), ()),
    ("car", "Autohaus / Kfz", "X", ("shop=car", "shop=car_repair"), ("Kfz",), ("autohaus", "kfz", "karosserie", "autoglas", "reifen", "automobile")),
    ("industry", "Industrie / Produktion", "X", ("man_made=works", "industrial=*"), ("Industrie & Produktion",), ("werk ", "fabrik", "maschinenbau", "metallbau")),
    ("logistics", "Logistik", "X", ("office=logistics", "industrial=warehouse"), ("Logistik",), ("spedition", "logistik", "zusteller")),
    ("competitor", "Reinigung (Wettbewerb)", "X", ("craft=cleaning", "shop=dry_cleaning"), ("Reinigung / Facility",), ("reinigung", "gebaeudeservice", "facility")),
]  # fmt: skip
GENERIC_CATEGORIES = {"", "office=company", "office=consulting", "office=yes"}
TIER_SCORE = {"A": 100, "B": 70, "C": 35, "?": 45, "X": 0}
TIER_LABEL = {"A": "sehr gut", "B": "gut", "C": "schwach", "?": "unbekannt", "X": "ausgeblendet"}


def fold(text: str) -> str:
    text = (text or "").casefold()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def tokens(name: str) -> list[str]:
    return [t for t in fold(name).split() if len(t) >= 3 and t not in STOP and not t.isdigit()]


def host_labels(website: str | None) -> list[str]:
    if not website:
        return []
    raw = website if "://" in website else "https://" + website
    host = (urlsplit(raw).hostname or "").casefold()
    parts = [p for p in host.split(".") if p and p != "www"]
    if len(parts) >= 2:
        parts = parts[:-1]  # drop TLD
    return [fold(p).replace(" ", "") for p in parts if p]


def _domain_hit(name: str, website: str | None) -> bool:
    labels = host_labels(website)
    if not labels:
        return False
    words = tokens(name)
    compact_name = fold(name).replace(" ", "")
    pieces = set()
    for label in labels:
        pieces.add(label)
        pieces.update(re.split(r"[^a-z0-9]", label))
    joined = "".join(labels)
    for word in words:
        if len(word) >= 4 and word in joined:
            return True
        if word in pieces:
            return True
    for label in labels:
        core = label.replace("-", "")
        if len(core) >= 4 and core in compact_name:
            return True
    initials = "".join(w[0] for w in fold(name).split() if w not in LEGAL)
    return len(initials) >= 2 and any(initials == p or initials in p for p in pieces if len(p) >= 2)


def _same_firm(name: str, impressum_name: str) -> bool:
    a, b = set(tokens(name)), set(tokens(impressum_name))
    if a & b:
        return True
    ca, cb = fold(name).replace(" ", ""), fold(impressum_name).replace(" ", "")
    return bool(ca and cb and (ca in cb or cb in ca))


def _postcode(value: str) -> str:
    m = re.search(r"\b(\d{5})\b", value or "")
    return m.group(1) if m else ""


def chain_signal(company: Company, impressum_address: str = "") -> dict:
    """Branch/chain signal: ``hide`` for known chains and OSM brands, a downgrade only
    when the Impressum seat lies outside the region (could also be a web agency's
    address picked up from the Impressum, so it is not proof)."""
    prov = company.provenance or {}
    # Only the brand tag: "operator" is often the owner itself (e.g. a town running a Kita).
    brand = (prov.get("brand") or "").strip()
    if brand:
        return {"reason": f"OSM-Marke: {brand}", "hide": True}
    lowered = f" {company.name.casefold()} "
    for chain in CHAINS:
        if re.search(rf"(?<![a-zäöü]){re.escape(chain)}(?![a-zäöü])", lowered):
            label = chain.title() if len(chain) > 4 else chain.upper()
            return {"reason": f"Filialnetz: {label}", "hide": True}
    own = _postcode(prov.get("address") or "")
    seat = _postcode(impressum_address)
    if own.startswith("77") and seat and not seat.startswith("77"):
        return {"reason": f"Impressum-Sitz {seat} außerhalb der Ortenau", "hide": False}
    return {"reason": "", "hide": False}


def website_check(company: Company, facts: dict[str, str]) -> dict:
    """status: passt | unstimmig | unklar | keine_website, with a short German reason."""
    website = company.website
    imp_name = facts.get("Firmenname (Impressum)", "")
    if not website:
        return {"status": "keine_website", "reason": "Keine Website hinterlegt"}
    host = ".".join(host_labels(website)) or website
    domain = _domain_hit(company.name, website)
    if imp_name:
        same = _same_firm(company.name, imp_name)
        if same:
            return {"status": "passt", "reason": f"Impressum nennt „{imp_name}“"}
        if domain:
            return {
                "status": "passt",
                "reason": f"Domain {host} passt zum Namen (Impressum: „{imp_name}“)",
            }
        return {
            "status": "unstimmig",
            "reason": f"Impressum nennt „{imp_name}“, Firma heißt „{company.name}“. Bitte prüfen",
        }
    if domain:
        return {"status": "passt", "reason": f"Domain {host} passt zum Namen"}
    return {"status": "unklar", "reason": f"Domain {host} zeigt keinen Bezug zum Namen"}


def segment(company: Company, chain: dict | None = None) -> dict:
    prov = company.provenance or {}
    category = prov.get("osm_category") or ""
    industry = company.industry or ""
    name = fold(company.name) + " "
    chain = chain or {"reason": "", "hide": False}
    if chain["hide"]:
        return {"key": "chain", "label": "Konzernfiliale", "tier": "X", "reason": chain["reason"]}
    best = None
    for key, label, tier, cats, industries, words in SEGMENTS:
        cat_hit = category in cats or any(
            c.endswith("=*") and category.startswith(c[:-1]) for c in cats
        )
        word_hit = any(fold(w) and fold(w) in name for w in words)
        industry_hit = industry in industries
        if cat_hit or industry_hit or word_hit:
            # A specific OSM category wins; for generic ones (office=company) the name
            # decides, e.g. "Hausverwaltung Beispiel" or "Werbeagentur Muster".
            generic = category in GENERIC_CATEGORIES
            score = (
                (2 if word_hit else 0) + (1 if cat_hit else 0) + (1 if industry_hit else 0)
                if generic
                else (3 if cat_hit else 0) + (1 if word_hit else 0) + (1 if industry_hit else 0)
            )
            rank = (-score, "ABC?X".index(tier))
            if best is None or rank < best[0]:
                best = (rank, key, label, tier)
    if not best:
        out = {"key": "unknown", "label": industry or "Unbekannt", "tier": "?", "reason": ""}
    else:
        _, key, label, tier = best
        out = {"key": key, "label": label, "tier": tier, "reason": ""}
    if chain["reason"] and out["tier"] in ("A", "B", "?"):
        out |= {"tier": "C", "label": out["label"] + " · Filiale?", "reason": chain["reason"]}
    return out


def fact_values(facts: list) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in facts:
        if f.field not in out:
            out[f.field] = f.value
    return out


def assess(company: Company, facts: list) -> dict:
    values = fact_values([f for f in facts if f.source_kind != CHECK_KIND])
    check = website_check(company, values)
    chain = chain_signal(company, values.get("Adresse (Impressum)", ""))
    seg = segment(company, chain)
    return {"check": check, "segment": seg | {"score": TIER_SCORE[seg["tier"]]}}


def store_check(db, ws: str, company: Company, facts: list, actor: str | None) -> dict:
    """Upsert the Website-Abgleich fact and (un)confirm Impressum facts accordingly."""
    result = assess(company, facts)
    check = result["check"]
    url = (company.provenance or {}).get("website_research", {}).get(
        "impressum_url"
    ) or company.website
    value = f"{check['status']}: {check['reason']}"[:1000]
    existing = next((f for f in facts if f.field == CHECK_FIELD), None)
    if check["status"] != "keine_website" and url:
        if existing is None:
            db.add(
                CompanyFact(
                    workspace_id=ws,
                    company_id=company.id,
                    field=CHECK_FIELD,
                    value=value,
                    source_url=url[:2000],
                    confidence="checked",
                    source_kind=CHECK_KIND,
                    source_id="data-quality",
                    actor_id=actor,
                )
            )
        elif existing.value != value:
            existing.value = value
            existing.source_url = url[:2000]
    target = UNCONFIRMED if check["status"] == "unstimmig" else "extracted"
    for f in facts:
        if f.source_kind == "website_impressum" and f.confidence != target:
            f.confidence = target
    return result


def recheck_workspace(db, ws: str, actor: str | None = None) -> dict:
    companies = db.scalars(select(Company).where(Company.workspace_id == ws)).all()
    facts: dict[str, list] = {}
    for f in db.scalars(select(CompanyFact).where(CompanyFact.workspace_id == ws)):
        facts.setdefault(f.company_id, []).append(f)
    counts: dict[str, int] = {}
    tiers: dict[str, int] = {}
    for company in companies:
        result = store_check(db, ws, company, facts.get(company.id, []), actor)
        counts[result["check"]["status"]] = counts.get(result["check"]["status"], 0) + 1
        tier = result["segment"]["tier"]
        tiers[tier] = tiers.get(tier, 0) + 1
    db.flush()
    return {"companies": len(companies), "checks": counts, "tiers": tiers}
