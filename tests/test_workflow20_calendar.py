"""Actual calendar query/availability semantics over synthetic sources only."""
import asyncio
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from service.tools import assistant_tools as A, schedule_extras as S


ROWS = [{"id": str(n), "title": title} for n, title in enumerate([
    "Physics Midterm", "Physics Quiz", "Physics Final", "Chemistry Midterm",
    "Physics Test Prep", "Physics exam review", "Dentist appointment",
])]


@pytest.mark.parametrize("query,titles", [
    ("physics test", ["Physics Midterm", "Physics Final"]),
    ("physcis exam", ["Physics Midterm", "Physics Final"]),
    ("when is my physics midterm", ["Physics Midterm"]),
    ("physics quiz", ["Physics Quiz"]),
    ("physics assessment", ["Physics Midterm", "Physics Quiz", "Physics Final"]),
    ("chemistry test", ["Chemistry Midterm"]),
    ("biology exam", []), ("dentist", ["Dentist appointment"]),
    ("physics final", ["Physics Final"]),
    ("test", ["Physics Midterm", "Physics Final", "Chemistry Midterm"]),
    ("Physics Test Prep", ["Physics Test Prep"]),
])
def test_assessment_candidates_preserve_identity_and_ambiguity(query, titles):
    matched = A._match_schedule_query(ROWS, query)
    assert [row["title"] for row in matched] == titles
    assert all(row is ROWS[int(row["id"])] for row in matched)


class Clock(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 30, 10)


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(S, "dt", SimpleNamespace(datetime=Clock, date=dt.date, time=dt.time, timedelta=dt.timedelta))
    monkeypatch.setattr(S, "_availability_timezone", lambda: "America/Los_Angeles")
    monkeypatch.setattr("service.assistant.sync_status.ensure_sources", AsyncMock(return_value={
        "sources": [{"id": "calendar", "state": "ready"}, {"id": "reminders", "state": "ready"}],
        "reminders_fresh": True}))
    captured = []
    def snapshot(day, zone):
        captured.append(day)
        return {"commitments": [], "tasks": []}
    monkeypatch.setattr(S, "_store", SimpleNamespace(today_snapshot=snapshot))
    return captured


@pytest.mark.parametrize("period,first,last,count", [
    ("today", "2026-10-30", "2026-10-30", 1),
    ("tomorrow", "2026-10-31", "2026-10-31", 1),
    ("this week", "2026-10-30", "2026-11-01", 3),
    ("next week", "2026-11-02", "2026-11-08", 7),
    ("this month", "2026-10-30", "2026-10-31", 2),
    ("next month", "2026-11-01", "2026-11-30", 30),
])
def test_exact_range_uses_each_local_day_not_fixed_seconds(period, first, last, count, ready):
    result = asyncio.run(S.find_free_time(period=period, minutes=45))
    assert len(ready) == count and ready[0] == first and ready[-1] == last
    assert "candidate" in result and "has not been created" in result


def test_real_end_and_overnight_blocks_not_assumed_hour(ready, monkeypatch):
    def stamp(day, hour): return dt.datetime(2026, 10, day, hour).timestamp()
    rows = [{"when_ts": stamp(30, 23), "end_ts": stamp(31, 11), "status": "active"},
            {"when_ts": stamp(31, 12), "end_ts": stamp(31, 15), "status": "active"}]
    monkeypatch.setattr(S, "_store", SimpleNamespace(today_snapshot=lambda *a: {"commitments": rows, "tasks": []}))
    result = asyncio.run(S.find_free_time(period="tomorrow", minutes=60))
    assert "11:00 AM–12:00 PM" in result and "3:00 PM–4:00 PM" in result
    assert "9:00 AM" not in result and "1:00 PM" not in result


@pytest.mark.parametrize("state", ["unavailable", "syncing", "denied", "stale"])
def test_availability_fails_closed_for_unverified_sources(state, ready, monkeypatch):
    monkeypatch.setattr("service.assistant.sync_status.ensure_sources", AsyncMock(return_value={
        "sources": [{"id": "calendar", "state": state}, {"id": "reminders", "state": "ready"}], "reminders_fresh": True}))
    result = asyncio.run(S.find_free_time(period="next week"))
    assert "No study slot has been verified" in result and ready == []


@pytest.mark.parametrize("period", ["last week", "2026-10-29", "next year", "whenever"])
def test_unsupported_or_past_range_has_no_snapshot_reads(period, ready):
    assert "error" in asyncio.run(S.find_free_time(period=period))
    assert ready == []
