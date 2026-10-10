"""Private-source constraints; routing only, no tools or models execute."""
import asyncio

import pytest

import service.tools
from service.router import router as R
from service.workflows.workflow20 import personal_read


def test_prohibition_optional_menu_cannot_activate_private_meeting(monkeypatch):
    async def core(_text):
        return ['plan_meeting', 'commit_private_meeting', 'clipboard_read']
    monkeypatch.setattr(R, '_semantic_core', core)
    decision = asyncio.run(R.route('Do not read my clipboard, it contains private information.'))
    assert not {'plan_meeting', 'commit_private_meeting'} & set(decision.tool_subset)
    assert not decision.direct_calls and not decision.required_tool_groups
    assert not decision.force_first_tool and not decision.expect_tool_first


def test_tomorrow_todo_actual_batch_reads_every_source_before_narration(monkeypatch):
    from service.agent import loop
    from service.workflows.reads import compile_read
    from tests.test_direct_dispatch_exec import Approver, ScriptedClient
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        raise AssertionError('No network, native process or unexpected source in this fixture')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr('service.memory.identity.identity_prompt_block', lambda **kwargs: '')
    prompt = "what's on my to-do list tomorrow?"
    decision = asyncio.run(R.route(prompt))
    assert compile_read(prompt) is None
    calls = []
    async def read(tool, args):
        calls.append((tool.name, args))
        return {'get_upcoming': 'Tomorrow appointment and dated native Reminder.',
                'summarize_messages': 'Earlier received: submit the blue form tomorrow.',
                'summarize_emails': 'Earlier received: bring the red folder tomorrow.',
                'search_notes': 'Undated: buy a green notebook; due date unknown.'}[tool.name]
    monkeypatch.setattr(loop, 'run_tool', read)
    class Client(ScriptedClient):
        async def stream_events(self, *args, **kwargs):
            assert calls == decision.direct_calls
            async for event in super().stream_events(*args, **kwargs):
                yield event
    client = Client([{'content': 'Synthetic narration after all source reads.'}])
    events = []
    async def emit(event): events.append(event)
    asyncio.run(loop.run_agent(client, 'Agents-A1-4B-oQe6',
        [{'role': 'user', 'content': decision.resolved_request}], emit, Approver(),
        tools=decision.tool_subset, direct_calls=decision.direct_calls,
        tool_argument_bindings=decision.tool_argument_bindings,
        narration_after=decision.narration_after, required_tool_groups=decision.required_tool_groups,
        strict_read_limits=decision.strict_read_limits, forbidden_tools=decision.forbidden_tools,
        multi_round=decision.multi_round,
        include_memory_context=False, max_steps=2))
    assert len(client.calls) == 1
    assert calls == decision.direct_calls
    assert not any(event['type'] == 'confirm' for event in events)


@pytest.mark.parametrize('prompt', [
    'plan arrival using traffic',
    'work backward from my arrival deadline',
    'get me there by tonight',
    'When should I leave home to reach SFO by 10:30 tonight?',
    'What time should I leave home to reach SFO by 10:30 tonight?',
    'How early should we leave home to reach SFO by 10:30 tonight?',
    'Plan me to go to SFO at 11PM with traffic and my location',
    'When do I need to leave to arrive at SFO by tomorrow at 11PM?',
    'When should I leave home to reach SFO by 10:30 tonight, then text Mom',
    'Plan my trip to SFO with traffic; then open Maps',
    'Plan arrival at SFO from home by 2026-10-12T23:00:00-07:00',
    'Plan arrival at SFO from here by 2026-10-12T23:00:00-07:00',
    'Plan arrival at SFO from current location by 2026-10-12T23:00:00-07:00',
    'Plan arrival at SFO from 123 Example Road, open Maps by 2026-10-12T23:00:00-07:00',
    'Plan arrival at SFO from 123 Example Road by 2026-10-12T23:00:00-07:00 with a 181-minute buffer',
])
def test_personal_arrival_clarifies_without_public_search_or_effect(prompt):
    assert R.rule_route(prompt) is None
    decision = asyncio.run(R.route(prompt))
    assert decision.direct_calls == []
    assert not decision.force_first_tool
    assert not decision.expect_tool_first
    assert not decision.tool_subset
    assert 'route_to_arrive' in decision.forbidden_tools
    assert {'web_search','web_fetch','http_request','run_shell','travel_time','get_directions',
            'send_message','add_calendar_event'} <= decision.forbidden_tools
    assert decision.resolved_request.startswith(prompt)
    assert 'Clarify' in decision.resolved_request


def test_complete_arrival_has_only_exact_checked_read_binding():
    prompt = 'Plan arrival at SFO from 123 Example Road by 2026-10-12T23:00:00-07:00 with a 30-minute buffer'
    decision = asyncio.run(R.route(prompt))
    assert decision.tool_subset == ['route_to_arrive']
    assert decision.tool_argument_bindings == {'route_to_arrive': {
        'destination':'SFO', 'origin':'123 Example Road',
        'arrive_by':'2026-10-12T23:00:00-07:00',
        'timezone':'America/Los_Angeles', 'buffer_minutes':30}}
    assert not decision.direct_calls and not decision.force_first_tool
    assert 'get_directions' in decision.forbidden_tools


def test_unresolved_arrival_actual_loop_asks_once_without_tool_nudges(monkeypatch):
    import socket
    import subprocess
    from service.agent import loop
    from tests.test_direct_dispatch_exec import ScriptedClient,Approver
    def forbidden(*args,**kwargs):
        raise AssertionError('Clarification may not read providers or execute tools')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket.socket,'connect_ex',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    monkeypatch.setattr(loop,'run_tool',forbidden)
    monkeypatch.setattr('service.memory.identity.identity_prompt_block',lambda **kwargs:'')
    prompt='When should I leave home to reach SFO by 10:30 tonight?'
    decision=asyncio.run(R.route(prompt))
    client=ScriptedClient([{'content':'What address should I use for home, and which arrival date?'}])
    events=[]
    async def emit(event): events.append(event)
    result=asyncio.run(loop.run_agent(client,'Agents-A1-4B-oQe6',
        [{'role':'user','content':decision.resolved_request}],emit,Approver(),
        tools=decision.tool_subset,expect_tool_first=decision.expect_tool_first,
        force_first_tool=decision.force_first_tool,required_tool_groups=decision.required_tool_groups,
        include_memory_context=False,max_steps=3))
    assert len(client.calls)==1
    assert 'address' in result and 'arrival date' in result
    assert not any(event['type'] in {'tool_call','confirm'} for event in events)


@pytest.mark.parametrize('prompt', [
    'Explain what the words "when should I leave to reach SFO" mean',
    'What is the history of SFO airport?',
    'What should tourists know about SFO traffic?',
])
def test_public_or_quoted_travel_topics_do_not_claim_personal_arrival(prompt):
    assert R._arrival_plan(prompt) is None


@pytest.mark.parametrize('prompt,args',[
    ('Give me today briefing.',{'period':'today'}),
    ('My daily digest, please.',{}),
    ('Give today briefing without weather.',{'period':'today','include_weather':False}),
    ('Give my daily briefing without email or texts.',{'include_email':False,'include_messages':False}),
])
def test_daily_envelope_variants_preserve_exclusions_at_both_entrypoints(prompt,args):
    from service.workflows.reads import compile_read
    from service.workflows.compiler import compile_new
    assert compile_new(prompt) is None
    assert compile_read(prompt)==([('daily_brief',args)],'')
    decision=asyncio.run(R.route(prompt))
    assert decision.direct_calls==[('daily_brief',args)]
    assert 'web_search' in decision.forbidden_tools


def test_calendar_only_brief_cannot_read_other_private_sources():
    from service.workflows.reads import compile_read
    prompt='Brief me on today calendar only.'
    assert compile_read(prompt)==([('get_upcoming',{'period':'today','calendar_only':True})],'')
    decision=asyncio.run(R.route(prompt))
    assert decision.tool_subset==['get_upcoming']


@pytest.mark.parametrize('prompt,args',[
    ('Recap the Studio crew group chat.',{'conversation':'Studio crew'}),
    ('Summarize the Family group from yesterday.',{'conversation':'Family','day':'yesterday'}),
    ('Catch me up on Studio crew chat from this week',{'conversation':'Studio crew','period':'this week'}),
])
def test_explicit_chat_recaps_bind_exact_conversation_and_range(prompt,args):
    from service.workflows.reads import compile_read
    from service.workflows.compiler import compile_new
    assert compile_new(prompt) is None
    assert compile_read(prompt)==([('summarize_messages',args)],'')
    decision=asyncio.run(R.route(prompt))
    assert decision.direct_calls==[('summarize_messages',args)]
    assert decision.tool_subset==['summarize_messages']
    assert 'web_search' in decision.forbidden_tools


@pytest.mark.parametrize('prompt',[
    'Summarize the Family group from yesterday and email Mom',
    'Recap the entire Studio crew chat',
    'Recap Studio crew group chat excluding what I wrote',
    'Recap Studio crew group chat about the budget',
    'Give today briefing without weather and open Maps',
    'Brief me on today calendar only and send it to Mom',
])
def test_new_read_grammars_never_drop_history_topic_sender_or_second_action(prompt):
    from service.workflows.workflow20 import daily_read,conversation_read
    assert daily_read(prompt) is None and conversation_read(prompt) is None


@pytest.mark.parametrize('prompt',[
    'What did Dad say yesterday?', 'What did Mom text today?',
    'What did my brother write yesterday?',
])
def test_relationship_communication_questions_remain_private_without_saved_contact(monkeypatch,prompt):
    monkeypatch.setattr('service.tools.imessage_tools.contact_names',lambda:[])
    decision=asyncio.run(R.route(prompt))
    assert 'web_search' in decision.forbidden_tools
    assert not any(name=='web_search' for name,args in decision.direct_calls)
    assert 'summarize_messages' in decision.tool_subset


def test_complete_excluded_source_names_do_not_count_as_required_reads():
    from service.workflows.reads import compile_read
    assert compile_read("What's on my calendar this week, do not include reminders")==([
        ('get_upcoming',{'period':'this week','calendar_only':True})],'')
    assert compile_read('show email summaries but not messages')==([('summarize_emails',{})],'')
    decision=asyncio.run(R.route("What's on my calendar this week, do not include reminders"))
    assert decision.direct_calls==[('get_upcoming',{'period':'this week','calendar_only':True})]
    assert decision.tool_subset==['get_upcoming']


@pytest.mark.parametrize('prompt',[
    'show email summaries but not messages about the budget',
    'show email summaries without private details',
    'show email summaries but not messages and email Mom',
    'show email summaries excluding what I wrote',
    "What's on my calendar this week, do not include reminders and open Maps",
])
def test_source_exclusion_shortcut_rejects_content_filters_and_additional_actions(prompt):
    from service.workflows.reads import compile_read
    assert compile_read(prompt) is None


@pytest.mark.parametrize("prompt", [
    "What is happening across mail and texts today?",
    "Give an overview of tomorrow commitments and recent texts.",
    "Tell me about today email and yesterday messages.",
    "Give me an overview of my email, messages and calendar.",
    "Check my inbox and iMessages, then tell me what meetings are next.",
    "What should I know from my calender, email and mesages?",
    "Read my notes and reminders for groceries.",
])
def test_multisource_private_read_never_preexecutes_web(prompt):
    decision = asyncio.run(R.route(prompt))
    assert "web_search" in decision.forbidden_tools
    assert not any(name == "web_search" for name, _ in decision.direct_calls)
    assert len(decision.required_tool_groups) >= 2


@pytest.mark.parametrize("prompt,tool,day", [
    ("What unread texts do I have?", "view_messages", None),
    ("Catch me up on unread email.", "view_emails", None),
    ("Show my unread messages from yesterday", "view_messages", "yesterday"),
    ("List my unread texts today.", "view_messages", "today"),
    ("Read all unread email yesterday", "view_emails", "yesterday"),
])
def test_unread_binding_cannot_be_dropped(prompt, tool, day):
    decision = asyncio.run(R.route(prompt))
    assert decision.tool_argument_bindings[tool]["unread"] is True
    if day:
        assert decision.direct_calls == [(tool, {"unread": True, "day": day})]
    assert "web_search" in decision.forbidden_tools


def test_unread_cross_channel_complete_read():
    decision = asyncio.run(R.route("Show me all unread email and messages."))
    assert decision.direct_calls == [("view_emails", {"unread": True}), ("view_messages", {"unread": True})]
    assert decision.verified_results_only


@pytest.mark.parametrize("prompt", [
    "Show unread emails and messages I have read",
    "Show unread emails today and messages yesterday",
    "Show unread emails and messages from Mom yesterday",
    "Show unread email and messages that I opened",
])
def test_source_specific_unread_qualifiers_are_not_flattened(prompt):
    from service.workflows.reads import compile_read
    read = personal_read(prompt)
    assert read is None or (not read.direct_calls and not read.bindings)
    assert compile_read(prompt) is None


@pytest.mark.parametrize("prompt", [
    "Show unread emails I have read",
    "Show unread messages I opened",
    "What unread texts did I read?",
])
def test_unread_shortcut_requires_complete_grammar(prompt):
    read = personal_read(prompt)
    assert read is None or not read.direct_calls


@pytest.mark.parametrize("prompt", [
    'Show unread messages "urgent"', 'Show unread emails "from Mom"',
    'Show email summary from Priya', 'Show email summary and open Maps',
    'Show email summary containing "invoice"',
    'Show email summary and send it to Mom',
    'Show email and open Safari, purchases from Amazon',
])
def test_entrypoint_retains_named_quoted_and_second_action_qualifiers(prompt):
    from service.workflows.reads import compile_read
    assert compile_read(prompt) is None


@pytest.mark.parametrize("prompt,args", [
    ("Show email summary", {}), ("Show my email summary from today", {"day": "today"}),
    ("Give me my inbox digest this week", {"period": "this week"}),
])
def test_complete_email_summary_shortcuts_remain_available(prompt, args):
    from service.workflows.reads import compile_read
    assert compile_read(prompt) == ([("summarize_emails", args)], "")


def test_complete_purchase_lookup_remains_available():
    from service.workflows.reads import compile_read
    assert compile_read("Show email purchases from Amazon") == (
        [("view_emails", {"query": "Amazon", "strict_match": True})], "")
    assert compile_read("**Can you check my email for purchases from PlayStation?**") == (
        [("view_emails", {"query": "PlayStation", "strict_match": True})], "")


@pytest.mark.parametrize("prompt,status", [
    ("What texts and emails are scheduled?", "pending"),
    ("Show pending delivery IDs and times.", "pending"),
    ("Was the interrupted Lee email outcome confirmed?", "all"),
    ("Which sends have uncertain outcomes?", "all"),
    ("Which scheduled texts missed their time?", "all"),
    ("Is the interrupted Lee email safe to retry automatically?", "all"),
])
def test_scheduled_status_review_uses_recorded_history_not_pending_absence(prompt, status):
    decision = asyncio.run(R.route(prompt))
    assert decision.tool_argument_bindings["list_scheduled_sends"] == {"status": status}
    assert "web_search" in decision.forbidden_tools
    assert "send_message" in decision.forbidden_tools and "schedule_send" in decision.forbidden_tools
    assert "cancel_scheduled_send" not in decision.tool_subset


def test_scheduled_exact_id_inspection_and_cancel_require_existing_record():
    decision = asyncio.run(R.route("Inspect queued email ID abcdef123456 full body"))
    assert decision.tool_argument_bindings["list_scheduled_sends"] == {"id": "abcdef123456"}
    cancel = asyncio.run(R.route("Cancel pending email abcdef123456"))
    assert cancel.force_first_tool == "list_scheduled_sends"
    assert "cancel_scheduled_send" in cancel.tool_subset
    assert not cancel.direct_calls


def test_scheduled_explanation_does_not_read_queue():
    assert R._scheduled_send_review("Explain scheduled sends without cancelling") is None


@pytest.mark.parametrize("prompt", [
    "Show pending sends and my calendar", "Show queued texts and lock my screen",
    "Review pending emails then open Safari", "Show queued texts and delete files",
    "Review pending sends and cancel tomorrow's Mom text",
])
def test_queue_review_does_not_swallow_other_domains_or_effects(prompt):
    assert R._scheduled_send_review(prompt) is None


def test_quoted_queue_example_cannot_bind_record_identity():
    decision = asyncio.run(R.route('Show pending sends like "abcdef123456"'))
    assert decision.tool_argument_bindings["list_scheduled_sends"] == {"status": "pending"}


def test_queue_guidance_preserves_original_recipient_body_and_date():
    prompt = 'Show queued texts to Mom tomorrow containing "blue folder"'
    decision = asyncio.run(R.route(prompt))
    assert decision.resolved_request.startswith(prompt + "\n")


@pytest.mark.parametrize("prompt", [
    "Schedule a meeting with Priya tomorrow at 4PM",
    "Plan a 30 minute meeting with Lee after my test tomorrow",
    "Book a meeting with Mom after this event",
    "Schedule a meeting inviting Priya tomorrow at 4PM",
])
def test_meeting_proposal_preserves_request_without_substituting_invitation(prompt):
    from service.workflows.compiler import compile_new
    from service.workflows.reads import compile_read
    assert compile_new(prompt) is None
    assert compile_read(prompt) is None
    decision = asyncio.run(R.route(prompt))
    assert "plan_meeting" in decision.tool_subset
    assert "add_calendar_event" in decision.forbidden_tools
    assert not decision.direct_calls
    assert not decision.expect_tool_first
    assert decision.resolved_request.startswith(prompt + "\n")


def test_private_block_creation_offers_only_checked_approval_bound_effect():
    prompt = "Add a private calendar block for a 30 minute meeting after my exam tomorrow"
    decision = asyncio.run(R.route(prompt))
    assert "add_calendar_event" in decision.forbidden_tools
    assert "commit_private_meeting" in decision.tool_subset
    assert "commit_private_meeting" not in decision.forbidden_tools
    assert not decision.required_tool_groups
    assert not decision.direct_calls
    assert "send_message" in decision.forbidden_tools
    assert "web_search" in decision.forbidden_tools
    assert decision.resolved_request.startswith(prompt + "\n")
    assert "exact commit_args" in decision.resolved_request


@pytest.mark.parametrize("prompt", [
    "Add a private calendar block for a meeting tomorrow",
    'Create a private calendar block titled "Remind me tomorrow at 9am" for 30 minutes at 4PM tomorrow',
    "Create a private calendar block that invites Priya tomorrow at 4PM for 30 minutes",
])
def test_meeting_missing_inputs_and_quoted_titles_cannot_force_or_invent_effects(prompt):
    decision = asyncio.run(R.route(prompt))
    assert not decision.expect_tool_first
    assert not decision.required_tool_groups
    assert not decision.reminder_action
    assert "add_calendar_event" in decision.forbidden_tools
    assert "add_reminder" in decision.forbidden_tools


def test_calendar_exclusion_also_excludes_new_planner():
    decision = asyncio.run(R.route("Plan a meeting tomorrow, not Calendar"))
    assert "plan_meeting" in decision.forbidden_tools
    assert "plan_meeting" not in decision.tool_subset


@pytest.mark.parametrize("prompt", ["What should I work on now?", "What should I work on tomorrow?", "What do I need to do this week?"])
def test_priorities_can_recover_overdue_reminders(prompt):
    decision = asyncio.run(R.route(prompt))
    assert "daily_brief" in decision.tool_subset
    assert "web_search" in decision.forbidden_tools
    period = "tomorrow" if "tomorrow" in prompt else "this week" if "this week" in prompt else "today"
    assert decision.tool_argument_bindings["daily_brief"] == {
        "period": period, "include_overdue": True, "include_undated": True, "include_weather": False}
    assert decision.tool_argument_bindings["search_notes"] == {"query": ""}
    assert "search_reminders" not in decision.tool_subset


@pytest.mark.parametrize("prompt,args", [
    ("Daily summary", {}),
    ("Give me a daily summary for tomorrow", {"period": "tomorrow"}),
    ("My daily brief without email or messages", {"include_email": False, "include_messages": False}),
    ("Daily digest next week, no calendar and weather", {"period": "next week", "include_calendar": False, "include_weather": False}),
])
def test_daily_envelope_preserves_date_and_source_constraints(prompt, args):
    from service.workflows.reads import compile_read
    assert compile_read(prompt) == ([("daily_brief", args)], "")
    decision = asyncio.run(R.route(prompt))
    assert decision.direct_calls == [("daily_brief", args)]
    assert decision.tool_argument_bindings["daily_brief"] == args
    assert "web_search" in decision.forbidden_tools


@pytest.mark.parametrize("prompt", [
    "Daily summary only work emails", "Daily summary without reading anything",
    "Daily summary then send it to Mom", "Daily summary if Mom agrees",
    "Daily summary but no medical details", "Daily summary with weather in Santa Clara",
])
def test_daily_shortcut_does_not_drop_unconsumed_constraints(prompt):
    from service.workflows.workflow20 import daily_read
    assert daily_read(prompt) is None


def test_agenda_preserves_both_dst_fold_offsets(monkeypatch):
    import datetime as dt
    import time
    from zoneinfo import ZoneInfo
    from service.tools.assistant_tools import _agenda_item
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    try:
        rows = []
        for fold in (0, 1):
            when = dt.datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/Los_Angeles"), fold=fold)
            rows.append(_agenda_item({"title": "Synthetic event", "when_ts": when.timestamp(), "source": "calendar"}))
        assert "1:30 AM PDT-0700" in rows[0]
        assert "1:30 AM PST-0800" in rows[1]
        assert rows[0] != rows[1]
    finally:
        monkeypatch.undo()
        time.tzset()


def test_missing_meeting_duration_can_ask_through_real_loop_without_tools(monkeypatch):
    from service.agent import loop
    from service.memory import identity
    prompt = "Add a private calendar block for a meeting tomorrow"
    decision = asyncio.run(R.route(prompt))
    question = "What duration and start time should I use for the private block?"
    choices = []
    def forbidden(*args, **kwargs):
        raise AssertionError("No reader, approval or effect may execute in this clarification control")
    monkeypatch.setattr(loop, "run_tool", forbidden)
    monkeypatch.setattr(identity, "identity_prompt_block", lambda **kwargs: "")
    class Client:
        managed = True
        base_url = "http://127.0.0.1:8000"
        async def ensure_only(self, *args, **kwargs):
            pass
        async def stream_events(self, model, messages, **kwargs):
            choices.append(kwargs.get("tool_choice"))
            assert any(prompt in str(row.get("content", "")) for row in messages)
            yield {"kind": "final", "message": {"role": "assistant", "content": question}}
    class Approver:
        confirm = forbidden
    async def emit(event):
        pass
    result = asyncio.run(loop.run_agent(Client(), decision.model,
        [{"role": "user", "content": decision.resolved_request}], emit, Approver(),
        tools=decision.tool_subset, required_tool_groups=decision.required_tool_groups,
        forbidden_tools=decision.forbidden_tools, expect_tool_first=decision.expect_tool_first,
        include_memory_context=False, max_steps=1, multi_round=decision.multi_round))
    assert choices == ["auto"]
    assert result == question


@pytest.mark.parametrize("prompt", [
    "Plan a meeting after restarting Chrome",
    "Plan a meeting after checking traffic",
    "Add a private calendar block for a 30 minute meeting tomorrow at 4PM after Priya agrees",
    "Plan a meeting tomorrow. Lock my screen",
    "Plan a meeting tomorrow using current news from the web",
    "Plan a meeting tomorrow based on my email",
    "Plan a meeting tomorrow while opening Safari",
    "Schedule a meeting then text Mom",
    "Plan a meeting and check battery",
    "Schedule a private block without checking calendar",
    "Add a private calendar block if Priya agrees",
    'Explain "schedule a meeting tomorrow"',
])
def test_meeting_shortcut_does_not_swallow_constraints_or_other_actions(prompt):
    assert R._meeting_plan(prompt) is None


@pytest.mark.parametrize("group_by,name,child", [
    ("extension", "protected.csv", "CSV"),
    ("debug_date", "debug-2026-10-10.log", "2026-10-10"),
])
def test_grouped_organization_policy_checks_actual_child_target(tmp_path, monkeypatch, group_by, name, child):
    from service.safety import policy
    folder = tmp_path / "source"
    folder.mkdir()
    (folder / name).write_text("synthetic")
    args = {"pattern": "*", "folder": str(folder), "destination": ".", "group_by": group_by}
    operands = dict(policy._derived_path_operands("organize_files", args))
    assert operands["source child"] == str(folder / name)
    assert operands["destination child"] == str(folder / child / name)
    import re
    prior = policy._rules
    monkeypatch.setattr(policy, "_rules", lambda key, default: [re.escape(str(folder / child))] if key == "path_deny" else prior(key, default))
    assert policy._hard_deny("fs_write", args, "organize_files").tier == policy.Tier.DENY


def test_organization_policy_excludes_symlinks_and_unclassified_dates(tmp_path):
    from service.safety import policy
    (tmp_path / "data.txt").write_text("synthetic")
    (tmp_path / "link.log").symlink_to(tmp_path / "data.txt")
    args = {"pattern": "*", "folder": str(tmp_path), "destination": ".", "group_by": "debug_date"}
    operands = list(policy._derived_path_operands("organize_files", args))
    assert set(operands) == {("source child", str(tmp_path / "data.txt")),
                             ("source child", str(tmp_path / "link.log"))}
    assert not any(key == "destination child" for key, _ in operands)


@pytest.mark.parametrize("group_by,name", [
    ("extension", "link.log"), ("debug_date", "debug-2026-10-10.log"),
    ("debug_date", "unclassified.log"),
])
def test_grouped_symlink_source_retains_protected_target_floor(tmp_path, monkeypatch, group_by, name):
    import re
    from service.safety import policy
    source = tmp_path / "source"
    source.mkdir()
    protected = tmp_path / "protected.log"
    protected.write_text("synthetic")
    link = source / name
    link.symlink_to(protected)
    args = {"pattern": "*", "folder": str(source), "destination": ".", "group_by": group_by}
    assert list(policy._derived_path_operands("organize_files", args)) == [("source child", str(link))]
    prior = policy._rules
    monkeypatch.setattr(policy, "_rules", lambda key, default: [re.escape(str(protected))] if key == "path_deny" else prior(key, default))
    assert policy._hard_deny("fs_write", args, "organize_files").tier == policy.Tier.DENY


def test_grouped_destination_symlink_retains_protected_target_floor(tmp_path, monkeypatch):
    import re
    from service.safety import policy
    source = tmp_path / "source"
    source.mkdir()
    (source / "data.csv").write_text("synthetic")
    protected = tmp_path / "protected"
    protected.mkdir()
    (source / "CSV").symlink_to(protected, target_is_directory=True)
    args = {"pattern": "*", "folder": str(source), "destination": ".", "group_by": "extension"}
    prior = policy._rules
    monkeypatch.setattr(policy, "_rules", lambda key, default: [re.escape(str(protected))] if key == "path_deny" else prior(key, default))
    assert policy._hard_deny("fs_write", args, "organize_files").tier == policy.Tier.DENY


def test_route_diagnostic_freezes_synthetic_clock_and_restores_environment():
    import datetime
    import os
    import time
    from scripts.run_workflow20_benchmark import scenario_context
    from service.tools.imessage_tools import contact_names
    prior = os.environ.get("TZ")
    real_datetime = datetime.datetime
    scenario = {"clock": "2026-10-12T10:00:00-07:00", "timezone": "America/Los_Angeles",
                "sources": {"contacts": {"state": "ready", "records": [{"name": "Synthetic Mom"}]}}}
    with scenario_context(scenario):
        from datetime import datetime as late_import
        from service.tools.imessage_tools import contact_names as seeded_names
        assert late_import.now().isoformat() == "2026-10-12T10:00:00"
        assert datetime.date.today().isoformat() == "2026-10-12"
        assert time.time() == real_datetime.fromisoformat(scenario["clock"]).timestamp()
        assert seeded_names() == ["Synthetic Mom"]
    assert os.environ.get("TZ") == prior
    assert datetime.datetime is real_datetime


@pytest.mark.parametrize("prompt", [
    "Send Mom my unread email summary", "Draft Maya my messages and calendar",
    "Delete unread email and messages", "Mark unread messages read",
    "Email Maya my calendar", "Schedule a meeting from my messages",
    "Compare Apple Mail and Calendar features", "Search the web for email and calendar apps",
    "Read my email without messages", "What is email?",
    "When is my dentist appointment on my calendar?", "What did my Mom say in messages?",
    "Read my email and tell Mom my calendar", "Read my messages and put this on my calendar",
    "Read my calendar and email Mom the summary", "Read my email and text Mom the summary",
    "Read my messages and schedule a meeting", "Show unread email and all messages today",
    "How do email and calendar work?",
    "Show my unread email and lock my screen", "Show my unread email and open Safari",
    "Summarize my notes and calendar then play music",
    "Show unread email. Open Safari", "Show unread email while opening Safari",
    "Read my email! Lock my screen", "Read my calendar after opening Maps",
    "Show unread messages about email", "Show unread messages about my calendar",
    "Show unread messages related to email", "Show unread messages mentioning email",
    "Show unread email and show my battery level",
    "Read my notes and reminders and check disk space", "Show unread email, open Safari",
])
def test_nonmatching_or_complex_requests_keep_existing_interpretation(prompt):
    assert personal_read(prompt) is None


@pytest.mark.parametrize("prompt", [
    'Show my messages containing "email and calendar"',
    'Read the note titled "email and calendar"',
])
def test_quoted_words_are_not_extra_personal_sources(prompt):
    from service.workflows.workflow20 import mentioned_sources
    assert "email" not in mentioned_sources(prompt) and "calendar" not in mentioned_sources(prompt)


@pytest.mark.parametrize("prompt", ["Show unread work email summary", "Show unread email summary from Priya"])
def test_qualified_unread_shortcut_does_not_drop_qualifiers(prompt):
    from service.workflows.reads import compile_read
    assert compile_read(prompt) is None


def test_named_unread_does_not_guess_conversation_or_drop_topic():
    decision = asyncio.run(R.route("Show unread messages from Mom about Saturday."))
    assert decision.direct_calls == []
    assert decision.tool_argument_bindings["view_messages"] == {"unread": True}
    assert decision.required_tool_groups == (frozenset({"view_messages", "summarize_messages"}),)


@pytest.mark.parametrize("prompt", [
    "Give me an email summary and my messages", "Give me my email summary and calendar",
    "Read my mail and texts today", "Read email and draft Mom my calendar",
    "Summarize only email without messages", 'Explain the phrase "unread email and messages"',
])
def test_actual_read_entrypoint_never_swallows_compound_request(prompt):
    from service.workflows.reads import compile_read
    assert compile_read(prompt) is None


def test_actual_read_entrypoint_shares_complete_unread_plan():
    from service.workflows.reads import compile_read
    calls, response = compile_read("Show unread email and messages from yesterday")
    assert calls == [("view_emails", {"unread": True, "day": "yesterday"}),
                     ("view_messages", {"unread": True, "day": "yesterday"})]
    assert response == ""


@pytest.mark.parametrize("prompt", [
    "Calendar a 90-minute Friday workshop at 4PM in Building A",
    "Please calendar a 30 minute appointment tomorrow at 2PM",
    "Could you calendar a study block tomorrow at 3PM for 45 minutes",
])
def test_calendar_as_verb_retains_confirmed_creation_route(prompt):
    decision = asyncio.run(R.route(prompt))
    assert "add_calendar_event" in decision.tool_subset
    assert "add_calendar_event" not in decision.forbidden_tools
    assert not decision.direct_calls
    assert not decision.reminder_action


@pytest.mark.parametrize("prompt", [
    "What is on my calendar tomorrow?",
    "Calendar appointments tomorrow",
    "Show my calendar and workshop",
    'Explain "calendar a workshop tomorrow"',
])
def test_calendar_as_verb_does_not_turn_reads_into_writes(prompt):
    assert not R._CALENDAR_WRITE_RE.search(R.mask_quoted(prompt))


@pytest.mark.parametrize("prompt", [
    "Cancel Maya agenda email", "Cancel Maya agenda email but leave Lee weekly email",
    "Please cancel the Mom summary text",
])
def test_named_delivery_cancel_requires_queue_discovery_and_exact_selection(prompt):
    decision = asyncio.run(R.route(prompt))
    assert "list_scheduled_sends" in decision.tool_subset
    assert "cancel_scheduled_send" in decision.tool_subset
    assert decision.tool_argument_bindings["list_scheduled_sends"] == {"status": "pending"}
    assert not decision.direct_calls
    assert decision.resolved_request.startswith(prompt + "\n")
    assert {"send_message", "send_email", "schedule_send"} <= decision.forbidden_tools


@pytest.mark.parametrize("prompt,args", [
    ("What is the weather in San Francisco, California today?", {"location":"San Francisco, California","period":"today"}),
    ("Weather in Santa Clara, CA tomorrow", {"location":"Santa Clara, CA","period":"tomorrow"}),
    ("Check weather for Santa Cruz, California", {"location":"Santa Cruz, California","period":""}),
])
def test_city_weather_uses_verified_provider_without_general_web(prompt,args):
    from service.workflows.reads import compile_read
    assert compile_read(prompt) == ([("get_weather",args)],"")
    decision = asyncio.run(R.route(prompt))
    assert decision.direct_calls == [("get_weather",args)]
    assert not any(name=="web_search" for name,_ in decision.direct_calls)


@pytest.mark.parametrize("prompt,args", [
    ("What time is Budget review this week?", {"calendar_only":True,"query":"Budget review","period":"this week"}),
    ("When does physics quiz two start?", {"calendar_only":True,"query":"physics quiz two","days":60}),
    ("When is my phsyics midterm?", {"calendar_only":True,"query":"phsyics midterm","days":60}),
])
def test_named_event_question_preserves_title_identity_and_bounded_horizon(prompt,args):
    from service.workflows.reads import compile_read
    assert compile_read(prompt) == ([("get_upcoming",args)],"")
    decision = asyncio.run(R.route(prompt))
    assert decision.direct_calls == [("get_upcoming",args)]
    assert "web_search" in decision.forbidden_tools


def test_which_unread_arrived_today_keeps_both_filters():
    decision = asyncio.run(R.route("Which unread emails arrived today?"))
    assert decision.direct_calls == [("view_emails",{"unread":True,"day":"today"})]


@pytest.mark.parametrize("prompt", [
    "What is the weather in Santa Clara and text Mom?",
    "Search the web for weather in Santa Clara",
    "What is the weather in SF without the web?",
    "When is my test from my work account?", "When is my test next semester?",
    "What time is my dentist appointment and lock my screen?",
])
def test_new_typed_read_grammars_decline_unconsumed_constraints(prompt):
    from service.workflows.workflow20 import weather_read,calendar_question
    assert weather_read(prompt) is None and calendar_question(prompt) is None


@pytest.mark.parametrize('suffix', ['without reminders', 'skip reminders',
    'excluding reminders', 'leave out reminders', 'do not include reminders'])
def test_calendar_exclusion_synonyms_remain_exact_verified_reads(suffix):
    prompt = f"Show my calendar this week {suffix}"
    decision = asyncio.run(R.route(prompt))
    assert decision.direct_calls == [('get_upcoming', {'period':'this week','calendar_only':True})]
    assert decision.verified_results_only
    assert decision.tool_subset == ['get_upcoming']


def test_generic_calendar_keeps_established_scope_and_context_isolation():
    from service import main
    prompt = "what is on my calendar"
    decision = asyncio.run(R.route(prompt))
    assert decision.direct_calls == [('get_upcoming', {'days':60})]
    assert main._current_schedule_source_route(decision, prompt)
    assert not decision.narration_after


@pytest.mark.parametrize('day, expected', [
    ('2026-10-09', '2026-10-10..2026-10-11'),
    ('2026-10-10', '2026-10-10..2026-10-11'),
    ('2026-10-11', '2026-10-10..2026-10-11'),
    ('2026-10-12', '2026-10-17..2026-10-18'),
    ('2026-10-31', '2026-10-31..2026-11-01'),
    ('2026-12-31', '2027-01-02..2027-01-03'),
])
def test_weekend_calendar_alias_has_executable_exact_private_range(monkeypatch, day, expected):
    from datetime import date, datetime
    from service.workflows import reads
    from service.tools import timeranges
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(day + 'T12:00:00')
    monkeypatch.setattr(reads, 'datetime', Clock)
    prompt = 'is there anything on my cal this weekend'
    args = reads._calendar_read_args(prompt, '', date.fromisoformat(day))
    assert args == {'period': expected}
    from datetime import timedelta
    start, end, _ = timeranges.resolve_span(expected)
    first, last = expected.split('..')
    assert start == datetime.fromisoformat(first).timestamp()
    assert end == (datetime.fromisoformat(last) + timedelta(days=1)).timestamp()
    decision = asyncio.run(R.route(prompt))
    assert decision.direct_calls == [('get_upcoming', args)]
    assert decision.tool_subset == ['get_upcoming']
    assert decision.verified_results_only
    assert {'web_search', 'web_fetch', 'http_request'} <= decision.forbidden_tools


@pytest.mark.parametrize('prompt', [
    'is there anything on my cal this weekend and text Mom',
    'is there anything on my cal this weekend about physics',
    'is there anything on my cal next weekend',
    'is there anything on my cal this weekend then open Maps',
])
def test_weekend_calendar_parser_declines_unrepresented_constraints(prompt):
    from service.workflows.reads import _calendar_read_args
    assert _calendar_read_args(prompt, '') is None


def test_public_weather_does_not_use_personal_data_voice():
    decision = asyncio.run(R.route('What is the weather in Tokyo?'))
    assert decision.direct_calls == [('get_weather', {'location':'Tokyo','period':''})]
    assert decision.tool_subset == ['get_weather']
    assert not decision.light_read
