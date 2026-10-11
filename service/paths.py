"""The single place ~/.moe is computed.

WISP_HOME redirects Wisp's OWN state (commitments, sessions, facts, caches,
grants, skills, config overlay) somewhere else — the sandbox uses it to get a
completely separate world without touching the user's real data.

Deliberately NOT $HOME: overriding HOME would also move ~/.omlx/settings.json
and ~/.omlx/model_settings.json (service/config/__init__.py), which is where
the model roster and the user's starred favorites live — the backend would
boot with no models.

Resolved once at import, matching the import-time constants it feeds.
"""
from __future__ import annotations

import os
from pathlib import Path


def moe_dir() -> Path:
    override = os.environ.get("WISP_HOME")
    return Path(override).expanduser() if override else Path.home() / ".moe"


MOE_DIR = moe_dir()


# The Aria founder demo (WISP_FOUNDER_DEMO=1) answers from fictional fixtures
# and learns a synthetic persona. In the Intel v5 build it runs against the
# same WISP_HOME as real mode (the app switches between them at runtime), so
# the state those modes WRITE — conversations, remembered facts, commitments
# and assistant events, scheduled sends, standing grants, the brief ledger and
# behavior learning — lives in its own subdirectory while the demo runs.
# Read-only mirrors of the user's real sources (the Mail/Messages/Notes caches,
# config overlay) stay shared. Resolved once at import, like MOE_DIR.
DEMO_STATE_SUBDIR = "aria-demo"


def state_dir() -> Path:
    base = moe_dir()
    if os.environ.get("WISP_FOUNDER_DEMO") == "1":
        return base / DEMO_STATE_SUBDIR
    return base


STATE_DIR = state_dir()
if STATE_DIR != MOE_DIR:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
