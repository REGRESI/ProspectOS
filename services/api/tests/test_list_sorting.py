"""Server-side sort and filters for the Firmen and Kontakte tables. Synthetic data."""


def test_contacts_sort_and_stage_filter(context):
    client, (ws, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    for first, last, firm in [("Anna", "Zeta", "Beta GmbH"), ("Bert", "Alpha", "Alpha AG")]:
        r = client.post(
            f"{w}/contacts", json={"first_name": first, "last_name": last, "company": firm}
        )
        assert r.status_code in (200, 201), r.text
    names = [c["last_name"] for c in client.get(f"{w}/contacts?sort=name").json()["items"]]
    assert names == ["Alpha", "Zeta"]
    names = [c["last_name"] for c in client.get(f"{w}/contacts?sort=-company").json()["items"]]
    assert names == ["Zeta", "Alpha"]
    target = client.get(f"{w}/contacts?sort=name").json()["items"][0]
    assert target["outreach_stage"] == "new"
    client.put(f"{w}/contacts/{target['id']}/outreach-stage", json={"stage": "meeting"})
    met = client.get(f"{w}/contacts?stage=meeting").json()
    assert met["total"] == 1 and met["items"][0]["id"] == target["id"]
    assert client.get(f"{w}/contacts?sort=evil").status_code == 422


def test_companies_sort(context):
    client, (ws, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    for first, firm, place in [("A", "Zeta Praxis", "Achern"), ("B", "Alpha Kanzlei", "Lahr")]:
        client.post(f"{w}/contacts", json={"first_name": first, "company": firm, "location": place})
    by_name = [c["name"] for c in client.get(f"{w}/companies/summary?sort=name").json()["items"]]
    assert by_name == ["Alpha Kanzlei", "Zeta Praxis"]
    by_place = [c["name"] for c in client.get(f"{w}/companies/summary?sort=-name").json()["items"]]
    assert by_place == ["Zeta Praxis", "Alpha Kanzlei"]
    assert client.get(f"{w}/companies/summary?sort=x").status_code == 422
