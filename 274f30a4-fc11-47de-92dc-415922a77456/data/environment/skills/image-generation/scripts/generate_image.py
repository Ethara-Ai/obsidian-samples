#!/usr/bin/env python3
"""Image generation client: send a prompt through the tools gateway and save the images.

Reads $WCB_TOOLS_URL and $WCB_TOOLS_TOKEN, which the harness sets in this environment.
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request


def _call(method, path, payload=None):
    base = os.environ.get("WCB_TOOLS_URL", "").rstrip("/")
    token = os.environ.get("WCB_TOOLS_TOKEN", "")
    if not base or not token:
        sys.exit("Image generation is not enabled in this environment (WCB_TOOLS_URL / WCB_TOOLS_TOKEN unset).")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            body = json.loads(err.read().decode("utf-8"))
            message = f"{body.get('error', 'error')}: {body.get('message', '')}"
        except ValueError:
            message = f"HTTP {err.code}"
        sys.exit(f"Refused ({err.code}) {message}")
    except urllib.error.URLError as err:
        sys.exit(f"Could not reach the image gateway: {err.reason}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prompt", nargs="?", help="what the image should show")
    p.add_argument("--out", help="output path prefix, e.g. /root/workspace/poster")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--size", default=None, help="WIDTHxHEIGHT, e.g. 1024x1024")
    p.add_argument("--format", dest="output_format", default=None, choices=["webp", "png", "jpeg"])
    p.add_argument("--info", action="store_true", help="show the configured model and exit")
    args = p.parse_args()

    if args.info:
        print(json.dumps(_call("GET", "/image/info"), indent=2))
        return 0
    if not args.prompt or not args.out:
        p.error("a prompt and --out are required")
    payload = {"prompt": args.prompt, "n": args.n}
    if args.size:
        payload["size"] = args.size
    if args.output_format:
        payload["output_format"] = args.output_format
    r = _call("POST", "/image/generate", payload)
    ext = r.get("output_format") or args.output_format or "webp"
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    files = []
    images = r.get("images", [])
    for i, image in enumerate(images, 1):
        path = f"{args.out}.{ext}" if len(images) == 1 else f"{args.out}_{i}.{ext}"
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(image["b64_json"]))
        files.append(path)
    print(json.dumps({"files": files, "model": r.get("model"), "usage": r.get("usage")}, indent=2))
    return 0 if files else 1


if __name__ == "__main__":
    raise SystemExit(main())
