"""Deterministic HTML-to-text rendering for the text browser.

Pure standard library and free of clocks or randomness, so the same page
always renders to the same text, page split, and link numbering. Links are
numbered in document order as ``[#n]`` after their anchor text and returned with
absolute URLs; script, style, and other non-content elements are dropped.
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Dict, List, Tuple
from urllib.parse import urljoin, urldefrag

_SKIP = {"script", "style", "noscript", "template", "svg", "canvas", "iframe", "head", "object"}
_BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "nav", "aside", "ul", "ol",
          "table", "tr", "blockquote", "form", "figure", "figcaption", "dl", "dt", "dd", "hr",
          "address", "details", "summary", "fieldset"}
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class _TextBuilder(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: List[str] = []
        self.links: List[Dict[str, str]] = []
        self.title = ""
        self._skip_depth = 0
        # Counted apart from _skip_depth: "head" is skipped too, and the
        # document's own <title> sits inside it.
        self._svg_depth = 0
        self._in_title = False
        self._pre_depth = 0
        self._href_stack: List[str] = []
        self._cell_open = False

    def _newline(self, count: int = 1) -> None:
        self.parts.append("\n" * count)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "svg":
            self._svg_depth += 1
        if tag == "title":
            self._in_title = not self._svg_depth
            return
        if tag == "base" and attrs.get("href"):
            self.base_url = urljoin(self.base_url, attrs["href"])
            return
        if tag in _SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in _HEADINGS:
            self._newline(2)
            self.parts.append("#" * _HEADINGS[tag] + " ")
        elif tag == "li":
            self._newline()
            self.parts.append("- ")
        elif tag in ("td", "th"):
            self.parts.append(" | " if self._cell_open else "")
            self._cell_open = True
        elif tag == "br":
            self._newline()
        elif tag == "pre":
            self._pre_depth += 1
            self._newline()
        elif tag in _BLOCK:
            self._newline()
            if tag == "tr":
                self._cell_open = False
        elif tag == "img":
            alt = (attrs.get("alt") or "").strip()
            if alt:
                self.parts.append(f" [image: {alt}] ")
        if tag == "a":
            self._href_stack.append(attrs.get("href") or "")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            return
        if tag == "svg":
            self._svg_depth = max(0, self._svg_depth - 1)
        if tag in _SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "a" and self._href_stack:
            href = self._href_stack.pop().strip()
            target = urldefrag(urljoin(self.base_url, href))[0] if href else ""
            if target.startswith(("http://", "https://")):
                self.links.append({"url": target})
                self.parts.append(f" [#{len(self.links)}]")
        elif tag in _HEADINGS or tag == "pre" or tag in _BLOCK:
            if tag == "pre":
                self._pre_depth = max(0, self._pre_depth - 1)
            self._newline()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip_depth:
            return
        if self._pre_depth:
            self.parts.append(data)
        else:
            self.parts.append(re.sub(r"\s+", " ", data))


def _tidy(text: str) -> str:
    lines = [line.strip() for line in text.split("\n")]
    out: List[str] = []
    blank = False
    for line in lines:
        if not line:
            if out and not blank:
                out.append("")
            blank = True
            continue
        out.append(line)
        blank = False
    return "\n".join(out).strip()


def render(body: str, content_type: str, base_url: str) -> Tuple[str, str, List[Dict[str, str]]]:
    """(title, text, links) for a fetched body."""
    if "html" in content_type or ("xml" in content_type and body.lstrip().startswith("<")):
        builder = _TextBuilder(base_url)
        builder.feed(body)
        builder.close()
        return re.sub(r"\s+", " ", builder.title).strip(), _tidy("".join(builder.parts)), builder.links
    if "json" in content_type:
        try:
            return "", json.dumps(json.loads(body), indent=2, ensure_ascii=False), []
        except ValueError:
            pass
    return "", _tidy(body), []


LINK_MARKER = re.compile(r"\[#(\d+)\]")


def paginate(text: str, page_chars: int) -> List[Tuple[int, int]]:
    """(start, end) offsets of each page, cut at line boundaries where possible."""
    pages: List[Tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + page_chars)
        if end < len(text):
            cut = text.rfind("\n", start, end)
            if cut > start:
                end = cut + 1
        pages.append((start, end))
        start = end
    return pages or [(0, 0)]
