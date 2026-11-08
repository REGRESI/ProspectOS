"""Adapters for external outreach tools (M9b). Opt-in, at the user's own risk.

ProspectOS never automates LinkedIn itself. These adapters only talk to the official APIs
of third-party tools where the user has their own account; the tools do the automation.
Every adapter has the same interface:

- ``test(cfg)``: check the key,
- ``campaigns(cfg)``: list target campaigns (if the API offers it),
- ``push_contacts(cfg, target, leads)``: hand contacts over to a campaign,
- ``pause_contact(cfg, handoff)``: stop a contact in the tool (``None`` = API can't),
- ``fetch_status(cfg, handoff)``: read the lead's state (``None`` = API can't),
- ``parse_webhook(body)``: normalise inbound events to
  ``{"kind": invite_sent|accepted|message_sent|replied|other, "linkedin_url", "external_ref", "text", "event_id"}``.

Endpoint facts come from the vendors' public docs read on 2026-11-08 (see
docs/CONNECTORS.md). Anything marked ``UNVERIFIED`` there is a best-effort guess and is
tolerant by design (unknown payloads become ``other`` and are ignored).
"""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

from app.providers.ai import ProviderError, request_json
from app.providers.web_guard import check_url, guarded_client

EVENT_KINDS = ("invite_sent", "accepted", "message_sent", "replied", "other")


def user_url_request(method, url, client=None, **kwargs):
    """Requests to URLs the user typed in (generic webhook, Expandi campaign URL) go through
    the egress guard: https only, public addresses only, pinned IP, no redirects."""
    if urlsplit(url).scheme != "https":
        raise ProviderError("unsafe_url")
    check_url(url)
    own = client is None
    client = client or guarded_client(30.0)
    try:
        return request_json(method, url, client=client, **kwargs)
    finally:
        if own:
            client.close()


def normalize_linkedin(url: str | None) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip() if "://" in url else "https://" + url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    if not host.endswith("linkedin.com"):
        return ""
    path = parts.path.rstrip("/").lower()
    return f"https://www.linkedin.com{path}" if path.startswith("/in/") else ""


def _dig(data, *paths):
    """First non-empty value among dotted paths, e.g. 'lead.profile_url'."""
    for path in paths:
        value = data
        for part in path.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if value not in (None, "", [], {}):
            return value
    return None


@dataclass
class Lead:
    contact_id: str
    first_name: str
    last_name: str
    company: str
    job_title: str
    linkedin_url: str
    email: str | None = None  # only set when an e-mail legal basis exists


@dataclass
class ToolSpec:
    id: str
    label: str
    docs: str
    price_hint: str
    can: list = field(default_factory=list)
    cannot: list = field(default_factory=list)
    secret_fields: tuple = ("api_key",)
    config_fields: tuple = ()
    webhook_events: tuple = ()


class Adapter:
    spec: ToolSpec

    def test(self, cfg, client=None) -> dict:
        raise NotImplementedError

    def campaigns(self, cfg, client=None) -> list[dict] | None:
        return None

    def push_contacts(self, cfg, target: str, leads: list[Lead], client=None) -> list[dict]:
        raise NotImplementedError

    def pause_contact(self, cfg, handoff: dict, client=None) -> dict | None:
        return None

    def fetch_status(self, cfg, handoff: dict, client=None) -> dict | None:
        return None

    def parse_webhook(self, body: dict) -> list[dict]:
        return []


def _event(kind, url, ref=None, text="", event_id=None):
    return {
        "kind": kind if kind in EVENT_KINDS else "other",
        "linkedin_url": normalize_linkedin(url),
        "external_ref": str(ref) if ref not in (None, "") else None,
        "text": (text or "")[:4000],
        "event_id": str(event_id) if event_id not in (None, "") else None,
    }


# ---- HeyReach ---------------------------------------------------------------------------


class HeyReach(Adapter):
    BASE = "https://api.heyreach.io"  # UNVERIFIED host: the Postman collection uses a placeholder
    EVENTS = {
        "CONNECTION_REQUEST_SENT": "invite_sent",
        "CONNECTION_REQUEST_ACCEPTED": "accepted",
        "MESSAGE_SENT": "message_sent",
        "INMAIL_SENT": "message_sent",
        "MESSAGE_REPLY_RECEIVED": "replied",
        "INMAIL_REPLY_RECEIVED": "replied",
        "EVERY_MESSAGE_REPLY_RECEIVED": "replied",
    }
    spec = ToolSpec(
        id="heyreach",
        label="HeyReach",
        docs="https://documenter.getpostman.com/view/23808049/2sA2xb5F75",
        price_hint="ca. 79 $ pro LinkedIn-Konto und Monat (unverifiziert, beim Anbieter prüfen)",
        can=[
            "Kontakte in eine gestartete Kampagne schicken",
            "Kontakt in der Kampagne stoppen",
            "Status eines Kontakts abfragen",
            "Webhooks für Annahme, Nachricht, Antwort",
        ],
        cannot=[
            "Kampagnen anlegen oder starten aus ProspectOS",
            "Signatur für Webhooks (Absicherung nur über geheime URL)",
        ],
        config_fields=("linkedin_account_id",),
        webhook_events=tuple(EVENTS),
    )

    def _headers(self, cfg):
        return {"X-API-KEY": cfg["api_key"], "Accept": "application/json"}

    def test(self, cfg, client=None):
        request_json(
            "GET",
            self.BASE + "/api/public/auth/CheckApiKey",
            client=client,
            headers=self._headers(cfg),
        )
        return {"ok": True}

    def campaigns(self, cfg, client=None):
        data, _ = request_json(
            "POST",
            self.BASE + "/api/public/campaign/GetAll",
            client=client,
            headers=self._headers(cfg),
            json={"offset": 0, "limit": 100},
        )
        items = data.get("items") or data.get("campaigns") or []
        return [
            {"id": str(c.get("id")), "name": c.get("name", ""), "status": c.get("status", "")}
            for c in items
            if isinstance(c, dict)
        ]

    def push_contacts(self, cfg, target, leads, client=None):
        account = cfg.get("linkedin_account_id")
        pairs = []
        for lead in leads:
            item = {
                "lead": {
                    "firstName": lead.first_name,
                    "lastName": lead.last_name,
                    "companyName": lead.company,
                    "position": lead.job_title,
                    "profileUrl": lead.linkedin_url,
                    **({"emailAddress": lead.email} if lead.email else {}),
                }
            }
            if account:
                item["linkedInAccountId"] = int(account)
            pairs.append(item)
        request_json(
            "POST",
            self.BASE + "/api/public/campaign/AddLeadsToCampaignV2",
            client=client,
            side_effect=True,
            headers=self._headers(cfg),
            json={
                "campaignId": int(target),
                "accountLeadPairs": pairs,
                "resumeFinishedCampaign": False,
                "resumePausedCampaign": False,
            },
        )
        return [
            {"contact_id": lead.contact_id, "external_ref": lead.linkedin_url} for lead in leads
        ]

    def pause_contact(self, cfg, handoff, client=None):
        request_json(
            "POST",
            self.BASE + "/api/public/campaign/StopLeadInCampaign",
            client=client,
            side_effect=True,
            headers=self._headers(cfg),
            json={"campaignId": int(handoff["target"]), "leadUrl": handoff["linkedin_url"]},
        )
        return {"paused": True}

    def fetch_status(self, cfg, handoff, client=None):
        data, _ = request_json(
            "POST",
            self.BASE + "/api/public/lead/GetLead",
            client=client,
            headers=self._headers(cfg),
            json={"profileUrl": handoff["linkedin_url"]},
        )
        return {"raw_status": str(_dig(data, "status", "leadStatus") or "unbekannt")}

    def parse_webhook(self, body):
        # Payload shape UNVERIFIED (not in the collection): tolerant field lookup.
        kind = self.EVENTS.get(
            str(_dig(body, "eventType", "event_type", "type") or "").upper(), "other"
        )
        url = _dig(
            body, "lead.profileUrl", "lead.profile_url", "profileUrl", "profile_url", "linkedin_url"
        )
        text = _dig(body, "message", "lastMessage", "message.text") or ""
        return [
            _event(
                kind, url, url, text if isinstance(text, str) else "", _dig(body, "id", "eventId")
            )
        ]


# ---- lemlist --------------------------------------------------------------------------------


class Lemlist(Adapter):
    BASE = "https://api.lemlist.com/api"
    EVENTS = {
        "linkedinInviteDone": "invite_sent",
        "linkedinInviteAccepted": "accepted",
        "linkedinSent": "message_sent",
        "linkedinReplied": "replied",
        "emailsReplied": "replied",
    }
    spec = ToolSpec(
        id="lemlist",
        label="lemlist",
        docs="https://developer.lemlist.com/",
        price_hint="Tarif mit LinkedIn-Schritten nötig; Preis unverifiziert, beim Anbieter prüfen",
        can=[
            "Kontakt in eine Kampagne anlegen",
            "Kontakt pausieren",
            "Status abfragen",
            "Webhooks mit gemeinsamem Geheimnis",
        ],
        cannot=["Leads aktualisieren über diesen Anschluss (nur neu anlegen)"],
        webhook_events=tuple(EVENTS),
    )

    def _headers(self, cfg):
        token = base64.b64encode((":" + cfg["api_key"]).encode()).decode()
        return {"Authorization": "Basic " + token}

    def test(self, cfg, client=None):
        request_json("GET", self.BASE + "/team", client=client, headers=self._headers(cfg))
        return {"ok": True}

    def campaigns(self, cfg, client=None):
        data, _ = request_json(
            "GET", self.BASE + "/campaigns", client=client, headers=self._headers(cfg)
        )
        items = (
            data.get("campaigns")
            if isinstance(data.get("campaigns"), list)
            else data.get("items", [])
        )
        return [
            {"id": c.get("_id", ""), "name": c.get("name", ""), "status": c.get("status", "")}
            for c in items or []
            if isinstance(c, dict)
        ]

    def push_contacts(self, cfg, target, leads, client=None):
        out = []
        for lead in leads:
            body = {
                "linkedinUrl": lead.linkedin_url,
                "firstName": lead.first_name,
                "lastName": lead.last_name,
                "companyName": lead.company,
                "jobTitle": lead.job_title,
                **({"email": lead.email} if lead.email else {}),
            }
            data, _ = request_json(
                "POST",
                f"{self.BASE}/campaigns/{quote(target)}/leads/?deduplicate=true",
                client=client,
                side_effect=True,
                headers=self._headers(cfg),
                json=body,
            )
            out.append(
                {
                    "contact_id": lead.contact_id,
                    "external_ref": data.get("_id") or lead.linkedin_url,
                }
            )
            time.sleep(0.11)  # documented limit: 20 requests per 2 seconds
        return out

    def pause_contact(self, cfg, handoff, client=None):
        if not str(handoff.get("external_ref", "")).startswith("lea_"):
            return None
        request_json(
            "POST",
            f"{self.BASE}/leads/pause/{quote(handoff['external_ref'])}?campaignId={quote(handoff['target'])}",
            client=client,
            side_effect=True,
            headers=self._headers(cfg),
        )
        return {"paused": True}

    def fetch_status(self, cfg, handoff, client=None):
        if not str(handoff.get("external_ref", "")).startswith("lea_"):
            return None
        data, _ = request_json(
            "GET",
            f"{self.BASE}/leads?id={quote(handoff['external_ref'])}",
            client=client,
            headers=self._headers(cfg),
        )
        return {"raw_status": str(_dig(data, "state", "status") or "unbekannt")}

    def parse_webhook(self, body):
        kind = self.EVENTS.get(str(body.get("type", "")), "other")
        return [
            _event(
                kind,
                body.get("linkedinUrl"),
                body.get("leadId"),
                body.get("text") or "",
                body.get("_id"),
            )
        ]


# ---- Waalaxy ------------------------------------------------------------------------------


class Waalaxy(Adapter):
    BASE = "https://api.waalaxy.com"
    spec = ToolSpec(
        id="waalaxy",
        label="Waalaxy",
        docs="https://docs.waalaxy.com/introduction",
        price_hint="ca. 0 bis 99 € pro Monat (unverifiziert, beim Anbieter prüfen)",
        can=["Kontakte in eine Liste und Kampagne importieren", "Kampagnen und Listen anzeigen"],
        cannot=[
            "Kontakt pausieren (in der Doku nicht beschrieben)",
            "Webhooks (Rückmeldung nur über Zapier/Make an den allgemeinen Webhook)",
        ],
        config_fields=("prospect_list_id",),
    )

    def _headers(self, cfg):
        return {"Authorization": "Bearer " + cfg["api_key"]}

    def test(self, cfg, client=None):
        request_json(
            "GET", self.BASE + "/integrations/test", client=client, headers=self._headers(cfg)
        )
        return {"ok": True}

    def campaigns(self, cfg, client=None):
        data, _ = request_json(
            "GET", self.BASE + "/campaigns/getAll", client=client, headers=self._headers(cfg)
        )
        items = data.get("campaigns") or data.get("items") or []
        return [
            {"id": c.get("_id", ""), "name": c.get("name", ""), "status": c.get("status", "")}
            for c in items
            if isinstance(c, dict)
        ]

    def push_contacts(self, cfg, target, leads, client=None):
        if not cfg.get("prospect_list_id"):
            raise ProviderError("missing_prospect_list")
        request_json(
            "POST",
            self.BASE + "/prospects/addProspectFromIntegration",
            client=client,
            side_effect=True,
            headers=self._headers(cfg),
            json={
                "prospects": [{"url": lead.linkedin_url} for lead in leads],
                "prospectListId": cfg["prospect_list_id"],
                **({"campaignId": target} if target else {}),
                "origin": {"name": "prospectos"},
            },
        )
        return [
            {"contact_id": lead.contact_id, "external_ref": lead.linkedin_url} for lead in leads
        ]


# ---- La Growth Machine ---------------------------------------------------------------------


class LaGrowthMachine(Adapter):
    BASE = "https://apiv2.lagrowthmachine.com"
    spec = ToolSpec(
        id="lgm",
        label="La Growth Machine",
        docs="https://help.lagrowthmachine.com/en/articles/8276597-how-can-i-use-la-growth-machine-s-api-to-automate-my-workflows",
        price_hint="API erst ab dem Pro-Tarif (laut Hilfe-Seite); Preis unverifiziert, beim Anbieter prüfen",
        can=["Leads anlegen und einer Audience zuordnen"],
        cannot=[
            "Schlüssel vorab prüfen (kein Test-Endpunkt dokumentiert)",
            "Kontakt pausieren (nicht dokumentiert)",
            "Webhook-Inhalt (nicht dokumentiert; über den allgemeinen Webhook)",
        ],
    )

    def test(self, cfg, client=None):
        if len(cfg.get("api_key", "")) < 10:
            raise ProviderError("missing_credentials")
        return {
            "ok": True,
            "note": "Kein Test-Endpunkt dokumentiert; nur das Format wurde geprüft.",
        }

    def push_contacts(self, cfg, target, leads, client=None):
        out = []
        for lead in leads:
            body = {
                "firstName": lead.first_name,
                "lastName": lead.last_name,
                "companyName": lead.company,
                "linkedinUrl": lead.linkedin_url,
                **({"audience": target} if target else {}),
                **({"proEmail": lead.email} if lead.email else {}),
            }
            data, _ = request_json(
                "POST",
                self.BASE + "/flow/leads",
                client=client,
                side_effect=True,
                headers={"x-api-key": cfg["api_key"]},
                json=body,
            )
            out.append(
                {
                    "contact_id": lead.contact_id,
                    "external_ref": _dig(data, "id", "leadId", "lead.id") or lead.linkedin_url,
                }
            )
        return out


# ---- Expandi ------------------------------------------------------------------------------


class Expandi(Adapter):
    PAUSE = "https://api.liaufa.com/api/v1/open-api/campaign-contact/{id}/pause/"
    EVENTS = {
        "connection request sent": "invite_sent",
        "connection request accepted": "accepted",
        "connection request accepted by contact in active campaign": "accepted",
        "message sent": "message_sent",
        "contact replied": "replied",
        "contact replied to campaign message": "replied",
        "contact replied first time since start": "replied",
    }
    spec = ToolSpec(
        id="expandi",
        label="Expandi",
        docs="https://help.expandi.io/en/articles/5405654-reversed-webhooks-api",
        price_hint="ca. 99 $ pro Monat (unverifiziert, beim Anbieter prüfen)",
        can=[
            "Kontakte über die Kampagnen-URL („reversed webhook“) hinzufügen",
            "Kontakt pausieren, sobald ein Ereignis die Kampagnen-Kontakt-ID geliefert hat",
            "Webhooks für Antwort, Annahme, Nachricht",
        ],
        cannot=["Kampagnen anzeigen (je Kampagne eine eigene URL eintragen)", "Status abfragen"],
        secret_fields=("api_key", "api_secret"),
        webhook_events=tuple(EVENTS),
    )

    def test(self, cfg, client=None):
        if not cfg.get("api_key") or not cfg.get("api_secret"):
            raise ProviderError("missing_credentials")
        return {
            "ok": True,
            "note": "Expandi hat keinen Test-Endpunkt; geprüft wird beim ersten Kontakt.",
        }

    def push_contacts(self, cfg, target, leads, client=None):
        parts = urlsplit(target)
        if parts.scheme != "https" or not parts.hostname:
            raise ProviderError("invalid_campaign_url")
        for lead in leads:
            user_url_request(
                "POST",
                target,
                client=client,
                side_effect=True,
                json={"profile_link": lead.linkedin_url, "company_name": lead.company},
            )
        return [
            {"contact_id": lead.contact_id, "external_ref": lead.linkedin_url} for lead in leads
        ]

    def pause_contact(self, cfg, handoff, client=None):
        contact_ref = handoff.get("tool_contact_id")
        if not contact_ref:
            return None
        request_json(
            "GET",
            self.PAUSE.format(id=quote(str(contact_ref))),
            client=client,
            side_effect=True,
            params={"key": cfg["api_key"], "secret": cfg["api_secret"]},
        )
        return {"paused": True}

    def parse_webhook(self, body):
        # Event names from the help centre; payload field names UNVERIFIED.
        name = str(_dig(body, "hook.event", "event", "hook_name", "type") or "").strip().lower()
        url = _dig(
            body, "contact.profile_link", "contact.linkedin_url", "profile_link", "linkedin_url"
        )
        ref = _dig(body, "campaign_instance_contact.id", "campaign_contact_id")
        text = _dig(body, "messenger.last_message", "message", "contact.last_message") or ""
        event = _event(
            self.EVENTS.get(name, "other"), url, url, text if isinstance(text, str) else ""
        )
        event["tool_contact_id"] = str(ref) if ref else None
        return [event]


# ---- Generic webhook (Zapier, Make, n8n; Dripify, Botdog via those) --------------------------


def sign(secret: str, body: bytes, timestamp: str) -> str:
    return (
        "sha256="
        + hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    )


class GenericWebhook(Adapter):
    spec = ToolSpec(
        id="webhook",
        label="Allgemeiner Webhook (Zapier, Make, n8n)",
        docs="https://zapier.com/apps/webhook/integrations",
        price_hint="je nach Automatisierungsdienst und Ziel-Tool",
        can=[
            "Signiertes JSON an eine URL senden (Übergabe, Stopp)",
            "Ereignisse über eine geheime URL empfangen",
        ],
        cannot=["Rückmeldung, ob das Ziel-Tool die Aktion wirklich ausgeführt hat"],
        secret_fields=("signing_secret",),
        config_fields=("outgoing_url",),
    )

    def test(self, cfg, client=None):
        self._send(cfg, {"event": "test", "sent_at": int(time.time())}, client)
        return {"ok": True}

    def _send(self, cfg, payload, client=None):
        url = cfg.get("outgoing_url", "")
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise ProviderError("invalid_outgoing_url")
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        ts = str(int(time.time()))
        user_url_request(
            "POST",
            url,
            client=client,
            side_effect=True,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-ProspectOS-Timestamp": ts,
                "X-ProspectOS-Signature": sign(cfg["signing_secret"], body, ts),
            },
        )

    def push_contacts(self, cfg, target, leads, client=None):
        self._send(
            cfg,
            {
                "event": "contacts.handoff",
                "target": target,
                "contacts": [
                    {
                        "contact_id": lead.contact_id,
                        "first_name": lead.first_name,
                        "last_name": lead.last_name,
                        "company": lead.company,
                        "job_title": lead.job_title,
                        "linkedin_url": lead.linkedin_url,
                        **({"email": lead.email} if lead.email else {}),
                    }
                    for lead in leads
                ],
            },
            client,
        )
        return [
            {"contact_id": lead.contact_id, "external_ref": lead.linkedin_url} for lead in leads
        ]

    def pause_contact(self, cfg, handoff, client=None):
        self._send(
            cfg,
            {
                "event": "contact.pause",
                "target": handoff["target"],
                "linkedin_url": handoff["linkedin_url"],
                "contact_id": handoff["contact_id"],
            },
            client,
        )
        return {"paused": True, "confirmed": False}

    def parse_webhook(self, body):
        events = body.get("events") if isinstance(body.get("events"), list) else [body]
        return [
            _event(
                str(e.get("event", "other")),
                e.get("linkedin_url"),
                e.get("external_id"),
                e.get("text", ""),
                e.get("id"),
            )
            for e in events
            if isinstance(e, dict)
        ]


ADAPTERS: dict[str, Adapter] = {
    a.spec.id: a
    for a in (HeyReach(), Waalaxy(), LaGrowthMachine(), Expandi(), Lemlist(), GenericWebhook())
}
