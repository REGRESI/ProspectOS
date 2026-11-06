"""Website ↔ company plausibility and office-cleaning segments (synthetic data only)."""

from sqlalchemy import select

from app import data_quality
from app.journeys import CompanyFact
from app.models import Company, Contact
from app.today import contacts_from_impressum


def company(name, website=None, category="", industry="", **prov):
    return Company(
        workspace_id="w",
        name=name,
        identity=name,
        location="Offenburg",
        industry=industry,
        website=website,
        provenance={"osm_category": category, **prov},
    )


def test_domain_and_impressum_plausibility():
    check = data_quality.website_check
    assert (
        check(company("Kanzlei Musterfrau", "https://kanzlei-musterfrau.example"), {})["status"]
        == "passt"
    )
    # Initials and compact names.
    assert (
        check(company("ADS Steuerberatung", "https://www.ads-steuer.example"), {})["status"]
        == "passt"
    )
    assert check(company("Grafik Team GmbH", "https://grafikteam.example"), {})["status"] == "passt"
    # Impressum names the same firm although the domain is generic.
    assert (
        check(
            company("Dr. Erika Beispiel", "https://zahnarzt-offenburg.example"),
            {"Firmenname (Impressum)": "Zahnarztpraxis Dr. Erika Beispiel"},
        )["status"]
        == "passt"
    )
    # Impressum names a different company: flagged, not adopted.
    flagged = check(
        company("Praxis Dr. Fiktiv", "https://orthopaede-og.example"),
        {"Firmenname (Impressum)": "Synthetische Betreiber GmbH & Co. KG"},
    )
    assert flagged["status"] == "unstimmig" and "Synthetische Betreiber" in flagged["reason"]
    assert check(company("Oestreich", "https://gaerfix.example"), {})["status"] == "unklar"
    assert check(company("Ohne Website"), {})["status"] == "keine_website"


def test_segments_rank_good_targets_up_and_hide_bad_ones():
    seg = data_quality.segment
    assert seg(company("Steuerbüro Fiktiv", category="office=tax_advisor"))["tier"] == "A"
    assert seg(company("Kita Sonnenschein", category="amenity=kindergarten"))["tier"] == "A"
    assert seg(company("Hausverwaltung Beispiel", category="office=company"))["key"] == "property"
    assert seg(company("Werbeagentur Muster", category="office=company"))["key"] == "agency"
    assert seg(company("Beispiel GmbH", category="office=company"))["tier"] == "B"
    assert seg(company("Rathaus", category="amenity=townhall"))["tier"] == "C"
    assert seg(company("Autohaus Fiktiv", category="shop=car"))["tier"] == "X"
    assert seg(company("Metallbau Beispiel", category="industrial=factory"))["tier"] == "X"
    chain = data_quality.chain_signal(company("Sparkasse Filiale Mitte"))
    assert (
        chain["hide"]
        and seg(company("Sparkasse Filiale Mitte"), chain)["label"] == "Konzernfiliale"
    )
    branded = company("Optik Beispiel", category="office=company", brand="Fiktivmarke")
    assert data_quality.chain_signal(branded)["hide"]
    # Seat outside the region: downgraded, not hidden (could be a web agency's address).
    outside = company("IT Beispiel", category="office=it", address="Weg 1, 77652 Offenburg")
    sig = data_quality.chain_signal(outside, "Allee 5, 80331 München")
    assert not sig["hide"] and seg(outside, sig)["tier"] == "C"


def test_mismatch_marks_impressum_unconfirmed_and_blocks_contacts(context, admin):
    _, (ws, *_), _ = context
    c = Company(
        workspace_id=ws,
        name="Praxis Dr. Fiktiv",
        identity="dq:1",
        location="Offenburg",
        industry="Gesundheit / Praxis",
        website="https://orthopaede-og.example",
        provenance={"osm_category": "amenity=doctors"},
    )
    admin.add(c)
    admin.flush()
    for field, value in [
        ("Firmenname (Impressum)", "Synthetische Betreiber GmbH & Co. KG"),
        ("Geschäftsführung / Inhaber", "Max Konzernchef"),
    ]:
        admin.add(
            CompanyFact(
                workspace_id=ws,
                company_id=c.id,
                field=field,
                value=value,
                source_url="https://orthopaede-og.example/impressum",
                source_kind="website_impressum",
                confidence="extracted",
            )
        )
    admin.flush()
    result = data_quality.recheck_workspace(admin, ws)
    assert result["checks"] == {"unstimmig": 1}
    facts = admin.scalars(select(CompanyFact).where(CompanyFact.company_id == c.id)).all()
    by = {f.field: f for f in facts}
    assert by["Website-Abgleich"].value.startswith("unstimmig: ")
    assert by["Geschäftsführung / Inhaber"].confidence == "unbestätigt"
    assert contacts_from_impressum(admin, ws) == 0
    assert not admin.scalars(select(Contact).where(Contact.workspace_id == ws)).all()
    # Idempotent and reversible once the Impressum matches.
    by["Firmenname (Impressum)"].value = "Praxis Dr. Fiktiv"
    admin.flush()
    assert data_quality.recheck_workspace(admin, ws)["checks"] == {"passt": 1}
    assert by["Geschäftsführung / Inhaber"].confidence == "extracted"
    assert contacts_from_impressum(admin, ws) == 1


def test_recheck_endpoint_and_ranking_penalty(context, admin):
    client, (ws, *_), _ = context
    client.post(
        f"/v1/workspaces/{ws}/icp-profiles/from-template",
        json={"template": "office_cleaning_ortenau"},
    )
    good = Company(
        workspace_id=ws,
        name="Steuerkanzlei Fiktiv",
        identity="dq:good",
        location="Offenburg",
        industry="Steuerberatung",
        website="https://steuerkanzlei-fiktiv.example",
        provenance={"osm_category": "office=tax_advisor"},
    )
    bad = Company(
        workspace_id=ws,
        name="Steuerbüro Beispiel",
        identity="dq:bad",
        location="Offenburg",
        industry="Steuerberatung",
        website="https://ganz-anders.example",
        provenance={"osm_category": "office=tax_advisor"},
    )
    admin.add_all([good, bad])
    admin.flush()
    admin.add(
        CompanyFact(
            workspace_id=ws,
            company_id=bad.id,
            field="Firmenname (Impressum)",
            value="Andere Holding AG",
            source_url="https://ganz-anders.example/impressum",
            source_kind="website_impressum",
            confidence="extracted",
        )
    )
    admin.commit()
    r = client.post(f"/v1/workspaces/{ws}/data-quality/recheck")
    assert r.status_code == 200 and r.json()["checks"] == {"passt": 1, "unstimmig": 1}
    items = {
        i["name"]: i for i in client.get(f"/v1/workspaces/{ws}/ranking/companies").json()["items"]
    }
    assert items["Steuerkanzlei Fiktiv"]["priority"] > items["Steuerbüro Beispiel"]["priority"]
    assert items["Steuerbüro Beispiel"]["website_check"]["status"] == "unstimmig"
    assert "Website unstimmig" in items["Steuerbüro Beispiel"]["reason"]
    assert "Firmenname (Impressum)" not in items["Steuerbüro Beispiel"]["known"]
