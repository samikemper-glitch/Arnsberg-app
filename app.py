from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

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

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

TIMEOUT = 20

SOURCES = [
    {
        "name": "Arnsberg.de",
        "type": "official",
        "base": "https://www.arnsberg.de",
        "urls": [
            "https://www.arnsberg.de/",
            "https://www.arnsberg.de/rathaus-politik/pressestelle/presse-infos",
        ],
        "allow_domains": ["www.arnsberg.de", "arnsberg.de"],
        "include_keywords": [
            "presse",
            "artikel",
            "news",
            "meldung",
            "mitteilung",
            "projekt",
            "rathaus",
            "politik",
            "stadt",
            "verkehr",
            "schule",
            "kita",
            "bau",
        ],
        "exclude_keywords": [
            "impressum",
            "datenschutz",
            "barrierefreiheit",
            "karriere",
            "serviceportal",
            "service-portal",
            "kontakt",
            "suche",
            "login",
        ],
    },
    {
        "name": "Westfalenpost Arnsberg",
        "type": "media",
        "base": "https://www.wp.de",
        "urls": [
            "https://www.wp.de/staedte/arnsberg/",
        ],
        "allow_domains": ["www.wp.de", "wp.de"],
        "include_keywords": [
            "arnsberg",
            "neheim",
            "hüsten",
            "oeventrop",
            "bruchhausen",
            "herdringen",
            "voßwinkel",
            "bachum",
            "politik",
            "rat",
            "stadt",
            "verkehr",
            "schule",
            "bau",
        ],
        "exclude_keywords": [
            "impressum",
            "datenschutz",
            "abo",
            "anmelden",
            "login",
            "newsletter",
            "podcast",
            "video",
            "trauer",
            "shop",
        ],
    },
    {
        "name": "Ratsinfosystem Arnsberg",
        "type": "ratsinfo",
        "base": "https://ratsinfo.arnsberg.de",
        "urls": [
            "https://ratsinfo.arnsberg.de/",
        ],
        "allow_domains": ["ratsinfo.arnsberg.de"],
        "include_keywords": [
            "vorlage",
            "sitzung",
            "top",
            "beschluss",
            "ausschuss",
            "rat",
            "bezirksausschuss",
            "recherche",
            "meeting",
            "document",
        ],
        "exclude_keywords": [
            "login",
            "impressum",
            "datenschutz",
            "hilfe",
            "javascript:",
        ],
    },
]

CITY_WIDE_KEYWORDS = [
    "stadt arnsberg",
    "gesamtstadt",
    "gesamtstädtisch",
    "stadtweit",
    "gesamte stadt",
    "alle ortsteile",
    "15 orte",
    "15 orte - eine stadt",
    "15 orte – eine stadt",
]

NOISE_PATTERNS = [
    r"\bzur suche springen\b",
    r"\bzur hauptnavigation springen\b",
    r"\bzum inhalt springen\b",
    r"\bbarrierefreiheit\b",
    r"\bgebärdensprache\b",
    r"\bleichte sprache\b",
    r"\bservice portal\b",
    r"\bservice-portal\b",
    r"\bkarriere\b",
    r"\bimpressum\b",
    r"\bdatenschutz\b",
    r"\bcookie[s]?\b",
    r"\bnewsletter\b",
    r"\banmelden\b",
    r"\blogin\b",
]

SECTION_KEYWORDS = {
    "Verkehr": ["verkehr", "straße", "ampel", "kreuzung", "park", "parken", "radweg", "brücke", "baustelle"],
    "Bauen": ["bauen", "bau", "sanierung", "umbau", "bebauung", "erschließung", "baugebiet"],
    "Schule/Kita": ["schule", "kita", "kindergarten", "bildung", "schüler", "schul"],
    "Politik": ["rat", "ausschuss", "beschluss", "vorlage", "sitzung", "bezirksausschuss"],
    "Sicherheit": ["feuerwehr", "polizei", "ordnungsamt", "sicherheit", "schutz"],
    "Umwelt": ["umwelt", "klima", "energie", "baum", "natur", "nachhaltigkeit"],
    "Finanzen": ["haushalt", "gebühr", "kosten", "förderung", "finanzen"],
    "Freizeit/Kultur": ["kultur", "sport", "museum", "veranstaltung", "freizeit", "tourismus"],
}


def fetch_html(url: str) -> str | None:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.text
    except Exception:
        return None


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()

    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    cleaned = parsed._replace(fragment="")
    return cleaned.geturl()


def allowed_domain(url: str, allowed_domains: list[str]) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in allowed_domains)


def guess_places(text: str, title: str = "") -> list[str]:
    haystack = f"{title} {text}".lower()
    found: list[str] = []

    for place in PLACES:
        if place.lower() in haystack:
            found.append(place)

    return found


def is_city_wide(text: str, title: str = "") -> bool:
    haystack = f"{title} {text}".lower()

    if any(keyword in haystack for keyword in CITY_WIDE_KEYWORDS):
        return True

    found = guess_places(text, title)
    if len(found) >= 4:
        return True

    return False


def infer_section(text: str, title: str = "") -> str:
    haystack = f"{title} {text}".lower()

    for section, keywords in SECTION_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return section

    return "Allgemein"


def simplify_text(text: str, max_len: int = 420) -> str:
    text = clean_text(text)
    if not text:
        return ""

    replacements = {
        "Beschlussvorlage": "Vorlage",
        "Sitzungsvorlage": "Vorlage",
        "Verwaltungsvorlage": "Vorlage",
        "Maßnahme": "Projekt",
        "Kenntnisnahme": "Info",
        "Beratung": "Besprechung",
        "Umsetzung": "Durchführung",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].strip() + "…"

    return text


def extract_title(soup: BeautifulSoup) -> str:
    candidates = [
        ("meta[property='og:title']", "content"),
        ("meta[name='twitter:title']", "content"),
        ("h1", None),
        ("title", None),
    ]

    for selector, attr in candidates:
        tag = soup.select_one(selector)
        if not tag:
            continue

        if attr:
            value = clean_text(tag.get(attr, ""))
        else:
            value = clean_text(tag.get_text(" ", strip=True))

        if value:
            return value[:220]

    return "Ohne Titel"


def extract_teaser(soup: BeautifulSoup) -> str:
    meta_desc = soup.select_one("meta[name='description']")
    if meta_desc and meta_desc.get("content"):
        teaser = clean_text(meta_desc.get("content", ""))
        if teaser:
            return teaser[:320]

    og_desc = soup.select_one("meta[property='og:description']")
    if og_desc and og_desc.get("content"):
        teaser = clean_text(og_desc.get("content", ""))
        if teaser:
            return teaser[:320]

    first_p = soup.select_one("main p, article p, .content p, .main p, p")
    if first_p:
        teaser = clean_text(first_p.get_text(" ", strip=True))
        if teaser:
            return teaser[:320]

    return ""


def remove_layout_noise(soup: BeautifulSoup) -> None:
    for tag in soup.select(
        "nav, header, footer, aside, script, style, noscript, form, iframe, svg"
    ):
        tag.decompose()

    for tag in soup.select(
        ".menu, .navigation, .nav, .breadcrumb, .breadcrumbs, .footer, .header, "
        ".sidebar, .cookie, .cookies, .consent, .skiplinks, .meta-nav, .social, "
        ".share, .sharing, .advertisement, .ad, .ads"
    ):
        tag.decompose()


def extract_main_text(soup: BeautifulSoup) -> str:
    remove_layout_noise(soup)

    paragraphs = [
        p.get_text(" ", strip=True)
        for p in soup.select("main p, article p, .content p, .main p, p")
    ]
    paragraphs = [clean_text(p) for p in paragraphs]
    paragraphs = [p for p in paragraphs if len(p) > 60]

    if paragraphs:
        return " ".join(paragraphs)

    text = soup.get_text(" ", strip=True)
    return clean_text(text)


def looks_like_interesting_link(url: str, title: str, source: dict[str, Any]) -> bool:
    haystack = f"{url} {title}".lower()

    if any(word in haystack for word in source.get("exclude_keywords", [])):
        return False

    if any(
        haystack.endswith(ext)
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".pdf", ".zip"]
    ):
        return False

    include_keywords = source.get("include_keywords", [])
    if include_keywords and any(word in haystack for word in include_keywords):
        return True

    if source["type"] == "official":
        return "/rathaus-politik/" in haystack or "/presse" in haystack or "/artikel/" in haystack

    if source["type"] == "media":
        return "/staedte/arnsberg/" in haystack or "arnsberg" in haystack

    if source["type"] == "ratsinfo":
        return any(word in haystack for word in ["vorlage", "sitzung", "beschluss", "ausschuss", "rat"])

    return False


def extract_links(list_html: str, list_url: str, source: dict[str, Any]) -> list[tuple[str, str]]:
    soup = BeautifulSoup(list_html, "html.parser")
    links: list[tuple[str, str]] = []
    seen: set[str] = set()

    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        title = clean_text(a.get_text(" ", strip=True))

        if not href:
            continue
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        absolute_url = normalize_url(urljoin(list_url, href))

        if not allowed_domain(absolute_url, source["allow_domains"]):
            continue
        if absolute_url in seen:
            continue
        if len(title) < 4:
            continue
        if not looks_like_interesting_link(absolute_url, title, source):
            continue

        seen.add(absolute_url)
        links.append((title, absolute_url))

    return links


def parse_article(url: str, source: dict[str, Any]) -> dict[str, Any] | None:
    html = fetch_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    title = extract_title(soup)
    teaser = extract_teaser(soup)
    full_text = extract_main_text(soup)

    if not title and not teaser and not full_text:
        return None

    logic_text = f"{title} {teaser} {full_text}"
    places_found = guess_places(logic_text, title)
    city_wide = is_city_wide(logic_text, title)

    if city_wide:
        assigned_places = PLACES[:]
    elif places_found:
        assigned_places = places_found
    else:
        assigned_places = ["Unklar"]

    citizen_summary_source = teaser or full_text or title
    citizen_summary = simplify_text(citizen_summary_source, max_len=420)

    if city_wide and citizen_summary:
        citizen_summary = (
            "Das betrifft die ganze Stadt und damit alle Ortsteile. Kurz erklärt: "
            + citizen_summary
        )

    if len(citizen_summary.strip()) < 20 and len(teaser.strip()) < 20:
        return None

    return {
        "title": title[:220],
        "teaser": teaser[:320],
        "citizen_summary": citizen_summary,
        "source": source["name"],
        "source_type": source["type"],
        "source_url": url,
        "published_at": None,
        "section": infer_section(logic_text, title),
        "places": assigned_places,
        "city_wide": city_wide,
    }


def collect_from_source(source: dict[str, Any], per_list_limit: int = 20) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for list_url in source["urls"]:
        html = fetch_html(list_url)
        if not html:
            continue

        links = extract_links(html, list_url, source)

        for _, url in links[:per_list_limit]:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            try:
                item = parse_article(url, source)
                if item:
                    results.append(item)
            except Exception:
                continue

    return results


def deduplicate_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in items:
        key = (
            item.get("source_url")
            or f"{item.get('source')}|{item.get('title')}|{item.get('teaser')}"
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return unique


def build_by_place(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_place: dict[str, list[dict[str, Any]]] = {place: [] for place in PLACES}
    by_place["Unklar"] = []

    for item in items:
        places = item.get("places") or ["Unklar"]

        for place in places:
            if place not in by_place:
                by_place["Unklar"].append(item)
            else:
                by_place[place].append(item)

    return by_place


def collect() -> dict[str, Any]:
    all_items: list[dict[str, Any]] = []

    for source in SOURCES:
        try:
            items = collect_from_source(source, per_list_limit=20)
            all_items.extend(items)
        except Exception:
            continue

    all_items = deduplicate_items(all_items)
    by_place = build_by_place(all_items)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "places": PLACES,
        "items_total": len(all_items),
        "by_place": by_place,
        "warning": None if all_items else "Es konnten aktuell keine oder nur sehr wenige Inhalte geladen werden.",
    }
