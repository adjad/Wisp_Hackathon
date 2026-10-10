"""Offline weather location checks; fake HTTP never reads a live provider."""
import asyncio
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

import pytest

from service.tools import web_tools
from service.tools.ca_locations import (
    CA_CITIES, normalize_weather_location, provider_area_matches,
)


def area(city="San Francisco", region="California", country="United States"):
    return {key: [{"value": value}] for key, value in (
        ("areaName", city), ("region", region), ("country", country),
    )}


def payload(city="San Francisco", region="California", country="United States"):
    return {
        "nearest_area": [area(city, region, country)],
        "current_condition": [{"temp_F": "99", "temp_C": "37",
            "weatherDesc": [{"value": "Sunny"}], "FeelsLikeF": "98",
            "humidity": "20", "windspeedMiles": "5"}],
        "weather": [
            {"date": "2026-10-12", "maxtempF": "80", "mintempF": "60",
             "hourly": [{"weatherDesc": [{"value": "Sunny"}], "chanceofrain": "0"}]},
            {"date": "2026-10-13", "maxtempF": "70", "mintempF": "50",
             "hourly": [{"weatherDesc": [{"value": "Cloudy"}], "chanceofrain": "20"}]},
        ],
    }


@pytest.fixture(autouse=True)
def deny_live_weather(monkeypatch):
    async def denied(*args, **kwargs):
        pytest.fail("weather test attempted an unmocked HTTP request")
    monkeypatch.setattr(web_tools, "_yahoo_get", denied)


def fake_weather(monkeypatch, data, *, status=200):
    calls = []
    async def get(url):
        calls.append(url)
        return SimpleNamespace(status_code=status, json=lambda: deepcopy(data))
    monkeypatch.setattr(web_tools, "_yahoo_get", get)
    return calls


@pytest.mark.parametrize("city", CA_CITIES)
def test_all_twenty_canonical_cities_normalize(city):
    for query in (f"{city},CA", f"{city.lower()}, California", f"{city} CA",
                  f"{city}, CA, USA"):
        result = normalize_weather_location(query)
        assert result.query == f"{city},CA"
        assert result.california_city == city


@pytest.mark.parametrize("query,city", [
    ("SF", "San Francisco"), ("S.F.", "San Francisco"),
    ("SF, CA", "San Francisco"), ("LA, CA", "Los Angeles"),
    ("SD, California", "San Diego"), ("SJ, CA", "San Jose"),
    ("Santa Clra, CA", "Santa Clara"), ("Santa Crz, California", "Santa Cruz"),
    ("San Fransisco, CA", "San Francisco"), ("San Jsoe, CA", "San Jose"),
    ("San José, California", "San Jose"), ("  San   Jose , CA  ", "San Jose"),
    ("SF, CA.", "San Francisco"), ("SF, C.A.", "San Francisco"),
    ("San Jose, Calif.", "San Jose"),
])
def test_finite_aliases_and_fixture_typos(query, city):
    result = normalize_weather_location(query)
    assert result.query == f"{city},CA" and result.california_city == city


@pytest.mark.parametrize("query", [
    "Santa, California", "Santa C, CA", "SC, CA", "San, CA", "CA", "California",
    "LA", "SD", "SJ", "Santa Clara", "San Francisco", "San Jsoe",
    "San Jose, CA, Canada", "San Francisco, California, Argentina", "Santa/Clara, CA",
    "San Francisco (CA)", "SF, CA!", "SF, C.A., Canada", "SF, Calif, Argentina",
    "CA,CA", "California,CA",
])
def test_ambiguous_or_conflicting_locations_refuse_before_http(query):
    result = asyncio.run(web_tools.get_weather(query))
    assert "ask" in result and "guess" in result


@pytest.mark.parametrize("query", ["", " ", "tomorrow", "next month"])
def test_missing_or_temporal_location_refuses_before_http(query):
    assert "ask the user" in asyncio.run(web_tools.get_weather(query))


@pytest.mark.parametrize("city", CA_CITIES)
def test_weather_requires_and_returns_the_requested_california_city(city, monkeypatch):
    calls = fake_weather(monkeypatch, payload(city))
    result = asyncio.run(web_tools.get_weather(f"{city}, California"))
    assert f"Weather for {city}, California, United States" in result
    assert "99°F" in result
    assert unquote(urlparse(calls[0]).path) == f"/{city},CA"
    assert len(calls) == 1


@pytest.mark.parametrize("query,city", [
    ("SF", "San Francisco"), ("Santa Clra,CA", "Santa Clara"),
    ("Santa Crz,California", "Santa Cruz"), ("San Fransisco,CA", "San Francisco"),
    ("San Jsoe,CA", "San Jose"), ("Dublin,CA", "Dublin"),
])
def test_normalized_queries_verify_the_canonical_city(query, city, monkeypatch):
    calls = fake_weather(monkeypatch, payload(city))
    result = asyncio.run(web_tools.get_weather(query))
    assert f"Weather for {city}, California, United States" in result
    assert unquote(urlparse(calls[0]).path) == f"/{city},CA"


@pytest.mark.parametrize("city", CA_CITIES)
@pytest.mark.parametrize("mismatch", ["city", "region", "country"])
def test_wrong_provider_city_state_or_country_never_returns_numbers(city, mismatch, monkeypatch):
    values = {"city": city, "region": "California", "country": "United States"}
    values[mismatch] = {"city": "Other City", "region": "Cordoba", "country": "Argentina"}[mismatch]
    fake_weather(monkeypatch, payload(**values))
    result = asyncio.run(web_tools.get_weather(f"{city},CA"))
    assert "could not verify" in result
    assert "99" not in result and "80" not in result and "°" not in result


@pytest.mark.parametrize("bad_area", [
    {}, {"areaName": [{"value": "San Francisco"}]},
    area(country=""), area(region=""), area(city=""),
    {"areaName": [{"value": 10}], **{k: v for k, v in area().items() if k != "areaName"}},
])
def test_missing_or_malformed_provider_identity_is_not_weather_evidence(bad_area, monkeypatch):
    data = payload()
    data["nearest_area"] = [bad_area]
    fake_weather(monkeypatch, data)
    result = asyncio.run(web_tools.get_weather("San Francisco,CA"))
    assert "could not verify" in result and "99" not in result


def test_multiple_provider_areas_are_ambiguous(monkeypatch):
    data = payload()
    data["nearest_area"].append(area())
    fake_weather(monkeypatch, data)
    assert "could not verify" in asyncio.run(web_tools.get_weather("SF"))


@pytest.mark.parametrize("country", ["United States", "United States of America", "US", "U.S.A."])
def test_supported_provider_identity_spellings(country):
    assert provider_area_matches(area("San José", "CA", country), "San Jose")


@pytest.mark.parametrize("query,city,country", [
    ("London", "London", "United Kingdom"),
    ("San Jose, Costa Rica", "San Jose", "Costa Rica"),
    ("Paris, France", "Paris", "France"),
    ("SFO", "San Francisco International Airport", "United States"),
    ("94568", "Dublin", "United States"),
])
def test_other_places_postcodes_and_airports_keep_the_existing_lookup(query, city, country, monkeypatch):
    calls = fake_weather(monkeypatch, payload(city, "Other Region", country))
    result = asyncio.run(web_tools.get_weather(query))
    assert f"Weather for {city}, Other Region, {country}" in result
    assert unquote(urlparse(calls[0]).path) == f"/{query}"


def test_tomorrow_uses_only_requested_forecast_and_requires_coverage(monkeypatch):
    from service.tools import timeranges
    real_resolve = timeranges.resolve_span
    monkeypatch.setattr(timeranges, "resolve_span", lambda p: real_resolve(p, now=datetime(2026, 10, 12, 9)))
    fake_weather(monkeypatch, payload())
    result = asyncio.run(web_tools.get_weather("SF", period="tomorrow"))
    assert "2026-10-13" in result and "2026-10-12" not in result and "now:" not in result
    assert "70°F" in result and "99°F" not in result
    assert "does not cover" in asyncio.run(web_tools.get_weather("SF", period="this week"))
    assert "unsupported weather range" in asyncio.run(web_tools.get_weather("SF", period="nonsense range"))


@pytest.mark.parametrize("data", [{}, {"current_condition": [], "nearest_area": []},
                                       {"current_condition": ["wrong"], "nearest_area": [area()]},
                                       {**payload(), "weather": "wrong"},
                                       {**payload(), "weather": ["wrong"]}])
def test_malformed_http_payload_fails_without_numbers(data, monkeypatch):
    fake_weather(monkeypatch, data)
    result = asyncio.run(web_tools.get_weather("SF"))
    assert "unexpected shape" in result and "99" not in result


def test_http_error_and_fetch_failure_remain_honest(monkeypatch):
    calls = fake_weather(monkeypatch, payload(), status=503)
    result = asyncio.run(web_tools.get_weather("SF"))
    assert "HTTP 503" in result and "99" not in result and len(calls) == 1
    async def failed(url):
        return "(timed out reaching Yahoo Finance)"
    monkeypatch.setattr(web_tools, "_yahoo_get", failed)
    assert "weather service" in asyncio.run(web_tools.get_weather("SF"))
