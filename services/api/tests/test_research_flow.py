"""M3 website/Impressum research. All sites, companies and people are synthetic fixtures;
HTTP is transport-mocked and DNS is injected (no network access)."""

import httpx
import pytest
from sqlalchemy import select

from app.jobs import execute_one
from app.journeys import CompanyFact
from app.models import Company
from app.providers import site_research
from app.providers.ai import GenerationResult, ProviderError
from app.providers.web_guard import GuardedTransport

PUBLIC_IP = "93.184.215.14"

HOME = """<html><head><title>Fiktiv Reinigung</title><script>var x='Impressum GmbH';</script></head>
<body><h1>Willkommen bei Fiktiv</h1><p>Wir betreuen Büros in Synthetic Town.</p>
<footer><a href="/rechtliches/impressum">Impressum</a></footer></body></html>"""

IMPRESSUM = """<html><body><h1>Impressum</h1>
<p>Fiktive Büroservice GmbH</p><p>Musterstraße 12</p><p>77600 Synthetic Town</p>
<table><tr><td>Telefon:</td><td>+49 781 000000</td></tr></table>
<p>E-Mail: info (at) fiktiv-buero (dot) example</p>
<p>Vertreten durch den Geschäftsführer:</p><p>Dr. Erika Musterfrau und Max Beispiel</p>
<p>Registergericht: Amtsgericht Synthetic Town, HRB 712345</p>
<p>USt-IdNr.: DE 123 456 789</p>
<p>Konzept und Design: Webagentur Kreativ GmbH</p></body></html>"""


def site_client(routes, resolver=lambda host, port: PUBLIC_IP, seen=None):
    def handler(request: httpx.Request):
        key = request.headers["host"] + request.url.path
        if seen is not None:
            seen.append(
                (request.url.host, request.headers["host"], request.extensions.get("sni_hostname"))
            )
        status, body, headers = routes.get(key, (404, "", {}))
        return httpx.Response(
            status, text=body, headers={"content-type": "text/html; charset=utf-8", **headers}
        )

    return httpx.Client(
        transport=GuardedTransport(httpx.MockTransport(handler), resolver=resolver),
        follow_redirects=False,
        trust_env=False,
    )


@pytest.fixture
def research_on(monkeypatch):
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setattr(site_research.time, "sleep", lambda s: None)


def test_impressum_extraction_variants():
    page = site_research._parse("https://fiktiv.example/impressum", "text/html", IMPRESSUM)
    f = site_research.extract_impressum(page)
    assert f["company"]["value"] == "Fiktive Büroservice GmbH"
    assert f["legal_form"]["value"] == "GmbH"
    assert f["address"]["value"] == "Musterstraße 12, 77600 Synthetic Town"
    assert f["phone"]["value"] == "+49 781 000000"
    assert f["email"]["value"] == "info@fiktiv-buero.example"
    assert f["managers"]["value"] == "Erika Musterfrau, Max Beispiel"
    assert f["register_id"]["value"] == "HRB 712345"
    assert f["register_court"]["value"] == "Amtsgericht Synthetic Town"
    assert f["vat_id"]["value"] == "DE123456789"
    assert all(v["source_url"] == "https://fiktiv.example/impressum" for v in f.values())
    # Agency credit line is never taken as the company.
    assert "Webagentur" not in f["company"]["value"]


def test_inline_footer_company_and_board():
    html = (
        "<p>Diese Seiten sind Eigentum der Fiktiv Tunnelbau AG.</p>"
        "<p>Vorstand: Dr.-Ing. E.h. Max Fiktiv (Vorsitzender), Dipl.-Ing. (FH) Eva Probe</p>"
        "<p>Aufsichtsrat: Hans Nicht</p>"
    )
    f = site_research.extract_impressum(
        site_research._parse("https://t.example/i", "text/html", html)
    )
    assert f["company"]["value"] == "Fiktiv Tunnelbau AG"
    assert f["managers"]["value"] == "Max Fiktiv, Eva Probe"


def test_site_research_follows_impressum_link_and_pins_ip(research_on):
    seen = []
    routes = {
        "fiktiv.example/robots.txt": (
            200,
            "User-agent: *\nDisallow: /intern/",
            {"content-type": "text/plain"},
        ),
        "fiktiv.example/": (301, "", {"location": "https://www.fiktiv.example/"}),
        "www.fiktiv.example/robots.txt": (
            200,
            "User-agent: *\nAllow: /",
            {"content-type": "text/plain"},
        ),
        "www.fiktiv.example/": (200, HOME, {}),
        "www.fiktiv.example/rechtliches/impressum": (200, IMPRESSUM, {}),
    }
    result = site_research.research_site(
        "https://fiktiv.example", client=site_client(routes, seen=seen)
    )
    assert result["impressum_url"] == "https://www.fiktiv.example/rechtliches/impressum"
    assert result["impressum"]["register_id"]["value"] == "HRB 712345"
    assert "Impressum GmbH" not in result["pages"][0]["text"]  # scripts dropped
    # Every request went to the validated IP with the original Host header and SNI.
    assert all(ip == PUBLIC_IP and sni == host for ip, host, sni in seen)


def test_robots_disallow_and_foreign_redirect_are_refused(research_on):
    blocked = {
        "fiktiv.example/robots.txt": (
            200,
            "User-agent: *\nDisallow: /",
            {"content-type": "text/plain"},
        ),
    }
    with pytest.raises(ProviderError, match="robots_disallowed"):
        site_research.research_site("https://fiktiv.example/", client=site_client(blocked))
    foreign = {
        "fiktiv.example/": (
            200,
            HOME.replace("/rechtliches/impressum", "https://evil.example/impressum"),
            {},
        ),
        "evil.example/impressum": (200, IMPRESSUM, {}),
    }
    result = site_research.research_site("https://fiktiv.example/", client=site_client(foreign))
    assert result["impressum_url"] is None  # the foreign link was never followed


def test_private_dns_result_is_blocked(research_on, monkeypatch):
    from app.providers import web_guard

    monkeypatch.setattr(
        web_guard.socket,
        "getaddrinfo",
        lambda host, port, type=0: [(2, 1, 6, "", ("10.0.0.7", port))],
    )
    with pytest.raises(ProviderError, match="unsafe_url"):
        site_research.research_site(
            "https://fiktiv.example/", client=site_client({}, resolver=web_guard.resolve_public)
        )


def test_disabled_without_flag(monkeypatch):
    monkeypatch.delenv("RESEARCH_ENABLED", raising=False)
    with pytest.raises(ProviderError, match="research_disabled"):
        site_research.research_site("https://fiktiv.example/")


def test_batch_research_facts_and_cited_profile(context, admin, research_on, monkeypatch):
    client, (ws, other, *_), _ = context
    company = Company(
        workspace_id=ws,
        name="Fiktive Büroservice GmbH",
        identity="osm:node/1",
        website="https://www.fiktiv.example/",
        provenance={},
    )
    foreign = Company(
        workspace_id=other,
        name="Fremd",
        identity="osm:node/2",
        website="https://x.example",
        provenance={},
    )
    admin.add_all([company, foreign])
    admin.commit()

    def fake(url, client=None):
        page = site_research._parse(
            "https://www.fiktiv.example/rechtliches/impressum", "text/html", IMPRESSUM
        )
        return {
            "website": "https://www.fiktiv.example/",
            "retrieved_at": "2026-11-04T10:00:00+00:00",
            "impressum_url": page["url"],
            "impressum": site_research.extract_impressum(page),
            "pages": [
                {
                    "url": "https://www.fiktiv.example/",
                    "title": "",
                    "text": "Wir betreuen Büros in Synthetic Town.",
                },
                {"url": page["url"], "title": "", "text": "\n".join(page["lines"])},
            ],
            "robots": "honoured",
        }

    monkeypatch.setattr(site_research, "research_site", fake)
    # Forged company id from another workspace is rejected.
    assert (
        client.post(
            f"/v1/workspaces/{ws}/companies/research-batch", json={"company_ids": [foreign.id]}
        ).status_code
        == 422
    )
    queued = client.post(f"/v1/workspaces/{ws}/companies/research-batch", json={"limit": 10})
    assert queued.status_code == 202 and queued.json()["queued"] == 1
    assert execute_one(ws)
    facts = {
        f.field: f
        for f in admin.scalars(
            select(CompanyFact).where(
                CompanyFact.workspace_id == ws, CompanyFact.company_id == company.id
            )
        )
    }
    assert facts["Handelsregister"].value == "HRB 712345"
    assert facts["Geschäftsführung / Inhaber"].value == "Erika Musterfrau, Max Beispiel"
    assert facts["Handelsregister"].source_url.endswith("/rechtliches/impressum")
    assert {f.source_kind for f in facts.values()} == {"website_impressum", "data_quality"}
    # Name ↔ domain ↔ Impressum plausibility is recorded alongside the Impressum facts.
    assert facts["Website-Abgleich"].value.split(":")[0] in ("passt", "unklar", "unstimmig")
    # Second batch skips already researched companies.
    assert (
        client.post(f"/v1/workspaces/{ws}/companies/research-batch", json={}).json()["queued"] == 0
    )

    # AI profile: only lines with valid citations are stored.
    monkeypatch.setenv("LLM_API_KEY", "synthetic")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setenv("LLM_INPUT_USD_PER_MILLION", "0.4")
    monkeypatch.setenv("LLM_OUTPUT_USD_PER_MILLION", "1.6")
    text = (
        "Tätigkeit: Büroservice für Unternehmen [p1]\n"
        "Standorte: Synthetic Town [p2]\n"
        "Hinweise Bürofläche: unbekannt\n"
        "Hinweise Mitarbeitende: 500 Personen [p9]\n"
        "Anknüpfungspunkte: betreut Büros in der Region [p1]"
    )
    monkeypatch.setattr(
        "app.providers.ai.generate_text",
        lambda prompt, sources=None, client=None: GenerationResult(
            text=text,
            citations=["p1", "p2"],
            unverified_claims=[],
            model="gpt-test",
            input_tokens=100,
            output_tokens=50,
            estimated_cost_microunits=120,
        ),
    )
    r = client.post(f"/v1/workspaces/{ws}/companies/{company.id}/profile")
    assert r.status_code == 202, r.text
    assert execute_one(ws)
    profile = {
        f.field: f
        for f in admin.scalars(
            select(CompanyFact).where(
                CompanyFact.workspace_id == ws, CompanyFact.source_kind == "ai_profile"
            )
        )
    }
    assert set(profile) == {
        "KI-Profil: Tätigkeit",
        "KI-Profil: Standorte",
        "KI-Profil: Anknüpfungspunkte",
    }
    assert profile["KI-Profil: Standorte"].source_url.endswith("/rechtliches/impressum")
    usage = client.get(f"/v1/workspaces/{ws}/usage").json()
    assert usage["ai_reserved_minor"] == 0 and usage["ai_spent_minor"] >= 1


def test_label_prefix_and_technical_mailbox_are_handled():
    html = (
        "<h1>Impressum</h1><p>Gesetzliche Anbieterkennung: Fiktiv Karosserie OHG</p>"
        "<p>E-Mail: technik@fiktiv.example</p><p>Kontakt: info@fiktiv.example</p>"
    )
    f = site_research.extract_impressum(
        site_research._parse("https://f.example/i", "text/html", html)
    )
    assert f["company"]["value"] == "Fiktiv Karosserie OHG"
    assert f["email"]["value"] == "info@fiktiv.example"
    page = site_research._parse(
        "https://f.example/i",
        "text/html",
        "<p>Anbieter: Fiktiv AG</p><a href='mailto:webmaster@f.example'>W</a><a href='mailto:hallo@f.example'>H</a>",
    )
    f = site_research.extract_impressum(page)
    assert f["company"]["value"] == "Fiktiv AG" and f["email"]["value"] == "hallo@f.example"
