"""M4 ranking with synthetic companies (no real data)."""

from app.journeys import CompanyFact, CompanyProfile
from app.models import Company


def add_company(admin, ws, name, location, industry, website=None):
    c = Company(
        workspace_id=ws,
        name=name,
        identity=f"test:{name}",
        location=location,
        industry=industry,
        website=website,
        provenance={"source_url": "https://www.openstreetmap.org/node/1"},
    )
    admin.add(c)
    admin.flush()
    return c


def test_template_ranking_explains_and_excludes(context, admin):
    client, (ws, other, *_), _ = context
    r = client.post(
        f"/v1/workspaces/{ws}/icp-profiles/from-template",
        json={"template": "office_cleaning_ortenau"},
    )
    assert r.status_code == 201, r.text
    assert "Ortenau" in r.json()["name"] or "Ortenaukreis" in r.json()["name"]
    # Idempotent.
    again = client.post(
        f"/v1/workspaces/{ws}/icp-profiles/from-template",
        json={"template": "office_cleaning_ortenau"},
    )
    assert again.json()["id"] == r.json()["id"]

    best = add_company(
        admin, ws, "Synthetische Steuerkanzlei", "Offenburg", "Steuerberatung", "https://a.example"
    )
    for field, value in [
        ("Geschäftsführung / Inhaber", "Erika Fiktiv"),
        ("Telefon (Impressum)", "+49 781 000"),
        ("E-Mail allgemein (Impressum)", "info@a.example"),
        ("Adresse (Impressum)", "Testweg 1, 77652 Offenburg"),
    ]:
        admin.add(
            CompanyFact(
                workspace_id=ws,
                company_id=best.id,
                field=field,
                value=value,
                source_url="https://a.example/impressum",
                source_kind="website_impressum",
                confidence="extracted",
            )
        )
    add_company(admin, ws, "Synthetisches Autohaus", "Lahr/Schwarzwald", "Kfz")
    add_company(admin, ws, "Synthetische Bäckerei", "Freiburg", "Einzelhandel")
    add_company(admin, ws, "Synthetische Konkurrenz Reinigung", "Offenburg", "Reinigung / Facility")
    customer = add_company(admin, ws, "Synthetischer Bestandskunde", "Offenburg", "Steuerberatung")
    admin.add(CompanyProfile(workspace_id=ws, company_id=customer.id, is_customer=True))
    add_company(admin, other, "Fremde Firma", "Offenburg", "Steuerberatung")
    admin.commit()

    ranking = client.get(f"/v1/workspaces/{ws}/ranking/companies").json()
    names = [i["name"] for i in ranking["items"]]
    assert names[0] == "Synthetische Steuerkanzlei"
    assert names[1] == "Synthetisches Autohaus"
    assert "Synthetische Konkurrenz Reinigung" not in names  # competitor excluded
    assert "Synthetischer Bestandskunde" not in names  # existing customer excluded
    assert "Fremde Firma" not in names  # tenant isolation
    top = ranking["items"][0]
    assert top["rank"] == 1 and top["fit"] == 100
    assert "Offenburg" in top["reason"] and "Steuerberatung" in top["reason"]
    assert top["sources"] == ["https://a.example/impressum"]
    assert "KI-Profil" in top["missing_facts"] and "Ansprechpartner" in top["missing_facts"]
    baker = next(i for i in ranking["items"] if i["name"] == "Synthetische Bäckerei")
    assert baker["fit"] == 0 and baker["gaps"]
    with_excluded = client.get(
        f"/v1/workspaces/{ws}/ranking/companies?include_excluded=true"
    ).json()
    competitor = next(i for i in with_excluded["items"] if "Konkurrenz" in i["name"])
    assert competitor["excluded"] and competitor["priority"] == 0
    # Forged profile id from another workspace.
    other_profile = client.post(
        f"/v1/workspaces/{other}/icp-profiles/from-template",
        json={"template": "office_cleaning_ortenau"},
    ).json()["id"]
    assert (
        client.get(f"/v1/workspaces/{ws}/ranking/companies?profile_id={other_profile}").status_code
        == 404
    )
