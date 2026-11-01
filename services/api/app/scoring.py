DEFAULT_ICP = {
    "name": "Dienstleister rund um Offenburg",
    "locations": ["Offenburg", "Ortenau"],
    "roles": ["Geschäftsführer", "Office", "Facility", "Inhaber"],
    "industries": ["Dienstleistung", "Büro"],
    "weights": {"location": 35, "role": 35, "industry": 30},
}


def score(contact, company, profile):
    factors, missing = [], []
    fields = [
        ("location", "Region", contact.location, profile["locations"]),
        ("role", "Entscheiderrolle", contact.job_title, profile["roles"]),
        ("industry", "Branche", company.industry if company else "", profile["industries"]),
    ]
    for key, label, value, terms in fields:
        maximum = profile["weights"][key]
        matched = bool(value and any(t.casefold() in value.casefold() for t in terms))
        if not value:
            missing.append(label)
        reason = (
            "Keine Angabe – unbekannt"
            if not value
            else (
                f"Übereinstimmung mit ICP: {value}"
                if matched
                else f"Keine Übereinstimmung: {value}"
            )
        )
        factors.append(
            {
                "name": label,
                "points": maximum if matched else 0,
                "max_points": maximum,
                "reason": reason,
            }
        )
    return {
        "value": sum(f["points"] for f in factors),
        "factors": factors,
        "missing_data": missing + ["Unternehmensgröße", "Kaufabsicht"],
        "notice": "Fit-Priorität, keine Kaufwahrscheinlichkeit. Angaben nicht extern verifiziert.",
    }
