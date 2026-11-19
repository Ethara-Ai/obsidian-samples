#!/usr/bin/env python3
"""CLI helper for the Google Drive API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$GOOGLE_DRIVE_API_URL, and requests stay on it: any other address, through --url or a
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

_ALLOWED = os.environ.get("GOOGLE_DRIVE_API_URL", "http://localhost:8106")


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
    """Refuse a URL off this connector's own service: $GOOGLE_DRIVE_API_URL, token endpoint included."""
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
            "client_id": os.environ.get("GOOGLE_DRIVE_CLIENT_ID", ""),
            "client_secret": os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET", "")}
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
    p = argparse.ArgumentParser(description="Query the Google Drive API (Mock) mock API")
    p.add_argument("--post-oauth-token", action="store_true", help="POST /oauth/token")
    p.add_argument("--get-oauth-tokeninfo", action="store_true", help="GET /oauth/tokeninfo")
    p.add_argument("--get-drive-files", action="store_true", help="GET /drive/v3/files")
    p.add_argument("--get-drive-files-fileid", metavar="FILEID", nargs=1, help="GET /drive/v3/files/{fileId}")
    p.add_argument("--get-drive-files-export-fileid", metavar="FILEID", nargs=1, help="GET /drive/v3/files/{fileId}/export")
    p.add_argument("--post-drive-files", action="store_true", help="POST /drive/v3/files")
    p.add_argument("--patch-drive-files-fileid", metavar="FILEID", nargs=1, help="PATCH /drive/v3/files/{fileId}")
    p.add_argument("--delete-drive-files-fileid", metavar="FILEID", nargs=1, help="DELETE /drive/v3/files/{fileId}")
    p.add_argument("--post-upload-drive-files", action="store_true", help="POST /upload/drive/v3/files")
    p.add_argument("--patch-upload-drive-files-fileid", metavar="FILEID", nargs=1, help="PATCH /upload/drive/v3/files/{fileId}")
    p.add_argument("--get-drive-files-permissions-fileid", metavar="FILEID", nargs=1, help="GET /drive/v3/files/{fileId}/permissions")
    p.add_argument("--post-drive-files-permissions-fileid", metavar="FILEID", nargs=1, help="POST /drive/v3/files/{fileId}/permissions")
    p.add_argument("--delete-drive-files-permissions-fileid-permissionid", metavar="FILEID/PERMISSIONID", nargs=2, help="DELETE /drive/v3/files/{fileId}/permissions/{permissionId}")
    p.add_argument("--get-drive-files-comments-fileid", metavar="FILEID", nargs=1, help="GET /drive/v3/files/{fileId}/comments")
    p.add_argument("--post-drive-files-comments-fileid", metavar="FILEID", nargs=1, help="POST /drive/v3/files/{fileId}/comments")
    p.add_argument("--get-drive-files-revisions-fileid", metavar="FILEID", nargs=1, help="GET /drive/v3/files/{fileId}/revisions")
    p.add_argument("--get-drive-files-revisions-fileid-revisionid", metavar="FILEID/REVISIONID", nargs=2, help="GET /drive/v3/files/{fileId}/revisions/{revisionId}")
    p.add_argument("--patch-drive-files-revisions-fileid-revisionid", metavar="FILEID/REVISIONID", nargs=2, help="PATCH /drive/v3/files/{fileId}/revisions/{revisionId}")
    p.add_argument("--token", default=os.environ.get("GOOGLE_DRIVE_ACCESS_TOKEN", ""),
                   help="Bearer access token (default: $GOOGLE_DRIVE_ACCESS_TOKEN)")
    p.add_argument("--get-token", action="store_true",
                   help="POST /oauth/token with $GOOGLE_DRIVE_CLIENT_ID/$GOOGLE_DRIVE_CLIENT_SECRET and print the token")
    p.add_argument("--scope", default="", help="Space-separated scopes for --get-token")
    p.add_argument("--query", default="", help="Query string appended to GET requests, e.g. 'limit=5&after=X'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string (POST/PUT/PATCH)")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file (POST/PUT/PATCH)")
    p.add_argument("--url", default=os.environ.get("GOOGLE_DRIVE_API_URL", "http://localhost:8106"),
                   help="API base URL (default: $GOOGLE_DRIVE_API_URL or http://localhost:8106)")
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
    if args.get_drive_files:
        return show(api_get(base, "/drive/v3/files"))
    if args.get_drive_files_fileid:
        return show(api_get(base, _fill('/drive/v3/files/{fileId}', args.get_drive_files_fileid)))
    if args.get_drive_files_export_fileid:
        return show(api_get(base, _fill('/drive/v3/files/{fileId}/export', args.get_drive_files_export_fileid)))
    if args.post_drive_files:
        return show(api_send(base, '/drive/v3/files', 'POST', _body(args)))
    if args.patch_drive_files_fileid:
        return show(api_send(base, _fill('/drive/v3/files/{fileId}', args.patch_drive_files_fileid), 'PATCH', _body(args)))
    if args.delete_drive_files_fileid:
        return show(api_delete(base, _fill('/drive/v3/files/{fileId}', args.delete_drive_files_fileid)))
    if args.post_upload_drive_files:
        return show(api_send(base, '/upload/drive/v3/files', 'POST', _body(args)))
    if args.patch_upload_drive_files_fileid:
        return show(api_send(base, _fill('/upload/drive/v3/files/{fileId}', args.patch_upload_drive_files_fileid), 'PATCH', _body(args)))
    if args.get_drive_files_permissions_fileid:
        return show(api_get(base, _fill('/drive/v3/files/{fileId}/permissions', args.get_drive_files_permissions_fileid)))
    if args.post_drive_files_permissions_fileid:
        return show(api_send(base, _fill('/drive/v3/files/{fileId}/permissions', args.post_drive_files_permissions_fileid), 'POST', _body(args)))
    if args.delete_drive_files_permissions_fileid_permissionid:
        return show(api_delete(base, _fill('/drive/v3/files/{fileId}/permissions/{permissionId}', args.delete_drive_files_permissions_fileid_permissionid)))
    if args.get_drive_files_comments_fileid:
        return show(api_get(base, _fill('/drive/v3/files/{fileId}/comments', args.get_drive_files_comments_fileid)))
    if args.post_drive_files_comments_fileid:
        return show(api_send(base, _fill('/drive/v3/files/{fileId}/comments', args.post_drive_files_comments_fileid), 'POST', _body(args)))
    if args.get_drive_files_revisions_fileid:
        return show(api_get(base, _fill('/drive/v3/files/{fileId}/revisions', args.get_drive_files_revisions_fileid)))
    if args.get_drive_files_revisions_fileid_revisionid:
        return show(api_get(base, _fill('/drive/v3/files/{fileId}/revisions/{revisionId}', args.get_drive_files_revisions_fileid_revisionid)))
    if args.patch_drive_files_revisions_fileid_revisionid:
        return show(api_send(base, _fill('/drive/v3/files/{fileId}/revisions/{revisionId}', args.patch_drive_files_revisions_fileid_revisionid), 'PATCH', _body(args)))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
