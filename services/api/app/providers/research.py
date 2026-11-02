"""Opt-in company-page research with strict source and infrastructure prerequisites.

DNS checks alone cannot prevent proxy-side DNS rebinding. Operators must deploy an
independent egress guard rejecting private/link-local/metadata IPs and attest it
before enabling this path. Without that prerequisite this adapter fails closed.
"""

import hashlib
import ipaddress
import os
import socket
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel

from app.providers.ai import ProviderError

USER_AGENT = "ProspectOSResearch/1.0"
MAX_BYTES = 512 * 1024


class ResearchResult(BaseModel):
    url: str
    title: str
    text: str
    source_id: str
    observed_at: str
    confidence: str = "unverified"
    notice: str = (
        "User-reviewed website excerpt; source text is untrusted, not independently verified."
    )


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "iframe", "object", "noscript"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if tag in ("p", "div", "br", "h1", "h2", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "iframe", "object", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if not self.hidden:
            if self.in_title:
                self.title.append(data)
            self.parts.append(data)


def validate_public_url(url: str) -> str:
    if len(url) > 2000 or any(ord(char) < 32 for char in url):
        raise ProviderError("unsafe_url")
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").encode("idna").decode("ascii").lower()
        allowed = {
            host.strip().encode("idna").decode("ascii").lower()
            for host in os.getenv("RESEARCH_ALLOWED_DOMAINS", "").split(",")
            if host.strip()
        }
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not hostname
            or hostname not in allowed
            or hostname == "linkedin.com"
            or hostname.endswith((".linkedin.com", ".licdn.com"))
        ):
            raise ValueError()
        # IP literals and all non-global resolver results are refused. This must
        # complement, not substitute for, the independent egress DNS/IP guard.
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise ValueError()
        addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(item[4][0]).is_global for item in addresses
        ):
            raise ValueError()
        return urlunsplit(("https", hostname, parsed.path or "/", parsed.query, ""))
    except (ValueError, UnicodeError, OSError):
        raise ProviderError("unsafe_url") from None


def _fetch(client, url, maximum, *, allow_missing=False, allow_redirects=True):
    for _ in range(4):
        url = validate_public_url(url)
        try:
            with client.stream(
                "GET", url, headers={"User-Agent": USER_AGENT}, follow_redirects=False
            ) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    if not allow_redirects:
                        raise ProviderError("source_redirect_review_required")
                    target = response.headers.get("location")
                    if not target:
                        raise ProviderError("invalid_research_response")
                    url = urljoin(url, target)
                    continue
                if allow_missing and response.status_code == 404:
                    return url, "", "text/plain"
                if response.status_code != 200:
                    raise ProviderError("research_unavailable")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type not in ("text/html", "text/plain", "application/xhtml+xml"):
                    raise ProviderError("unsupported_research_content")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > maximum:
                        raise ProviderError("research_size_limit")
                return url, body.decode("utf-8", errors="replace"), content_type
        except (httpx.HTTPError, UnicodeError):
            raise ProviderError("research_unavailable", retryable=True) from None
    raise ProviderError("research_redirect_limit")


def research_company(url: str, *, client=None) -> ResearchResult:
    if os.getenv("RESEARCH_TERMS_APPROVED", "false").lower() != "true":
        raise ProviderError("source_review_required")
    if os.getenv("RESEARCH_NETWORK_GUARD_APPROVED", "false").lower() != "true":
        raise ProviderError("egress_guard_required")
    normalized = validate_public_url(url)
    own_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False)
    try:
        origin = "https://" + urlsplit(normalized).netloc
        _, rules, _ = _fetch(client, origin + "/robots.txt", 64 * 1024, allow_missing=True)
        robots = RobotFileParser()
        robots.parse(rules.splitlines())
        if rules and not robots.can_fetch(USER_AGENT, normalized):
            raise ProviderError("robots_disallowed")
        final_url, content, content_type = _fetch(
            client, normalized, MAX_BYTES, allow_redirects=False
        )
        parser = _TextExtractor()
        parser.feed(content)
        excerpt = (
            " ".join(" ".join(parser.parts).split())[:16000]
            if content_type != "text/plain"
            else content[:16000]
        )
        return ResearchResult(
            url=final_url,
            title=" ".join(parser.title)[:300],
            text=excerpt,
            source_id=hashlib.sha256(final_url.encode()).hexdigest()[:32],
            observed_at=datetime.now(UTC).isoformat(),
        )
    finally:
        if own_client:
            client.close()
