"""M9d/M9e: register gap, role fallback, Art. 14 notice, names from company names, website
finder. Synthetic companies and addresses only; search and website fetches are fakes."""

import pytest
from sqlalchemy import select

from app import register_gap, website_finder
from app.flows import FlowTask
from app.journeys import CompanyFact
from app.letters import Letter, render_pdf
from app.models import Company, Contact
from app.providers.ai import ProviderError
from tests.test_v3_channels import firm, person, w
from tests.test_v3_letters import configure


@pytest.mark.parametrize(
    ("name", "kind", "form"),
    [
        ("Muster Gebäudetechnik GmbH & Co. KG", "registered", "GmbH & Co. KG"),
        ("Fiktiv Bau GmbH", "registered", "GmbH"),
        ("Synthetik UG (haftungsbeschränkt)", "registered", "UG"),
        ("Beispiel Holding AG", "registered", "AG"),
        ("Muster & Sohn OHG", "registered", "OHG"),
        ("Testhandel KG", "registered", "KG"),
        ("Malerei Muster e.K.", "registered", "e.K."),
        ("Kanzlei Muster Rechtsanwälte GmbH", "registered", "GmbH"),
        ("Praxis Dr. med. Anna Fiktiv", "unregistered", "Praxis"),
        ("Kanzlei Weber und Schmidt", "unregistered", "Kanzlei"),
        ("Muster und Partner GbR", "unregistered", "GbR"),
        ("Blumen Fiktiv Inh. Anna Muster", "unregistered", "Einzelunternehmen"),
        ("Sonnenschein", "unknown", ""),
    ],
)
def test_legal_form(name, kind, form):
    assert register_gap.legal_form(name) == (kind, form)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Praxis Dr. med. Anna Fiktiv", ("Anna", "Fiktiv", "hoch")),
        ("Steuerberaterin Lena Muster", ("Lena", "Muster", "hoch")),
        ("Dr. Jonas Beispiel Zahnarztpraxis", ("Jonas", "Beispiel", "hoch")),
        ("Mara Synthetik Steuerberatung", ("Mara", "Synthetik", "mittel")),
        ("Kanzlei Weber", None),
        ("Gemeinschaftspraxis Muster", None),
        ("Fiktiv Bau GmbH", None),
    ],
)
def test_names_from_company_names_are_rules_only(name, expected):
    found = register_gap.name_from_company(name)
    if expected is None:
        assert found is None
    else:
        assert (found["first_name"], found["last_name"], found["confidence"]) == expected


def test_model_answers_must_appear_verbatim():
    company = "Kanzlei am Markt Weber Schmidt"
    assert register_gap.checked_model_name(company, "Anna Weber") is None  # invented first name
    assert register_gap.checked_model_name(company, "keiner") is None
    assert register_gap.checked_model_name(company, "Weber Schmidt")["confidence"] == "KI"


def test_gap_counts_split_and_estimate(context, admin):
    client, (ws, other, *_), _ = context
    firm(admin, ws, "Fiktiv Bau GmbH")
    firm(admin, ws, "Testhandel KG")
    firm(admin, ws, "Praxis Dr. med. Anna Fiktiv")
    firm(admin, ws, "Sonnenschein")
    named = firm(admin, ws, "Muster Reinigung GmbH")
    person(admin, ws, named, "Ida")
    admin.commit()
    gap = client.get(w(ws, "/sources/register-gap")).json()
    assert gap["companies"] == 5 and gap["without_contact"] == 4
    assert (gap["registered"], gap["unregistered"], gap["unknown"]) == (2, 1, 1)
    assert gap["estimate"] == gap["estimate"] | {"extra_contacts": 2, "measured": False}
    assert "Annahme" in gap["estimate"]["basis"]
    assert client.get(w(other, "/sources/register-gap")).json()["companies"] == 0
    # Measured once this workspace has North Data companies: 2 people across 2 imports.
    for i in range(2):
        nd = Company(
            workspace_id=ws, name=f"ND Fiktiv {i} GmbH", identity=f"northdata:x{i}", provenance={}
        )
        admin.add(nd)
        admin.flush()
        person(admin, ws, nd, f"GF{i}")
    admin.commit()
    measured = client.get(w(ws, "/sources/register-gap")).json()["estimate"]
    assert measured["measured"] and measured["per_company"] == 1.0
    assert measured["extra_contacts"] == 2


def test_role_contact_letter_goes_to_management_with_art14_note(context, admin):
    client, (ws, other, *_), _ = context
    configure(client, ws)
    company = firm(admin, ws, "Fiktiv Bau GmbH")
    praxis = firm(admin, ws, "Praxis Dr. med. Anna Fiktiv")
    admin.commit()
    forged = client.post(w(other, "/companies/role-contacts"), json={"company_ids": [company.id]})
    assert forged.status_code == 404
    made = client.post(
        w(ws, "/companies/role-contacts"), json={"company_ids": [company.id, praxis.id]}
    )
    assert made.status_code == 201, made.text
    roles = {i["company_id"]: i for i in made.json()["items"]}
    assert roles[company.id]["role"] == "Geschäftsführung"
    assert roles[praxis.id]["role"] == "Praxisleitung"
    # Idempotent: no second role contact, no second visit task.
    client.post(w(ws, "/companies/role-contacts"), json={"company_ids": [company.id]})
    admin.expire_all()
    contact = admin.get(Contact, roles[company.id]["contact_id"])
    assert contact.linkedin_status == "not_found" and contact.channel_route == "letter"
    visits = admin.scalars(
        select(FlowTask).where(FlowTask.workspace_id == ws, FlowTask.origin == "role_fallback")
    ).all()
    assert len(visits) == 2 and "zuständigen Person" in visits[0].title
    # Role contacts do not count as a named contact person.
    assert client.get(w(ws, "/sources/register-gap")).json()["without_contact"] == 2

    first = client.post(w(ws, "/letters/prepare"), json={"contact_ids": [contact.id]}).json()
    letter = first["created"][0]
    assert letter["recipient"][:2] == ["Fiktiv Bau GmbH", "An die Geschäftsführung"]
    note = letter["privacy_note"]
    assert "Art. 14 DSGVO" in note and "Impressum" in note and "widersprechen" in note
    assert "abgerufen am" in note and "CleanStar (Test)" in note
    stored = admin.get(Letter, letter["id"])
    pdf = render_pdf(admin, ws, [stored])
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") == 1
    # Second letter to the same company: no repeated notice.
    admin.execute(
        Letter.__table__.update().where(Letter.id == letter["id"]).values(state="printed")
    )
    admin.commit()
    again = admin.get(Contact, roles[company.id]["contact_id"])
    from app.jobs import tenant
    from app.letters import compose_letter, get_settings

    tenant(admin, ws)
    follow = compose_letter(admin, ws, again, get_settings(admin, ws))
    assert follow.privacy_note == ""
    admin.rollback()


def test_names_endpoint_creates_only_high_confidence_contacts(context, admin):
    client, (ws, *_), _ = context
    firm(admin, ws, "Praxis Dr. med. Anna Fiktiv")
    firm(admin, ws, "Mara Synthetik Steuerberatung")
    firm(admin, ws, "Kanzlei Weber")
    admin.commit()
    result = client.post(w(ws, "/companies/names-from-company-names")).json()
    assert [c["name"] for c in result["created"]] == ["Dr. med. Anna Fiktiv"]
    assert [s["name"] for s in result["suggested"]] == ["Mara Synthetik"]
    assert result["unclear"] == 1
    facts = admin.scalars(
        select(CompanyFact).where(
            CompanyFact.workspace_id == ws, CompanyFact.field == register_gap.NAME_FACT
        )
    ).all()
    assert {f.confidence for f in facts} == {"regel_hoch", "regel_mittel"}
    assert all(f.source_kind == "company_name" for f in facts)
    contact = admin.get(Contact, result["created"][0]["contact_id"])
    assert contact.source == "company_name"


def test_register_links_are_links_only(context, admin):
    client, (ws, other, *_), _ = context
    praxis = firm(admin, ws, "Praxis Dr. med. Anna Fiktiv")
    admin.commit()
    items = client.get(w(ws, f"/companies/{praxis.id}/register-links")).json()["items"]
    assert {i["id"] for i in items} >= {"arztsuche_bw", "anwaltsverzeichnis", "steuerberater"}
    assert [i["id"] for i in items if i["suggested"]] == ["arztsuche_bw"]
    assert all(i["url"].startswith("https://") and not i["verified"] for i in items)
    assert client.get(w(other, f"/companies/{praxis.id}/register-links")).status_code == 404


def research_page(company, address):
    return {
        "website": "https://fiktiv-bau.example.test/",
        "retrieved_at": "2026-11-08T10:00:00+00:00",
        "impressum_url": "https://fiktiv-bau.example.test/impressum",
        "impressum": {
            "company": {
                "value": company,
                "source_url": "https://fiktiv-bau.example.test/impressum",
            },
            "address": {
                "value": address,
                "source_url": "https://fiktiv-bau.example.test/impressum",
            },
        },
        "pages": [{"url": "https://fiktiv-bau.example.test/", "title": "", "text": company}],
        "robots": "honoured",
    }


def test_website_finder_accepts_only_name_and_address_match(context, admin):
    client, (ws, *_), _ = context
    company = firm(admin, ws, "Fiktiv Bau GmbH", phone=False, email=False)
    other_place = firm(admin, ws, "Sonnenschein Kita", phone=False, email=False)
    admin.commit()
    tenant_ws = ws
    from app.jobs import tenant

    tenant(admin, tenant_ws)
    job = type("J", (), {"workspace_id": ws, "payload": {}, "actor_id": None})()
    items = [
        {"company_id": c.id, "name": c.name, "address": website_finder.known_address(admin, ws, c)}
        for c in (company, other_place)
    ]
    assert items[0]["address"]["postcode"] == "77652" and items[0]["address"]["street"] == "Testweg"
    searched, fetched = [], []

    def search(query):
        searched.append(query)
        return [
            "https://www.gelbeseiten.de/fiktiv-bau",
            "https://www.linkedin.com/company/fiktiv",
            "https://fiktiv-bau.example.test/kontakt",
            "https://wrong.example.test/",
        ]

    def research(root):
        fetched.append(root)
        if "wrong" in root:
            raise ProviderError("robots_disallowed")
        if "Sonnenschein" in searched[-1]:
            return research_page("Andere Firma GmbH", "Hauptstraße 9, 10115 Berlin")
        return research_page("Fiktiv Bau GmbH", "Testweg 1, 77652 Offenburg")

    result = website_finder.run({"key": "synthetic", "items": items}, search, research)
    assert searched[0] == '"Fiktiv Bau GmbH" Offenburg'
    # Directories and LinkedIn are never fetched.
    assert not any("gelbeseiten" in u or "linkedin" in u for u in fetched)
    found, missing = result["items"]
    assert found["result"] == "found" and found["website"] == "https://fiktiv-bau.example.test/"
    assert missing["result"] == "not_found"
    assert {c["reason"] for c in missing["checked"]} == {
        "Name im Impressum nicht gefunden",
        "robots_disallowed",
    }
    summary = website_finder.finalize(admin, job, result)
    admin.flush()
    assert (summary["found"], summary["not_found"]) == (1, 1)
    admin.refresh(company)
    assert company.website == "https://fiktiv-bau.example.test/"
    assert company.provenance["website_finder"]["result"] == "found"
    facts = admin.scalars(
        select(CompanyFact).where(
            CompanyFact.company_id == company.id, CompanyFact.source_kind == "website_impressum"
        )
    ).all()
    assert any(f.field == "Firmenname (Impressum)" for f in facts)
    admin.rollback()


def test_website_finder_needs_key_and_research_switch(context, admin, monkeypatch):
    client, (ws, *_), _ = context
    result = client.post(w(ws, "/companies/find-websites"), json={})
    assert result.status_code == 409 and "Brave" in result.json()["message"]
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "synthetic-not-real")
    result = client.post(w(ws, "/companies/find-websites"), json={})
    assert result.status_code == 409 and "ausgeschaltet" in result.json()["message"]
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    queued = client.post(w(ws, "/companies/find-websites"), json={})
    assert queued.status_code == 202
    assert client.post(w(ws, "/companies/find-websites"), json={}).status_code == 409
    report = client.get(w(ws, "/website-finder")).json()
    assert report["last"]["status"] == "queued"


def test_cli_prints_the_split(context, admin, capsys):
    _, (ws, *_), _ = context
    firm(admin, ws, "Fiktiv Bau GmbH")
    firm(admin, ws, "Praxis Dr. med. Anna Fiktiv")
    admin.commit()
    assert register_gap.main(["--workspace", ws]) == 0
    out = capsys.readouterr().out
    assert "2 ohne Ansprechpartner" in out and "registerpflichtige Rechtsform: 1" in out
    assert "North Data würde etwa 1 Ansprechpartner ergänzen" in out
