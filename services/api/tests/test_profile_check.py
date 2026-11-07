"""LinkedIn profile check via (mocked) Brave results, email campaign list, data quality.

Synthetic people and companies only. Nothing calls Brave or LinkedIn: the search is a
local function returning fictional results.
"""

from sqlalchemy import select

from app import profile_check as pc
from app.jobs import execute_one
from app.journeys import CompanyFact
from app.models import Company, Contact


def hit(url, title, description=""):
    return {"url": url, "title": title, "description": description}


def test_judge_requires_name_and_company_or_place():
    names = pc.name_tokens("Erika", "Fiktiv")
    firm = pc.firm_tokens("Synthetische Kanzlei Sonnenschein GmbH")
    v = pc.judge(
        names,
        firm,
        "Offenburg",
        hit(
            "https://de.linkedin.com/in/erika-fiktiv?trk=x",
            "Erika Fiktiv – Inhaberin – Kanzlei Sonnenschein",
            "Offenburg, Baden-Württemberg",
        ),
    )
    assert v["status"] == "verified" and v["url"] == "https://www.linkedin.com/in/erika-fiktiv/"
    assert v["reason"] == "Name, Firma und Ort stimmen im Suchtreffer überein"
    place_only = pc.judge(
        names,
        firm,
        "Offenburg",
        hit("https://www.linkedin.com/in/erika-f", "Erika Fiktiv – Steuerberaterin", "Offenburg"),
    )
    assert place_only["status"] == "verified" and "Ort" in place_only["reason"]
    name_only = pc.judge(
        names,
        firm,
        "Offenburg",
        hit("https://www.linkedin.com/in/erika-f2", "Erika Fiktiv – Beraterin", "Hamburg"),
    )
    assert name_only["status"] == "unsure"
    assert (
        pc.judge(
            names,
            firm,
            "Offenburg",
            hit(
                "https://www.linkedin.com/in/other",
                "Max Anders – Kanzlei Sonnenschein",
                "Offenburg",
            ),
        )
        is None
    )
    # Company pages are no profiles.
    assert (
        pc.judge(
            names,
            firm,
            "Offenburg",
            hit(
                "https://www.linkedin.com/company/sonnenschein",
                "Erika Fiktiv Sonnenschein",
                "Offenburg",
            ),
        )
        is None
    )


def test_check_person_unsure_when_several_profiles_match():
    person = {
        "first_name": "Erika",
        "last_name": "Fiktiv",
        "company": "Kanzlei Sonnenschein",
        "location": "Offenburg",
    }
    two = lambda q: [  # noqa: E731
        hit("https://www.linkedin.com/in/erika-1", "Erika Fiktiv – Sonnenschein", ""),
        hit("https://www.linkedin.com/in/erika-2", "Erika Fiktiv – Offenburg", ""),
    ]
    assert pc.check_person(person, two)["status"] == "unsure"
    assert pc.check_person(person, lambda q: [])["status"] == "not_found"


def test_role_search_needs_company_and_role():
    company = {"id": "c1", "name": "Praxis Dr. Beispiel Zahnmedizin", "location": "Lahr"}
    results = [
        hit(
            "https://www.linkedin.com/in/lea-muster",
            "Lea Muster – Praxismanagerin – Zahnmedizin Beispiel",
            "Lahr",
        ),
        hit(
            "https://www.linkedin.com/in/tom-other",
            "Tom Other – Praxismanager – Andere Praxis",
            "Lahr",
        ),
        hit("https://www.linkedin.com/in/ina-x", "Ina Xeno – Zahnmedizin Beispiel", "Lahr"),
    ]
    found = pc.role_search(company, lambda q: results, set())
    assert [f["url"] for f in found] == ["https://www.linkedin.com/in/lea-muster/"]
    assert found[0]["role"] == "Praxismanager" and found[0]["first_name"] == "Lea"


def test_email_kind():
    assert pc.email_kind("info@k.example", []) == "allgemein"
    assert pc.email_kind("kanzlei@k.example", []) == "allgemein"
    assert pc.email_kind("erika@k.example", ["Erika Fiktiv"]) == "persönlich"
    assert pc.email_kind("e.fiktiv@k.example", ["Erika Fiktiv"]) == "persönlich"
    assert pc.email_kind("max.probe@k.example", []) == "persönlich"


def seed(admin, ws):
    a = Company(
        workspace_id=ws,
        name="Synthetische Kanzlei Sonnenschein GmbH",
        identity="t:a",
        location="Offenburg",
    )
    b = Company(
        workspace_id=ws, name="Fiktive Zahnmedizin Beispiel", identity="t:b", location="Lahr"
    )
    c = Company(workspace_id=ws, name="Beispiel Büro Nirgendwo", identity="t:c", location="Kehl")
    admin.add_all([a, b, c])
    admin.flush()
    admin.add_all(
        [
            Contact(workspace_id=ws, company_id=a.id, first_name="Erika", last_name="Fiktiv"),
            Contact(workspace_id=ws, company_id=b.id, first_name="Bernd", last_name="Unbekannt"),
            CompanyFact(
                workspace_id=ws,
                company_id=b.id,
                field="E-Mail allgemein (Impressum)",
                value="info@zahn.example, b.unbekannt@zahn.example",
                source_url="https://zahn.example/impressum",
                source_kind="website_impressum",
                confidence="extracted",
            ),
        ]
    )
    admin.commit()
    return a, b, c


def test_check_job_stores_only_url_and_own_reason(context, admin, monkeypatch):
    client, (ws, other, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    a, b, c = seed(admin, ws)
    assert client.post(f"{w}/linkedin-check", json={}).status_code == 503  # no Brave key
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "synthetic")
    queries = []

    def search(query):
        queries.append(query)
        if "Erika Fiktiv" in query:
            return [
                hit(
                    "https://de.linkedin.com/in/erika-fiktiv",
                    "Erika Fiktiv – Kanzlei Sonnenschein",
                    "Offenburg · secret snippet",
                )
            ]
        if "zahnmedizin" in query.casefold() and "Praxismanager" in query:
            return [
                hit(
                    "https://www.linkedin.com/in/lea-muster",
                    "Lea Muster – Praxismanagerin – Fiktive Zahnmedizin Beispiel",
                    "Lahr",
                )
            ]
        return []

    monkeypatch.setattr(pc, "brave_search", lambda key, client=None, interval=None: search)
    r = client.post(f"{w}/linkedin-check", json={"roles_limit": 5})
    assert r.status_code == 202, r.text
    assert execute_one(ws)
    erika = admin.scalar(
        select(Contact).where(Contact.workspace_id == ws, Contact.first_name == "Erika")
    )
    admin.refresh(erika)
    assert erika.linkedin_status == "verified"
    assert erika.linkedin_url == "https://www.linkedin.com/in/erika-fiktiv/"
    assert erika.linkedin_reason == "Name, Firma und Ort stimmen im Suchtreffer überein"
    bernd = admin.scalar(
        select(Contact).where(Contact.workspace_id == ws, Contact.first_name == "Bernd")
    )
    admin.refresh(bernd)
    assert bernd.linkedin_status == "not_found" and bernd.linkedin_url is None
    lea = admin.scalar(
        select(Contact).where(Contact.workspace_id == ws, Contact.first_name == "Lea")
    )
    assert lea and lea.linkedin_status == "verified" and lea.company_id == b.id
    assert lea.job_title.startswith("Praxismanager") and lea.source == "LinkedIn-Suche (Brave)"
    # No Brave title or snippet is stored anywhere on the contacts.
    for contact in admin.scalars(select(Contact).where(Contact.workspace_id == ws)):
        assert "secret snippet" not in (contact.linkedin_reason + contact.job_title)
    assert not any("linkedin.com/in" in q and "site:" in q for q in queries)

    camp = client.get(f"{w}/email-campaign").json()
    # Company b now has a verified role contact: it leaves the email list. Nobody else has mail.
    assert camp["sending"] == "gesperrt" and camp["total"] == 0
    dq = client.get(f"{w}/data-quality", params={"seed": "x"}).json()
    assert dq["counts"]["companies"] == 3 and dq["counts"]["with_linkedin"] == 2
    assert dq["counts"]["nothing"] == 1 and len(dq["sample"]) == 3
    # Tenant isolation.
    assert client.get(f"/v1/workspaces/{other}/data-quality").json()["counts"]["companies"] == 0


def test_email_campaign_lists_people_without_profile(context, admin):
    client, (ws, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    seed(admin, ws)
    camp = client.get(f"{w}/email-campaign").json()
    assert camp["total"] == 2 and camp["personal"] == 1 and camp["general"] == 1
    first = camp["items"][0]
    assert first["email"] == "b.unbekannt@zahn.example" and first["kind"] == "persönlich"
    assert (
        first["source"] == "Impressum" and first["source_url"] == "https://zahn.example/impressum"
    )
    assert "nichts versendet" in camp["notice"]


def test_heute_only_with_verified_profile(context, admin):
    from tests.test_today import SENDER

    client, (ws, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    a, b, c = seed(admin, ws)
    client.post(f"{w}/icp-profiles/from-template", json={"template": "office_cleaning_ortenau"})
    assert client.post(f"{w}/today/build", json=SENDER).json()["created"]["connect"] == 0
    erika = admin.scalar(
        select(Contact).where(Contact.workspace_id == ws, Contact.first_name == "Erika")
    )
    erika.linkedin_url, erika.linkedin_status = (
        "https://www.linkedin.com/in/erika-fiktiv/",
        "verified",
    )
    admin.commit()
    client.post(f"{w}/today/build", json=SENDER)
    items = client.get(f"{w}/today").json()["items"]
    connects = [i for i in items if i["kind"] == "connect"]
    assert [i["contact"]["name"] for i in connects] == ["Erika Fiktiv"]
    assert connects[0]["profile_url"] == "https://www.linkedin.com/in/erika-fiktiv/"
