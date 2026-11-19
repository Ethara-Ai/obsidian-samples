---
name: text-browser
description: Open web pages as plain text, follow their links, and search inside a page. Blocked domains are refused, and every read fetches the live page.
metadata: {"clawdbot":{"requires":{"bins":["python3"]}}}
---

# Text browser

Read the web as text through the browser gateway. Use it for every web page you read.

## Open a page

```bash
python3 {baseDir}/scripts/browse.py open "https://example.com/some/page"
python3 {baseDir}/scripts/browse.py open "https://example.com/some/page" --page 2
```

The output gives the page title, the final URL after redirects, the HTTP status whenever it is not 200, `page N of M`, a note when the page has almost no readable text (often a sign-in page or one built by JavaScript, which this browser does not run), the page text, and the links on that page. A link appears in the text as `[#12]` after its anchor text and is listed below the text with its absolute URL. To follow it, open that URL.

## Find text inside a page

```bash
python3 {baseDir}/scripts/browse.py find "https://example.com/some/page" "opening hours"
```

Case-insensitive plain-text match. Each hit shows the page number it is on and the surrounding text.

## What you should know

- Requests to domains on the blocked-domain list are refused with `blocked_domain` and nothing is fetched. Redirects into a blocked domain are refused the same way. Do not try to reach a blocked site another way.
- Every open and find fetches the page live, so a page that changed since your last read shows its current content.
- Only text content is read: HTML, plain text, JSON, XML. Binary files are refused with `unsupported_content_type`.
- Private and internal network addresses are refused with `forbidden_address`.
- A URL whose host is an IP address rather than a domain name is refused with `ip_literal_not_allowed`. Open the site by its domain name.
- The tool opens addresses and has no search command of its own. Any site that is not on the blocked-domain list can be opened, a search engine's results page included.
