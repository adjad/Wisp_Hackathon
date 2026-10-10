"""Offline unread and strict-query regressions over fictional Messages records."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from service.tools import imessage_tools as M
from service.tools.registry import REGISTRY


def stamp(day=12, hour=9):
    return datetime(2026, 10, day, hour).timestamp()


def row(text, *, state="U", chat=1, context="Trisha Jain", day=12, hour=9):
    return f"V2 | {stamp(day, hour)} | {state} | chat:{chat} | {context} | {text}"


@pytest.fixture(autouse=True)
def world(monkeypatch):
    from service.assistant import sync_status
    from service.memory import identity

    monkeypatch.setattr(sync_status, "ensure_sources", AsyncMock())
    monkeypatch.setattr(identity, "user_name", lambda: "Adi")
    monkeypatch.setattr(M, "_contacts", {})
    monkeypatch.setattr(M, "_sync_completed", True)
    monkeypatch.setattr(M, "_available", True)
    monkeypatch.setattr(M, "_unavailable_reason", "")
    monkeypatch.setattr(M, "_lines", "\n".join([
        row("Trisha Jain: Pickup is Tuesday at 6 PM."),
        row("Trisha Jain: Bring the blue folder.", state="R", hour=8),
        row("Jordan Ellis: Thanks!", chat=2, context="Jordan Ellis", hour=10),
        row("Dan Smith: Review Project Apollo by Thursday.", state="R", chat=3, context="Dan Smith"),
        row("Mom: Dinner is Sunday at 7 PM.", chat=4, context="Mom", day=11),
    ]))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unread read must not call a model or persist data")

    monkeypatch.setattr(M, "_c", forbidden)
    monkeypatch.setattr(M.cache_store, "save", forbidden)


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_unread_includes_routine_replies_and_excludes_read_work_requests(tool):
    before = M._lines
    result = run(tool(unread=True))
    assert "Pickup is Tuesday" in result and "Thanks!" in result
    assert "blue folder" not in result and "Project Apollo" not in result
    assert M._lines == before


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_unread_date_scope_is_applied_before_selection(tool):
    result = run(tool(unread=True, day="2026-10-11"))
    assert "Dinner is Sunday" in result
    assert "Pickup" not in result and "Thanks!" not in result


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_period_overrides_day_and_still_filters_unread(tool):
    result = run(tool(unread=True, day="2026-10-11", period="2026-10-12"))
    assert "Pickup" in result and "Dinner" not in result
    assert "Project Apollo" not in result


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_unread_named_conversation_is_exact_and_supports_typo(tool):
    result = run(tool(unread=True, conversation="trishe"))
    assert "Pickup" in result
    assert "Thanks!" not in result and "blue folder" not in result


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_named_conversation_with_only_read_messages_is_empty(tool):
    result = run(tool(unread=True, conversation="Dan Smith"))
    assert "No " in result and "unread" in result.lower()
    assert "Project Apollo" not in result and "Pickup" not in result


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_ambiguous_current_conversation_names_never_select_one(tool, monkeypatch):
    monkeypatch.setattr(M, "_lines", "\n".join([
        row("Alex: First private text.", chat=7, context="Alex"),
        row("Alex: Second private text.", chat=8, context="Alex"),
    ]))
    result = run(tool(unread=True, conversation="Alex"))
    assert "More than one conversation" in result
    assert "private text" not in result


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_current_conversation_miss_never_broadens(tool):
    result = run(tool(unread=True, conversation="Zebedee"))
    assert "No conversation matched" in result
    assert "Pickup" not in result and "Thanks!" not in result


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_unknown_read_state_is_not_zero_unread_or_a_private_excerpt(tool, monkeypatch):
    monkeypatch.setattr(M, "_lines", f"{stamp()} | Trisha Jain | Trisha Jain: Private legacy content.")
    result = run(tool(unread=True))
    assert "status is unavailable" in result
    assert "Private legacy content" not in result
    assert "No unread messages found" not in result


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_mixed_unknown_state_discloses_incomplete_read_coverage(tool, monkeypatch):
    monkeypatch.setattr(M, "_lines", M._lines + f"\n{stamp()} | Lee | Lee: Unknown private content.")
    result = run(tool(unread=True))
    assert "unknown read status" in result and "Pickup" in result
    assert "Unknown private content" not in result


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_unread_result_limit_is_disclosed_even_without_period(tool):
    result = run(tool(unread=True, count=1))
    assert "Thanks!" in result
    assert "not shown" in result.lower()


@pytest.mark.parametrize("tool", [M.summarize_messages, M.view_messages])
def test_current_launch_and_permission_boundaries_are_preserved(tool, monkeypatch):
    monkeypatch.setattr(M, "_sync_completed", False)
    assert "still syncing" in run(tool(unread=True))
    monkeypatch.setattr(M, "_sync_completed", True)
    monkeypatch.setattr(M, "_available", False)
    monkeypatch.setattr(M, "_unavailable_reason", "Synthetic permission denial")
    result = run(tool(unread=True))
    assert "Can't read Messages" in result and "Pickup" not in result


def test_strict_raw_query_miss_returns_no_unrelated_records():
    result = run(M.view_messages(query="nonexistent Ocean rescue"))
    assert "No messages matching" in result
    assert "Pickup" not in result and "Project Apollo" not in result


def test_strict_raw_query_and_unread_compose_without_broadening():
    result = run(M.view_messages(query="Project Apollo", unread=True))
    assert "No messages matching" in result and "Project Apollo by" not in result
    assert "Pickup" not in result


def test_named_identity_and_topic_miss_never_broaden():
    scoped = run(M.view_messages(query="nonexistent", conversation="Dan Smith"))
    assert "No messages matching" in scoped and "Project Apollo by" not in scoped


def test_original_positional_api_still_reads_unfiltered_messages():
    result = run(M.view_messages(None, "2026-10-12", 20, None))
    assert "Pickup" in result and "Project Apollo" in result


def test_unread_summary_keeps_sender_and_group_addressee(monkeypatch):
    monkeypatch.setattr(M, "_contacts", {"5555550123": "Trisha"})
    monkeypatch.setattr(M, "_lines", row(
        "Mom: @Trisha - Your conference starts Wednesday at 9 AM.",
        context='Group "Family"', chat=12))
    result = run(M.summarize_messages(unread=True, conversation="Family"))
    assert "Mom" in result and "Trisha" in result
    assert "NOT the user" in result


def test_unread_summary_uses_existing_code_redaction(monkeypatch):
    monkeypatch.setattr(M, "_lines", row("Bank: Your verification code is 123456.", context="Bank", chat=12))
    result = run(M.summarize_messages(unread=True))
    assert "123456" not in result


def test_partial_native_scan_does_not_claim_complete_unread_inventory(monkeypatch):
    coverage = {"version": 1, "kind": "coverage", "attempted": 4, "emitted": 0,
                "skipped": 4, "truncated": 0, "limit": 2000, "byte_limit": 4000000,
                "window_days": 365, "row_limit": 20000, "reached_row_limit": False}
    monkeypatch.setattr(M, "_lines", "V3 | " + json.dumps(coverage) + "\n" + M._lines)
    result = run(M.summarize_messages(unread=True))
    assert "scan coverage is partial" in result and "Pickup" in result


def test_unread_options_are_registered_for_model_selection():
    for name in ("summarize_messages", "view_messages"):
        properties = REGISTRY[name].parameters["properties"]
        assert properties["unread"]["type"] == "boolean"
        assert properties["conversation"]["type"] == "string"
