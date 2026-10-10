"""Pure personal-source read constraints shared by entry points.

This module gathers no data and makes no action decision. Complex constraints
remain with model selection; only complete bounded unread requests run directly.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from service.utterance_shape import mask_quoted


_SOURCE = {
    "email": r"\b(?:e-?mails?|mail|inbox)\b",
    "messages": r"\b(?:messages?|texts?|imessages?|mesages)\b",
    "calendar": r"\b(?:calendar|calender|schedule|meetings?|events?|commitments?)\b",
    "notes": r"\bnotes?\b",
    "reminders": r"\breminders?\b",
}
_TOOLS = {"email": ("view_emails", "summarize_emails"),
          "messages": ("view_messages", "summarize_messages"),
          "calendar": ("get_upcoming",), "notes": ("search_notes",),
          "reminders": ("search_reminders",)}
_ACTION = re.compile(r"\b(?:send|text|email|draft|reply|forward|schedule|create|add|delete|remove|mark|archive|unsubscribe|cancel|move|update|remind|save|write)\b", re.I)
_PUBLIC = re.compile(r"\b(?:news|web|internet|public|product|app|apps|settings|tutorial|install|download|features?|versus|vs|API|security|encryption)\b", re.I)
_EXCLUSION = re.compile(r"\b(?:without|skip|except|exclude|excluding|not|never|don['’]t|do not)\b", re.I)
_READ = re.compile(r"\b(?:what|show|check|read|list|tell\s+me|give\s+me|summari[sz]e|summary|summaries|overview|recap|brief|briefing|digest|catch|happening|priorities|focus|work)\b", re.I)


@dataclass(frozen=True)
class PersonalRead:
    sources: tuple[str, ...]
    tools: tuple[str, ...]
    groups: tuple[frozenset[str], ...]
    bindings: dict[str, dict]
    direct_calls: tuple[tuple[str, dict], ...] = ()


def mentioned_sources(text: str) -> tuple[str, ...]:
    source = mask_quoted(text)
    return tuple(name for name, pattern in _SOURCE.items() if re.search(pattern, source, re.I))


def personal_read(text: str) -> PersonalRead | None:
    source = mask_quoted(text).strip()
    sources = mentioned_sources(source)
    if not sources or not _READ.search(source) or _PUBLIC.search(source) or _EXCLUSION.search(source):
        return None
    # Nouns such as email/schedule/text may appear in a read; action verb
    # positions (or independent effect verbs anywhere) must reach normal policy.
    actions = set(m.group().casefold() for m in _ACTION.finditer(source))
    if actions - {"email", "text", "schedule"}:
        return None
    if re.match(r"(?:please\s+)?(?:email|text|schedule)\b", source, re.I):
        return None
    if re.search(r"(?:\b(?:and|then|also)\b|;)\s+(?:email|text|schedule)\b", source, re.I):
        return None
    if re.search(r"\b(?:tell|inform)\s+(?!me\b|us\b)|\bput\s+(?:it|this|that)\b", source, re.I):
        return None
    # A separate imperative must be understood as another read. Unknown
    # clauses belong to normal interpretation, including device/app actions.
    for clause in re.split(r"\b(?:and|then|also)\b|;", source, flags=re.I)[1:]:
        if not re.match(r"\s*(?:my|our|the|all|only|unread|today|yesterday|tomorrow|recent|current|e-?mails?|mail|inbox|messages?|texts?|imessages?|calendar|calender|schedule|meetings?|events?|notes?|reminders?|show|check|read|list|summari[sz]e|recap|tell\s+me|give\s+me)\b", clause, re.I):
            return None
    unread = bool(re.search(r"\bunread\b|\bhaven['’]t\s+(?:read|opened)\b", source, re.I))
    if not unread and len(sources) < 2:
        return None
    personal = bool(re.search(r"\b(?:my|me|our|I)\b", source, re.I))
    across = bool(re.search(r"\b(?:across|overview|recap|summary|summaries|summari[sz]e)\b", source, re.I))
    if not (personal or unread or (len(sources) > 1 and across)):
        return None
    if unread and len(sources) > 1 and re.search(r"\b(?:all|read)\s+(?:my\s+)?(?:messages?|texts?|e-?mails?|mail)\b", source, re.I):
        return None
    tools = tuple(tool for name in sources for tool in _TOOLS[name])
    bindings = {}
    if unread:
        for name in sources:
            if name in {"email", "messages"}:
                bindings.update({tool: {"unread": True} for tool in _TOOLS[name]})
    # Only exact, fully consumed source-only unread shapes can bypass selection.
    # Named people, accounts, topics, exclusions, ranges and numeric dates keep
    # their full request and reach model/identity resolution.
    direct = ()
    if unread and set(sources) <= {"email", "messages"}:
        residue = text.casefold()
        for pattern in _SOURCE.values():
            residue = re.sub(pattern, " ", residue, flags=re.I)
        residue = re.sub(r"\b(?:please|can|could|you|give|show|check|read|list|summarize|summarise|summary|summaries|recap|catch|me|up|on|what|do|does|did|i|have|my|our|the|all|only|unread|and|across|in|of|from|today|yesterday)\b", " ", residue)
        if not re.search(r"[^\s,.?!'’]", residue):
            days = re.findall(r"\b(?:today|yesterday)\b", source, re.I)
            if len(set(word.casefold() for word in days)) <= 1:
                calls = []
                for name in sources:
                    tool = "view_emails" if name == "email" else "view_messages"
                    args = {"unread": True}
                    if days:
                        args["day"] = days[0].casefold()
                    calls.append((tool, args))
                    bindings[tool] = dict(args)
                direct = tuple(calls)
    return PersonalRead(sources, tools, tuple(frozenset(_TOOLS[name]) for name in sources), bindings, direct)
