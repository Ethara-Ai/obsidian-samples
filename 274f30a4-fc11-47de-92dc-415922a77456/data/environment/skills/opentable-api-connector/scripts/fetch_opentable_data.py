#!/usr/bin/env python3
"""CLI helper for the OpenTable API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$OPENTABLE_API_URL, and requests stay on it: any other address, through --url or a
redirect, is refused. POST/PUT/PATCH bodies are read from --data (JSON string)
or --data-file; DELETE/GET take only path params.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

_ALLOWED = os.environ.get("OPENTABLE_API_URL", "http://localhost:8114")


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _origin(url):
    parts = urllib.parse.urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        return None
    return parts.scheme, parts.hostname or "", port or {"http": 80, "https": 443}.get(parts.scheme)


def _ssrf_check_url(url):
    """Refuse a URL off this connector's own service: $OPENTABLE_API_URL, token endpoint included."""
    origin = _origin(url)
    if origin is None or origin[0] not in ("http", "https") or origin != _origin(_ALLOWED):
        raise urllib.error.URLError(f"refused {url}: this connector reaches only {_ALLOWED}")


class _SsrfRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only while it stays on the connector's own service."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _ssrf_check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _safe_urlopen(req):
    _ssrf_check_url(req.full_url)
    return urllib.request.build_opener(_SsrfRedirectHandler).open(req, timeout=60)


_TOKEN = ""
_QUERY = ""


def _request(base, path, method, body=None):
    url = base.rstrip("/") + path
    if _QUERY and method == "GET":
        url += ("&" if "?" in url else "?") + _QUERY
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if _TOKEN:
        headers["Authorization"] = "Bearer " + _TOKEN
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with _safe_urlopen(req) as resp:
        raw = resp.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def api_get(base, path):
    return _request(base, path, "GET")


def api_delete(base, path):
    return _request(base, path, "DELETE")


def api_send(base, path, method, body):
    return _request(base, path, method, body if body is not None else {})


def get_token(base, scope):
    """Exchange the connected account's client credentials for an access token."""
    form = {"grant_type": "client_credentials",
            "client_id": os.environ.get("OPENTABLE_CLIENT_ID", ""),
            "client_secret": os.environ.get("OPENTABLE_CLIENT_SECRET", "")}
    if scope:
        form["scope"] = scope
    req = urllib.request.Request(base.rstrip("/") + "/oauth/token",
                                 data=urllib.parse.urlencode(form).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"},
                                 method="POST")
    with _safe_urlopen(req) as resp:
        return json.loads(resp.read().decode())


def _body(args):
    if getattr(args, "data_file", None):
        with open(args.data_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if getattr(args, "data", None):
        return json.loads(args.data)
    return {}


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False) if not isinstance(data, str) else data)
    return 0


def main():
    p = argparse.ArgumentParser(description="Query the OpenTable API (Mock) mock API")
    p.add_argument("--post-oauth-token", action="store_true", help="POST /oauth/token")
    p.add_argument("--get-oauth-tokeninfo", action="store_true", help="GET /oauth/tokeninfo")
    p.add_argument("--get-directory-restaurants", action="store_true", help="GET /v2/directory/restaurants")
    p.add_argument("--get-availability-rid", metavar="RID", nargs=1, help="GET /v2/availability/{rid}")
    p.add_argument("--post-booking-slot-locks-rid", metavar="RID", nargs=1, help="POST /v2/booking/{rid}/slot_locks")
    p.add_argument("--post-booking-reservations-rid", metavar="RID", nargs=1, help="POST /v2/booking/{rid}/reservations")
    p.add_argument("--get-booking-reservations-rid-confirmation-number", metavar="RID/CONFIRMATION_NUMBER", nargs=2, help="GET /v2/booking/{rid}/reservations/{confirmation_number}")
    p.add_argument("--delete-booking-reservations-rid-confirmation-number", metavar="RID/CONFIRMATION_NUMBER", nargs=2, help="DELETE /v2/booking/{rid}/reservations/{confirmation_number}")
    p.add_argument("--token", default=os.environ.get("OPENTABLE_ACCESS_TOKEN", ""),
                   help="Bearer access token (default: $OPENTABLE_ACCESS_TOKEN)")
    p.add_argument("--get-token", action="store_true",
                   help="POST /oauth/token with $OPENTABLE_CLIENT_ID/$OPENTABLE_CLIENT_SECRET and print the token")
    p.add_argument("--scope", default="", help="Space-separated scopes for --get-token")
    p.add_argument("--query", default="", help="Query string appended to GET requests, e.g. 'limit=5&after=X'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string (POST/PUT/PATCH)")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file (POST/PUT/PATCH)")
    p.add_argument("--url", default=os.environ.get("OPENTABLE_API_URL", "http://localhost:8114"),
                   help="API base URL (default: $OPENTABLE_API_URL or http://localhost:8114)")
    args = p.parse_args()
    base = args.url.rstrip("/")
    global _TOKEN, _QUERY
    _TOKEN = args.token
    _QUERY = args.query

    try:
        return _dispatch(args, base)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        return 1


def _dispatch(args, base):
    if args.get_token:
        return show(get_token(base, args.scope))
    if args.post_oauth_token:
        return show(api_send(base, '/oauth/token', 'POST', _body(args)))
    if args.get_oauth_tokeninfo:
        return show(api_get(base, "/oauth/tokeninfo"))
    if args.get_directory_restaurants:
        return show(api_get(base, "/v2/directory/restaurants"))
    if args.get_availability_rid:
        return show(api_get(base, _fill('/v2/availability/{rid}', args.get_availability_rid)))
    if args.post_booking_slot_locks_rid:
        return show(api_send(base, _fill('/v2/booking/{rid}/slot_locks', args.post_booking_slot_locks_rid), 'POST', _body(args)))
    if args.post_booking_reservations_rid:
        return show(api_send(base, _fill('/v2/booking/{rid}/reservations', args.post_booking_reservations_rid), 'POST', _body(args)))
    if args.get_booking_reservations_rid_confirmation_number:
        return show(api_get(base, _fill('/v2/booking/{rid}/reservations/{confirmation_number}', args.get_booking_reservations_rid_confirmation_number)))
    if args.delete_booking_reservations_rid_confirmation_number:
        return show(api_delete(base, _fill('/v2/booking/{rid}/reservations/{confirmation_number}', args.delete_booking_reservations_rid_confirmation_number)))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
