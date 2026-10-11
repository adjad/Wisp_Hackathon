"""Process-pinned, opt-in Intel/GX10 demo policy; never resolves credentials.

The launcher supplies WISP_REMOTE_ONLY=1 plus the exact nonsecret profile in
inference.remote_only. Settings cannot change this snapshot after startup.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from functools import lru_cache
import json
import math
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from service.config.endpoints import Target

_FORCED_MODE = os.environ.get("WISP_REMOTE_ONLY")
_READ_TOOLS = frozenset({"get_upcoming", "get_past_events", "search_reminders",
                         "view_emails", "summarize_emails", "view_messages",
                         "summarize_messages"})
_BEHAVIOR_TOOLS = frozenset({"describe_me", "predict_my_day", "my_patterns", "correct_pattern"})


def _refuse(message: str):
    from service.config.endpoints import EndpointConfigurationError
    raise EndpointConfigurationError(message)


@dataclass(frozen=True)
class RemoteOnlyProfile:
    enabled: bool = True
    endpoint_name: str = "gx10_demo"
    base_url: str = "https://6wjp.tail4cc204.ts.net"
    provider: str = "openai-compatible"
    api_prefix: str = "/v1"
    credential_ref: str = "keychain:gx10demo"
    model_id: str = "qwen3.6:35b"
    context_window: int = 8000
    max_tokens: int = 4096
    readiness_timeout: float = 5.0
    request_bytes: int = 131072
    messages: int = 32
    aggregate_bytes: int = 24000
    tools: int = 32
    response_bytes: int = 4194304
    generation_roles: tuple[str, ...] = ("fast", "router", "agent", "general", "reasoning", "coding")
    tool_capabilities: tuple[str, ...] = ("tools",)

    def fit_output(self, value: int) -> int:
        if type(value) is not int or value <= 0:
            _refuse("Remote output budget must be a positive integer")
        return min(value, self.max_tokens)

    def validate_payload(self, payload: dict) -> None:
        allowed = {"model", "messages", "max_tokens", "stream", "temperature", "tools", "tool_choice"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            _refuse("Unsupported remote-only inference options")
        if payload.get("model") != self.model_id or type(payload.get("stream")) is not bool:
            _refuse("Remote-only inference requires its exact model and stream flag")
        value = payload.get("max_tokens")
        if type(value) is not int or not 1 <= value <= self.max_tokens:
            _refuse("Remote-only output budget exceeds the gateway contract")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not 1 <= len(messages) <= self.messages:
            _refuse("Remote-only message budget exceeded")
        for row in messages:
            if not isinstance(row, dict) or not isinstance(row.get("role"), str):
                _refuse("Invalid remote-only message")
            if row["role"] not in {"system", "user", "assistant", "tool"}:
                _refuse("Unsupported remote-only message role")
            content = row.get("content")
            if not isinstance(content, str) and not (row["role"] == "assistant" and row.get("tool_calls") and content is None):
                _refuse("Remote-only inference accepts text and tool transcripts only")
        tools = payload.get("tools")
        if tools is not None and (not isinstance(tools, list) or not 1 <= len(tools) <= self.tools):
            _refuse("Remote-only tool schema budget exceeded")
        if "temperature" in payload:
            t = payload["temperature"]
            if type(t) not in {int, float}:
                _refuse("Invalid remote-only temperature")
            try:
                valid = math.isfinite(t) and 0 <= t <= 2
            except OverflowError:
                valid = False
            if not valid:
                _refuse("Invalid remote-only temperature")
        try:
            wire = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            aggregate = json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False,
                                   separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, RecursionError, UnicodeError):
            _refuse("Invalid bounded remote-only payload")
        if len(wire) > self.request_bytes or len(aggregate) > self.aggregate_bytes:
            _refuse("Remote-only transcript/schema byte budget exceeded")


@lru_cache(maxsize=1)
def remote_only_profile() -> RemoteOnlyProfile | None:
    """Validate one startup snapshot; deliberately not cleared by Settings."""
    if _FORCED_MODE not in {None, "1"}:
        _refuse("Invalid remote-only launch mode")
    from service.config import models_config
    config = models_config()
    inference = config.get("inference", {})
    if not isinstance(inference, dict):
        _refuse("Invalid inference configuration")
    raw = inference.get("remote_only")
    if raw is None and _FORCED_MODE is None:
        return None
    expected = RemoteOnlyProfile()
    fields = asdict(expected)
    if not isinstance(raw, dict) or set(raw) != set(fields):
        _refuse("Remote-only launch requires the complete fixed profile")
    normalized = dict(raw)
    for key in ("generation_roles", "tool_capabilities"):
        if not isinstance(raw[key], (list, tuple)):
            _refuse("Invalid remote-only role/capability metadata")
        normalized[key] = tuple(raw[key])
    for key, value in fields.items():
        observed = normalized[key]
        if (key == "readiness_timeout" and type(observed) in {int, float}):
            good = observed == value
        else:
            good = type(observed) is type(value) and observed == value
        if not good:
            _refuse("Remote-only profile differs from the approved fixed contract")
    return expected


def require_generation_role(role: str) -> None:
    profile = remote_only_profile()
    if profile is not None and (not isinstance(role, str) or role not in profile.generation_roles):
        _refuse("This role is unavailable in the remote-only demo")


def remote_default_target(role: str = "fast") -> Target:
    profile = remote_only_profile()
    if profile is None:
        _refuse("Remote-only profile is not enabled")
    require_generation_role(role)
    from service.config.endpoints import Target, endpoint_from_config
    ep = endpoint_from_config(profile.endpoint_name, {
        "base_url": profile.base_url, "credential_ref": profile.credential_ref,
        "managed": False, "provider": profile.provider, "api_prefix": profile.api_prefix,
        "readiness_timeout": profile.readiness_timeout,
    })
    return Target(role, ep, profile.model_id, profile="intel-gx10-hours-demo-v1",
                  context_window=profile.context_window, capabilities=profile.tool_capabilities)


def validate_remote_target(target: Target) -> None:
    if remote_only_profile() is None:
        return
    from service.config.endpoints import Target
    if not isinstance(target, Target):
        _refuse("Remote-only inference requires an explicit bound target")
    require_generation_role(target.role)
    if target != remote_default_target(target.role):
        _refuse("Remote-only inference refuses alternate targets or credentials")


def require_local_models_disabled(operation: str) -> None:
    if remote_only_profile() is not None:
        _refuse(f"{operation} is unavailable in the remote-only demo")


def remote_demo_tool_allowed(tool_name: str | None) -> bool:
    if not isinstance(tool_name, str):
        return False
    if tool_name in _READ_TOOLS:
        return True
    # Behavior-learning tools read (or, for correct_pattern, edit) only Wisp's
    # own learned profile — never a native source — and they are the point of
    # the founder demo. Allowed only while behavior learning is on, so the
    # pinned read set (_READ_TOOLS) is unchanged. Their schemas are small; the
    # demo routes offer them alone (see router._behavior_request).
    if tool_name in _BEHAVIOR_TOOLS:
        # Mirrors service.assistant.behavior_runtime.enabled() without importing
        # the assistant package (which opens stores) from this policy module.
        return os.environ.get("WISP_BEHAVIOR") == "1" or os.environ.get("WISP_FOUNDER_DEMO") == "1"
    from service.demo.founder import enabled
    return tool_name in {"search_notes", "lookup_contact", "list_contacts"} and enabled()
