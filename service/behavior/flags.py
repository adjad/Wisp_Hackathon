"""Behavior-learning on/off switch, readable without importing anything else.

Callers on hot or tightly stubbed paths (main.lifespan in the remote-only
build, the router, prompt assembly, the remote policy) check this BEFORE
importing ``service.assistant.behavior_runtime``, whose import chain opens
stores and pulls in modules those paths must not load while behavior learning
is off. Pure stdlib; ``behavior_runtime.enabled()`` delegates here.
"""
from __future__ import annotations

import os


def founder_demo_env() -> bool:
    return os.environ.get("WISP_FOUNDER_DEMO") == "1"


def env_enabled() -> bool:
    """On with ``WISP_BEHAVIOR=1`` or automatically in the founder demo build."""
    return os.environ.get("WISP_BEHAVIOR") == "1" or founder_demo_env()
