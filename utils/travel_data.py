"""Live travel data helpers shared by the trip-planning dashboard.

The services used here are public OpenStreetMap and Wikipedia endpoints. They
do not need a user-supplied API key.
"""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import urlencode

import requests
import streamlit as st

from config import (
    ATTRACTION_CATEGORIES,
    CACHE_TTL_ATTRACTIONS,
    CACHE_TTL_COORDINATES,
    MAX_ATTRACTION_DISTANCE_KM,
    NOMINATIM_API,
    NON_ATTRACTION_CATEGORIES,
    USER_AGENT,
    WIKIPEDIA_API,
)

REQUEST_HEADERS = {"User-Agent": USER_AGENT}


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two coordinates in kilometres."""
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    a = math.sin((lat2_rad - lat1_rad) / 2) ** 2
    a += (
        math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin((lon2_rad - lon1_rad) / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


@st.cache_data(ttl=CACHE_TTL_COORDINATES, show_spinner=False)
def geocode_location(location_name: str) -> dict[str, float | str] | None:
    """Look up a destination or a visitor-entered location in OpenStreetMap."""
    if not location_name or not location_name.strip():
        return None

    try:
        response = requests.get(
            NOMINATIM_API,
            params={"q": location_name.strip(), "format": "jsonv2", "limit": 1},
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            return None
        result = results[0]
        return {
            "lat": float(result["lat"]),
            "lon": float(result["lon"]),
            "label": result.get("display_name", location_name.strip()),
        }
    except (requests.RequestException, TypeError, ValueError, KeyError, IndexError):
        return None


def _is_likely_attraction(page: dict[str, Any]) -> bool:
    category_text = " ".join(
        category.get("title", "").replace("Category:", "").lower()
        for category in page.get("categories", [])
    )
    return not any(hint in category_text for hint in NON_ATTRACTION_CATEGORIES) and any(
        hint in category_text for hint in ATTRACTION_CATEGORIES
    )


@st.cache_data(ttl=CACHE_TTL_ATTRACTIONS, show_spinner=False)
def get_city_attractions(city: str, limit: int = 6) -> list[dict[str, Any]]:
    """Return public attractions near *city*, with Wikipedia as the source."""
    destination = geocode_location(city)
    if not destination:
        return []

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"tourist attractions in {city}",
        "gsrnamespace": 0,
        "gsrlimit": 30,
        "prop": "pageimages|extracts|coordinates|pageprops|categories",
        "cllimit": "max",
        "piprop": "thumbnail",
        "pithumbsize": 1200,
        "exintro": 1,
        "explaintext": 1,
        "exsentences": 2,
    }
    try:
        response = requests.get(
            WIKIPEDIA_API, params=params, headers=REQUEST_HEADERS, timeout=10
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {}).values()
    except (requests.RequestException, TypeError, ValueError):
        return []

    requested_name = " ".join(city.lower().split())
    category_matches: list[dict[str, Any]] = []
    fallback_matches: list[dict[str, Any]] = []

    for page in sorted(pages, key=lambda item: int(item.get("index", 9999))):
        if "disambiguation" in page.get("pageprops", {}):
            continue

        name = page.get("title", "").strip()
        description = page.get("extract", "").strip()
        coordinate = page.get("coordinates", [{}])[0]
        if (
            not name
            or not description
            or " ".join(name.lower().split()) == requested_name
        ):
            continue

        try:
            lat, lon = float(coordinate["lat"]), float(coordinate["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        city_distance = distance_km(
            float(destination["lat"]), float(destination["lon"]), lat, lon
        )
        if city_distance > MAX_ATTRACTION_DISTANCE_KM:
            continue

        place = {
            "name": name,
            "description": description,
            "image": page.get("thumbnail", {}).get("source"),
            "lat": lat,
            "lon": lon,
            "source": (
                f"https://en.wikipedia.org/?curid={page['pageid']}"
                if page.get("pageid")
                else None
            ),
            "city_distance": city_distance,
        }
        (category_matches if _is_likely_attraction(page) else fallback_matches).append(
            place
        )

    places = category_matches or fallback_matches
    places.sort(key=lambda item: (item["image"] is None, item["city_distance"]))
    return places[:limit]


def directions_url(
    destination_lat: float,
    destination_lon: float,
    origin: dict[str, float] | None = None,
) -> str:
    """Build a Google Maps directions URL, optionally from the visitor's location."""
    params = {
        "api": 1,
        "destination": f"{destination_lat:.6f},{destination_lon:.6f}",
        "travelmode": "driving",
    }
    if origin:
        params["origin"] = f"{origin['lat']:.6f},{origin['lon']:.6f}"
    return f"https://www.google.com/maps/dir/?{urlencode(params)}"


def hotel_search_url(
    city: str, check_in: str, check_out: str, travelers: int, rooms: int
) -> str:
    """Build a live Google Hotels comparison link for the selected trip."""
    query = f"Hotels in {city}, {check_in} to {check_out}, {travelers} guests, {rooms} rooms"
    return f"https://www.google.com/travel/search?{urlencode({'q': query})}"
