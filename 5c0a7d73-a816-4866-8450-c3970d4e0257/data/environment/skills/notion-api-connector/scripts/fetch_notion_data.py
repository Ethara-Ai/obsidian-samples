#!/usr/bin/env python3
"""CLI helper for the Notion API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$NOTION_API_URL, and requests stay on it: any other address, through --url or a
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

_ALLOWED = os.environ.get("NOTION_API_URL", "http://localhost:8122")


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
    """Refuse a URL off this connector's own service: $NOTION_API_URL, token endpoint included."""
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
            "client_id": os.environ.get("NOTION_CLIENT_ID", ""),
            "client_secret": os.environ.get("NOTION_CLIENT_SECRET", "")}
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
    p = argparse.ArgumentParser(description="Query the Notion API (Mock) mock API")
    p.add_argument("--post-oauth-token", action="store_true", help="POST /oauth/token")
    p.add_argument("--get-oauth-tokeninfo", action="store_true", help="GET /oauth/tokeninfo")
    p.add_argument("--post-search", action="store_true", help="POST /v1/search")
    p.add_argument("--get-pages-page-id", metavar="PAGE_ID", nargs=1, help="GET /v1/pages/{page_id}")
    p.add_argument("--post-pages", action="store_true", help="POST /v1/pages")
    p.add_argument("--patch-pages-page-id", metavar="PAGE_ID", nargs=1, help="PATCH /v1/pages/{page_id}")
    p.add_argument("--post-databases-query-database-id", metavar="DATABASE_ID", nargs=1, help="POST /v1/databases/{database_id}/query")
    p.add_argument("--get-blocks-children-block-id", metavar="BLOCK_ID", nargs=1, help="GET /v1/blocks/{block_id}/children")
    p.add_argument("--patch-blocks-children-block-id", metavar="BLOCK_ID", nargs=1, help="PATCH /v1/blocks/{block_id}/children")
    p.add_argument("--token", default=os.environ.get("NOTION_ACCESS_TOKEN", ""),
                   help="Bearer access token (default: $NOTION_ACCESS_TOKEN)")
    p.add_argument("--get-token", action="store_true",
                   help="POST /oauth/token with $NOTION_CLIENT_ID/$NOTION_CLIENT_SECRET and print the token")
    p.add_argument("--scope", default="", help="Space-separated scopes for --get-token")
    p.add_argument("--query", default="", help="Query string appended to GET requests, e.g. 'limit=5&after=X'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string (POST/PUT/PATCH)")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file (POST/PUT/PATCH)")
    p.add_argument("--url", default=os.environ.get("NOTION_API_URL", "http://localhost:8122"),
                   help="API base URL (default: $NOTION_API_URL or http://localhost:8122)")
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
    if args.post_search:
        return show(api_send(base, '/v1/search', 'POST', _body(args)))
    if args.get_pages_page_id:
        return show(api_get(base, _fill('/v1/pages/{page_id}', args.get_pages_page_id)))
    if args.post_pages:
        return show(api_send(base, '/v1/pages', 'POST', _body(args)))
    if args.patch_pages_page_id:
        return show(api_send(base, _fill('/v1/pages/{page_id}', args.patch_pages_page_id), 'PATCH', _body(args)))
    if args.post_databases_query_database_id:
        return show(api_send(base, _fill('/v1/databases/{database_id}/query', args.post_databases_query_database_id), 'POST', _body(args)))
    if args.get_blocks_children_block_id:
        return show(api_get(base, _fill('/v1/blocks/{block_id}/children', args.get_blocks_children_block_id)))
    if args.patch_blocks_children_block_id:
        return show(api_send(base, _fill('/v1/blocks/{block_id}/children', args.patch_blocks_children_block_id), 'PATCH', _body(args)))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
