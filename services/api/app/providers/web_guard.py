"""Application-level egress guard for website research.

Every request (including each redirect hop, which callers follow manually):
- only http/https on default ports, no credentials in URLs, no IP literals;
- the hostname is resolved here and *all* addresses must be globally routable
  (no private, loopback, link-local, metadata, multicast, reserved, CGNAT ranges);
- the connection is pinned to the validated IP (no second DNS lookup -> no DNS
  rebinding) while TLS still verifies the certificate against the hostname (SNI);
- environment proxies are ignored (trust_env=False), so no proxy re-resolves names;
- response size and time are bounded by the caller.
"""

import ipaddress
import socket

import httpx

from app.providers.ai import ProviderError

BLOCKED_HOSTS = ("linkedin.com", "licdn.com", "localhost")


def resolve_public(hostname: str, port: int) -> str:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ProviderError("unsafe_url")
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        raise ProviderError("dns_failed", retryable=True) from None
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise ProviderError("dns_failed")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if (
            not ip.is_global
            or ip.is_multicast
            or ip.is_reserved
            or (ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"))
        ):
            raise ProviderError("unsafe_url")
    # Prefer IPv4 for broad reachability; all candidates were validated above.
    return sorted(addresses, key=lambda a: ":" in a)[0]


def check_url(url: str) -> httpx.URL:
    if len(url) > 2000 or any(ord(c) < 32 for c in url):
        raise ProviderError("unsafe_url")
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, ValueError):
        raise ProviderError("unsafe_url") from None
    host = (parsed.host or "").lower().rstrip(".")
    if (
        parsed.scheme not in ("http", "https")
        or parsed.userinfo
        or parsed.port not in (None, 80, 443)
        or not host
        or "." not in host
        or any(host == b or host.endswith("." + b) for b in BLOCKED_HOSTS)
    ):
        raise ProviderError("unsafe_url")
    return parsed


class GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport | None = None, resolver=resolve_public):
        self.inner = inner or httpx.HTTPTransport(retries=0)
        self.resolver = resolver

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = check_url(str(request.url))
        port = url.port or (443 if url.scheme == "https" else 80)
        ip = self.resolver(url.host, port)
        request.url = url.copy_with(host=ip)
        request.headers["Host"] = url.host if url.port in (None, 80, 443) else f"{url.host}:{port}"
        if url.scheme == "https":
            request.extensions = {**request.extensions, "sni_hostname": url.host}
        return self.inner.handle_request(request)

    def close(self):
        self.inner.close()


def guarded_client(timeout: float = 10.0, transport: httpx.BaseTransport | None = None):
    return httpx.Client(
        transport=GuardedTransport(transport) if transport else GuardedTransport(),
        timeout=httpx.Timeout(timeout, connect=5),
        follow_redirects=False,
        trust_env=False,
    )
