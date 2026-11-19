#!/usr/bin/env python3
"""CLI helper for the WhatsApp Cloud API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$WHATSAPP_API_URL, and requests stay on it: any other address, through --url or a
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

_ALLOWED = os.environ.get("WHATSAPP_API_URL", "http://localhost:8015")


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
    """Refuse a URL off this connector's own service: $WHATSAPP_API_URL, token endpoint included."""
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


def _request(base, path, method, body=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
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
    p = argparse.ArgumentParser(description="Query the WhatsApp Cloud API (Mock) mock API")
    p.add_argument("--get-v17-0-business", action="store_true", help="GET /v17.0/business")
    p.add_argument("--get-v17-0-contacts", action="store_true", help="GET /v17.0/contacts")
    p.add_argument("--get-v17-0-contacts-wa-id", metavar="WA_ID", nargs=1, help="GET /v17.0/contacts/{wa_id}")
    p.add_argument("--get-v17-0-message-templates", action="store_true", help="GET /v17.0/message_templates")
    p.add_argument("--get-v17-0-message-templates-name", metavar="NAME", nargs=1, help="GET /v17.0/message_templates/{name}")
    p.add_argument("--get-v17-0-conversations", action="store_true", help="GET /v17.0/conversations")
    p.add_argument("--get-v17-0-messages", action="store_true", help="GET /v17.0/messages")
    p.add_argument("--post-v17-0-messages", action="store_true", help="POST /v17.0/messages")
    p.add_argument("--post-v17-0-messages-status", action="store_true", help="POST /v17.0/messages/status")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string (POST/PUT/PATCH)")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file (POST/PUT/PATCH)")
    p.add_argument("--url", default=os.environ.get("WHATSAPP_API_URL", "http://localhost:8015"),
                   help="API base URL (default: $WHATSAPP_API_URL or http://localhost:8015)")
    args = p.parse_args()
    base = args.url.rstrip("/")

    try:
        return _dispatch(args, base)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        return 1


def _dispatch(args, base):
    if args.get_v17_0_business:
        return show(api_get(base, "/v17.0/business"))
    if args.get_v17_0_contacts:
        return show(api_get(base, "/v17.0/contacts"))
    if args.get_v17_0_contacts_wa_id:
        return show(api_get(base, _fill('/v17.0/contacts/{wa_id}', args.get_v17_0_contacts_wa_id)))
    if args.get_v17_0_message_templates:
        return show(api_get(base, "/v17.0/message_templates"))
    if args.get_v17_0_message_templates_name:
        return show(api_get(base, _fill('/v17.0/message_templates/{name}', args.get_v17_0_message_templates_name)))
    if args.get_v17_0_conversations:
        return show(api_get(base, "/v17.0/conversations"))
    if args.get_v17_0_messages:
        return show(api_get(base, "/v17.0/messages"))
    if args.post_v17_0_messages:
        return show(api_send(base, '/v17.0/messages', 'POST', _body(args)))
    if args.post_v17_0_messages_status:
        return show(api_send(base, '/v17.0/messages/status', 'POST', _body(args)))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
