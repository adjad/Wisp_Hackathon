"""Synthetic, isolated knowledge storage/source authenticity regressions."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from service.personal_knowledge import KnowledgeStore, digest, selected_source
from service.tools import knowledge_tools as K
from service.memory.capture import current_source


@contextmanager
def user(quote, **changes):
    source = {"source_type": "user_request", "source_id": "synthetic-request",
              "session_id": "synthetic-session", "quote": quote, "observed_at": 1}
    token = current_source.set({**source, **changes})
    try:
        yield
    finally:
        current_source.reset(token)


@pytest.fixture
def storage(tmp_path, monkeypatch):
    store = KnowledgeStore(tmp_path / "knowledge")
    monkeypatch.setattr(K, "_store", store)
    return store


def save(text="Bring blue folder.", title="Project", kind="knowledge"):
    with user(f"Save a {K._LABELS[kind]} titled {title}:\n{text}"):
        result = K.save_knowledge(title, text, kind)
    assert result.startswith("Saved knowledge:"), result
    return json.loads(result.split("\n")[0].split(": ", 1)[1])


@pytest.mark.parametrize("kind", ["knowledge", "style_example", "followup_candidate"])
def test_explicit_full_user_text_has_host_provenance_and_no_scheduled_effect(storage, kind):
    row = save(kind=kind)
    assert row["provenance"]["source_id"] == "synthetic-request"
    assert row["provenance"]["quote"] == "Bring blue folder."
    assert storage.read(kind=kind)["records"] == [row]
    assert "Saved historical evidence" in K.read_knowledge()
    assert not (storage.root.parent / "assistant.db").exists()


@pytest.mark.parametrize("source_type", ["assistant", "tool", "conversation", ""])
def test_only_current_human_request_can_mutate(storage, source_type):
    with user("Save a knowledge note titled Project:\nBring blue folder.", source_type=source_type):
        assert K.save_knowledge("Project", "Bring blue folder.").startswith("(error:")
    assert storage.read()["records"] == []


@pytest.mark.parametrize("quote,text", [
    ("Remember something about Project", "Bring blue folder."),
    ("Save a knowledge note titled Project:\nDo not bring blue folder.", "bring blue folder."),
    ("Save a knowledge note titled Project:\nBring blue folder, unless cancelled.", "Bring blue folder"),
    ("Explain how to save a knowledge note titled Project:\nBring blue folder.", "Bring blue folder."),
    ("Save a knowledge note titled Project:\nBring blue folder.", "bring blue folder."),
])
def test_inferred_partial_quoted_or_altered_content_cannot_be_saved(storage, quote, text):
    with user(quote):
        assert K.save_knowledge("Project", text).startswith("(error:")
    assert storage.read()["records"] == []


def test_repeated_delivery_is_idempotent(storage):
    first, second = save(), save()
    assert first == second
    assert len(storage.read()["records"]) == 1


def test_relocated_store_after_publication_reports_unknown(storage, monkeypatch):
    from service import personal_knowledge as module
    replace = module.os.replace
    relocated = storage.root.with_name("relocated")
    def relocate(*args, **kwargs):
        replace(*args, **kwargs)
        storage.root.rename(relocated)
        storage.root.mkdir()
    monkeypatch.setattr(module.os, "replace", relocate)
    with user("Save a knowledge note titled Project:\nBring blue folder."):
        result = K.save_knowledge("Project", "Bring blue folder.")
    assert result.startswith("(error:") and "unknown" in result
    assert (relocated / "records.json").exists()
    assert storage.read()["records"] == []


def test_edit_replaces_provider_attribution_and_stale_revision_refuses(storage):
    first = save()
    rid, prior = first["id"], first["revision"]
    with user(f"Update knowledge {rid} titled Project:\nBring red folder."):
        result = K.edit_knowledge(rid, prior, "Project", "Bring red folder.")
        assert result.startswith("Updated knowledge:")
        assert K.edit_knowledge(rid, prior, "Project", "Bring red folder.").startswith("(error:")
    row = storage.read(record_id=rid)["records"][0]
    assert row["text"] == "Bring red folder."
    assert row["provenance"]["quote"] == row["text"]


def test_delete_requires_current_exact_id_and_revision(storage):
    row = save()
    with user("Delete all knowledge"):
        assert K.delete_knowledge(row["id"], row["revision"]).startswith("(error:")
    with user("Delete knowledge " + row["id"]):
        assert K.delete_knowledge(row["id"], "wrong revision").startswith("(error:")
        assert K.delete_knowledge(row["id"], row["revision"]).startswith("Deleted knowledge:")
    assert storage.read()["records"] == []


@pytest.mark.parametrize("field,value", [("title", ""), ("title", "x" * 201), ("text", "x" * 16385), ("text", "a\x00b")])
def test_input_bounds_fail_without_records(storage, field, value):
    args = {"title": "Project", "text": "Bring blue folder."}
    args[field] = value
    with user(f"Save a knowledge note titled {args['title']}:\n{args['text']}"):
        assert K.save_knowledge(**args).startswith("(error:")
    assert storage.read()["records"] == []


@pytest.mark.parametrize("record_id", ["../escape", "/tmp/escape", "x" * 32, "a" * 33])
def test_record_ids_cannot_be_paths(storage, record_id):
    with pytest.raises(ValueError):
        storage.read(record_id=record_id)


def test_store_rejects_symlink_state_and_parent(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        KnowledgeStore(tmp_path / "linked").read()
    root = tmp_path / "knowledge"
    root.mkdir()
    target = outside / "secret"
    target.write_text("not knowledge")
    (root / "records.json").symlink_to(target)
    with pytest.raises(OSError):
        KnowledgeStore(root).read()
    assert target.read_text() == "not knowledge"


def test_corrupt_or_oversized_state_fails_closed(storage):
    storage.read()
    path = storage.root / "records.json"
    path.write_text("not json")
    with pytest.raises(ValueError):
        storage.read()
    path.write_bytes(b" " * 1048577)
    with pytest.raises(ValueError):
        storage.read()


def test_search_intersects_words_and_discloses_omissions(storage):
    save("Bring blue folder.", "Project")
    save("Bring blue bag.", "Weekend")
    assert len(storage.read("blue folder")["records"]) == 1
    result = storage.read("blue", limit=1)
    assert len(result["records"]) == 1 and result["omitted"] == 1


def test_save_after_replace_sync_error_is_unknown_not_safely_retryable(storage, monkeypatch):
    real = os.fsync
    calls = []
    def fail_directory(fd):
        calls.append(fd)
        if len(calls) == 2:
            raise OSError("synthetic directory sync failed")
        return real(fd)
    monkeypatch.setattr(os, "fsync", fail_directory)
    with user("Save a knowledge note titled Project:\nBring blue folder."):
        result = K.save_knowledge("Project", "Bring blue folder.")
    assert "outcome unknown" in result and "may have changed" in result
    assert len(storage.read()["records"]) == 1


@pytest.fixture
def email_source(monkeypatch):
    from service.tools import email_tools as mail
    rows = [{"account_id": "account.synthetic", "message_id": "<synthetic@example.com>", "body": "Bring blue folder."}]
    monkeypatch.setattr(mail, "raw_email_snapshot", lambda: SimpleNamespace(
        rows=rows, generation=1, raw_digest=digest("synthetic generation"), synced_at=1))
    def forbidden(*args, **kwargs):
        raise AssertionError("Knowledge must not mix separate Mail metadata and body reads")
    monkeypatch.setattr(mail, "raw_reference_metadata", forbidden)
    monkeypatch.setattr(mail, "_parse_raw", forbidden)
    return rows


def test_source_import_resolves_actual_account_message_and_full_body(storage, email_source):
    with user("Save email <synthetic@example.com> in account account.synthetic as a knowledge note titled Project"):
        result = K.save_knowledge("Project", source_type="email", source_id="<synthetic@example.com>", container_id="account.synthetic")
    assert result.startswith("Saved knowledge:")
    row = storage.read()["records"][0]
    assert row["text"] == email_source[0]["body"]
    assert row["provenance"]["kind"] == "email"


@pytest.mark.parametrize("problem", ["missing", "duplicate", "stale", "partial", "style", "account", "unavailable"])
def test_cached_mail_source_failures_do_not_import(storage, email_source, monkeypatch, problem):
    from service.tools import email_tools as mail
    if problem == "missing":
        email_source.clear()
    elif problem == "duplicate":
        email_source.append(dict(email_source[0]))
    elif problem in {"stale", "partial"}:
        monkeypatch.setattr(mail, "raw_email_snapshot", lambda: None)
    elif problem == "account":
        email_source[0]["account_id"] = "another-account"
    elif problem == "unavailable":
        monkeypatch.setattr(mail, "raw_email_snapshot", lambda: None)
    with pytest.raises(ValueError):
        selected_source("email", "<synthetic@example.com>", "account.synthetic", style=problem == "style")
    assert storage.read()["records"] == []


@pytest.mark.parametrize("direction,style,works", [("outgoing", True, True), ("incoming", True, False), ("incoming", False, True)])
def test_messages_style_requires_exact_outgoing_native_source(monkeypatch, direction, style, works):
    from service.tools import imessage_tools as messages
    snapshot = {"state": "ready", "coverage": {"malformed": 0}, "records": [{
        "guid": "message.synthetic", "conversation": "chat.synthetic", "status": "complete",
        "direction": direction, "text": "Hi team, here is the update."}]}
    monkeypatch.setattr(messages, "structured_messages_snapshot", lambda: snapshot)
    if works:
        text, proof = selected_source("messages", "message.synthetic", "chat.synthetic", style=style)
        assert proof["sha256"] == digest(text)
    else:
        with pytest.raises(ValueError):
            selected_source("messages", "message.synthetic", "chat.synthetic", style=style)


def test_unsupported_source_has_no_invented_provenance():
    with pytest.raises(ValueError, match="no validated knowledge identity adapter"):
        selected_source("notes", "invented-note", "invented-folder")


def test_import_case_changed_native_id_cannot_hide_in_title(storage, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Wrong native selection must be rejected before reading")
    monkeypatch.setattr(K, "selected_source", forbidden)
    with user("Save messages MSG.ABC in chat chat.synthetic as a knowledge note titled msg.abc"):
        result = K.save_knowledge("msg.abc", source_type="messages", source_id="msg.abc", container_id="chat.synthetic")
    assert result.startswith("(error:")
    assert storage.read()["records"] == []


def test_fixed_state_fifo_is_rejected_without_blocking(storage):
    storage.read()
    os.mkfifo(storage.root / "records.json")
    with pytest.raises(ValueError, match="regular file"):
        storage.read()


def test_registered_mutation_categories_preserve_existing_view_only_policy(monkeypatch):
    from service.safety import policy
    from service.tools.registry import REGISTRY
    monkeypatch.setattr(policy, "_FULL_ACCESS", False)
    monkeypatch.setattr(policy, "_READ_ONLY", True)
    for name in ("save_knowledge", "edit_knowledge", "delete_knowledge"):
        assert policy.decide(REGISTRY[name].category, {}, name).tier == policy.Tier.DENY
