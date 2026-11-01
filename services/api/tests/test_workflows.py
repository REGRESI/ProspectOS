import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import scoped
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.db import SessionLocal, now
from app.imports import DEFAULT_MAPPING, HEADERS, normalize_url, parse_csv
from app.main import app
from app.models import Company, Contact, Membership
from app.schemas import Schedule


def url(ws, path):
    return f"/v1/workspaces/{ws}/{path}"


def fixture_csv(count=773, delimiter=","):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=HEADERS, delimiter=delimiter)
    writer.writeheader()
    for i in range(count):
        writer.writerow(
            {
                "First Name": f"Demo{i}",
                "Last Name": "Müller'Beispiel",
                "Company Name": f"Demo Büro{i // 4}" if i else "",
                "Job title": "Office Manager" if i else "",
                "Company Location": "Offenburg",
                "Linkedin Profile Url": f"https://www.linkedin.com/in/fictional-{i}/?tracking=demo",
                "Linkedin Company Url": f"https://www.linkedin.com/company/fictional-{i // 4}",
            }
        )
    return ("\ufeff" + stream.getvalue()).encode()


def preview(client, ws, count=3):
    response = client.post(
        url(ws, "imports/preview"), files={"file": ("demo.csv", fixture_csv(count), "text/csv")}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_import_773_reimport_and_empty_fields(context):
    c, (ws, *_), _ = context
    result = preview(c, ws, 773)
    assert result["total"] == result["valid"] == 773
    assert result["invalid"] == 0
    assert result["rows"][0]["company"] == ""
    commit = c.post(url(ws, f"imports/{result['id']}/commit"))
    assert commit.status_code == 200, commit.text
    assert commit.json()["created"] == 773
    assert c.post(url(ws, f"imports/{result['id']}/commit")).json() == commit.json()
    page = c.get(url(ws, "contacts"), params={"limit": 25}).json()
    assert page["total"] == 773 and len(page["items"]) == 25
    assert all(x["email"] is None and x["phone"] is None for x in page["items"])
    second = preview(c, ws, 773)
    assert second["duplicates"] == 773
    assert c.post(url(ws, f"imports/{second['id']}/commit")).json()["created"] == 0


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_csv_unicode_delimiters(delimiter):
    headers, mapping, rows = parse_csv(fixture_csv(4, delimiter))
    assert headers == HEADERS and mapping == DEFAULT_MAPPING
    assert rows[0]["last_name"] == "Müller'Beispiel"
    assert rows[0]["linkedin_url"] == "https://www.linkedin.com/in/fictional-0"


@pytest.mark.parametrize(
    "bad",
    [
        "javascript:alert(1)",
        "https://linkedin.com.evil.test/in/a",
        "https://www.linkedin.com/in/",
        "https://u:p@linkedin.com/in/a",
        "https://linkedin.com:443/in/a",
        "https://127.0.0.1/in/a",
    ],
)
def test_url_validation(bad):
    with pytest.raises(ValueError):
        normalize_url(bad)


def test_mapping_validation_errors_and_duplicate_rows(context):
    c, (ws, *_), _ = context
    payload = "Vorname;Profil\nAnna;https://www.linkedin.com/in/demo-a\nAnna;https://www.linkedin.com/in/demo-a\nBob;not-a-url\n"
    r = c.post(
        url(ws, "imports/preview"),
        files={"file": ("demo.csv", payload.encode())},
        data={"mapping": '{"first_name":"Vorname","linkedin_url":"Profil"}'},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["duplicates"] == 1 and result["invalid"] == 1
    summary = c.post(url(ws, f"imports/{result['id']}/commit")).json()
    assert summary == {"created": 1, "duplicates": 1, "invalid": 1, "status": "completed"}


def test_rollback_preserves_edits_and_companies(context):
    c, (ws, *_), _ = context
    result = preview(c, ws)
    c.post(url(ws, f"imports/{result['id']}/commit"))
    lead = c.get(url(ws, "contacts")).json()["items"][0]
    body = {
        k: lead[k]
        for k in (
            "first_name",
            "last_name",
            "company",
            "job_title",
            "location",
            "email",
            "phone",
            "linkedin_url",
            "status",
            "version",
        )
    }
    body["job_title"] = "Human edit"
    assert c.patch(url(ws, f"contacts/{lead['id']}"), json=body).status_code == 200
    rollback = c.post(url(ws, f"imports/{result['id']}/rollback")).json()
    assert rollback["deleted"] == 2 and rollback["conflicts"] == [lead["id"]]
    assert c.get(url(ws, "contacts")).json()["total"] == 1
    assert c.get(url(ws, "companies")).json()["total"] > 0


def test_tenant_api_read_update_delete_and_foreign_workspace(context, admin):
    c, (a, b, private), _ = context
    lead = c.post(url(b, "contacts"), json={"first_name": "Tenant B"}).json()
    for method in ("get", "patch", "delete"):
        kwargs = {"json": {"first_name": "Attacker"}} if method == "patch" else {}
        assert getattr(c, method)(url(a, f"contacts/{lead['id']}"), **kwargs).status_code == 404
    assert c.get(url(private, "contacts")).status_code == 404
    assert (
        c.post(
            url(a, "deals"), json={"title": "Cross-tenant", "contact_id": lead["id"]}
        ).status_code
        == 404
    )
    assert c.get(url(a, "contacts")).json()["total"] == 0


def test_rls_missing_context_mismatch_and_composite_fk(context, admin):
    c, (a, b, *_), _ = context
    company = Company(workspace_id=b, name="Private", identity=str(uuid4()))
    admin.add(company)
    admin.commit()
    with SessionLocal() as db:
        assert db.scalars(select(Company)).all() == []
        scoped(db, a)
        assert db.get(Company, company.id) is None
        with pytest.raises(IntegrityError):
            db.add(Contact(workspace_id=a, company_id=company.id, first_name="Forbidden"))
            db.flush()
        db.rollback()
        with pytest.raises(ProgrammingError):
            db.add(Contact(workspace_id=a, first_name="No context"))
            db.flush()


def test_app_role_cannot_mutate_audit_or_bypass(context):
    c, (ws, *_), _ = context
    c.post(url(ws, "contacts"), json={"first_name": "Audit"})
    with SessionLocal() as db:
        scoped(db, ws)
        assert db.execute(
            text("SELECT rolbypassrls,rolsuper FROM pg_roles WHERE rolname=current_user")
        ).one() == (False, False)
        with pytest.raises(ProgrammingError):
            db.execute(text("DELETE FROM audit_events"))


def test_csrf_logout_and_unauthenticated(context):
    c, (ws, *_), _ = context
    token = c.headers.pop("X-CSRF-Token")
    assert c.post(url(ws, "contacts"), json={"first_name": "Blocked"}).status_code == 403
    c.headers["X-CSRF-Token"] = token
    assert c.post("/v1/auth/logout").status_code == 200
    assert c.get(url(ws, "contacts")).status_code == 401


def test_analyst_and_approver_permissions(context, admin):
    c, (ws, *_), user = context
    membership = admin.get(Membership, (ws, user))
    membership.role = "analyst"
    admin.commit()
    assert c.get(url(ws, "contacts")).status_code == 200
    assert c.post(url(ws, "contacts"), json={"first_name": "No"}).status_code == 403
    membership.role = "approver"
    admin.commit()
    assert c.post(url(ws, "social/posts"), json={"caption": "No"}).status_code == 403


def test_scoring_unknowns_and_profile_updates(context):
    c, (ws, *_), _ = context
    r = c.post(
        url(ws, "contacts"),
        json={"first_name": "Demo", "location": "Offenburg", "job_title": "Office Manager"},
    )
    assert r.status_code == 201, r.text
    lead = r.json()
    assert lead["score"]["value"] == 70
    assert "Branche" in lead["score"]["missing_data"]
    icp = c.get(url(ws, "icp")).json()
    icp["weights"] = {"location": 50, "role": 50, "industry": 0}
    assert c.put(url(ws, "icp"), json=icp).status_code == 200
    assert c.get(url(ws, f"contacts/{lead['id']}")).json()["score"]["value"] == 100
    icp["weights"]["role"] = 1
    assert c.put(url(ws, "icp"), json=icp).status_code == 422


def test_social_revision_schedule_and_conflict(context):
    c, (ws, *_), _ = context
    p = c.post(url(ws, "social/posts"), json={"caption": "First revision"}).json()
    path = url(ws, f"social/posts/{p['id']}")
    assert c.post(path + "/approve").status_code == 409
    assert c.post(path + "/submit-review").status_code == 200
    assert c.post(path + "/approve").json()["approved_revision"] == 1
    scheduled = c.post(
        path + "/schedule", json={"scheduled_at": (now() + timedelta(days=2)).isoformat()}
    )
    assert scheduled.status_code == 200, scheduled.text
    assert scheduled.json()["state"] == "scheduled"
    edited = c.patch(path, json={"caption": "Edited", "version": 1}).json()
    assert (
        edited["state"] == "needs_review"
        and edited["approved_revision"] is None
        and edited["scheduled_at"] is None
    )
    assert c.patch(path, json={"caption": "stale", "version": 1}).status_code == 409
    assert (
        c.post(
            path + "/schedule", json={"scheduled_at": (now() + timedelta(days=2)).isoformat()}
        ).status_code
        == 409
    )


def test_schedule_timezone_dst():
    with pytest.raises(ValueError):
        Schedule(scheduled_at="2027-10-31T02:30:00")
    a = Schedule(scheduled_at="2027-10-31T02:30:00+02:00")
    b = Schedule(scheduled_at="2027-10-31T02:30:00+01:00")
    assert a.scheduled_at.timestamp() != b.scheduled_at.timestamp()


def test_outreach_no_send_and_discovery_honesty(context):
    c, (ws, *_), _ = context
    run = c.post(url(ws, "discovery/runs"), json={"topic": "Office teams near Offenburg"}).json()
    assert "synthetisch" in run["notice"]
    assert all(row["source"] == "synthetic_demo" for row in run["results"])
    assert c.post(url(ws, f"discovery/runs/{run['id']}/import")).json()["created"] == 5
    assert c.post(url(ws, f"discovery/runs/{run['id']}/import")).json()["created"] == 0
    lead = c.get(url(ws, "contacts")).json()["items"][0]
    draft = c.post(url(ws, "outreach/drafts"), json={"contact_id": lead["id"]}).json()
    assert draft["send_allowed"] is False and draft["source"] == "offline"
    assert c.post(url(ws, f"outreach/drafts/{draft['id']}/send")).status_code == 404
    integrations = c.get(url(ws, "integrations")).json()
    assert all(i["status"] == "not_configured" for i in integrations["items"])


def test_pagination_validation(context):
    c, (ws, *_), _ = context
    assert c.get(url(ws, "contacts"), params={"limit": 101}).status_code == 422
    assert c.get(url(ws, "contacts"), params={"page": 0}).status_code == 422


def test_production_fails_closed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="Production auth"):
        with TestClient(app):
            pass


def test_concurrent_import_idempotency(context):
    c, (ws, *_), _ = context
    previews = [preview(c, ws, 10) for _ in range(2)]

    def commit(job):
        # Independent clients, connections and HTTP requests; shared authenticated session.
        with TestClient(app) as client:
            client.cookies.update(c.cookies)
            client.headers.update({"X-CSRF-Token": c.headers["X-CSRF-Token"]})
            return client.post(url(ws, f"imports/{job['id']}/commit"))

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(commit, previews))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert sum(r.json()["created"] for r in results) == 10
    assert c.get(url(ws, "contacts")).json()["total"] == 10


def test_cancel_editorial_schedule(context):
    c, (ws, *_), _ = context
    post = c.post(url(ws, "social/posts"), json={"caption": "Calendar test"}).json()
    path = url(ws, f"social/posts/{post['id']}")
    c.post(path + "/submit-review")
    c.post(path + "/approve")
    c.post(path + "/schedule", json={"scheduled_at": (now() + timedelta(days=1)).isoformat()})
    result = c.post(path + "/cancel")
    assert result.status_code == 200
    assert result.json()["scheduled_at"] is None and result.json()["state"] == "approved"
