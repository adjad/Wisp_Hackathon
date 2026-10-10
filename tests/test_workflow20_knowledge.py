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


@pytest.mark.parametrize('prompt,tool', [
    ('Save a knowledge note titled Project:\nBring blue folder.','save_knowledge'),
    ('Read my saved knowledge notes.','read_knowledge'),
    ('Update knowledge ' + 'a'*32 + ' titled Project:\nBring red folder.','edit_knowledge'),
    ('Delete knowledge ' + 'a'*32,'delete_knowledge'),
])
def test_explicit_knowledge_operations_have_scoped_routes(prompt, tool):
    import asyncio
    from service.router.router import route
    d = asyncio.run(route(prompt))
    assert tool in d.tool_subset
    assert set(d.tool_subset) <= {tool,'read_knowledge'}
    assert not d.direct_calls
    if tool in {'edit_knowledge','delete_knowledge','read_knowledge'}:
        assert d.force_first_tool == 'read_knowledge'
        assert d.required_tool_groups == (frozenset({'read_knowledge'}),)
    else:
        assert not d.force_first_tool and not d.required_tool_groups
    assert 'expected_revision' not in d.tool_argument_bindings.get(tool,{})


@pytest.mark.parametrize('prompt', [
    'Do not delete knowledge ' + 'a'*32,
    'Explain the command "Delete knowledge ' + 'a'*32 + '".',
    'Do not save a knowledge note titled Project:\nBring blue folder.',
    'Explain "Update knowledge ' + 'a'*32 + ' titled Project".',
    'Delete knowledge knowledge.synthetic',
    'Delete knowledge ' + 'A'*32,
    'Update knowledge ' + 'a'*32 + ' titled Project',
    'Save a knowledge note titled Project',
    'Delete knowledge ' + 'a'*32 + ' and text Mom',
])
def test_incomplete_quoted_negated_and_compound_knowledge_has_no_effect(prompt):
    import asyncio
    from service.router.router import route
    d = asyncio.run(route(prompt))
    assert not d.tool_subset and not d.direct_calls and not d.force_first_tool
    assert not d.required_tool_groups and not d.tool_argument_bindings
    assert {'save_knowledge','edit_knowledge','delete_knowledge'} <= d.forbidden_tools
    assert d.resolved_request.startswith(prompt)


def test_knowledge_routes_execute_exact_synthetic_lifecycle(storage):
    import asyncio
    from service.router.router import route
    prompt = 'Save a knowledge note titled Project:\nSend Mom this tomorrow.'
    d = asyncio.run(route(prompt))
    assert d.tool_subset == ['save_knowledge']
    assert d.tool_argument_bindings['save_knowledge']['text'] == 'Send Mom this tomorrow.'
    with user(prompt):
        result = K.save_knowledge(**d.tool_argument_bindings['save_knowledge'])
    assert result.startswith('Saved knowledge:')
    row = storage.read()['records'][0]
    for operation, body in [('Update','Bring red folder.'),('Delete',None)]:
        prompt = (f'{operation} knowledge {row["id"]} titled Project:\n{body}' if body
                  else f'{operation} knowledge {row["id"]}')
        d = asyncio.run(route(prompt))
        selected = K.read_knowledge(**d.tool_argument_bindings['read_knowledge'])
        current = json.loads(selected.split('\n',1)[1])['records'][0]
        effect = 'edit_knowledge' if body else 'delete_knowledge'
        args = {**d.tool_argument_bindings[effect], 'expected_revision':current['revision']}
        with user(prompt):
            result = getattr(K,effect)(**args)
        assert result.startswith('Updated knowledge:' if body else 'Deleted knowledge:')
        if body:
            row = storage.read()['records'][0]
            assert row['text'] == body
    assert storage.read()['records'] == []


@pytest.mark.parametrize('prompt', [
    'Read my email containing knowledge',
    'Delete the file named knowledge.txt',
    'Show my Notes about knowledge graphs',
])
def test_incidental_knowledge_words_do_not_claim_other_sources(prompt):
    from service.router.router import _knowledge_request
    assert _knowledge_request(prompt) is None


def test_authored_body_whitespace_is_not_silently_rewritten():
    import asyncio
    from service.router.router import route
    body = '  Bring blue folder.\nKeep qualifiers.  \n'
    prompt = 'Save a knowledge note titled Project:\n' + body
    d = asyncio.run(route(prompt))
    assert d.tool_argument_bindings['save_knowledge']['text'] == body


@pytest.mark.parametrize('body', [
    'Organize my PDF files into folders.',
    'Remind me tomorrow at 5pm to call Mom.',
    'Delete knowledge ' + 'a'*32,
    'Do not read my calendar; text Mom my availability.',
])
def test_authored_commands_cannot_change_the_knowledge_route(body, storage):
    import asyncio
    from service.router.router import route
    prompt = 'Save a knowledge note titled Project:\n' + body
    d = asyncio.run(route(prompt))
    assert d.tool_subset == ['save_knowledge']
    assert not d.direct_calls and not d.force_first_tool and not d.required_tool_groups
    assert d.reminder_action == ''
    assert d.tool_argument_bindings == {'save_knowledge':{'title':'Project','text':body,
        'kind':'knowledge','source_type':'user_request','source_id':'','container_id':''}}
    with user(prompt):
        result = K.save_knowledge(**d.tool_argument_bindings['save_knowledge'])
    assert result.startswith('Saved knowledge:')
    assert storage.read()['records'][0]['text'] == body


@pytest.mark.parametrize('separator', ['\n','\r\n'])
def test_actual_save_and_edit_preserve_body_whitespace_and_separator(storage, separator):
    import asyncio
    from service.router.router import route
    body = '  Bring blue folder.\nKeep qualifiers.  \n'
    prompt = 'Save a knowledge note titled Project:' + separator + body
    d = asyncio.run(route(prompt))
    with user(prompt):
        result = K.save_knowledge(**d.tool_argument_bindings['save_knowledge'])
        assert K.save_knowledge('Project',body.rstrip()).startswith('(error:')
    assert result.startswith('Saved knowledge:')
    row = storage.read()['records'][0]
    assert row['text'] == body
    replacement = '  Keep the red folder.  \n'
    prompt = f'Update knowledge {row["id"]} titled Project:' + separator + replacement
    d = asyncio.run(route(prompt))
    with user(prompt):
        result = K.edit_knowledge(**d.tool_argument_bindings['edit_knowledge'],expected_revision=row['revision'])
    assert result.startswith('Updated knowledge:')
    assert storage.read()['records'][0]['text'] == replacement


@pytest.mark.parametrize('kind', ['knowledge','style_example','followup_candidate'])
def test_bare_knowledge_id_reads_do_not_filter_out_other_record_kinds(storage, kind):
    import asyncio
    from service.router.router import route
    row = save(kind=kind)
    d = asyncio.run(route('Read knowledge ' + row['id']))
    assert d.tool_argument_bindings['read_knowledge'] == {'record_id':row['id'],'kind':''}
    result = K.read_knowledge(**d.tool_argument_bindings['read_knowledge'])
    assert json.loads(result.split('\n',1)[1])['records'] == [row]


def test_instruction_label_whitespace_preserves_exact_authored_data(storage):
    import asyncio
    from service.router.router import route
    prompt = 'Save a knowledge  note titled Project:\nBring Blue Folder.'
    d = asyncio.run(route(prompt))
    with user(prompt):
        result = K.save_knowledge(**d.tool_argument_bindings['save_knowledge'])
    assert result.startswith('Saved knowledge:')
    assert storage.read()['records'][0]['text'] == 'Bring Blue Folder.'



def _knowledge_loop(monkeypatch, prompt, steps, *, approve=True, read_error=False, after_read=None, read_only=False, unforced_contract=False):
    import asyncio
    from service.agent import loop
    from service.router.router import route
    from service.safety import policy, grants
    from tests.test_direct_dispatch_exec import ScriptedClient, Approver
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        raise AssertionError('No network, native process or real model in this fixture')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket.socket,'connect_ex',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    monkeypatch.setattr('service.memory.identity.identity_prompt_block',lambda **kwargs:'')
    monkeypatch.setattr(policy,'_FULL_ACCESS',False)
    monkeypatch.setattr(policy,'_READ_ONLY',read_only)
    monkeypatch.setattr(grants,'check',lambda *args,**kwargs:None)
    d = asyncio.run(route(prompt))
    if unforced_contract:
        # Synthetic contract variant: retain the declared prerequisite without
        # an explicit first-tool hint, to observe the ordering audit itself.
        d.force_first_tool = None
        d.expect_tool_first = False
    actual = loop.run_tool
    calls = []
    async def run(tool,args):
        calls.append((tool.name,dict(args)))
        if tool.name == 'read_knowledge' and read_error:
            return '(error: synthetic knowledge read unavailable)'
        result = await actual(tool,args)
        if tool.name == 'read_knowledge' and after_read:
            after_read()
        return result
    monkeypatch.setattr(loop,'run_tool',run)
    client, approver, events = ScriptedClient(steps), Approver(approve), []
    monkeypatch.setattr(loop,'audit',lambda action,**fields: events.append(
        {'type':'audit','action':action,**fields}))
    async def emit(event): events.append(event)
    with user(prompt):
        output = asyncio.run(loop.run_agent(client,'Agents-A1-4B-oQe6',
            [{'role':'user','content':prompt}],emit,approver,tools=d.tool_subset,
            force_first_tool=d.force_first_tool,expect_tool_first=d.expect_tool_first,
            required_tool_groups=d.required_tool_groups,tool_argument_bindings=d.tool_argument_bindings,
            forbidden_tools=d.forbidden_tools,multi_round=d.multi_round,
            include_memory_context=False,max_steps=8))
    return output,calls,approver,events


def test_actual_loop_blocks_premature_and_duplicate_knowledge_effect(storage, monkeypatch):
    from tests.test_direct_dispatch_exec import _tool_call
    row = save()
    prompt = 'Delete knowledge ' + row['id']
    args = {'record_id':row['id'],'expected_revision':row['revision']}
    steps = [
        {'tool_calls':[_tool_call('delete_knowledge',args,'premature')]},
        {'tool_calls':[_tool_call('read_knowledge',{'record_id':row['id']},'read')]},
        {'tool_calls':[_tool_call('delete_knowledge',args,'delete')]},
        {'tool_calls':[_tool_call('delete_knowledge',{**args,'expected_revision':'b'*64},'duplicate')]},
        {'content':'The selected saved snapshot was deleted.'},
    ]
    output,calls,approver,events = _knowledge_loop(monkeypatch,prompt,steps)
    assert [name for name,args in calls] == ['read_knowledge','delete_knowledge']
    assert len(approver.seen) == 1
    assert storage.read()['records'] == []
    results = [e['result'] for e in events if e['type'] == 'tool_result']
    assert any('premature' in result for result in results)
    assert any('already succeeded' in result for result in results)
    assert any(e['type'] == 'audit' and e['action'] == 'reject_ungrounded_order' for e in events)
    assert any(e['type'] == 'audit' and e['action'] == 'reject_duplicate_effect' for e in events)
    assert any(result.startswith('Deleted knowledge:') for result in results)


def test_actual_loop_read_failure_never_invokes_knowledge_mutation(storage, monkeypatch):
    from tests.test_direct_dispatch_exec import _tool_call
    row = save()
    args = {'record_id':row['id'],'expected_revision':row['revision']}
    steps = [
        {'tool_calls':[_tool_call('read_knowledge',{'record_id':row['id']},'read')]},
        {'tool_calls':[_tool_call('delete_knowledge',args,'delete')]},
        {'content':'The read failed; nothing was deleted.'},
    ]
    output,calls,approver,events = _knowledge_loop(monkeypatch,'Delete knowledge ' + row['id'],
                                                steps,read_error=True)
    assert not any(name == 'delete_knowledge' for name,args in calls)
    assert not approver.seen
    assert storage.read()['records'] == [row]
    assert not any(e['type'] == 'tool_result' and e['result'].startswith('Deleted knowledge:') for e in events)


def test_actual_loop_preserves_existing_mutation_confirmation_denial(storage, monkeypatch):
    from tests.test_direct_dispatch_exec import _tool_call
    prompt = 'Save a knowledge note titled Project:\nBring blue folder.'
    steps = [{'tool_calls':[_tool_call('save_knowledge',{'title':'Project','text':'Bring blue folder.'},'save')]},
             {'content':'Nothing was saved.'}]
    output,calls,approver,events = _knowledge_loop(monkeypatch,prompt,steps,approve=False)
    assert len(approver.seen) == 1 and not calls
    assert storage.read()['records'] == []
    assert not any(e['type'] == 'tool_result' and e['result'].startswith('Saved knowledge:') for e in events)


def test_actual_loop_stale_revision_cannot_overwrite_intervening_edit(storage, monkeypatch):
    from tests.test_direct_dispatch_exec import _tool_call
    row = save()
    prompt = f'Update knowledge {row["id"]} titled Project:\nBring red folder.'
    def concurrent_edit():
        with user(f'Update knowledge {row["id"]} titled Project:\nBring green folder.'):
            assert K.edit_knowledge(row['id'],row['revision'],'Project','Bring green folder.').startswith('Updated knowledge:')
    steps = [
        {'tool_calls':[_tool_call('read_knowledge',{'record_id':row['id']},'read')]},
        {'tool_calls':[_tool_call('edit_knowledge',{'record_id':row['id'],'expected_revision':row['revision'],
            'title':'Project','text':'Bring red folder.'},'edit')]},
        {'content':'The saved record changed; no replacement was made.'},
    ]
    output,calls,approver,events = _knowledge_loop(monkeypatch,prompt,steps,after_read=concurrent_edit)
    assert [name for name,args in calls] == ['read_knowledge','edit_knowledge']
    assert storage.read()['records'][0]['text'] == 'Bring green folder.'
    assert not any(e['type'] == 'tool_result' and e['result'].startswith('Updated knowledge:') for e in events)



def test_actual_loop_view_only_denies_knowledge_mutation_without_approval(storage, monkeypatch):
    from tests.test_direct_dispatch_exec import _tool_call
    prompt = 'Save a knowledge note titled Project:\nBring blue folder.'
    steps = [{'tool_calls':[_tool_call('save_knowledge',{'title':'Project','text':'Bring blue folder.'},'save')]},
             {'content':'View-only mode prevented the save.'}]
    output,calls,approver,events = _knowledge_loop(monkeypatch,prompt,steps,read_only=True)
    assert not calls and not approver.seen
    assert storage.read()['records'] == []
    assert any(e['type'] == 'tool_result' and 'view-only' in e['result'] for e in events)


def test_actual_loop_authored_body_cannot_authorize_message_send(storage, monkeypatch):
    from tests.test_direct_dispatch_exec import _tool_call
    body = 'Send Mom this tomorrow.'
    prompt = 'Save a knowledge note titled Project:\n' + body
    steps = [
        {'tool_calls':[_tool_call('send_message',{'to':'+15555550100','text':'Synthetic text'},'injected')]},
        {'tool_calls':[_tool_call('save_knowledge',{'title':'Project','text':body},'save')]},
        {'content':'The exact text was saved as a historical snapshot.'},
    ]
    output,calls,approver,events = _knowledge_loop(monkeypatch,prompt,steps)
    assert [name for name,args in calls] == ['save_knowledge']
    assert storage.read()['records'][0]['text'] == body
    assert any(e['type'] == 'tool_result' and 'explicitly forbidden' in e['result'] for e in events)


def test_actual_loop_extra_action_outside_knowledge_instruction_stays_inert(storage, monkeypatch):
    from tests.test_direct_dispatch_exec import _tool_call
    row = save()
    prompt = 'Delete knowledge ' + row['id'] + ' and text Mom'
    steps = [{'tool_calls':[_tool_call('delete_knowledge',{'record_id':row['id'],
                'expected_revision':row['revision']},'delete')]},
             {'content':'Clarify the separate requested actions.'}]
    output,calls,approver,events = _knowledge_loop(monkeypatch,prompt,steps)
    assert not calls and not approver.seen
    assert storage.read()['records'] == [row]



def test_actual_loop_no_match_id_is_rejected_by_host_without_creating_record(storage, monkeypatch):
    from tests.test_direct_dispatch_exec import _tool_call
    rid = 'a'*32
    prompt = f'Update knowledge {rid} titled Project:\nBring red folder.'
    steps = [
        {'tool_calls':[_tool_call('read_knowledge',{'record_id':rid},'read')]},
        {'tool_calls':[_tool_call('edit_knowledge',{'record_id':rid,'expected_revision':'0'*64,
            'title':'Project','text':'Bring red folder.'},'edit')]},
        {'content':'The selected record was not found; nothing was changed.'},
    ]
    output,calls,approver,events = _knowledge_loop(monkeypatch,prompt,steps)
    assert [name for name,args in calls] == ['read_knowledge','edit_knowledge']
    assert storage.read()['records'] == []
    assert any(e['type'] == 'tool_result' and 'Knowledge record is missing' in e['result'] for e in events)
    assert not any(e['type'] == 'tool_result' and e['result'].startswith('Updated knowledge:') for e in events)



@pytest.mark.parametrize('effect', ['save_knowledge','edit_knowledge'])
def test_actual_loop_name_guard_blocks_changed_argument_duplicate_writes(storage, monkeypatch, effect):
    from tests.test_direct_dispatch_exec import _tool_call
    if effect == 'save_knowledge':
        prompt = 'Save a knowledge note titled Project:\nBring blue folder.'
        args = {'title':'Project','text':'Bring blue folder.'}
        steps = [{'tool_calls':[_tool_call(effect,args,'first')]},
                 {'tool_calls':[_tool_call(effect,{**args,'text':'Altered text.'},'repeat')]},
                 {'content':'The exact snapshot was saved once.'}]
    else:
        row = save()
        prompt = f'Update knowledge {row["id"]} titled Project:\nBring red folder.'
        args = {'record_id':row['id'],'expected_revision':row['revision'],
                'title':'Project','text':'Bring red folder.'}
        steps = [{'tool_calls':[_tool_call('read_knowledge',{'record_id':row['id']},'read')]},
                 {'tool_calls':[_tool_call(effect,args,'first')]},
                 {'tool_calls':[_tool_call(effect,{**args,'expected_revision':'b'*64},'repeat')]},
                 {'content':'The exact snapshot was updated once.'}]
    output,calls,approver,events = _knowledge_loop(monkeypatch,prompt,steps)
    assert sum(name == effect for name,args in calls) == 1
    assert len(approver.seen) == 1
    assert any(e['type'] == 'audit' and e['action'] == 'reject_duplicate_effect'
               and e['tool'] == effect for e in events)
    rows = storage.read()['records']
    assert len(rows) == 1
    assert rows[0]['text'] == ('Bring blue folder.' if effect == 'save_knowledge' else 'Bring red folder.')


@pytest.mark.parametrize('operation,effect', [('Update','edit_knowledge'),('Delete','delete_knowledge')])
def test_actual_loop_declared_read_guard_without_explicit_force_hint(storage, monkeypatch, operation, effect):
    from tests.test_direct_dispatch_exec import _tool_call
    row = save()
    prompt = (f'Update knowledge {row["id"]} titled Project:\nBring red folder.'
              if operation == 'Update' else 'Delete knowledge ' + row['id'])
    args = {'record_id':row['id'],'expected_revision':row['revision']}
    if operation == 'Update': args.update(title='Project',text='Bring red folder.')
    steps = [{'tool_calls':[_tool_call(effect,args,'premature')]},
             {'tool_calls':[_tool_call('read_knowledge',{'record_id':row['id']},'failed-read')]},
             {'tool_calls':[_tool_call(effect,args,'after-failure')]},
             {'content':'No change was made because the read failed.'}]
    output,calls,approver,events = _knowledge_loop(monkeypatch,prompt,steps,
        read_error=True,unforced_contract=True)
    assert not any(name == effect for name,args in calls)
    assert not approver.seen and storage.read()['records'] == [row]
    assert any(e['type'] == 'audit' and e['action'] == 'reject_ungrounded_order'
               and e['tool'] == effect for e in events)
