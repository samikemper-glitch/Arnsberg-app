from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from arnsberg_buergermonitor import PLACES, collect

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR
FRONTEND_DIR = BASE_DIR
DATA_FILE = BASE_DIR / "data.json"

app = FastAPI(
    title="Arnsberg Bürger Monitor",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def empty_data_structure(warning: str | None = None) -> dict[str, Any]:
    return {
        "generated_at": None,
        "places": PLACES,
        "items_total": 0,
        "by_place": {place: [] for place in PLACES} | {"Unklar": []},
        "warning": warning,
    }


def save_data(data: dict[str, Any]) -> None:
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_data() -> dict[str, Any]:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    try:
        data = collect()
        save_data(data)
        return data
    except Exception:
        return empty_data_structure(
            warning="Daten konnten aktuell nicht von den Quellen geladen werden."
        )


def ensure_file(path: Path, media_type: str | None = None) -> FileResponse:
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Datei nicht gefunden: {path.name}")
    if media_type:
        return FileResponse(path, media_type=media_type)
    return FileResponse(path)


@app.get("/api")
def api_root() -> dict[str, str]:
    return {
        "status": "ok",
        "message": "Arnsberg Bürger Monitor API läuft.",
    }


@app.get("/api/refresh")
def refresh() -> dict[str, Any]:
    try:
        data = collect()
        save_data(data)
        return {
            "status": "ok",
            "generated_at": data.get("generated_at"),
            "items_total": data.get("items_total", 0),
        }
    except Exception:
        return {
            "status": "error",
            "message": "Daten konnten nicht neu geladen werden.",
        }


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    data = load_data()
    return {
        "generated_at": data.get("generated_at"),
        "places": data.get("places", []),
        "items_total": data.get("items_total", 0),
        "warning": data.get("warning"),
    }


@app.get("/api/places")
def places() -> list[str]:
    data = load_data()
    return data.get("places", [])


@app.get("/api/items")
def items(
    ort: str | None = Query(default=None),
    stadtweit: bool | None = Query(default=None),
    suche: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    data = load_data()

    if ort:
        values = data.get("by_place", {}).get(ort, [])
    else:
        values = []
        seen: set[str] = set()

        for place_items in data.get("by_place", {}).values():
            for item in place_items:
                key = (
                    item.get("source_url")
                    or item.get("title")
                    or json.dumps(item, ensure_ascii=False, sort_keys=True)
                )
                if key in seen:
                    continue
                seen.add(key)
                values.append(item)

    if stadtweit is not None:
        values = [
            item
            for item in values
            if bool(item.get("city_wide")) is stadtweit
        ]

    if suche:
        needle = suche.lower().strip()
        values = [
            item
            for item in values
            if needle in (item.get("title") or "").lower()
            or needle in (item.get("teaser") or "").lower()
            or needle in (item.get("citizen_summary") or "").lower()
            or needle in (item.get("section") or "").lower()
        ]

    values.sort(
        key=lambda x: (
            x.get("published_at") or "",
            x.get("title") or "",
        ),
        reverse=True,
    )
    return values[:limit]


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return ensure_file(
        FRONTEND_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@app.get("/service-worker.js")
def service_worker() -> FileResponse:
    return ensure_file(
        FRONTEND_DIR / "service-worker.js",
        media_type="application/javascript",
    )


@app.get("/")
def index() -> FileResponse:
    return ensure_file(FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
