#!/usr/bin/env python3
"""Check Quarto or fallback website output using only Python's standard library."""

from __future__ import annotations

import json
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
EXPECTED_PAGES = {'index.html', 'research.html', 'publications.html', 'data.html',
                  'teaching.html', 'cv.html', 'contact.html', 'healthcare-capacity.html',
                  'czechoslovak-foreign-trade.html', 'czechoslovakia-eer.html',
                  'czechoslovakia-financial-stress.html', 'czechoslovak-commercial-banking.html',
                  'the-missing-j.html', '404.html'}


class Page(HTMLParser):
    """Collect metadata, link targets and anchor names from one HTML document."""

    LINK_ATTRIBUTES = {
        "a": ("href",), "img": ("src",), "script": ("src",),
        "link": ("href",), "source": ("src",), "audio": ("src",),
        "video": ("src", "poster"), "iframe": ("src",), "object": ("data",),
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.description = ""
        self.has_main = False
        self.has_h1 = False
        self.ids: list[str] = []
        self.anchors: set[str] = set()
        self.links: list[str] = []
        self.images_without_alt: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta" and (values.get("name") or "").lower() == "description":
            self.description = (values.get("content") or "").strip()
        elif tag == "main" or "ac-page" in (values.get("class") or "").split():
            self.has_main = True
        elif tag == "h1":
            self.has_h1 = True
        identifier = values.get("id")
        if identifier:
            self.ids.append(identifier)
            self.anchors.add(identifier)
        if tag == "a" and values.get("name"):
            self.anchors.add(values["name"] or "")
        for attr in self.LINK_ATTRIBUTES.get(tag, ()):
            if values.get(attr):
                self.links.append(values[attr] or "")
        # An explicitly empty alt is valid for a decorative image.
        if tag == "img" and "alt" not in values:
            self.images_without_alt.append(values.get("src") or "?")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


def check_target(page: Path, value: str, documents: dict[Path, Page]) -> str | None:
    """Resolve local paths from their page, or from docs/ for a leading slash."""
    value = value.strip()
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return f"invalid URL: {value}"
    if parsed.scheme or parsed.netloc:
        return None
    path_part = unquote(parsed.path)
    if path_part.startswith("/"):
        target = DOCS / path_part.lstrip("/")
    elif path_part:
        target = page.parent / path_part
    else:
        target = page
    target = target.resolve()
    try:
        target.relative_to(DOCS.resolve())
    except ValueError:
        return f"path escapes docs directory: {value}"
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        return f"missing target: {value}"
    fragment = unquote(parsed.fragment)
    # Text fragments are browser directives, not element IDs.
    fragment = fragment.split(":~:text=", 1)[0]
    if fragment and target.suffix.lower() in {".html", ".htm"}:
        document = documents.get(target)
        if document is None:
            return f"unreadable HTML target: {value}"
        if fragment not in document.anchors:
            return f"missing anchor #{fragment} in {target.relative_to(DOCS.resolve())}"
    if target.suffix.lower() == ".pdf":
        with target.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                return f"linked PDF is empty or invalid: {value}"
    return None


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    pages = sorted(DOCS.rglob("*.html"))
    actual_pages = {page.relative_to(DOCS).as_posix() for page in pages}
    for missing in sorted(EXPECTED_PAGES - actual_pages):
        errors.append(f"Required page missing: {missing}")
    for extra in sorted(actual_pages - EXPECTED_PAGES):
        errors.append(f"Unexpected public HTML page: {extra}")

    documents: dict[Path, Page] = {}
    for page in pages:
        document = Page()
        try:
            document.feed(page.read_text(encoding="utf-8"))
            document.close()
        except (OSError, UnicodeError) as exc:
            errors.append(f"{page.name}: cannot read HTML: {exc}")
            continue
        documents[page.resolve()] = document

    for page, document in documents.items():
        name = page.relative_to(DOCS.resolve()).as_posix()
        if not "".join(document.title_parts).strip():
            errors.append(f"{name}: missing <title>")
        if not document.description:
            errors.append(f"{name}: missing meta description")
        if not document.has_main:
            errors.append(f"{name}: missing <main>")
        if name != "404.html" and not document.has_h1:
            errors.append(f"{name}: missing H1")
        duplicates = [item for item, count in Counter(document.ids).items() if count > 1]
        if duplicates:
            errors.append(f"{name}: duplicate IDs {duplicates}")
        for value in document.links:
            problem = check_target(page, value, documents)
            if problem:
                errors.append(f"{name}: {problem}")
        for source in document.images_without_alt:
            warnings.append(f"{name}: image without alt attribute: {source}")

    required_assets = [
        "assets/css/site-v4.css", "assets/js/site.js",
    ]
    for relative_path in required_assets:
        if not (DOCS / relative_path).is_file():
            errors.append(f"Required output missing: docs/{relative_path}")

    search_files = [
        path for path in (DOCS / "search.json", DOCS / "search-index.json")
        if path.is_file()
    ]
    if not search_files:
        errors.append("Search output missing: expected search.json or search-index.json")
    for search_file in search_files:
        try:
            entries = json.loads(search_file.read_text(encoding="utf-8"))
            if not isinstance(entries, list) or not entries:
                errors.append(f"{search_file.name}: expected a non-empty search index")
                continue
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("href"), str):
                    errors.append(f"{search_file.name}: search entry lacks an href")
                    continue
                problem = check_target(DOCS / "index.html", entry["href"], documents)
                if problem:
                    errors.append(f"{search_file.name}: {problem}")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{search_file.name}: cannot read search index: {exc}")

    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))
    print(f"Checked {len(pages)} HTML pages (expected {len(EXPECTED_PAGES)}).")
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"All structural checks passed ({len(warnings)} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
