"""Synthetic immutable grocery evidence, no personal/native/model/network use."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import json
import threading
import time
from unittest.mock import AsyncMock, Mock

import pytest

from service.assistant.store import AssistantStore, parse_undated_snapshot
from service.tools import assistant_tools, grocery_lists as G, notes_tools as N
from service.tools.registry import REGISTRY, run_tool, is_tool_error

STAMP = 1_791_800_000.0


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(time, "time", lambda: STAMP)
    for name, value in {"_notes": "", "_notes_at": 0., "_snapshot_at": 0., "_snapshot_started_at": 0.,
            "_received_at": 0., "_receipt_started": 0., "_receipt_available": None, "_receipt_reason": "",
            "_available": None, "_reason": "", "_notes_origin": "none", "_notes_generation": 0}.items():
        monkeypatch.setattr(N, name, value)
    monkeypatch.setattr(N.cache_store, "save", Mock())
    store = AssistantStore(tmp_path / "synthetic.db")
    monkeypatch.setattr(assistant_tools, "assistant_store", store)
    def forbidden(*args, **kwargs):
        raise AssertionError("no native/network/model effects")
    import socket
    import subprocess
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    from service.assistant.hub import hub
    import importlib
    monkeypatch.setattr(hub, "publish", AsyncMock(side_effect=forbidden))
    monkeypatch.setattr(importlib.import_module("service.assistant.outbox"), "request", AsyncMock(side_effect=forbidden))
    yield store
    store._db.close()


def raw(title="Groceries", body="[ ] Milk 2 L\n[x] Eggs 12\nOat milk 1 carton", folder="Lists", stamp=STAMP):
    return N._FS.join((str(stamp), title, folder, body))


def dispatch(name, **args):
    assert REGISTRY[name].func in (G.grocery_note_evidence, G.grocery_reminder_evidence)
    return json.loads(asyncio.run(run_tool(REGISTRY[name], args)))


def seed(store, *, stamp=STAMP, undated=True, total=None):
    rows = [{"source_id": sid, "title": "Milk 2 L", "kind": "reminder", "when_ts": STAMP + 60,
             "context": label} for sid, label in (("one", "Costco"), ("two", "Costco"), ("three", "Home"))]
    rows.append({"source_id": "label-not-title", "title": "Costco bread", "kind": "reminder",
                 "when_ts": STAMP + 120, "context": "Home"})
    items = [{"source_id": "undated", "title": "Milk 1 carton", "context": "Costco"}]
    store.sync_source("reminders", rows, diagnostics={"snapshot_started_at": stamp},
        undated=parse_undated_snapshot(items, total or len(items)) if undated else None)


def test_store_snapshot_keeps_native_ids_and_separates_label_from_item_query(isolated):
    seed(isolated)
    result = isolated.raw_reminder_list_snapshot(list_label="Costco", query="milk")
    assert {row["source_id"] for row in result["records"]} == {"one", "two", "undated"}
    assert result["matching"] == result["shown"] == 3 and result["omitted"] == 0
    assert result["stable_list_id"] is None and result["account_id"] is None
    assert result["undated_view"]["freshness"] == "current"
    assert isolated.raw_reminder_list_snapshot(list_label="Unknown")["matching"] == 0


def test_registered_reminder_evidence_keeps_quantities_and_unknown_list_identity(isolated):
    seed(isolated)
    result = dispatch("grocery_reminder_evidence", list_label="Costco")
    assert result["source_state"] == "current_cached_read"
    assert len(result["records"]) == 3
    assert {row["native_id"] for row in result["records"]} == {"one", "two", "undated"}
    assert {row["text"] for row in result["records"]} == {"Milk 2 L", "Milk 1 carton"}
    assert all(row["list_id"] is None for row in result["records"])
    assert all(row["checked_state"] == "incomplete_native_snapshot" for row in result["records"])


@pytest.mark.parametrize("problem", ["stale", "future", "failed", "partial", "syncing"])
def test_unverified_reminders_withheld_without_claiming_completion(isolated, problem):
    seed(isolated)
    with isolated.transaction() as db:
        payload = json.loads(db.execute("SELECT payload FROM today_source_sync WHERE source='reminders'").fetchone()[0])
        if problem == "stale": payload["snapshot_started_at"] = STAMP - 1201
        if problem == "future": payload["snapshot_started_at"] = STAMP + 1
        if problem == "failed": payload["available"] = False
        if problem == "partial": payload["complete"] = False
        if problem == "syncing": payload["syncing"] = True
        db.execute("UPDATE today_source_sync SET payload=? WHERE source='reminders'", (json.dumps(payload),))
    result = dispatch("grocery_reminder_evidence")
    assert result["records"] == [] and result["withheld_unverified"] == 5
    assert result["source_state"].startswith("unknown")
    assert any("absence does not prove completion" in text for text in result["limitations"])


def test_dated_only_later_read_does_not_refresh_undated_items(isolated):
    seed(isolated)
    seed(isolated, stamp=STAMP + 1, undated=False)
    # Make the newer receipt a current read, while the undated view stays stale.
    import service.tools.everyday as E
    original = E._native_receipt_current
    # A native read must not be in the future; move the test clock too.
    from unittest.mock import patch
    with patch.object(time, "time", return_value=STAMP + 1):
        result = dispatch("grocery_reminder_evidence", list_label="Costco")
    assert original is E._native_receipt_current
    assert result["undated_state"]["freshness"] == "stale"
    assert {row["native_id"] for row in result["records"]} == {"one", "two"}
    assert result["withheld_unverified"] == 1


def test_notes_preserve_original_bytes_and_explicit_plaintext_states():
    body = "  - [ ] Milk 2 L  \n[x] Eggs 12\nOat milk 1 carton\n[ ] Soy milk 500 ml"
    N.cache_notes(raw(body=body), snapshot_started_at=STAMP - 1)
    snapshot = N.raw_notes_snapshot()
    assert snapshot.records[0]["body"] == body
    with pytest.raises(FrozenInstanceError): snapshot.origin = "changed"
    with pytest.raises(TypeError): snapshot.records[0]["body"] = "changed"
    result = dispatch("grocery_note_evidence")
    assert [row["text"] for row in result["records"]] == body.splitlines()
    assert [row["checked_state"] for row in result["records"]] == [
        "unchecked_plaintext", "checked_plaintext", "unknown", "unchecked_plaintext"]
    assert all(row["native_id"] is None for row in result["records"])
    assert all(row["reference"].startswith("notes-local:") for row in result["records"])


def test_notes_label_is_context_not_item_query_and_duplicate_titles_remain():
    N.cache_notes(N._RS.join((raw(title="Costco", body="[ ] Milk 2 L"),
        raw(title="Costco", body="[ ] Milk 1 carton"), raw(title="Home", body="[ ] Costco bread"))))
    result = dispatch("grocery_note_evidence", list_label="Costco", query="milk")
    assert result["counts"]["matching_notes"] == 2
    assert len({row["reference"] for row in result["records"]}) == 2
    assert [row["text"] for row in result["records"]] == ["[ ] Milk 2 L", "[ ] Milk 1 carton"]


@pytest.mark.parametrize("kind,expected", [("note", "[ ] title item"), ("folder", "[ ] folder item")])
def test_note_and_folder_selectors_do_not_cross_match(kind, expected):
    N.cache_notes(N._RS.join((raw(title="Costco", folder="Other", body="[ ] title item"),
                             raw(title="Other", folder="Costco", body="[ ] folder item"))))
    result = dispatch("grocery_note_evidence", list_label="Costco", label_kind=kind)
    assert [row["text"] for row in result["records"]] == [expected]


def test_unicode_metadata_no_match_stays_below_agent_result_limit():
    N.cache_notes(raw())
    N.cache_notes("", available=False, reason="\U0001f600" * 500)
    result = asyncio.run(G.grocery_note_evidence(list_label="\U0001f600" * 200, query="\U0001f600" * 200))
    assert len(result) <= 11_000
    assert result.startswith("(error:") or json.loads(result)["records"] == []


def test_unavailable_publication_does_not_refresh_held_body(monkeypatch):
    N.cache_notes(raw(), snapshot_started_at=STAMP - 10)
    old = N.raw_notes_snapshot()
    monkeypatch.setattr(time, "time", lambda: STAMP + 30)
    N.cache_notes("", available=False, reason="permission denied", snapshot_started_at=STAMP + 20)
    result = N.raw_notes_snapshot()
    assert result.records == old.records and result.body_received_at == old.body_received_at
    assert result.latest_receipt["available"] is False and result.latest_receipt["received_at"] == STAMP + 30
    assert result.generation > old.generation
    output = dispatch("grocery_note_evidence")
    assert output["held_body_is_latest_available_publish"] is False
    assert output["body_age_seconds"] == 40


def test_restored_and_expired_body_never_claimed_fresh(monkeypatch):
    N.cache_notes(raw())
    monkeypatch.setattr(N, "_notes_origin", "restored")
    assert not dispatch("grocery_note_evidence")["held_body_is_latest_available_publish"]
    monkeypatch.setattr(time, "time", lambda: STAMP + N._TTL_SECONDS + 1)
    result = N.raw_notes_snapshot()
    assert result.origin == "expired" and not result.records


def test_malformed_nonfinite_caps_and_output_omissions_are_counted():
    N.cache_notes(N._RS.join((raw(), "bad", raw(stamp="nan"), raw(stamp="inf"), raw(body="Z" * 5000))))
    result = N.raw_notes_snapshot(limit=1, byte_limit=500)
    assert result.raw_records == 5 and result.malformed == 3 and result.omitted == 1 and len(result.records) == 1
    N.cache_notes(raw(body="\n".join(f"[ ] Item {n} " + "z" * 300 for n in range(250))))
    output = asyncio.run(G.grocery_note_evidence())
    assert len(output) <= 11_000
    parsed = json.loads(output)
    assert parsed["counts"]["matching_lines"] == 250 and parsed["counts"]["output_omitted"] > 0


def test_snapshot_parses_captured_bytes_after_concurrent_publication(monkeypatch):
    N.cache_notes(raw(title="First", body="[ ] A"))
    entered, resume = threading.Event(), threading.Event()
    real_sha = N.hashlib.sha256
    def pause(data):
        if threading.current_thread().name.startswith("snapshot-test") and not entered.is_set():
            entered.set()
            assert resume.wait(5)
        return real_sha(data)
    monkeypatch.setattr(N.hashlib, "sha256", pause)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="snapshot-test") as pool:
        pending = pool.submit(N.raw_notes_snapshot)
        assert entered.wait(5)
        N.cache_notes(raw(title="Second", body="[ ] B"))
        resume.set()
        snapshot = pending.result(5)
    assert snapshot.records[0]["title"] == "First" and snapshot.records[0]["body"] == "[ ] A"
    assert snapshot.generation < N.raw_notes_snapshot().generation


@pytest.mark.parametrize("bad", [None, 1, True, "x" * 201])
@pytest.mark.parametrize("name", ["grocery_note_evidence", "grocery_reminder_evidence"])
def test_invalid_filters_fail_before_access(monkeypatch, bad, name):
    monkeypatch.setattr(N, "raw_notes_snapshot", Mock(side_effect=AssertionError("no read")))
    monkeypatch.setattr(assistant_tools.assistant_store, "raw_reminder_list_snapshot", Mock(side_effect=AssertionError("no read")))
    assert is_tool_error(asyncio.run(run_tool(REGISTRY[name], {"list_label": bad})))


@pytest.mark.parametrize("kind", [None, [], {}, True, "unknown"])
@pytest.mark.parametrize("name", ["grocery_note_evidence", "grocery_reminder_evidence"])
def test_invalid_selector_kind_direct_call_fails_before_access(monkeypatch, kind, name):
    monkeypatch.setattr(N, "raw_notes_snapshot", Mock(side_effect=AssertionError("no read")))
    monkeypatch.setattr(assistant_tools.assistant_store, "raw_reminder_list_snapshot", Mock(side_effect=AssertionError("no read")))
    assert is_tool_error(asyncio.run(getattr(G, name)(label_kind=kind)))
