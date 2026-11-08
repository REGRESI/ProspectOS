"""V3 M6: guided start derives its state from real data."""

from app.models import Membership
from tests.test_v3_channels import w


def test_five_steps_from_empty_to_first_campaign(context, admin):
    client, (ws, *_), user_id = context
    start = client.get(w(ws, "/start")).json()
    assert start["done"] == 0 and start["next"] == "company" and start["total"] == 5
    bad = client.put(
        w(ws, "/start/company"), json={"sender_company": "C", "sender_name": "N", "offer": "x"}
    )
    assert bad.status_code == 422
    s = client.put(
        w(ws, "/start/company"),
        json={
            "sender_company": "CleanStar (Test)",
            "sender_name": "Nico Test",
            "offer": "Büroreinigung",
        },
    ).json()
    assert s.get("steps") and s["steps"][0]["done"] and s["next"] == "area", s
    s = client.put(
        w(ws, "/start/area"), json={"region": "der Ortenau", "places": ["Lahr", "779"]}
    ).json()
    assert s["steps"][1]["done"] and s["settings"]["region"] == "der Ortenau"
    pace = client.get(w(ws, "/team/pace")).json()["members"][0]
    assert pace["territory"] == ["Lahr", "779"]
    client.post(w(ws, "/icp-profiles/from-template"), json={"template": "office_cleaning_ortenau"})
    s = client.post(w(ws, "/start/linkedin/skip")).json()
    assert [x["done"] for x in s["steps"]] == [True, True, True, True, False]
    assert s["steps"][3]["summary"] == "übersprungen"
    client.post(
        w(ws, "/campaigns/from-recipe"), json={"recipe": "letter_only", "audience": "routed"}
    )
    s = client.get(w(ws, "/start")).json()
    assert s["done"] == 5 and s["next"] is None
    # Letter sender was prefilled from step 1.
    assert client.get(w(ws, "/letters/settings")).json()["sender_company"] == "CleanStar (Test)"
    admin.get(Membership, (ws, user_id)).role = "editor"
    admin.commit()
    assert client.put(w(ws, "/start/area"), json={"region": "Baden"}).status_code == 403
