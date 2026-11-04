"""Keep the restricted GIS page out of generated public discovery indexes."""

from __future__ import annotations

import json
import posixpath
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit


PROTECTED_PAGE = "czech-lands-historical-gis.html"
PLAINTEXT_PREFIXES = (
    "assets/files/datasets/historical-gis/",
    "data_sources/historical-gis/",
)


def protected_page_href(value: str) -> bool:
    """Match the page, including absolute URLs and section/search fragments."""
    path = unquote(urlsplit(value).path).rstrip("/")
    return path.rsplit("/", 1)[-1] in {PROTECTED_PAGE, PROTECTED_PAGE[:-5] + ".qmd"}


def plaintext_gis_href(value: str) -> bool:
    """Recognise former GIS assets on this website, not external providers."""
    parsed = urlsplit(value)
    if parsed.netloc and parsed.netloc.lower() != "adamdittrich.github.io":
        return False
    path = posixpath.normpath("/" + unquote(parsed.path).lstrip("/")).lstrip("/")
    return any(path.startswith(prefix) for prefix in PLAINTEXT_PREFIXES)


def scrub_indexes(output: Path) -> None:
    """Remove restricted-page entries without changing other search results."""
    for path in (output / "search.json", output / "search-index.json"):
        if not path.is_file():
            continue
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError(f"Cannot safely filter unexpected search index: {path}")
        if any(not isinstance(item, dict) or not isinstance(item.get("href"), str)
               for item in entries):
            raise ValueError(f"Cannot safely filter malformed search entries: {path}")
        filtered = [item for item in entries if not protected_page_href(item["href"])]
        if len(filtered) != len(entries):
            path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            print(f"Excluded {len(entries) - len(filtered)} restricted GIS search entries.")

    sitemap = output / "sitemap.xml"
    if not sitemap.is_file():
        raise FileNotFoundError("The website sitemap is missing.")
    tree = ET.parse(sitemap)
    root = tree.getroot()
    removed = 0
    for entry in list(root):
        location = entry.find("{*}loc")
        if location is not None and protected_page_href(location.text or ""):
            root.remove(entry)
            removed += 1
    if removed:
        if root.tag.startswith("{"):
            ET.register_namespace("", root.tag.split("}", 1)[0][1:])
        tree.write(sitemap, encoding="utf-8", xml_declaration=True)
        print(f"Excluded {removed} restricted GIS sitemap entries.")
