#!/usr/bin/env python3
"""Render a browser-ready static preview of the Quarto source using Pandoc.

This helper is not a replacement for Quarto's full renderer. It exists so that the
repository includes a tested preview even on systems where the Quarto CLI is not
installed. GitHub Actions uses Quarto itself when the repository is published.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGES = [
    "index.qmd",
    "research.qmd",
    "publications.qmd",
    "data.qmd",
    "teaching.qmd",
    "cv.qmd",
    "contact.qmd",
    "404.qmd",
]

NAV = [
    ("index.html", "Home"),
    ("research.html", "Research"),
    ("publications.html", "Publications"),
    ("data.html", "Data"),
    ("teaching.html", "Teaching"),
    ("cv.html", "CV"),
]


def read_front_matter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    data = yaml.safe_load(text[4:end])
    return data if isinstance(data, dict) else {}


def render_fragment(path: Path) -> str:
    cmd = [
        "pandoc",
        str(path),
        "--from=markdown+fenced_divs+link_attributes-implicit_figures",
        "--to=html5",
        "--wrap=none",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def convert_qmd_links(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(["a", "img", "script", "link"]):
        attr = "href" if tag.name in {"a", "link"} else "src"
        value = tag.get(attr)
        if not value:
            continue
        value = str(value)
        if attr == "href" and ".qmd" in value:
            tag[attr] = re.sub(r"\.qmd(?=($|#|\?))", ".html", value)
        if tag.name == "a" and value.startswith(("http://", "https://")):
            tag["target"] = "_blank"
            tag["rel"] = "noopener noreferrer"


def nav_html(current: str) -> str:
    links = []
    for href, label in NAV:
        active = " active" if href == current else ""
        current_attr = ' aria-current="page"' if active else ""
        links.append(
            f'<a class="{active.strip()}" href="{href}"{current_attr}>{html.escape(label)}</a>'
        )
    return f"""
<nav class="site-nav" aria-label="Primary navigation">
  <div class="site-nav-inner">
    <a class="site-brand" href="index.html" aria-label="Adam Dittrich home">
      <img src="assets/img/logo.svg" alt="Adam Dittrich monogram">
    </a>
    <div class="site-nav-links" id="site-nav-links">
      {''.join(links)}
    </div>
    <div class="site-nav-tools">
      <button class="search-trigger" type="button" aria-label="Search site">Search</button>
      <a class="site-contact-link" href="contact.html">Contact</a>
      <button class="site-nav-toggle" type="button" aria-controls="site-nav-links" aria-expanded="false" aria-label="Open navigation">☰</button>
    </div>
  </div>
</nav>
"""


def footer_html() -> str:
    return """
<footer class="site-footer">
  <div class="site-footer-inner">
    <div>© 2026 Adam Dittrich</div>
    <div class="site-footer-center">Economic history · Monetary history · Interwar Central Europe</div>
    <div class="site-footer-links">
      <a href="mailto:adam.dittrich@vse.cz">Email</a>
      <a href="https://scholar.google.com/citations?hl=en&amp;user=w20HpZcAAAAJ" target="_blank" rel="noopener noreferrer">Scholar</a>
      <a href="https://ideas.repec.org/f/pdi678.html" target="_blank" rel="noopener noreferrer">RePEc</a>
    </div>
  </div>
</footer>
"""


def search_html() -> str:
    return """
<div class="static-search" aria-hidden="true" role="dialog" aria-modal="true" aria-label="Search website">
  <div class="static-search-panel">
    <div class="static-search-head">
      <input id="static-search-input" type="search" placeholder="Search research, publications, data…" autocomplete="off" aria-label="Search query">
      <button class="static-search-close" type="button" aria-label="Close search">Close</button>
    </div>
    <div class="static-search-results" aria-live="polite"><p>Type at least two characters.</p></div>
  </div>
</div>
"""


def full_document(meta: dict[str, Any], body: str, current: str) -> str:
    title = str(meta.get("title") or "Adam Dittrich")
    description = str(meta.get("description") or "Academic website of economic historian Adam Dittrich.")
    body_classes = str(meta.get("body-classes") or "")
    page_title = title if title == "Adam Dittrich" else f"{title} — Adam Dittrich"
    og_image = "assets/img/og-card.png"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page_title)}</title>
  <meta name="description" content="{html.escape(description, quote=True)}">
  <meta name="author" content="Adam Dittrich">
  <meta name="theme-color" content="#102b3b">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="Adam Dittrich — Economic Historian">
  <meta property="og:title" content="{html.escape(page_title, quote=True)}">
  <meta property="og:description" content="{html.escape(description, quote=True)}">
  <meta property="og:image" content="{og_image}">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="icon" href="assets/img/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="assets/css/styles.css">
</head>
<body class="{html.escape(body_classes, quote=True)}">
  <a class="skip-link" href="#main-content">Skip to content</a>
  {nav_html(current)}
  <main id="main-content" class="content">
    {body}
  </main>
  {footer_html()}
  {search_html()}
  <script src="assets/js/site.js" defer></script>
</body>
</html>
"""


def copy_assets() -> None:
    target = DOCS / "assets"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(ROOT / "assets", target)
    # Quarto-only include snippets are not part of the browser-facing preview.
    includes = target / "includes"
    if includes.exists():
        shutil.rmtree(includes)


def make_excerpt(text: str, limit: int = 210) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rsplit(" ", 1)[0] + "…"


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    for old in DOCS.glob("*.html"):
        old.unlink()
    copy_assets()

    search_index: list[dict[str, str]] = []

    for filename in PAGES:
        source = ROOT / filename
        if not source.exists():
            raise FileNotFoundError(source)
        meta = read_front_matter(source)
        fragment = render_fragment(source)
        fragment_soup = BeautifulSoup(fragment, "html.parser")
        convert_qmd_links(fragment_soup)

        # Improve image accessibility for the hero when Pandoc preserves Quarto's fig-alt attribute.
        for image in fragment_soup.find_all("img"):
            fig_alt = image.get("fig-alt") or image.get("data-fig-alt")
            if fig_alt and not image.get("alt"):
                image["alt"] = fig_alt
            for key in ("fig-alt", "data-fig-alt"):
                if image.get(key) is not None:
                    del image[key]

        body = str(fragment_soup)
        output_name = filename.replace(".qmd", ".html")
        document = full_document(meta, body, output_name)
        (DOCS / output_name).write_text(document, encoding="utf-8")

        if output_name != "404.html":
            plain = fragment_soup.get_text(" ", strip=True)
            search_index.append(
                {
                    "title": str(meta.get("title") or output_name),
                    "href": output_name,
                    "text": plain,
                    "excerpt": make_excerpt(str(meta.get("description") or plain)),
                }
            )

    (DOCS / "search-index.json").write_text(
        json.dumps(search_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    cname = ROOT / "CNAME"
    if cname.exists():
        shutil.copy2(cname, DOCS / "CNAME")

    print(f"Rendered {len(PAGES)} pages to {DOCS}")


if __name__ == "__main__":
    main()
