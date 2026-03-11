from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import re
import sys
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

USER_AGENT = "ArnsbergBuergermonitor/0.1 (+lokales Analyse-Skript)"
TIMEOUT = 20

PLACES = [
    "Arnsberg",
    "Bachum",
    "Bruchhausen",
    "Breitenbruch",
    "Herdringen",
    "Holzen",
    "Hüsten",
    "Müschede",
    "Neheim",
    "Niedereimer",
    "Oeventrop",
    "Rumbeck",
    "Uentrop",
    "Voßwinkel",
    "Wennigloh",
]
CITY_WIDE_HINTS = {
    "stadt arnsberg",
    "gesamtstadt",
    "stadtweit",
    "alle ortsteile",
    "gesamtstädtisch",
    "im gesamten stadtgebiet",
}

OFFICIAL_SOURCES = {
    "ratsinfo_news": "https://ratsinfo.arnsberg.de/news",
    "ratsinfo_vorlagen": "https://ratsinfo.arnsberg.de/vorlagen",
    "arnsberg_home": "https://www.arnsberg.de/",
    "pressestelle": "https://www.arnsberg.de/rathaus-politik/pressestelle/presse-infos",
}

# Nur Quellen eintragen, die du ausdrücklich als "offizielle Medien" freigibst.
# Beispiele: RSS-Feeds oder Übersichtsseiten lokaler, offizieller Stellen.
OFFICIAL_MEDIA_FEEDS: list[str] = []


@dataclasses.dataclass
class Item:
    title: str
    source_name: str
    source_url: str
    section: str
    teaser: str
    places: list[str]
    city_wide: bool
    published_at: str | None = None
    raw_text: str | None = None
    citizen_summary: str | None = None


session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def fetch_html(url: str) -> BeautifulSoup:
    response = session.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}


def parse_german_date(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        day, month, year = map(int, m.groups())
        return dt.date(year, month, day).isoformat()
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜ]+)\s*(\d{4})", text)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        year = int(m.group(3))
        month = MONTHS.get(month_name)
        if month:
            return dt.date(year, month, day).isoformat()
    return None


def detect_places(text: str) -> tuple[list[str], bool]:
    haystack = f" {text.lower()} "
    found = [place for place in PLACES if place.lower() in haystack]
    city_wide = any(hint in haystack for hint in CITY_WIDE_HINTS)
    if "arnsberg" in haystack and not found:
        found.append("Arnsberg")
    if city_wide and "Arnsberg" not in found:
        found.insert(0, "Arnsberg")
    return sorted(set(found)), city_wide


def simplify_text(title: str, teaser: str, places: list[str], city_wide: bool) -> str:
    # Regelbasierte Kurzfassung ohne KI. Für bessere Ergebnisse kann später ein LLM ergänzt werden.
    parts: list[str] = []
    if places:
        if city_wide:
            parts.append("Das betrifft die ganze Stadt und damit alle Ortsteile.")
        else:
            parts.append(f"Das betrifft vor allem: {', '.join(places)}.")
    core = teaser or title
    core = re.sub(r"\([^)]*\)", "", core)
    core = re.sub(r"\b(Beschlussvorlage|Berichtsvorlage|Mitteilungsvorlage)\b", "Vorlage", core, flags=re.I)
    core = clean_text(core)
    if core:
        parts.append(f"Kurz erklärt: {core}")
    if not parts:
        parts.append(f"Thema: {title}")
    return " ".join(parts)


def parse_ratsinfo_vorlagen(max_items: int = 25) -> list[Item]:
    soup = fetch_html(OFFICIAL_SOURCES["ratsinfo_vorlagen"])
    items: list[Item] = []
    # Sternberg RIS list: titles typically appear as links followed by number and teaser paragraphs.
    for link in soup.select("a[href]"):
        title = clean_text(link.get_text(" ", strip=True))
        href = urljoin(OFFICIAL_SOURCES["ratsinfo_vorlagen"], link.get("href", ""))
        if not title or "Vorgang" in title or not re.search(r"\b\d{1,3}/\d{4}\b", title):
            continue
        parent_text = clean_text(link.parent.get_text(" ", strip=True))
        teaser = parent_text.replace(title, "", 1).strip(" -")
        places, city_wide = detect_places(f"{title} {teaser}")
        exported_date = parse_german_date(title)
        item = Item(
            title=title,
            source_name="Ratsinfo",
            source_url=href,
            section="Vorlagen",
            teaser=teaser,
            places=places,
            city_wide=city_wide,
            published_at=exported_date,
        )
        item.citizen_summary = simplify_text(item.title, item.teaser, item.places, item.city_wide)
        items.append(item)
        if len(items) >= max_items:
            break
    return dedupe_items(items)


def parse_ratsinfo_news(max_items: int = 20) -> list[Item]:
    soup = fetch_html(OFFICIAL_SOURCES["ratsinfo_news"])
    items: list[Item] = []
    for link in soup.select("a[href]"):
        title = clean_text(link.get_text(" ", strip=True))
        href = urljoin(OFFICIAL_SOURCES["ratsinfo_news"], link.get("href", ""))
        if not title or title in {"News", "Startseite", "Ratsinfosystem"}:
            continue
        if href.rstrip("/") == OFFICIAL_SOURCES["ratsinfo_news"].rstrip("/"):
            continue
        ctx = clean_text(link.parent.get_text(" ", strip=True))
        if len(title) < 8:
            continue
        places, city_wide = detect_places(f"{title} {ctx}")
        item = Item(
            title=title,
            source_name="Ratsinfo",
            source_url=href,
            section="News",
            teaser=ctx.replace(title, "", 1).strip(" -"),
            places=places,
            city_wide=city_wide,
        )
        item.citizen_summary = simplify_text(item.title, item.teaser, item.places, item.city_wide)
        items.append(item)
        if len(items) >= max_items:
            break
    return dedupe_items(items)


def parse_arnsberg_home(max_items: int = 40) -> list[Item]:
    soup = fetch_html(OFFICIAL_SOURCES["arnsberg_home"])
    items: list[Item] = []
    for link in soup.select("a[href]"):
        title = clean_text(link.get_text(" ", strip=True))
        href = urljoin(OFFICIAL_SOURCES["arnsberg_home"], link.get("href", ""))
        if not title or len(title) < 6:
            continue
        # nur interne Links berücksichtigen
        if not href.startswith("https://www.arnsberg.de"):
            continue
        # Navigationsmüll reduzieren
        bad = {"Zurück", "Nach oben springen", "Zum Inhalt springen", "Service & Kontakt", "Startseite"}
        if title in bad:
            continue
        ctx = clean_text(link.parent.get_text(" ", strip=True))
        places, city_wide = detect_places(f"{title} {ctx}")
        item = Item(
            title=title,
            source_name="Arnsberg.de",
            source_url=href,
            section="Website",
            teaser=ctx.replace(title, "", 1).strip(" -"),
            places=places,
            city_wide=city_wide,
        )
        item.citizen_summary = simplify_text(item.title, item.teaser, item.places, item.city_wide)
        items.append(item)
        if len(items) >= max_items:
            break
    return dedupe_items(items)


def dedupe_items(items: Iterable[Item]) -> list[Item]:
    seen: set[tuple[str, str]] = set()
    out: list[Item] = []
    for item in items:
        key = (item.title.lower(), item.source_url)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def expand_city_wide_items(items: list[Item]) -> list[Item]:
    expanded: list[Item] = []
    for item in items:
        if item.city_wide:
            for place in PLACES:
                clone = dataclasses.replace(item, places=[place])
                expanded.append(clone)
        elif item.places:
            expanded.append(item)
        else:
            clone = dataclasses.replace(item, places=["Unklar"])
            expanded.append(clone)
    return expanded


def group_by_place(items: list[Item]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {place: [] for place in PLACES}
    result["Unklar"] = []
    for item in expand_city_wide_items(items):
        place = item.places[0] if item.places else "Unklar"
        result.setdefault(place, []).append(dataclasses.asdict(item))
    for place, bucket in result.items():
        bucket.sort(key=lambda x: (x.get("published_at") or "9999-12-31", x["title"]))
    return result


def collect() -> dict:
    all_items = []
    all_items.extend(parse_ratsinfo_vorlagen())
    all_items.extend(parse_ratsinfo_news())
    all_items.extend(parse_arnsberg_home())
    all_items = dedupe_items(all_items)
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sources": OFFICIAL_SOURCES,
        "places": PLACES,
        "items_total": len(all_items),
        "by_place": group_by_place(all_items),
    }


def main() -> int:
    output_path = sys.argv[1] if len(sys.argv) > 1 else "arnsberg_buergermonitor.json"
    data = collect()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Datei geschrieben: {output_path} | Einträge: {data['items_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
