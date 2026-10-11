"""Behavior runtime: ingest -> mine -> nudge -> hub, auto actions + Undo,
Calendar snapshot mapping, remote fallback, profile card. Synthetic data only;
every store lives under tmp_path."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta

import pytest

from service.assistant import behavior_runtime as br
from service.behavior.types import Action, Feedback, Nudge, Observation, Pattern, Prediction, Window

NOW = datetime(2026, 10, 12, 9, 0).timestamp()          # Monday 9:00 local


def at(hour, minute=0, day=0):
    return (datetime(2026, 10, 12) + timedelta(days=day)).replace(hour=hour, minute=minute).timestamp()


# --------------------------------------------------------------------------
# Fakes that honour the engine contract
# --------------------------------------------------------------------------

class FakeEngine:
    def __init__(self, path=None, nudges=()):
        self.path = path
        self.obs: dict[str, Observation] = {}
        self.snapshots: dict[str, dict] = {}
        self.snapshot_calls = []
        self.mined = 0
        self.generated = 0
        self.feedbacks: list[Feedback] = []
        self._queued = list(nudges)
        self._nudges: list[Nudge] = []
        self._patterns = {
            "p_gym": Pattern(id="p_gym", kind="habit", subject="fitness",
                             statement="You go to the gym on weekday mornings (6:30-8:00)",
                             window=Window((0, 1, 2, 3, 4), 390, 480), support=14, opportunities=16,
                             confidence=0.72, evidence=("cal:g:1",)),
            "p_sam": Pattern(id="p_sam", kind="contact_rhythm", subject="Sam",
                             statement="You talk to Sam in the afternoons", support=9,
                             opportunities=12, confidence=0.55),
            "p_b2b": Pattern(id="p_b2b", kind="cancel_propensity", subject="back_to_back_last",
                             statement="You usually cancel the last of 3+ back-to-back meetings",
                             support=5, opportunities=7, confidence=0.41),
        }
        self.card = "- Gym weekday mornings 6:30-8:00\n- Talks to Sam in the afternoons"

    def observe(self, observations):
        n = 0
        for o in observations:
            if self.obs.get(o.id) != o:
                n += 1
            self.obs[o.id] = o
        return n

    def observe_snapshot(self, source, observations, *, window_start, window_end, taken_at):
        observations = list(observations)
        self.snapshot_calls.append((source, [o.id for o in observations], window_start, window_end, taken_at))
        prev = self.snapshots.get(source, {})
        now_ids = {o.id: o for o in observations}
        cancelled = 0
        for oid, o in prev.items():
            if oid not in now_ids and o.ts > taken_at:
                cancelled += 1
                self.obs["x:" + oid] = Observation(id="x:" + oid, kind="event_cancelled", ts=taken_at,
                                                   subject=o.subject, source=source, source_id=o.source_id)
        self.snapshots[source] = now_ids
        upserted = self.observe(observations)
        return {"upserted": upserted, "cancelled": cancelled, "moved": 0}

    def mine(self, now=None):
        self.mined += 1
        return list(self._patterns.values())

    def patterns(self, *, status=None, kind=None):
        return [p for p in self._patterns.values()
                if (status is None or p.status == status) and (kind is None or p.kind == kind)]

    def set_pattern_status(self, pattern_id, status):
        if pattern_id not in self._patterns:
            raise KeyError(pattern_id)
        from dataclasses import replace
        self._patterns[pattern_id] = replace(self._patterns[pattern_id], status=status)
        return self._patterns[pattern_id]

    def predict(self, now=None, horizon_s=86400.0):
        now = now or NOW
        return [Prediction(kind="activity", subject="gym", ts=at(6, 30, 1), end_ts=at(8, 0, 1),
                           probability=0.82, because="14 of the last 16 weekday mornings", pattern_id="p_gym"),
                Prediction(kind="cancel_risk", subject="Team sync", ts=at(16, 0, 1), probability=0.6,
                           because="last of 3 back-to-back meetings", pattern_id="p_b2b")]

    def generate_nudges(self, now=None):
        self.generated += 1
        out = []
        for n in self._queued:
            if any(x.id == n.id for x in self._nudges):
                continue
            from dataclasses import replace
            n = replace(n, seq=len(self._nudges) + 1)
            self._nudges.append(n)
            out.append(n)
        self._queued = []
        return out

    def nudges_since(self, cursor=0, limit=50):
        rows = [n for n in self._nudges if n.seq > cursor][:limit]
        return rows, (rows[-1].seq if rows else cursor)

    def feedback(self, fb):
        self.feedbacks.append(fb)

    def profile_card(self, now=None, max_bytes=700):
        return self.card

    def describe(self, subject=None, now=None):
        pats = [p.to_dict() for p in self._patterns.values()]
        if subject:
            pats = [p for p in pats if subject.casefold() in (p["subject"] + p["statement"]).casefold()]
        return {"patterns": pats, "predictions": [p.to_dict() for p in self.predict(now)],
                "summary": "Early riser who protects gym time."}

    def status(self):
        kinds = {}
        for o in self.obs.values():
            kinds[o.kind] = kinds.get(o.kind, 0) + 1
        return {"observations": kinds, "patterns": len(self._patterns), "nudge_cursor": len(self._nudges)}


class FakeHub:
    def __init__(self):
        self.events = []

    async def publish(self, event, *, dedupe_key=None, target=None, durable=True, expires_at=None):
        self.events.append({"event": event, "dedupe_key": dedupe_key, "durable": durable,
                            "expires_at": expires_at})
        return {**event, "event_id": f"ev{len(self.events)}"}


class FakePersona:
    def __init__(self, now):
        self.observations = [Observation(id=f"demo:gym:{d}", kind="event", ts=at(6, 30, -d),
                                         end_ts=at(8, 0, -d), subject="Gym", source="demo",
                                         category="fitness") for d in range(1, 15)]
        self.upcoming = [Observation(id="demo:sync:1", kind="event", ts=at(16, 0, 1), subject="Team sync",
                                     source="demo", category="meeting")]


def gym_conflict_nudge(nid="n1", expires=None):
    return Nudge(
        id=nid, kind="habit_conflict", title="Gym vs. 7:00 meeting",
        body="Your 7:00 call lands on gym time.", because="14 of the last 16 weekday mornings",
        created_at=NOW, expires_at=expires if expires is not None else at(7, 0, 1), priority=0.8,
        pattern_ids=("p_gym",),
        actions=(Action("add_reminder", {"title": "Pack gym bag", "when_ts": at(21, 0), "notes": "gym tomorrow"},
                        auto=True, label="Remind me tonight"),
                 Action("add_hold", {"title": "Gym", "when_ts": at(17, 30, 1), "end_ts": at(18, 30, 1)},
                        auto=True, label="Hold an evening slot"),
                 Action("open_prompt", {"prompt": "Draft a note asking to move my 7:00 call to 9:00"},
                        auto=False, label="Draft reschedule note")))


@pytest.fixture
def store(tmp_path):
    from service.assistant.store import AssistantStore
    return AssistantStore(tmp_path / "assistant.db")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key in ("WISP_BEHAVIOR", "WISP_FOUNDER_DEMO", "WISP_BEHAVIOR_SYNTHETIC_ONLY", "WISP_BRAIN_URL",
                "WISP_BRAIN_MODE", "WISP_BRAIN_TOKEN", "WISP_QA_SEED"):
        monkeypatch.delenv(key, raising=False)
    br.set_runtime(None)
    yield
    br.set_runtime(None)


def make_runtime(tmp_path, engine=None, *, synthetic=True, founder=False, calendar=None,
                 messages=None, mode="local", remote=None, clock=lambda: NOW, persona=FakePersona):
    engine = engine or FakeEngine()
    calls = {"persona": 0, "messages": 0}

    def persona_fn(now):
        calls["persona"] += 1
        return persona(now)

    def messages_fn():
        calls["messages"] += 1
        return messages or {"state": "unavailable", "records": []}

    rt = br.BehaviorRuntime(
        tmp_path / "home", mode=mode, synthetic=synthetic, founder=founder,
        local_factory=lambda path: engine, remote_factory=lambda home: remote,
        persona_fn=persona_fn, messages_fn=messages_fn,
        calendar_sync_fn=lambda: calendar if calendar is not None else {"available": False},
        session_db_fn=lambda: (_ for _ in ()).throw(RuntimeError("no sessions in tests")),
        clock=clock)
    rt.calls = calls
    return rt, engine


def tick(rt, store, hub, now=NOW, force=False):
    return asyncio.run(rt.tick(store, hub, now=now, force=force))


# --------------------------------------------------------------------------
# Flags
# --------------------------------------------------------------------------

def test_off_by_default(monkeypatch, store):
    assert not br.enabled() and br.get_runtime() is None
    assert asyncio.run(br.tick(store, FakeHub())) == []
    br.record_decision("send_message", True)          # no-op, no error
    assert br.profile_card() == ""


def test_founder_demo_turns_it_on_and_synthetic(monkeypatch):
    monkeypatch.setenv("WISP_FOUNDER_DEMO", "1")
    assert br.enabled() and br.synthetic_only() and br.founder_demo()
    monkeypatch.delenv("WISP_FOUNDER_DEMO")
    monkeypatch.setenv("WISP_BEHAVIOR", "1")
    assert br.enabled() and not br.synthetic_only()
    monkeypatch.setenv("WISP_BEHAVIOR_SYNTHETIC_ONLY", "1")
    assert br.synthetic_only()


def test_brain_mode_selection(monkeypatch):
    assert br.brain_mode() == "local"
    monkeypatch.setenv("WISP_BRAIN_URL", "https://brain.example.test")
    assert br.brain_mode() == "remote"
    monkeypatch.setenv("WISP_BRAIN_MODE", "local")
    assert br.brain_mode() == "local"


# --------------------------------------------------------------------------
# Synthetic ingest -> mine -> nudge -> hub
# --------------------------------------------------------------------------

def test_synthetic_persona_ingested_once_per_day_and_never_real_messages(tmp_path, store):
    rt, eng = make_runtime(tmp_path)
    hub = FakeHub()
    tick(rt, store, hub)
    assert rt.calls["persona"] == 1 and rt.calls["messages"] == 0
    assert "demo:gym:1" in eng.obs and "demo:sync:1" in eng.obs
    assert eng.mined == 1
    tick(rt, store, hub, now=NOW + 400, force=True)      # same day: idempotent, no re-generation
    assert rt.calls["persona"] == 1
    tick(rt, store, hub, now=NOW + 86400, force=True)    # next day: refreshed
    assert rt.calls["persona"] == 2


def test_nudge_published_with_app_event_shape_and_auto_actions(tmp_path, store):
    rt, eng = make_runtime(tmp_path, FakeEngine(nudges=[gym_conflict_nudge()]))
    hub = FakeHub()
    [row] = tick(rt, store, hub)
    nudge_events = [e for e in hub.events if e["event"]["type"] == "nudge"]
    assert len(nudge_events) == 1
    sent = nudge_events[0]
    ev = sent["event"]
    assert sent["dedupe_key"] == "behavior:n1" and sent["expires_at"] == at(7, 0, 1)
    for key in ("type", "nudge_id", "title", "body", "because"):
        assert ev[key]
    assert ev["nudge_id"] == "n1" and ev["kind"] == "habit_conflict"
    assert [a["type"] for a in ev["actions"]] == ["add_reminder", "add_hold", "open_prompt"]
    assert ev["can_undo"] is True
    assert [a["type"] for a in ev["auto_performed"]] == ["add_reminder", "add_hold"]
    assert row["event_id"] == "ev1"
    # The reversible actions landed on Wisp's own schedule; open_prompt did not run.
    rows = {r["title"]: r for r in (dict(x) for x in store._db.execute("SELECT * FROM commitments"))}
    assert set(rows) == {"Pack gym bag", "Tentative: Gym"}
    assert rows["Pack gym bag"]["kind"] == "reminder" and rows["Pack gym bag"]["when_ts"] == at(21, 0)
    assert rows["Pack gym bag"]["context"].startswith(br.BEHAVIOR_CONTEXT)
    assert rows["Tentative: Gym"]["kind"] == "event" and rows["Tentative: Gym"]["source"] == "manual"
    end = store._db.execute("SELECT end_ts FROM calendar_event_ends WHERE commitment_id=?",
                            (rows["Tentative: Gym"]["id"],)).fetchone()[0]
    assert end == at(18, 30, 1)
    # A changed ping lets the app refresh its schedule views.
    assert any(e["event"] == {"type": "changed"} and e["durable"] is False for e in hub.events)


def test_second_tick_does_not_republish_or_duplicate(tmp_path, store):
    rt, eng = make_runtime(tmp_path, FakeEngine(nudges=[gym_conflict_nudge()]))
    hub = FakeHub()
    tick(rt, store, hub)
    assert tick(rt, store, hub, now=NOW + 120, force=True) == []
    assert store._db.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 2
    assert rt.status()["cursor"]["local"] == 1


def test_rate_limits_between_ticks(tmp_path, store):
    rt, eng = make_runtime(tmp_path)
    hub = FakeHub()
    tick(rt, store, hub)
    tick(rt, store, hub, now=NOW + 30)
    assert eng.mined == 1 and eng.generated == 1              # nothing new, too soon
    tick(rt, store, hub, now=NOW + br.NUDGE_EVERY_S + 1)
    assert eng.generated == 2 and eng.mined == 1
    tick(rt, store, hub, now=NOW + br.MINE_EVERY_S + 1)
    assert eng.mined == 2


def test_expired_nudge_is_skipped_but_cursor_advances(tmp_path, store):
    rt, eng = make_runtime(tmp_path, FakeEngine(nudges=[gym_conflict_nudge(expires=NOW - 1)]))
    hub = FakeHub()
    assert tick(rt, store, hub) == []
    assert hub.events == [] and rt.status()["cursor"]["local"] == 1
    assert store._db.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 0


def test_undo_removes_auto_actions_and_records_feedback(tmp_path, store):
    rt, eng = make_runtime(tmp_path, FakeEngine(nudges=[gym_conflict_nudge()]))
    tick(rt, store, FakeHub())
    removed = rt.undo(store, "n1")
    assert sorted(r["title"] for r in removed) == ["Pack gym bag", "Tentative: Gym"]
    assert store._db.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 0
    assert store._db.execute("SELECT COUNT(*) FROM calendar_event_ends").fetchone()[0] == 0
    assert [f.verdict for f in eng.feedbacks] == ["undo"] and eng.feedbacks[0].nudge_id == "n1"
    assert rt.undo(store, "n1") == []                        # idempotent
    # An undone action is never silently recreated by a retry.
    assert rt.perform_action(store, "n1", 0, gym_conflict_nudge().actions[0], NOW) is None


def test_auto_action_skips_existing_item_and_past_times(tmp_path, store):
    rt, _ = make_runtime(tmp_path)
    store.add_manual("Pack gym bag", at(21, 0))
    nudge = gym_conflict_nudge()
    assert rt.perform_action(store, "n1", 0, nudge.actions[0], NOW) is None      # already on file
    past = Action("add_reminder", {"title": "Too late", "when_ts": NOW - 3600}, auto=True)
    assert rt.perform_action(store, "n1", 5, past, NOW) is None
    assert rt.perform_action(store, "n1", 2, nudge.actions[2], NOW) is None      # open_prompt never


def test_real_hub_persists_nudge_and_expiry_retires_it(tmp_path, store):
    from service.assistant.hub import Hub
    hub = Hub(store)
    rt, eng = make_runtime(tmp_path, FakeEngine(nudges=[gym_conflict_nudge(expires=NOW + 600)]))
    [row] = tick(rt, store, hub)
    ev = store.event_by_key("behavior:n1")
    assert ev["kind"] == "nudge" and ev["state"] == "pending" and ev["expires_at"] == NOW + 600
    assert row["event_id"] == ev["id"]
    # Reminder invalidation never touches nudge events.
    assert [e["id"] for e in store.pending_events() if e["kind"] == "nudge"] == [ev["id"]]
    # The app's generic acknowledgement works for kind=nudge.
    assert store.acknowledge_event(ev["id"], "nudge") is True
    # Expiry: a second nudge past its expiry is retired so the hub stops replaying it.
    rt2, _ = make_runtime(tmp_path / "b", FakeEngine(nudges=[gym_conflict_nudge("n2", expires=NOW + 60)]))
    tick(rt2, store, hub)
    assert store.event_by_key("behavior:n2")["state"] == "pending"
    rt2.expire_events(store, NOW + 61)
    assert store.event_by_key("behavior:n2")["state"] == "superseded"


def test_feedback_retires_pending_event(tmp_path, store):
    from service.assistant.hub import Hub
    rt, eng = make_runtime(tmp_path, FakeEngine(nudges=[gym_conflict_nudge(expires=NOW + 3600)]))
    tick(rt, store, Hub(store))
    rt.feedback(store, "n1", "not_now")
    assert store.event_by_key("behavior:n1")["state"] == "ack"
    assert eng.feedbacks[-1].verdict == "not_now"


# --------------------------------------------------------------------------
# Calendar snapshot mapping (cancellations are detected by the engine diff)
# --------------------------------------------------------------------------

def _cal(title, when, *, sid, calendar="Wisp Demo", end=None, all_day=False):
    return {"source_id": sid, "kind": "meeting", "title": title, "context": calendar, "when_ts": when,
            "end_ts": end, "all_day": all_day, "confidence": 1.0}


def test_calendar_snapshot_maps_ids_and_detects_cancellation(tmp_path, store):
    items = [_cal("Gym", at(6, 30, -1), sid="g", end=at(8, 0, -1)),
             _cal("Team sync", at(16, 0, 1), sid="t", end=at(16, 30, 1)),
             _cal("Board prep", at(17, 0, 1), sid="b"),
             _cal("Holiday", at(0, 0, 2), sid="h", all_day=True),
             _cal("Real dentist", at(11, 0, 1), sid="r", calendar="Home")]
    store.sync_source("calendar", items)
    sync = {"available": True, "last_sync": NOW - 5}
    rt, eng = make_runtime(tmp_path, calendar=sync)
    tick(rt, store, FakeHub())
    source, ids, start, end, taken = eng.snapshot_calls[-1]
    assert source == "calendar" and taken == NOW - 5
    # Wisp Demo only, upcoming only (persona supplies history), no all-day.
    assert sorted(ids) == sorted([f"cal:t:{int(at(16, 0, 1))}", f"cal:b:{int(at(17, 0, 1))}"])
    sync_ = eng.obs[f"cal:t:{int(at(16, 0, 1))}"]
    assert sync_.kind == "event" and sync_.end_ts == at(16, 30, 1) and sync_.source_id == "t"
    assert sync_.attrs["calendar"] == "Wisp Demo"
    # With a seeded demo calendar the persona contributes history only.
    assert "demo:gym:1" in eng.obs and "demo:sync:1" not in eng.obs
    mined = eng.mined
    # The presenter deletes "Board prep"; the app re-syncs the calendar.
    store.sync_source("calendar", [i for i in items if i["source_id"] != "b"])
    sync["last_sync"] = NOW + 10
    tick(rt, store, FakeHub(), now=NOW + 20)              # a fresh sync is ingested immediately
    assert f"x:cal:b:{int(at(17, 0, 1))}" in eng.obs      # engine diff saw the cancellation
    assert eng.mined == mined + 1                         # changed -> re-mined right away


def test_seeding_demo_calendar_later_drops_persona_upcoming(tmp_path, store):
    class StoreEngine(FakeEngine):
        class _Store:
            def __init__(self, outer):
                self.outer = outer

            def delete_observations(self, ids):
                return sum(1 for i in ids if self.outer.obs.pop(i, None) is not None)

        def __init__(self):
            super().__init__()
            self._store = self._Store(self)
    sync = {"available": True, "last_sync": NOW}
    rt, eng = make_runtime(tmp_path, StoreEngine(), calendar=sync)
    tick(rt, store, FakeHub())
    assert "demo:sync:1" in eng.obs                        # no demo calendar yet: persona upcoming
    store.sync_source("calendar", [_cal("Team sync", at(16, 0, 1), sid="t")])
    sync["last_sync"] = NOW + 10
    tick(rt, store, FakeHub(), now=NOW + 20)
    assert "demo:sync:1" not in eng.obs and f"cal:t:{int(at(16, 0, 1))}" in eng.obs
    assert "demo:gym:1" in eng.obs                         # history stays


def test_wisp_marked_done_calendar_row_is_not_a_cancellation(tmp_path, store):
    items = [_cal("Team sync", at(16, 0, 1), sid="t"), _cal("Board prep", at(17, 0, 1), sid="b")]
    items[1]["organizer"] = "Nora Keene"
    store.sync_source("calendar", items)
    sync = {"available": True, "last_sync": NOW - 5}
    rt, eng = make_runtime(tmp_path, calendar=sync)
    tick(rt, store, FakeHub())
    team, board = eng.obs[f"cal:t:{int(at(16, 0, 1))}"], eng.obs[f"cal:b:{int(at(17, 0, 1))}"]
    assert team.attrs["organizer_is_user"] is True and team.attrs["organizer"] == ""
    assert board.attrs["organizer_is_user"] is False and board.attrs["organizer"] == "Nora Keene"
    # The user marks "Board prep" done inside Wisp; Apple Calendar still has it.
    cid = store._db.execute("SELECT id FROM commitments WHERE source_id='b'").fetchone()[0]
    store.set_status(cid, "done")
    sync["last_sync"] = NOW + 10
    tick(rt, store, FakeHub(), now=NOW + 20)
    assert not any(k.startswith("x:") for k in eng.obs)
    assert f"cal:b:{int(at(17, 0, 1))}" in eng.snapshot_calls[-1][1]


def test_calendar_not_read_until_a_completed_sync(tmp_path, store):
    store.sync_source("calendar", [_cal("Gym", at(6, 30, 1), sid="g")])
    rt, eng = make_runtime(tmp_path, calendar={"available": False, "syncing": True})
    tick(rt, store, FakeHub())
    assert eng.snapshot_calls == []


def test_synthetic_without_demo_calendar_uses_persona_only(tmp_path, store):
    store.sync_source("calendar", [_cal("Real thing", at(10, 0, 1), sid="r", calendar="Work")])
    rt, eng = make_runtime(tmp_path, calendar={"available": True, "last_sync": NOW})
    tick(rt, store, FakeHub())
    assert eng.snapshot_calls == [] and "demo:gym:1" in eng.obs
    assert not any(k.startswith("cal:") for k in eng.obs)


def test_real_mode_reads_all_calendars_messages_metadata_and_reminders(tmp_path, store):
    store.sync_source("calendar", [_cal("Standup", at(10, 0, 1), sid="s", calendar="Work")])
    store.add_manual("Call mom", at(18, 0))
    messages = {"state": "ready", "records": [
        {"identity": "m1", "timestamp": NOW - 600, "direction": "incoming", "sender": "Sam",
         "conversation": "Sam", "text": "secret text never ingested"},
        {"identity": "m2", "timestamp": NOW - 300, "direction": "outgoing", "sender": "Me",
         "conversation": "Priya", "text": "also secret"}]}
    rt, eng = make_runtime(tmp_path, synthetic=False, calendar={"available": True, "last_sync": NOW},
                           messages=messages)
    store.sync_source("calendar", [_cal("Standup", at(10, 0, 1), sid="s", calendar="Work"),
                                   _cal("Old 1:1", at(15, 0, -7), sid="o", calendar="Work",
                                        end=at(15, 30, -7))])
    tick(rt, store, FakeHub())
    assert rt.calls["persona"] == 0
    assert any(k.startswith("cal:s:") for k in eng.obs)
    assert eng.obs[f"cal:o:{int(at(15, 0, -7))}"].end_ts == at(15, 30, -7)     # real mode keeps history
    assert eng.obs["msg:m1"].kind == "message_in" and eng.obs["msg:m1"].subject == "Sam"
    assert eng.obs["msg:m2"].kind == "message_out" and eng.obs["msg:m2"].subject == "Priya"
    assert "secret" not in json.dumps([o.to_dict() for o in eng.obs.values()])
    assert any(o.kind == "reminder" and o.subject == "Call mom" for o in eng.obs.values())
    assert "asks" in rt.errors                             # a failing source never stops the others


def test_founder_never_reads_reminders_or_messages(tmp_path, store):
    store.add_manual("Native-ish reminder", at(18, 0))
    rt, eng = make_runtime(tmp_path, synthetic=True, founder=True,
                           messages={"state": "ready", "records": []})
    tick(rt, store, FakeHub())
    assert rt.calls["messages"] == 0
    assert not any(o.kind.startswith("reminder") for o in eng.obs.values())


def test_behavior_created_reminders_are_not_ingested_back(tmp_path, store):
    rt, eng = make_runtime(tmp_path, FakeEngine(nudges=[gym_conflict_nudge()]), synthetic=False)
    tick(rt, store, FakeHub())
    tick(rt, store, FakeHub(), now=NOW + br.INGEST_EVERY_S + 1)
    assert not any(o.subject == "Pack gym bag" for o in eng.obs.values())


def test_approval_and_denial_are_recorded(tmp_path, store):
    rt, eng = make_runtime(tmp_path)
    rt.record_decision("send_message", True)
    rt.record_decision("add_calendar_event", False)
    tick(rt, store, FakeHub())
    kinds = sorted((o.kind, o.subject) for o in eng.obs.values() if o.source == "wisp")
    assert kinds == [("approval", "send_message"), ("denial", "add_calendar_event")]


def test_agent_loop_hook_is_safe(monkeypatch, tmp_path):
    from service.agent.loop import _note_decision
    assert _note_decision("send_message", True) is True       # disabled: pass-through
    monkeypatch.setenv("WISP_BEHAVIOR", "1")
    rt, eng = make_runtime(tmp_path)
    br.set_runtime(rt)
    assert _note_decision("send_email", False) is False
    assert [o.kind for o in rt._pending] == ["denial"]


# --------------------------------------------------------------------------
# Remote brain falls back to the local engine
# --------------------------------------------------------------------------

class DownBrain:
    def __getattr__(self, name):
        def fail(*a, **k):
            from service.behavior.client import BrainUnavailable
            raise BrainUnavailable("synthetic outage")
        return fail


def test_remote_unavailable_falls_back_to_local(tmp_path, store):
    rt, local = make_runtime(tmp_path, FakeEngine(nudges=[gym_conflict_nudge()]), mode="remote",
                             remote=DownBrain())
    published = tick(rt, store, FakeHub())
    assert len(published) == 1                       # the demo keeps going on the local engine
    assert rt.active == "local" and "remote" in rt.errors
    assert local.obs and local.mined == 1
    assert rt.status()["active_engine"] == "local"


def test_remote_semantic_errors_propagate(tmp_path):
    class Brain(FakeEngine):
        def set_pattern_status(self, pattern_id, status):
            raise KeyError(pattern_id)
    remote = Brain()
    rt, local = make_runtime(tmp_path, mode="remote", remote=remote)
    with pytest.raises(KeyError):
        rt.call("set_pattern_status", "nope", "rejected")
    assert rt.call("patterns") and rt.active == "remote"


def test_remote_used_when_healthy(tmp_path, store):
    remote = FakeEngine(nudges=[gym_conflict_nudge()])
    rt, local = make_runtime(tmp_path, mode="remote", remote=remote)
    tick(rt, store, FakeHub())
    assert remote.obs and not local.obs and rt.status()["cursor"]["remote"] == 1


# --------------------------------------------------------------------------
# Profile card + prompt assembly
# --------------------------------------------------------------------------

def test_profile_card_cached_and_bounded(tmp_path):
    eng = FakeEngine()
    eng.card = "\n".join(f"- pattern line number {i} " + "x" * 40 for i in range(40))
    rt, _ = make_runtime(tmp_path, eng)
    card = rt.refresh_card()
    assert len(card.encode()) <= 700 and card.startswith("- pattern line number 0")
    eng.card = "changed"
    assert rt.profile_card() == card                    # cached for 60s


def test_profile_block_in_memory_and_remote_only_assembly(monkeypatch, tmp_path):
    from service.memory import prompt_blocks
    monkeypatch.setattr("service.memory.facts.memory_context_block", lambda query="": "\nFACT", raising=False)
    assert prompt_blocks.profile_block() == ""
    assert prompt_blocks.remote_only_context_block() == ""
    monkeypatch.setenv("WISP_FOUNDER_DEMO", "1")
    rt, eng = make_runtime(tmp_path)
    rt.refresh_card()
    br.set_runtime(rt)
    block = prompt_blocks.remote_only_context_block()
    assert block.startswith(prompt_blocks.PROFILE_HEADER) and "Gym weekday mornings" in block
    assert "FACT" not in block                          # only the card in remote-only mode
    assert prompt_blocks.memory_block("x").endswith(block)
    # The card fits the remote-only gateway budget alongside a system prompt.
    from service.inference.remote_policy import RemoteOnlyProfile
    RemoteOnlyProfile().validate_payload({
        "model": "qwen3.6:35b", "stream": True, "max_tokens": 512,
        "messages": [{"role": "system", "content": "You are Wisp." + block},
                     {"role": "user", "content": "plan my morning"}]})


def test_main_wires_profile_into_remote_only_paths():
    """Source contract: remote-only plain chat and agent turns get only the card."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "service/main.py").read_text()
    assert src.count("remote_only_context_block()") == 2
    tree = ast.parse(src)
    agent = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "agent")
    text = ast.unparse(agent)
    assert "style_hint += remote_only_context_block()" in text
    assert "include_memory_context=remote_only_profile() is None and" in text
    assert "behavior_router" in src and "behavior_runtime.run_loop(assistant_store, assistant_hub)" in src


# --------------------------------------------------------------------------
# Cleanup
# --------------------------------------------------------------------------

def test_clear_demo_state(tmp_path, store):
    from service.assistant.hub import Hub
    rt, eng = make_runtime(tmp_path, FakeEngine(nudges=[gym_conflict_nudge()]))
    tick(rt, store, Hub(store))
    mine = store.add_manual("My own reminder", at(19, 0))
    (rt.home / br.ENGINE_DB).write_text("engine")
    br.set_runtime(rt)
    out = br.clear_demo_state(store, rt.home)
    assert out["commitments"] == 2 and out["events"] == 1
    assert set(out["files"]) >= {br.ENGINE_DB, br.RUNTIME_DB}
    left = [r[0] for r in store._db.execute("SELECT id FROM commitments")]
    assert left == [mine["id"]]
    assert store.event_by_key("behavior:n1") is None


def test_qa_seed_source_used_in_rehearsal(monkeypatch, tmp_path, store):
    monkeypatch.setenv("WISP_QA_SEED", "1")
    rt, _ = make_runtime(tmp_path, FakeEngine(nudges=[gym_conflict_nudge()]))
    tick(rt, store, FakeHub())
    assert {r[0] for r in store._db.execute("SELECT source FROM commitments")} == {"wisp_seed"}


# --------------------------------------------------------------------------
# Phraser adapter
# --------------------------------------------------------------------------

class FakeClient:
    def __init__(self, content, *, managed=True, loaded=("fast-model",)):
        self.content, self.managed, self.loaded, self.calls = content, managed, loaded, []

    async def loaded_models(self):
        return list(self.loaded)

    async def chat(self, model, messages, **kw):
        self.calls.append((model, messages, kw))
        return {"choices": [{"message": {"content": self.content}, "finish_reason": "stop"}]}

    async def aclose(self):
        pass


def _target(monkeypatch, model="fast-model"):
    from types import SimpleNamespace
    target = SimpleNamespace(model=model)
    monkeypatch.setattr("service.config.endpoints.role_target", lambda role: target)
    return target


def test_phraser_rewrites_and_rejects_new_facts(monkeypatch):
    from service.assistant.behavior_phraser import WispPhraser
    from service import idle
    _target(monkeypatch)
    monkeypatch.setattr("service.inference.remote_policy.remote_only_profile", lambda: None)
    monkeypatch.setattr("service.config.no_thinking_kwargs", lambda model: {})
    client = FakeClient("You usually hit the gym around 6:30 — want me to protect that slot?")
    ph = WispPhraser(client_factory=lambda t: client)
    facts = {"habit": "gym", "time": "6:30"}
    assert ph.phrase("habit_conflict", facts) == client.content
    client.content = "Your 7:15 call with Dana conflicts."          # invents a time and a person
    assert ph.phrase("habit_conflict", facts) is None
    idle.begin_foreground()
    try:
        assert ph.phrase("habit_conflict", facts) is None             # never during foreground work
    finally:
        idle.end_foreground()
    cold = WispPhraser(client_factory=lambda t: FakeClient("ok", loaded=()))
    assert cold.phrase("x", facts) is None                            # never cold-loads a model


def test_phraser_categorize_and_failure(monkeypatch):
    from service.assistant.behavior_phraser import WispPhraser
    _target(monkeypatch)
    monkeypatch.setattr("service.inference.remote_policy.remote_only_profile", lambda: None)
    monkeypatch.setattr("service.config.no_thinking_kwargs", lambda model: {})
    ph = WispPhraser(client_factory=lambda t: FakeClient('{"1": "fitness", "2": "bogus"}'))
    assert ph.categorize(["Orangetheory", "Thing"], ("fitness", "other")) == {"Orangetheory": "fitness"}

    class Boom(FakeClient):
        async def chat(self, *a, **k):
            raise RuntimeError("down")
    assert WispPhraser(client_factory=lambda t: Boom("")).phrase("x", {"a": 1}) is None


def test_phraser_remote_only_payload_satisfies_gateway(monkeypatch):
    from service.assistant.behavior_phraser import WispPhraser
    from service.inference.remote_policy import RemoteOnlyProfile
    profile = RemoteOnlyProfile()
    _target(monkeypatch, profile.model_id)
    monkeypatch.setattr("service.inference.remote_policy.remote_only_profile", lambda: profile)
    client = FakeClient("You protect your gym mornings.", managed=False, loaded=())
    ph = WispPhraser(client_factory=lambda t: client)
    assert ph.phrase("day_preview", {"habit": "gym mornings"}) == "You protect your gym mornings."
    model, messages, kw = client.calls[0]
    assert set(kw) == {"temperature", "max_tokens"}                  # no template kwargs on the gateway
    profile.validate_payload({"model": model, "messages": messages, "stream": False, **kw})


def test_phraser_returns_none_on_event_loop():
    from service.assistant.behavior_phraser import WispPhraser

    async def inside():
        return WispPhraser(client_factory=lambda t: FakeClient("hi")).phrase("x", {"a": "hi"})
    assert asyncio.run(inside()) is None


# --------------------------------------------------------------------------
# Against the real engine + persona, once they exist
# --------------------------------------------------------------------------

def _real_engine_or_skip(path):
    try:
        from service.behavior.engine import BehaviorEngine
        return BehaviorEngine(path)
    except (NotImplementedError, ImportError) as exc:
        pytest.skip(f"behavior engine not implemented yet: {exc}")


def test_with_real_engine_and_persona(tmp_path, store):
    engine = _real_engine_or_skip(tmp_path / "real.db")
    try:
        from service.behavior.persona import generate_persona
    except ImportError:
        pytest.skip("persona generator not available yet")
    now = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0).timestamp()
    rt = br.BehaviorRuntime(tmp_path / "home", mode="local", synthetic=True, founder=True,
                            local_factory=lambda p: engine, persona_fn=generate_persona,
                            messages_fn=lambda: {"state": "unavailable"},
                            calendar_sync_fn=lambda: {"available": False}, clock=lambda: now)
    hub = FakeHub()
    asyncio.run(rt.tick(store, hub, now=now, force=True))
    assert rt.errors.get("persona") is None and rt.errors.get("engine") is None, rt.errors
    assert engine.patterns(), "persona produced no patterns"
    assert len(rt.refresh_card(now).encode()) <= 700
    for e in hub.events:
        if e["event"]["type"] == "nudge":
            assert all(e["event"][k] for k in ("nudge_id", "title", "body", "because"))


# --------------------------------------------------------------------------
# Remote-only (Intel founder) build: no assistant scheduler, so main.lifespan
# starts the behavior loop itself — and only when behavior learning is on.
# --------------------------------------------------------------------------

from tests.test_intel_remote_policy import RemoteFixture, policy  # noqa: E402


class RemoteOnlyLifespan(RemoteFixture):
    def _run(self):
        import ast
        from contextlib import asynccontextmanager
        from pathlib import Path
        from types import ModuleType, SimpleNamespace
        from unittest.mock import AsyncMock, Mock, patch
        source = Path(__file__).resolve().parents[1] / "service/main.py"
        tree = ast.parse(source.read_text())
        nodes = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
        nodes += [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name in {"lifespan", "_sync_keep_warm", "_prepare_remote_inference"}]
        fake = SimpleNamespace(health=AsyncMock(return_value={"ok": True}), aclose=AsyncMock())
        watched = []
        q = ModuleType("service.config.quarantine")
        q.check = Mock()

        async def watch(tasks, close):
            watched.append(tasks)
            await asyncio.Event().wait()
        q.watch = watch
        identity = ModuleType("service.identity")
        identity.refuse_sandbox_on_production_port = Mock()
        host = ModuleType("service.browser.host")
        host.start_from_environment = Mock(return_value=None)
        browser = ModuleType("service.browser")
        browser.host = host
        bomb = Mock(side_effect=AssertionError("local/background operation forbidden"))
        store_obj, hub_obj = object(), object()
        ns = {"asyncio": asyncio, "asynccontextmanager": asynccontextmanager,
              "remote_only_profile": policy.remote_only_profile,
              "require_local_models_disabled": policy.require_local_models_disabled,
              "OMLXClient": lambda: fake, "role_to_model": lambda role: "qwen3.6:35b",
              "skills": SimpleNamespace(load=bomb), "mcp_manager": SimpleNamespace(start=bomb, stop=bomb),
              "idle_unloader": SimpleNamespace(run=bomb), "assistant_scheduler": SimpleNamespace(run=bomb),
              "cloud_super_model_enabled": bomb, "start_laya_warmup": bomb,
              "research_manager": SimpleNamespace(store=SimpleNamespace(purge_stale_bodies=Mock())),
              "research_cache": SimpleNamespace(purge_older_than=Mock()),
              "assistant_store": store_obj, "assistant_hub": hub_obj}
        module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
        exec(compile(module, str(source), "exec"), ns)
        started = []

        async def fake_loop(store, hub):
            started.append((store, hub))
            await asyncio.Event().wait()

        async def run():
            with patch.dict("sys.modules", {"service.identity": identity, "service.config.quarantine": q,
                                            "service.browser": browser, "service.browser.host": host}), \
                    patch("service.config.quarantine", q), patch.object(br, "run_loop", fake_loop):
                async with ns["lifespan"](None):
                    await asyncio.sleep(0)
        asyncio.run(run())
        bomb.assert_not_called()
        return watched, started, (store_obj, hub_obj)

    def test_behavior_loop_started_only_when_enabled(self):
        old = {k: os.environ.pop(k, None) for k in ("WISP_BEHAVIOR", "WISP_FOUNDER_DEMO")}
        try:
            watched, started, _ = self._run()
            self.assertEqual(watched, [()])
            self.assertEqual(started, [])
            os.environ["WISP_BEHAVIOR"] = "1"
            watched, started, pair = self._run()
            self.assertEqual(len(watched[0]), 1)
            self.assertEqual(started, [pair])
        finally:
            for k, v in old.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v
