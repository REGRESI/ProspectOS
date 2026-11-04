"""SMTP/IMAP mailbox adapter for outreach from the customer's own mailboxes.

- Host names are user supplied: every connection is resolved via ``web_guard``
  (public IPs only) and pinned to the validated IP; TLS verifies the hostname.
- Only implicit TLS (465/993) or STARTTLS (587/143) with certificate verification;
  plaintext auth is never attempted.
- Secrets are passed in, never logged; provider error texts are not stored verbatim.
"""

import email.utils
import imaplib
import re
import smtplib
import socket
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from app.providers.ai import ProviderError
from app.providers.web_guard import resolve_public

TIMEOUT = 20


@dataclass
class MailboxConfig:
    email: str
    username: str
    password: str
    smtp_host: str
    smtp_port: int
    smtp_security: str  # "ssl" | "starttls"
    imap_host: str
    imap_port: int
    display_name: str = ""


def _ctx():
    return ssl.create_default_context()


class _PinnedSMTP(smtplib.SMTP):
    def __init__(self, ip, *a, **k):
        self._pinned_ip = ip
        super().__init__(*a, **k)

    def _get_socket(self, host, port, timeout):
        return socket.create_connection((self._pinned_ip, port), timeout)


class _PinnedSMTPSSL(smtplib.SMTP_SSL):
    def __init__(self, ip, *a, **k):
        self._pinned_ip = ip
        super().__init__(*a, **k)

    def _get_socket(self, host, port, timeout):
        sock = socket.create_connection((self._pinned_ip, port), timeout)
        return self.context.wrap_socket(sock, server_hostname=self._host)


class _PinnedIMAP(imaplib.IMAP4_SSL):
    def __init__(self, ip, host, port):
        self._pinned_ip = ip
        super().__init__(host, port, ssl_context=_ctx(), timeout=TIMEOUT)

    def _create_socket(self, timeout):
        sock = socket.create_connection((self._pinned_ip, self.port), timeout)
        return self.ssl_context.wrap_socket(sock, server_hostname=self.host)


def _check_host(host: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9.-]{3,253}", host or "") or "." not in host:
        raise ProviderError("invalid_mail_host")
    return resolve_public(host, 0)


def smtp_connect(cfg: MailboxConfig):
    if cfg.smtp_security not in ("ssl", "starttls") or cfg.smtp_port not in (465, 587, 25, 2525):
        raise ProviderError("invalid_smtp_settings")
    ip = _check_host(cfg.smtp_host)
    try:
        if cfg.smtp_security == "ssl":
            server = _PinnedSMTPSSL(
                ip, cfg.smtp_host, cfg.smtp_port, timeout=TIMEOUT, context=_ctx()
            )
        else:
            server = _PinnedSMTP(ip, cfg.smtp_host, cfg.smtp_port, timeout=TIMEOUT)
            server.ehlo()
            server.starttls(context=_ctx())
            server.ehlo()
        server.login(cfg.username, cfg.password)
        return server
    except smtplib.SMTPAuthenticationError:
        raise ProviderError("smtp_auth_failed") from None
    except (smtplib.SMTPException, OSError, ssl.SSLError):
        raise ProviderError("smtp_unavailable", retryable=True) from None


def imap_connect(cfg: MailboxConfig):
    if cfg.imap_port not in (993,):
        raise ProviderError("invalid_imap_settings")
    ip = _check_host(cfg.imap_host)
    try:
        client = _PinnedIMAP(ip, cfg.imap_host, cfg.imap_port)
        client.login(cfg.username, cfg.password)
        return client
    except imaplib.IMAP4.error:
        raise ProviderError("imap_auth_failed") from None
    except (OSError, ssl.SSLError):
        raise ProviderError("imap_unavailable", retryable=True) from None


def test_mailbox(cfg: MailboxConfig, *, smtp=smtp_connect, imap=imap_connect) -> dict:
    server = smtp(cfg)
    try:
        server.noop()
    finally:
        try:
            server.quit()
        except Exception:
            pass
    client = imap(cfg)
    try:
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise ProviderError("imap_inbox_unavailable")
    finally:
        try:
            client.logout()
        except Exception:
            pass
    return {
        "detail": "SMTP-Anmeldung und IMAP-Posteingang erfolgreich geprüft (keine Mail gesendet)."
    }


def build_message(
    cfg: MailboxConfig,
    *,
    to: str,
    subject: str,
    text: str,
    unsubscribe_url: str,
    unsubscribe_mailto: str,
    sender_footer: str,
    domain: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = email.utils.formataddr((cfg.display_name or "", cfg.email))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=False)
    msg["Message-ID"] = email.utils.make_msgid(domain=domain)
    # RFC 8058 one-click unsubscribe (required by Gmail/Yahoo bulk sender rules).
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>, <{unsubscribe_mailto}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    footer = (
        "\n\n-- \n"
        + sender_footer.strip()
        + f"\n\nKeine weiteren Nachrichten erhalten: {unsubscribe_url}"
    )
    msg.set_content(text.strip() + footer)
    return msg


def send_message(cfg: MailboxConfig, msg: EmailMessage, *, smtp=smtp_connect) -> str:
    """Returns the Message-ID. Errors after DATA started are ambiguous (never retried)."""
    server = smtp(cfg)
    try:
        refused = server.send_message(msg)
        if refused:
            raise ProviderError("recipient_refused")
        return msg["Message-ID"]
    except smtplib.SMTPRecipientsRefused:
        raise ProviderError("recipient_refused") from None
    except smtplib.SMTPSenderRefused:
        raise ProviderError("sender_refused") from None
    except (smtplib.SMTPException, OSError):
        raise ProviderError("ambiguous_result", ambiguous=True) from None
    finally:
        try:
            server.quit()
        except Exception:
            pass


REPORT_ID = re.compile(r"Message-ID:\s*(<[^>\s]+>)", re.I)


def classify(raw: bytes) -> dict:
    """Classify an inbound message: reply to one of ours, bounce (DSN) or complaint (ARF)."""
    from email import message_from_bytes, policy

    msg = message_from_bytes(raw, policy=policy.default)
    ctype = msg.get_content_type()
    report = (msg.get_param("report-type") or "").lower() if ctype == "multipart/report" else ""
    sender = (msg.get("From") or "").lower()
    refs = " ".join(filter(None, [msg.get("In-Reply-To"), msg.get("References")]))
    if report == "feedback-report":
        ids = REPORT_ID.findall(msg.as_string())
        return {"kind": "complaint", "ids": ids}
    if report == "delivery-status" or "mailer-daemon" in sender or "postmaster" in sender:
        text = msg.as_string()
        permanent = bool(re.search(r"Status:\s*5\.\d+\.\d+|Action:\s*failed", text, re.I))
        return {"kind": "bounce", "hard": permanent, "ids": REPORT_ID.findall(text)}
    ids = re.findall(r"<[^>\s]+>", refs)
    if ids:
        body = msg.get_body(preferencelist=("plain",))
        text = body.get_content() if body else ""
        return {"kind": "reply", "ids": ids, "text": text[:4000]}
    return {"kind": "other", "ids": []}


def fetch_new(
    cfg: MailboxConfig, last_uid: int, *, imap=imap_connect, limit=200
) -> tuple[list, int]:
    client = imap(cfg)
    try:
        client.select("INBOX", readonly=True)
        status, data = client.uid("search", None, f"UID {last_uid + 1}:*")
        if status != "OK":
            raise ProviderError("imap_search_failed")
        uids = [int(u) for u in (data[0] or b"").split() if int(u) > last_uid][:limit]
        out = []
        for uid in uids:
            status, parts = client.uid("fetch", str(uid), "(BODY.PEEK[])")
            if status == "OK" and parts and isinstance(parts[0], tuple):
                out.append((uid, parts[0][1]))
        return out, max(uids) if uids else last_uid
    finally:
        try:
            client.logout()
        except Exception:
            pass
