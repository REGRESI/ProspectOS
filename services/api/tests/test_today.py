"""M5 "Heute" LinkedIn day view. Synthetic companies/people; Brave and LLM are mocked."""

from datetime import timedelta

import httpx
from sqlalchemy import select

from app.db import now
from app.jobs import execute_one
from app.journeys import CompanyFact
from app.linkedin_channel import LinkedInAction
from app.models import Company, Contact
from app.platform_models import Task
from app.providers.ai import GenerationResult

SENDER = {
    "sender_name": "Nico Test",
    "sender_company": "Synthetische Reinigung",
    "followup_days": 5,
}


def give_profiles(admin, ws):
    """Synthetic verified LinkedIn profiles (as the Brave check would store them)."""
    for contact in admin.scalars(
        select(Contact).where(Contact.workspace_id == ws, Contact.linkedin_url.is_(None))
    ):
        slug = f"{contact.first_name}-{contact.last_name}".casefold().replace(" ", "-")
        contact.linkedin_url = f"https://www.linkedin.com/in/synthetisch-{slug}/"
        contact.linkedin_status = "verified"
        contact.linkedin_reason = "Name und Firma stimmen im Suchtreffer überein"
    admin.commit()


def seed(admin, ws, n=3):
    ids = []
    for i in range(n):
        c = Company(
            workspace_id=ws,
            name=f"Synthetische Kanzlei {i} GmbH",
            identity=f"test:k{i}",
            location="Offenburg",
            industry="Rechtsberatung",
            website=f"https://k{i}.example",
            provenance={"source_url": f"https://www.openstreetmap.org/node/{i}"},
        )
        admin.add(c)
        admin.flush()
        admin.add(
            CompanyFact(
                workspace_id=ws,
                company_id=c.id,
                field="Geschäftsführung / Inhaber",
                value=f"Erika Fiktiv{i}, Max Probe{i}",
                source_url=f"https://k{i}.example/impressum",
                source_kind="website_impressum",
                confidence="extracted",
            )
        )
        ids.append(c.id)
    admin.commit()
    return ids


def test_full_day_flow(context, admin, monkeypatch):
    client, (ws, other, *_), _ = context
    monkeypatch.setenv("LINKEDIN_DAILY_CONNECTION_LIMIT", "4")
    seed(admin, ws)
    w = f"/v1/workspaces/{ws}"
    assert (
        client.post(
            f"{w}/icp-profiles/from-template", json={"template": "office_cleaning_ortenau"}
        ).status_code
        == 201
    )
    created = client.post(f"{w}/contacts/from-impressum", json={}).json()["created"]
    assert created == 6
    assert client.post(f"{w}/contacts/from-impressum", json={}).json()["created"] == 0  # idempotent
    # Without a verified LinkedIn profile nobody reaches "Heute".
    assert client.post(f"{w}/today/build", json=SENDER).json()["created"]["connect"] == 0
    give_profiles(admin, ws)
    built = client.post(f"{w}/today/build", json=SENDER).json()
    assert built["created"]["connect"] == 4  # daily pacing limit
    day = client.get(f"{w}/today").json()
    items = day["items"]
    assert len(items) == 4 and all(i["state"] == "pending" for i in items)
    first = items[0]
    assert len(first["note"]) <= 200 and first["note_limit"] == 200
    # The button opens the verified profile directly, never a people search.
    assert first["profile_url"].startswith("https://www.linkedin.com/in/synthetisch-")
    assert first["profile_confirmed"] and first["profile_status"] == "verified"
    assert first["profile_reason"] == "Name und Firma stimmen im Suchtreffer überein"
    assert "Rang 1" in first["reason"] and any(s.endswith("/impressum") for s in first["sources"])
    assert "Nico Test" in first["message"]
    # Rebuild is idempotent for the same day.
    assert client.post(f"{w}/today/build", json=SENDER).json()["created"]["connect"] == 0
    # Sending before approval is refused.
    assert client.post(f"{w}/today/items/{first['id']}/sent", json={}).status_code == 409
    assert client.post(f"{w}/today/approve", json={"all_pending": True}).json()["approved"] == 4
    # Confirm the profile (normalised), forged profile path rejected.
    bad = client.put(
        f"{w}/contacts/{first['contact']['id']}/linkedin-profile",
        json={"url": "https://evil.example/in/x"},
    )
    assert bad.status_code == 422
    ok = client.put(
        f"{w}/contacts/{first['contact']['id']}/linkedin-profile",
        json={"url": "https://de.linkedin.com/in/erika-fiktiv0?trk=x"},
    )
    assert ok.json()["linkedin_url"] == "https://de.linkedin.com/in/erika-fiktiv0/".replace(
        "de.", "www."
    )
    sent = client.post(f"{w}/today/items/{first['id']}/sent", json={"elapsed_ms": 12000}).json()
    assert sent["state"] == "sent" and sent["profile_confirmed"]
    action = admin.scalar(select(LinkedInAction).where(LinkedInAction.id == sent["action_id"]))
    assert action.channel == "manual" and not action.simulated and action.state == "sent"
    contact = admin.get(Contact, first["contact"]["id"])
    admin.refresh(contact)
    assert contact.status == "contacted"
    assert (
        admin.scalar(select(Task).where(Task.workspace_id == ws, Task.contact_id == contact.id))
        is not None
    )
    day = client.get(f"{w}/today").json()
    assert day["stats"]["sent"] == 1 and day["stats"]["avg_seconds_per_contact"] == 12.0
    assert day["checks"][0]["question"] == "angenommen?"
    # User reports acceptance -> tomorrow's build creates the message step.
    assert (
        client.post(
            f"{w}/linkedin/actions/{action.id}/outcome", json={"outcome": "accepted"}
        ).status_code
        == 200
    )
    rebuilt = client.post(f"{w}/today/build", json=SENDER).json()
    assert rebuilt["created"]["message"] == 1
    msg = next(i for i in client.get(f"{w}/today").json()["items"] if i["kind"] == "message")
    client.post(f"{w}/today/approve", json={"item_ids": [msg["id"]]})
    # Editing invalidates the approval.
    edited = client.patch(f"{w}/today/items/{msg['id']}", json={"message": "Neuer Text"}).json()
    assert edited["state"] == "pending"
    client.post(f"{w}/today/approve", json={"item_ids": [msg["id"]]})
    sent_msg = client.post(f"{w}/today/items/{msg['id']}/sent", json={}).json()
    # Follow-up becomes due after followup_days.
    message_action = admin.get(LinkedInAction, sent_msg["action_id"])
    message_action.created_at = now() - timedelta(days=6)
    admin.commit()
    assert client.post(f"{w}/today/build", json=SENDER).json()["created"]["followup"] == 1
    # Tenant isolation: other workspace cannot touch items.
    assert client.post(f"/v1/workspaces/{other}/today/items/{msg['id']}/skip").status_code == 404

    # Reply analysis via LLM (mocked): suggestion only, nothing is sent.
    monkeypatch.setenv("LLM_API_KEY", "synthetic")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setenv("LLM_INPUT_USD_PER_MILLION", "0.4")
    monkeypatch.setenv("LLM_OUTPUT_USD_PER_MILLION", "1.6")
    monkeypatch.setattr(
        "app.providers.ai.generate_text",
        lambda prompt, sources=None, client=None: GenerationResult(
            text="Einordnung: Termin gewünscht\nNächster Schritt: Besichtigung\nAntwortvorschlag: Gerne, passt Dienstag 10 Uhr?",
            citations=["r1"],
            unverified_claims=[],
            model="gpt-test",
            input_tokens=10,
            output_tokens=10,
            estimated_cost_microunits=10,
        ),
    )
    job = client.post(
        f"{w}/today/replies",
        json={"action_id": message_action.id, "text": "Gern, kommen Sie vorbei."},
    )
    assert job.status_code == 202, job.text
    assert execute_one(ws)
    result = client.get(f"{w}/jobs/{job.json()['id']}").json()["result"]
    assert result["next_step"] == "Besichtigung" and result["sent"] is False


def test_brave_candidates_are_transient_and_scored(context, admin, monkeypatch):
    client, (ws, *_), _ = context
    seed(admin, ws, 1)
    w = f"/v1/workspaces/{ws}"
    client.post(f"{w}/contacts/from-impressum", json={})
    contact = admin.scalar(
        select(Contact).where(Contact.workspace_id == ws, Contact.last_name == "Fiktiv0")
    )
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "synthetic-brave")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "url": "https://de.linkedin.com/in/erika-fiktiv0",
                            "title": "Erika Fiktiv0 – Synthetische Kanzlei 0",
                            "description": "Offenburg",
                        },
                        {
                            "url": "https://www.linkedin.com/in/someone-else",
                            "title": "Erika Andere",
                            "description": "Berlin",
                        },
                        {
                            "url": "https://www.linkedin.com/company/x",
                            "title": "Firma",
                            "description": "",
                        },
                    ]
                }
            },
        )

    real = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *a, **k: real(
            *a,
            transport=httpx.MockTransport(handler),
            **{x: y for x, y in k.items() if x != "transport"},
        ),
    )
    r = client.get(f"{w}/contacts/{contact.id}/linkedin-candidates").json()
    assert [c["url"] for c in r["items"]] == [
        "https://www.linkedin.com/in/erika-fiktiv0/",
        "https://www.linkedin.com/in/someone-else/",
    ]
    assert r["items"][0]["confidence"] > r["items"][1]["confidence"]
    assert seen[0].url.params["q"] == 'linkedin "Erika Fiktiv0" Synthetische Offenburg'
    assert r["fallback_search_url"].startswith("https://www.linkedin.com/search/results/people/")
    # Cached in memory only: a second call does not hit Brave again, nothing stored on the contact.
    client.get(f"{w}/contacts/{contact.id}/linkedin-candidates")
    assert len(seen) == 1
    admin.refresh(contact)
    assert contact.linkedin_url is None
