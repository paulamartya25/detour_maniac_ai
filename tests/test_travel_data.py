"""Tests for travel-planning links and local calculation helpers."""

from urllib.parse import parse_qs, urlparse

from utils.travel_data import directions_url, distance_km, hotel_search_url


def test_directions_url_uses_current_location_when_available():
    url = directions_url(15.4909, 73.8278, {"lat": 19.076, "lon": 72.8777})
    params = parse_qs(urlparse(url).query)

    assert params["api"] == ["1"]
    assert params["origin"] == ["19.076000,72.877700"]
    assert params["destination"] == ["15.490900,73.827800"]


def test_directions_url_allows_google_maps_to_choose_an_origin():
    url = directions_url(15.4909, 73.8278)
    params = parse_qs(urlparse(url).query)

    assert "origin" not in params
    assert params["destination"] == ["15.490900,73.827800"]


def test_hotel_search_url_keeps_trip_details():
    url = hotel_search_url("Goa, India", "2026-12-01", "2026-12-06", 2, 1)
    params = parse_qs(urlparse(url).query)

    assert "Goa, India" in params["q"][0]
    assert "2026-12-01 to 2026-12-06" in params["q"][0]
    assert "2 guests" in params["q"][0]


def test_distance_is_zero_for_same_coordinates():
    assert distance_km(15.4909, 73.8278, 15.4909, 73.8278) == 0.0
