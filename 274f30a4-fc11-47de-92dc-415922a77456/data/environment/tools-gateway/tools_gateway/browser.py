"""The text browser: blocked-domain enforcement, SSRF guard, live fetch, rendering.

Every URL the agent opens, and every redirect hop on the way, is checked against
the client's blocked-domain list before any network traffic, and against
private, loopback, link-local, multicast, and reserved addresses after DNS
resolution, so the gateway can reach neither a blocked site nor the harness's
own internal services. A host written as an IP address is refused outright, in
any notation a resolver accepts: a private one as ``forbidden_address``, a public
one as ``ip_literal_not_allowed``, because the blocked-domain list names sites
and an address would reach a blocked site around it. The fetch then connects to
an address that passed that check and never resolves the name again, so a host
whose DNS answer changes between the check and the fetch (rebinding) cannot
steer it inside. A refused request is reported with a machine-readable reason;
nothing is fetched for it.

Every open and find fetches the page live; nothing is ever served from a saved
copy. Each fetched page, an error page included, is handed to a write-only
recorder so a reviewer can see what the rollout read. The fetch time is kept
in that record only: it is the host's real clock, and the agent works on the
task's simulated clock, so the answer the agent reads carries no time.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass
from email.message import Message
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote, urljoin, urlsplit

from .blocklist import Blocklist
from .render import LINK_MARKER, paginate, render
from .snapshots import SnapshotRecorder
from .usage import utc_now

TEXT_TYPES = ("text/", "application/json", "application/xml", "application/xhtml+xml",
              "application/rss+xml", "application/atom+xml", "application/ld+json")
MAX_REDIRECTS = 5
SPARSE_TEXT_CHARS = 200  # a 200 page with fewer readable characters than this gets a note saying why
USER_AGENT = "WildClawBench-TextBrowser/1.0 (+evaluation harness)"
ACCEPT = "text/html,text/plain,application/json;q=0.9,*/*;q=0.1"
_URL_SAFE = ":/?#[]@!$&'()*+,;=%"


class BrowserRefused(Exception):
    def __init__(self, status: int, reason: str, message: str, **detail: Any):
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.message = message
        self.detail = detail


@dataclass
class Response:
    status: int
    url: str
    headers: Dict[str, str]
    body: bytes


Transport = Callable[[str, Sequence[str], float, int], Response]
Resolver = Callable[[str], List[str]]


def _resolve(host: str) -> List[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def _connect(addresses: Sequence[str], port: int, timeout: float) -> socket.socket:
    """A socket to the first of ``addresses`` that accepts, IPv4 before IPv6."""
    error: OSError = OSError("no vetted address to connect to")
    for address in sorted(addresses, key=lambda a: (":" in a, a)):
        try:
            return socket.create_connection((address, port), timeout)
        except OSError as exc:
            error = exc
    raise error


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, addresses: Sequence[str], timeout: float):
        super().__init__(host, port, timeout=timeout)
        self._addresses = list(addresses)

    def connect(self) -> None:
        self.sock = _connect(self._addresses, self.port, self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, addresses: Sequence[str], timeout: float):
        self._tls = ssl.create_default_context()
        super().__init__(host, port, timeout=timeout, context=self._tls)
        self._addresses = list(addresses)

    def connect(self) -> None:
        raw = _connect(self._addresses, self.port, self.timeout)
        self.sock = self._tls.wrap_socket(raw, server_hostname=self.host)


def _pinned_transport(url: str, addresses: Sequence[str], timeout: float, max_bytes: int) -> Response:
    """GET ``url`` from one of ``addresses``; the URL's host name is never resolved again.

    The name still travels in the Host header and as the TLS server name, so
    virtual hosting and certificate verification work as for any client.
    """
    parts = urlsplit(url)
    secure = parts.scheme == "https"
    port = parts.port or (443 if secure else 80)
    conn = (_PinnedHTTPS if secure else _PinnedHTTP)(parts.hostname or "", port, addresses, timeout)
    target = quote((parts.path or "/") + (f"?{parts.query}" if parts.query else ""), safe=_URL_SAFE)
    try:
        conn.request("GET", target, headers={"User-Agent": USER_AGENT, "Accept": ACCEPT})
        resp = conn.getresponse()
        body = resp.read(max_bytes + 1)
        return Response(resp.status, url, {k.lower(): v for k, v in resp.getheaders()}, body)
    finally:
        conn.close()


def _forbidden_address(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
            or ip.is_reserved or ip.is_unspecified or not ip.is_global)


def _ip_literal(host: str) -> Optional[str]:
    """The address ``host`` spells when it is an IP literal, else None.

    Covers every spelling the resolver would accept for one, not just dotted
    quads: ``1572395042``, ``0x5db8d822``, ``0135.0270.0330.042``, ``127.1``, and a
    trailing dot all resolve to an address without any DNS lookup.
    """
    bare = host.rstrip(".").split("%", 1)[0]
    try:
        return str(ipaddress.ip_address(bare))
    except ValueError:
        pass
    try:
        return socket.inet_ntoa(socket.inet_aton(bare))
    except (OSError, ValueError):
        return None


class Browser:
    def __init__(self, blocklist: Blocklist, recorder: Optional[SnapshotRecorder] = None, *,
                 timeout: float = 20.0, max_bytes: int = 3_000_000, page_chars: int = 8000,
                 transport: Transport = _pinned_transport, resolver: Resolver = _resolve):
        self.blocklist = blocklist
        self.recorder = recorder if recorder is not None else SnapshotRecorder(None)
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.page_chars = page_chars
        self._transport = transport
        self._resolver = resolver

    # -- guards ----------------------------------------------------------------

    def check_url(self, url: str) -> str:
        """The URL's host name after the scheme, blocked-domain, and IP-literal checks; refuses otherwise."""
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            raise BrowserRefused(400, "unsupported_scheme",
                                 f"only http and https URLs can be opened, not {parts.scheme or 'none'!r}")
        host = parts.hostname or ""
        if not host:
            raise BrowserRefused(400, "invalid_url", f"the URL has no host: {url}")
        matched = self.blocklist.match(host)
        if matched:
            raise BrowserRefused(403, "blocked_domain",
                                 f"{host} is on the blocked-domain list (entry {matched}); the request was not sent",
                                 host=host, matched=matched)
        address = _ip_literal(host)
        if address is not None:
            if _forbidden_address(address):
                raise BrowserRefused(403, "forbidden_address",
                                     f"{host} is a non-public address; the request was not sent", host=host)
            raise BrowserRefused(403, "ip_literal_not_allowed",
                                 f"{host} is an IP address; open the site by its domain name so the "
                                 f"blocked-domain list applies. The request was not sent", host=host)
        return host

    def _check_addresses(self, host: str) -> List[str]:
        """Every address ``host`` resolves to, when all of them are public; refuses otherwise."""
        try:
            addresses = self._resolver(host)
        except OSError as exc:
            raise BrowserRefused(502, "dns_failure", f"could not resolve {host}: {exc}")
        if not addresses:
            raise BrowserRefused(502, "dns_failure", f"could not resolve {host}")
        bad = [a for a in addresses if _forbidden_address(a)]
        if bad:
            raise BrowserRefused(403, "forbidden_address",
                                 f"{host} resolves to a non-public address; the request was not sent",
                                 host=host)
        return addresses

    # -- fetch -----------------------------------------------------------------

    def _fetch_live(self, url: str) -> Dict[str, Any]:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            host = self.check_url(current)
            addresses = self._check_addresses(host)
            try:
                resp = self._transport(current, addresses, self.timeout, self.max_bytes)
            except (OSError, ValueError, http.client.HTTPException) as exc:
                raise BrowserRefused(502, "fetch_failed", f"could not fetch {current}: {exc}")
            if resp.status in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                current = urljoin(current, resp.headers["location"])
                continue
            if len(resp.body) > self.max_bytes:
                raise BrowserRefused(413, "too_large", f"{current} is larger than {self.max_bytes} bytes")
            msg = Message()
            msg["content-type"] = resp.headers.get("content-type", "text/html")
            content_type = msg.get_content_type()
            if not content_type.startswith(TEXT_TYPES):
                raise BrowserRefused(415, "unsupported_content_type",
                                     f"{current} serves {content_type}, which the text browser does not read")
            charset = msg.get_content_charset() or "utf-8"
            try:
                text = resp.body.decode(charset, errors="replace")
            except LookupError:
                text = resp.body.decode("utf-8", errors="replace")
            return {"url": url, "final_url": current, "status": resp.status,
                    "content_type": content_type, "body": text, "fetched_at": utc_now()}
        raise BrowserRefused(508, "too_many_redirects", f"{url} redirected more than {MAX_REDIRECTS} times")

    def fetch(self, url: str) -> Tuple[Dict[str, Any], Optional[str]]:
        """The page as fetched live now, and the key of its review record (None when none is kept)."""
        record = self._fetch_live(url)
        return record, self.recorder.write(record)

    # -- views -----------------------------------------------------------------

    def open(self, url: str, page: int = 1) -> Tuple[Dict[str, Any], str]:
        record, key = self.fetch(url)
        title, text, links = render(record["body"], record["content_type"], record["final_url"])
        pages = paginate(text, self.page_chars)
        if page < 1 or page > len(pages):
            raise BrowserRefused(400, "page_out_of_range", f"page must be between 1 and {len(pages)}")
        start, end = pages[page - 1]
        chunk = text[start:end]
        shown = sorted({int(n) for n in LINK_MARKER.findall(chunk)})
        note = {}
        if record["status"] == 200 and len("".join(text.split())) < SPARSE_TEXT_CHARS:
            note = {"note": "this page has almost no readable text; it may need a login, or JavaScript, "
                            "which this text browser does not run"}
        return {**note,
            "url": record["url"],
            "final_url": record["final_url"],
            "status": record["status"],
            "title": title,
            "page": page,
            "pages": len(pages),
            "text": chunk,
            "links": [{"id": n, "url": links[n - 1]["url"]} for n in shown if 0 < n <= len(links)],
            "snapshot": {"source": "live", "key": key},
        }, "live"

    def find(self, url: str, pattern: str, max_matches: int = 50) -> Tuple[Dict[str, Any], str]:
        if not pattern.strip():
            raise BrowserRefused(400, "empty_pattern", "pattern must not be empty")
        record, key = self.fetch(url)
        title, text, _ = render(record["body"], record["content_type"], record["final_url"])
        pages = paginate(text, self.page_chars)
        lowered, needle = text.lower(), pattern.lower()
        matches = []
        at = lowered.find(needle)
        while at != -1 and len(matches) < max_matches:
            page = next(i for i, (s, e) in enumerate(pages, 1) if s <= at < e)
            matches.append({"page": page,
                            "context": text[max(0, at - 120): at + len(pattern) + 120].replace("\n", " ")})
            at = lowered.find(needle, at + len(needle))
        return {"url": record["url"], "final_url": record["final_url"], "status": record["status"], "title": title,
                "pattern": pattern, "matches": matches, "pages": len(pages),
                "snapshot": {"source": "live", "key": key}}, "live"
