"""Tests for budget filtering of live hotel records."""

from utils.hotels import get_real_hotels
from utils.pricing import HotelStarCategory


def test_hotels_are_listed_only_when_their_full_estimated_band_fits_budget(monkeypatch):
    monkeypatch.setattr(
        "utils.hotels.fetch_real_hotels_from_osm",
        lambda city, limit: [
            {"name": "Budget Lodge", "stars": 2, "area": "Centre"},
            {"name": "Midrange Hotel", "stars": 3, "area": "Centre"},
            {"name": "Upscale Hotel", "stars": 4, "area": "Centre"},
        ],
    )

    hotels = get_real_hotels("Goa", (5000, 15000))

    assert [hotel["name"] for hotel in hotels] == ["Midrange Hotel"]
    assert hotels[0]["category"] is HotelStarCategory.THREE_STAR
