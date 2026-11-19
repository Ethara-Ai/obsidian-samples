#!/usr/bin/env python3
"""Text browser client: open a URL as text or find text in it, through the tools gateway.

Reads $WCB_TOOLS_URL and $WCB_TOOLS_TOKEN, which the harness sets in this environment.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _call(path, payload):
    base = os.environ.get("WCB_TOOLS_URL", "").rstrip("/")
    token = os.environ.get("WCB_TOOLS_TOKEN", "")
    if not base or not token:
        sys.exit("The text browser is not enabled in this environment (WCB_TOOLS_URL / WCB_TOOLS_TOKEN unset).")
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            body = json.loads(err.read().decode("utf-8"))
            message = f"{body.get('error', 'error')}: {body.get('message', '')}"
        except ValueError:
            message = f"HTTP {err.code}"
        sys.exit(f"Refused ({err.code}) {message}")
    except urllib.error.URLError as err:
        sys.exit(f"Could not reach the browser gateway: {err.reason}")


def _fetched_line(snap):
    # No time: the gateway runs on the host's real clock, and a real date here
    # contradicts the task's simulated date the agent works in.
    return "fetched live"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    o = sub.add_parser("open", help="open a URL and print one page of its text")
    o.add_argument("url")
    o.add_argument("--page", type=int, default=1)
    f = sub.add_parser("find", help="find text inside a URL's page")
    f.add_argument("url")
    f.add_argument("pattern")
    args = p.parse_args()

    if args.command == "open":
        r = _call("/browser/open", {"url": args.url, "page": args.page})
        print(f"Title: {r.get('title') or '(none)'}")
        print(f"URL: {r['final_url']}")
        if r.get("status", 200) != 200:
            print(f"HTTP status: {r['status']}")
        print(f"Page {r['page']} of {r['pages']} | {_fetched_line(r['snapshot'])}")
        if r.get("note"):
            print(f"Note: {r['note']}")
        print("-" * 72)
        print(r["text"])
        if r["links"]:
            print("-" * 72)
            print("Links on this page:")
            for link in r["links"]:
                print(f"[#{link['id']}] {link['url']}")
        return 0

    r = _call("/browser/find", {"url": args.url, "pattern": args.pattern})
    print(f"URL: {r['final_url']} | {r['pages']} page(s) | {_fetched_line(r['snapshot'])}")
    if r.get("status", 200) != 200:
        print(f"HTTP status: {r['status']}")
    if not r["matches"]:
        print(f"No match for {args.pattern!r}.")
    for m in r["matches"]:
        print(f"page {m['page']}: ...{m['context']}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
