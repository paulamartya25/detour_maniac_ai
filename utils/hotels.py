"""Real hotel data fetched from OpenStreetMap via Overpass API."""

from typing import Dict, List, Tuple

import requests
import streamlit as st

OVERPASS_APIS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
NOMINATIM_API = "https://nominatim.openstreetmap.org/search"
REQUEST_HEADERS = {"User-Agent": "detour-maniax/1.0 travel-planner"}
OVERPASS_TIMEOUT_SECONDS = 15


def estimate_hotel_stars(tags: dict) -> int:
    """Estimate hotel star rating from OpenStreetMap tags."""
    if "stars" in tags:
        try:
            stars = int(tags["stars"])
            return min(max(stars, 1), 5)
        except (ValueError, TypeError):
            pass

    name = tags.get("name", "").lower()

    luxury_keywords = [
        "taj",
        "oberoi",
        "itc",
        "leela",
        "palace",
        "grand",
        "luxury",
        "ritz",
        "four seasons",
        "shangri",
    ]
    if any(keyword in name for keyword in luxury_keywords):
        return 5

    upscale_keywords = [
        "hyatt",
        "marriott",
        "radisson",
        "novotel",
        "hilton",
        "westin",
        "sheraton",
        "crowne plaza",
    ]
    if any(keyword in name for keyword in upscale_keywords):
        return 4

    midrange_keywords = [
        "lemon tree",
        "keys",
        "ginger",
        "country inn",
        "holiday inn express",
    ]
    if any(keyword in name for keyword in midrange_keywords):
        return 3

    budget_keywords = ["fab", "treebo", "oyo", "zostel", "hostel", "lodge"]
    if any(keyword in name for keyword in budget_keywords):
        return 2

    return 3


def _hotel_records_from_overpass(elements: list[dict], limit: int) -> List[Dict]:
    """Convert Overpass elements to the hotel format used by the UI."""
    hotels = []
    seen_names = set()
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name", "").strip()
        if not name or name in seen_names:
            continue

        seen_names.add(name)
        hotels.append(
            {
                "name": name,
                "stars": estimate_hotel_stars(tags),
                "area": (
                    tags.get("addr:suburb", "")
                    or tags.get("addr:locality", "")
                    or tags.get("addr:neighbourhood", "")
                    or "City Center"
                ),
                "lat": element.get("lat"),
                "lon": element.get("lon"),
            }
        )
        if len(hotels) >= limit:
            break

    hotels.sort(key=lambda hotel: hotel["stars"], reverse=True)
    return hotels


def _fallback_hotels_from_nominatim(city: str, limit: int) -> List[Dict]:
    """Use OpenStreetMap search when an Overpass mirror is temporarily down."""
    try:
        response = requests.get(
            NOMINATIM_API,
            params={"q": f"hotels in {city}", "format": "jsonv2", "limit": limit},
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, TypeError, ValueError):
        return []

    hotels = []
    seen_names = set()
    for result in results:
        display_name = result.get("display_name", "")
        name = (result.get("name") or display_name.split(",", 1)[0]).strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        hotels.append(
            {
                "name": name,
                "stars": estimate_hotel_stars({"name": name}),
                "area": ",".join(display_name.split(",")[1:3]).strip() or "City Center",
                "lat": result.get("lat"),
                "lon": result.get("lon"),
            }
        )
    hotels.sort(key=lambda hotel: hotel["stars"], reverse=True)
    return hotels


@st.cache_data(ttl=900, show_spinner=False)
def fetch_real_hotels_from_osm(city: str, limit: int = 20) -> List[Dict]:
    """Fetch real hotels, trying alternate public OpenStreetMap services."""
    try:
        response = requests.get(
            NOMINATIM_API,
            params={"q": city, "format": "jsonv2", "limit": 1},
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        city_data = response.json()
        if not city_data:
            return []

        lat = float(city_data[0]["lat"])
        lon = float(city_data[0]["lon"])
    except (requests.RequestException, TypeError, ValueError, KeyError, IndexError):
        return _fallback_hotels_from_nominatim(city, limit)

    overpass_query = f"""
    [out:json][timeout:12];
    (
      node["tourism"="hotel"](around:15000,{lat},{lon});
      way["tourism"="hotel"](around:15000,{lat},{lon});
      node["tourism"="guest_house"](around:15000,{lat},{lon});
      way["tourism"="guest_house"](around:15000,{lat},{lon});
    );
    out tags;
    """

    for endpoint in OVERPASS_APIS:
        try:
            response = requests.post(
                endpoint,
                data=overpass_query,
                headers=REQUEST_HEADERS,
                timeout=OVERPASS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            hotels = _hotel_records_from_overpass(
                response.json().get("elements", []), limit
            )
            if hotels:
                return hotels
        except (requests.RequestException, TypeError, ValueError):
            continue

    return _fallback_hotels_from_nominatim(city, limit)


def get_real_hotels(city: str, budget_range: Tuple[int, int]) -> List[Dict]:
    """Get REAL hotels for a city filtered by budget."""
    from utils.pricing import HotelPricingModel, HotelStarCategory

    available_hotels = fetch_real_hotels_from_osm(city, limit=30)

    if not available_hotels:
        return []

    user_min, user_max = budget_range
    filtered = []

    for hotel in available_hotels:
        try:
            star_category = [
                cat for cat in HotelStarCategory if cat.value == hotel["stars"]
            ][0]
            price_range = HotelPricingModel.get_price_range(star_category)

            if price_range.min_price >= user_min and price_range.max_price <= user_max:
                filtered.append(
                    {
                        "name": hotel["name"],
                        "category": star_category,
                        "area": hotel["area"],
                    }
                )
        except (IndexError, KeyError):
            continue

    return filtered
