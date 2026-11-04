#!/usr/bin/env python3
"""Fail closed if a build would expose plaintext from the restricted GIS portal.

Only the password form, its loader, public encryption parameters and ciphertext
are publishable. These checks require no password and never decrypt the data.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from gis_access_policy import PROTECTED_PAGE, protected_page_href


ROOT = Path(__file__).resolve().parents[1]
RELATIVE = Path("assets/files/datasets/historical-gis-protected")
OLD_LOCATIONS = (
    Path("assets/files/datasets/historical-gis"),
    Path("data_sources/historical-gis"),
    Path("assets/js/historical-gis.js"),
    Path("assets/css/historical-gis.css"),
)
RAW_FILE_NAMES = re.compile(
    r"^(?:GIS_Czech_Lands_|Czech_Lands_Historical_Atlas_|"
    r"historical_gis_czech_lands_|histCzechia_|gis_.*\.(?:csv|gpkg|zip|xz))",
    re.IGNORECASE,
)


class Gate(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: dict[str, tuple[str, dict]] = {}
        self.meta: dict[str, str] = {}
        self.scripts: list[str] = []
        self.explorer_markup = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.nodes[values["id"]] = (tag, values)
        if tag == "meta":
            self.meta[(values.get("name") or "").lower()] = values.get("content") or ""
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        if "gis-page" in (values.get("class") or "").split():
            self.explorer_markup = True


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_no_plaintext(base: Path, errors: list[str]) -> None:
    for relative in OLD_LOCATIONS:
        path = base / relative
        if path.is_file() or (path.is_dir() and any(p.is_file() for p in path.rglob("*"))):
            errors.append(f"Former plaintext GIS location remains: {path}")
    for folder in (base / "assets", base / "data_sources"):
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.is_relative_to(base / RELATIVE):
                continue
            if path.is_file() and RAW_FILE_NAMES.match(path.name):
                errors.append(f"Unencrypted GIS file remains in the publication tree: {path}")


def verify_ciphertext(base: Path, errors: list[str]) -> dict[str, str]:
    folder = base / RELATIVE
    config_path = folder / "config.json"
    hashes: dict[str, str] = {}
    if not config_path.is_file():
        errors.append(f"Protected GIS encryption config missing: {config_path}")
        return hashes
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("config must be an object")
        if set(config) != {"version", "kdf", "cipher", "manifest", "aadPrefix"}:
            raise ValueError("config has unexpected or missing fields")
        if config["version"] != 1 or config["cipher"] != "AES-GCM":
            raise ValueError("unsupported encrypted GIS format")
        kdf = config["kdf"]
        if not isinstance(kdf, dict) or set(kdf) != {"name", "hash", "iterations", "salt"}:
            raise ValueError("invalid key-derivation settings")
        if kdf["name"] != "PBKDF2" or kdf["hash"] != "SHA-256":
            raise ValueError("unsupported key-derivation algorithm")
        if type(kdf["iterations"]) is not int or kdf["iterations"] < 600000:
            raise ValueError("password derivation must use at least 600,000 iterations")
        if len(base64.b64decode(kdf["salt"], validate=True)) < 16:
            raise ValueError("key-derivation salt is too short")
        if config["manifest"] != "vault.bin" or config["aadPrefix"] != "adamdittrich-gis-v1/":
            raise ValueError("invalid encrypted manifest or authentication context")
        if not (folder / config["manifest"]).is_file():
            raise ValueError("encrypted manifest is missing")
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, binascii.Error) as exc:
        errors.append(f"Unsafe GIS encryption config in {base}: {exc}")
        return hashes

    nonces: set[bytes] = set()
    count = 0
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(folder).as_posix()
        if path == config_path:
            hashes[name] = digest(path)
            continue
        if path.suffix != ".bin":
            errors.append(f"Unexpected non-ciphertext file in protected GIS assets: {path}")
            continue
        # Envelope: a unique 12-byte nonce, ciphertext, and 16-byte GCM tag.
        if path.stat().st_size < 29:
            errors.append(f"Incomplete encrypted GIS object: {path}")
            continue
        with path.open("rb") as stream:
            nonce = stream.read(12)
        if nonce in nonces:
            errors.append(f"Reused AES-GCM nonce within protected GIS assets: {path}")
        nonces.add(nonce)
        hashes[name] = digest(path)
        count += 1
    if count < 2:
        errors.append(f"Protected GIS content is incomplete in {folder}")
    return hashes


def verify_gate(root: Path, errors: list[str]) -> None:
    source = root / "czech-lands-historical-gis.qmd"
    source_text = source.read_text(encoding="utf-8")
    front = re.match(r"\s*---\s*\n(.*?)\n---(?:\s|$)", source_text, re.DOTALL)
    if not front or not re.search(r"(?m)^search:\s*false\s*$", front.group(1)):
        errors.append("The restricted GIS document must set search: false.")
    page = root / "docs" / PROTECTED_PAGE
    if not page.is_file():
        errors.append("The GIS password page was not rendered.")
        return
    gate = Gate()
    gate.feed(page.read_text(encoding="utf-8"))
    gate.close()
    for identifier in ("gis-access-form", "gis-password", "gis-unlock-status", "gis-private-root"):
        if identifier not in gate.nodes:
            errors.append(f"GIS password page is missing #{identifier}.")
    if gate.nodes.get("gis-access-form", (None,))[0] != "form":
        errors.append("GIS access control must use an actual form.")
    tag, attrs = gate.nodes.get("gis-password", (None, {}))
    if tag != "input" or attrs.get("type", "").lower() != "password":
        errors.append("GIS access control must use a password input.")
    if not any(path.split("?", 1)[0].endswith("assets/js/gis-access.js") for path in gate.scripts):
        errors.append("The GIS password page does not load gis-access.js.")
    required_robots = {"noindex", "nofollow", "noarchive"}
    robots = set(re.split(r"[,\s]+", gate.meta.get("robots", "").lower()))
    if not required_robots <= robots:
        errors.append("The restricted GIS page must set noindex, nofollow and noarchive.")
    if gate.explorer_markup or any(identifier in gate.nodes for identifier in (
            "gis-map-canvas", "gis-map-svg-element", "gis-district-name", "gis-gallery")):
        errors.append("The GIS explorer is present as plaintext before unlocking.")
    if "prepare_historical_gis.py" in (root / "_quarto.yml").read_text(encoding="utf-8"):
        errors.append("The obsolete plaintext GIS build step is still configured.")
    if (root / "scripts/prepare_historical_gis.py").exists():
        errors.append("The obsolete plaintext GIS assembler remains in the source tree.")


def verify_discovery(output: Path, errors: list[str]) -> None:
    for path in (output / "search.json", output / "search-index.json"):
        if path.is_file():
            entries = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entries, list) or any(
                    not isinstance(item, dict) or not isinstance(item.get("href"), str)
                    for item in entries):
                errors.append(f"Malformed search output: {path}")
            elif any(protected_page_href(item["href"]) for item in entries):
                errors.append(f"The restricted GIS page is indexed in {path.name}.")
    sitemap = output / "sitemap.xml"
    if not sitemap.is_file():
        errors.append("Website sitemap missing.")
    elif any(protected_page_href(item.text or "")
             for item in ET.parse(sitemap).getroot().findall(".//{*}loc")):
        errors.append("The restricted GIS page remains in the sitemap.")


def main() -> int:
    errors: list[str] = []
    try:
        for base in (ROOT, ROOT / "docs"):
            verify_no_plaintext(base, errors)
        source = verify_ciphertext(ROOT, errors)
        published = verify_ciphertext(ROOT / "docs", errors)
        if source != published:
            errors.append("Source and published GIS ciphertext files differ.")
        verify_gate(ROOT, errors)
        verify_discovery(ROOT / "docs", errors)
    except (OSError, UnicodeError, ValueError, TypeError, ET.ParseError) as exc:
        errors.append(f"Cannot verify restricted GIS publication: {exc}")
    if errors:
        for error in dict.fromkeys(errors):
            print("ERROR:", error)
        return 1
    print(f"Restricted GIS checks passed: locked page, {len(source) - 1} ciphertext objects, "
          "no plaintext assets or discovery entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
