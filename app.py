"""Single-page travel planner for stays, attractions, and directions."""

from __future__ import annotations

import html
from datetime import date, timedelta

import pandas as pd
import streamlit as st

try:
    from streamlit_js_eval import get_geolocation
except ImportError:  # A clear fallback is shown until requirements are installed.
    get_geolocation = None

from utils.hotels import get_real_hotels
from utils.pricing import HotelPricingModel
from utils.session_state import SessionStateManager, TripSettings
from utils.styling import get_base_styles
from utils.travel_data import (
    directions_url,
    geocode_location,
    get_city_attractions,
    hotel_search_url,
)

st.set_page_config(
    page_title="DETOUR_MANIAX | Trip planner", layout="wide", page_icon="✈️"
)
st.markdown(get_base_styles(), unsafe_allow_html=True)
st.markdown(
    """
    <style>
    .planner-hero {text-align:center; padding:1.4rem 1rem .8rem;}
    .planner-hero h1 {font-family: 'Playfair Display', Georgia, serif; color:#0b172a; margin:0;}
    .planner-hero p {color:#4b5563; font-size:1.08rem; margin:.45rem 0 0;}
    .section-heading {font-family:'Playfair Display', Georgia, serif; color:#0b172a; margin:1.8rem 0 .35rem;}
    .hotel-note {color:#5b6470; font-size:.88rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def save_visitor_location(lat: float, lon: float, label: str) -> None:
    """Persist the visitor's location for destination and attraction routes."""
    location = {"lat": float(lat), "lon": float(lon), "label": label}
    st.session_state["visitor_location"] = location
    SessionStateManager.save_user_location(location["lat"], location["lon"])


def current_visitor_location() -> dict | None:
    """Return a valid session location, if the visitor has supplied one."""
    location = st.session_state.get("visitor_location")
    if not isinstance(location, dict) or "lat" not in location or "lon" not in location:
        return None
    return location


def render_location_picker() -> dict | None:
    """Offer browser GPS and two manual fallbacks in the same dashboard."""
    st.markdown(
        '<h2 class="section-heading">Your current location</h2>', unsafe_allow_html=True
    )
    st.caption(
        "Used only to create your route links. It is kept in this browser session, not stored by the app."
    )

    method = st.radio(
        "How would you like to set your location?",
        ("Use this device", "Search for a place", "Enter coordinates"),
        horizontal=True,
        index=1,
    )

    if method == "Use this device":
        if get_geolocation is None:
            st.warning(
                "Browser location needs the `streamlit-js-eval` dependency. Install the project requirements, then reload."
            )
        else:
            location_data = get_geolocation(component_key="trip-planner-geolocation")
            if location_data and "error" in location_data:
                error = location_data["error"]
                st.warning(
                    f"Location unavailable: {error.get('message', 'unknown browser error')}"
                )
            elif location_data and "coords" in location_data:
                coords = location_data["coords"]
                try:
                    save_visitor_location(
                        coords["latitude"],
                        coords["longitude"],
                        "Current device location",
                    )
                    st.success("Current device location is ready for directions.")
                except (KeyError, TypeError, ValueError):
                    st.warning(
                        "The browser returned an invalid location. Try again or use one of the manual options."
                    )
            else:
                st.info(
                    "Allow the browser location prompt to get directions from your current position."
                )

    elif method == "Search for a place":
        search_col, button_col = st.columns([4, 1])
        with search_col:
            location_name = st.text_input(
                "Starting location",
                placeholder="e.g. Mumbai, India",
                label_visibility="collapsed",
            )
        with button_col:
            locate = st.button("Set location", type="primary", width="stretch")
        if locate:
            location = geocode_location(location_name)
            if location:
                save_visitor_location(
                    location["lat"], location["lon"], str(location["label"])
                )
                st.success(f"Starting point set to {location['label']}.")
            else:
                st.error(
                    "That location could not be found. Try a more specific city or use coordinates."
                )

    else:
        lat_col, lon_col, set_col = st.columns([2, 2, 1])
        with lat_col:
            latitude = st.number_input(
                "Latitude", min_value=-90.0, max_value=90.0, value=None, format="%.6f"
            )
        with lon_col:
            longitude = st.number_input(
                "Longitude",
                min_value=-180.0,
                max_value=180.0,
                value=None,
                format="%.6f",
            )
        with set_col:
            st.write("")
            set_coordinates = st.button(
                "Set location",
                type="primary",
                width="stretch",
                disabled=latitude is None or longitude is None,
            )
        if set_coordinates:
            save_visitor_location(latitude, longitude, "Custom coordinates")
            st.success("Starting point set from your coordinates.")

    location = current_visitor_location()
    if location:
        status_col, clear_col = st.columns([4, 1])
        with status_col:
            st.success(
                f"Directions start at: {html.escape(str(location.get('label', 'your selected location')))}"
            )
        with clear_col:
            if st.button("Clear", width="stretch"):
                st.session_state.pop("visitor_location", None)
                st.session_state.pop(SessionStateManager.USER_LOCATION_KEY, None)
                st.rerun()
    return location


with st.sidebar:
    st.header("Build your trip")
    city = st.text_input(
        "Destination", key="planner_destination", placeholder="e.g. Goa, India"
    )
    travelers = st.number_input("Travellers", min_value=1, max_value=20, value=2)
    rooms = st.number_input("Rooms", min_value=1, max_value=10, value=1)
    check_in = st.date_input(
        "Check-in", value=date.today() + timedelta(days=30), min_value=date.today()
    )
    nights = st.slider("Nights", min_value=1, max_value=14, value=5)
    budget = st.slider(
        "Hotel budget per room / night (INR)", 1000, 50000, (5000, 15000), step=500
    )

    if st.button("Start a fresh plan", width="stretch"):
        st.cache_data.clear()
        st.session_state.clear()
        st.rerun()

if city.strip():
    settings = TripSettings(
        destination=city.strip(),
        travelers=int(travelers),
        rooms=int(rooms),
        check_in=check_in,
        duration_nights=int(nights),
        price_range=budget,
    )
    SessionStateManager.save_trip_settings(settings)
else:
    settings = None

st.markdown(
    """
    <section class="planner-hero">
      <h1>Plan the whole detour in one place</h1>
      <p>Set a destination, choose a hotel budget, discover public attractions, and open routes from your current location.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

if not settings:
    st.info("Enter a destination in the sidebar to build your complete trip plan.")
    st.stop()

with st.spinner(f"Finding {html.escape(settings.destination)}..."):
    destination = geocode_location(settings.destination)

if not destination:
    st.error(
        "The destination could not be found. Please enter a city or place name with a country, such as ‘Goa, India’."
    )
    st.stop()

st.markdown(f"## {html.escape(settings.destination)} trip plan")
st.caption(f"Destination found: {destination['label']}")

visitor_location = render_location_picker()
check_out = settings.check_in + timedelta(days=settings.duration_nights)

st.markdown(
    '<h2 class="section-heading">Directions to your destination</h2>',
    unsafe_allow_html=True,
)
direction_col, budget_col, trip_col = st.columns(3)
with direction_col:
    st.link_button(
        f"Get directions to {settings.destination}",
        directions_url(
            float(destination["lat"]), float(destination["lon"]), visitor_location
        ),
        width="stretch",
    )
with budget_col:
    st.metric(
        "Hotel budget", f"INR {settings.price_range[0]:,}–{settings.price_range[1]:,}"
    )
with trip_col:
    st.metric("Trip dates", f"{settings.check_in:%d %b} – {check_out:%d %b}")

st.markdown(
    '<h2 class="section-heading">Stays within your hotel budget</h2>',
    unsafe_allow_html=True,
)
st.caption(
    "Only stays whose full estimated nightly price band fits your selected budget are shown. Open live comparison before booking because availability and rates change."
)
with st.spinner("Checking live hotel listings..."):
    hotels = get_real_hotels(settings.destination, settings.price_range)

if hotels:
    for index, hotel in enumerate(hotels[:8]):
        price_range = HotelPricingModel.get_price_range(hotel["category"])
        details_col, action_col = st.columns([4, 1])
        with details_col:
            st.markdown(f"#### {html.escape(hotel['name'])}")
            st.write(
                f"{hotel['category'].value}-star category · {html.escape(hotel['area'])}"
            )
            st.caption(
                f"Estimated nightly band: INR {price_range.min_price:,}–{price_range.max_price:,}"
            )
        with action_col:
            st.write("")
            st.link_button(
                "Compare rate",
                hotel_search_url(
                    settings.destination,
                    str(settings.check_in),
                    str(check_out),
                    settings.travelers,
                    settings.rooms,
                ),
                width="stretch",
                key=f"hotel-rate-{index}",
            )
        st.divider()
else:
    st.warning(
        "Live hotel inventory is temporarily unavailable for this destination. Use the live comparison link below to see current stays."
    )

st.link_button(
    "Compare live hotels for these dates",
    hotel_search_url(
        settings.destination,
        str(settings.check_in),
        str(check_out),
        settings.travelers,
        settings.rooms,
    ),
    width="stretch",
)

st.markdown(
    '<h2 class="section-heading">Public attractions and routes</h2>',
    unsafe_allow_html=True,
)
with st.spinner("Finding public attractions..."):
    attractions = get_city_attractions(settings.destination)

if not attractions:
    st.info(
        "No public attractions were found nearby right now. Please try again shortly or use a more specific destination."
    )
else:
    map_data = pd.DataFrame(
        [
            {"latitude": place["lat"], "longitude": place["lon"], "name": place["name"]}
            for place in attractions
        ]
    )
    st.map(
        map_data, latitude="latitude", longitude="longitude", zoom=11, width="stretch"
    )

    for index, place in enumerate(attractions, start=1):
        text_col, image_col = st.columns([3, 2])
        with text_col:
            st.markdown(f"### {index}. {html.escape(place['name'])}")
            st.write(place["description"])
            st.caption(
                f"About {place['city_distance']:.1f} km from {settings.destination}"
            )
            st.link_button(
                "Get directions",
                directions_url(place["lat"], place["lon"], visitor_location),
                key=f"attraction-directions-{index}",
            )
            if place.get("source"):
                st.link_button(
                    "Read about it on Wikipedia",
                    place["source"],
                    key=f"attraction-source-{index}",
                )
        with image_col:
            if place.get("image"):
                st.image(place["image"], width="stretch")
        st.divider()
