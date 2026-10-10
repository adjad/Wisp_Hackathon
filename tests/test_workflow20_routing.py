"""Private-source constraints; routing only, no tools or models execute."""
import asyncio

import pytest

import service.tools
from service.router import router as R
from service.workflows.workflow20 import personal_read


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
