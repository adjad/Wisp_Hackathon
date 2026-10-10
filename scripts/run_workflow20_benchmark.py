#!/usr/bin/env python3
"""Validate corpus, diagnose actual offline routing, or grade supplied observations.

No installed application, model inference, personal readers or effect tools run.
Routing is a tool-availability diagnostic; it is never answer accuracy.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.workflow20.contract import aggregate, grade, load_corpus, subset


def forbidden(*args, **kwargs):
    raise AssertionError("Workflow20 offline boundary: network/process/credential/effect forbidden")


async def diagnose_routes(corpus):
    if "service.paths" in sys.modules:
        raise RuntimeError("Run in a fresh process; Wisp state imported before isolation")
    rows = []
    with tempfile.TemporaryDirectory(prefix="wisp-workflow20-") as scratch, ExitStack() as stack:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("WISP_", "WISPAIR_"))}
        env.update(WISP_HOME=scratch, WISPAIR_HOME=str(Path(scratch) / "air"), PYTHONDONTWRITEBYTECODE="1")
        stack.enter_context(patch.dict(os.environ, env, clear=True))
        stack.enter_context(patch("socket.socket.connect", forbidden))
        stack.enter_context(patch("socket.socket.connect_ex", forbidden))
        stack.enter_context(patch("socket.socket.sendto", forbidden))
        stack.enter_context(patch("subprocess.Popen", forbidden))
        from service import config
        from service.config import credentials, endpoints
        stack.enter_context(patch.object(config, "OMLX_SETTINGS", Path(scratch) / "absent-settings.json"))
        stack.enter_context(patch.object(config, "OMLX_MODEL_SETTINGS", Path(scratch) / "absent-models.json"))
        stack.enter_context(patch.object(config, "omlx_api_key", forbidden))
        stack.enter_context(patch.object(config, "_credential", forbidden))
        stack.enter_context(patch.object(credentials, "resolve", forbidden))
        stack.enter_context(patch.object(endpoints.Endpoint, "api_key", forbidden))
        import service.tools
        from service.tools.registry import REGISTRY
        stack.enter_context(patch.dict(REGISTRY, {name: replace(tool, func=forbidden) for name, tool in REGISTRY.items()}))
        from service.router import router
        if (config.models_config().get("tool_retrieval") or {}).get("provider") != "lexical":
            raise RuntimeError("Offline route diagnostic requires packaged lexical retrieval")
        for case in corpus["cases"]:
            history = case["turns"][:-1]
            users = [t["text"] for t in history if t["role"] == "user"]
            assistants = [t["text"] for t in history if t["role"] == "assistant"]
            started = time.perf_counter()
            try:
                decision = await router.route(case["turns"][-1]["text"], last_user=users[-1] if users else None,
                    recent_users=users, last_assistant=assistants[-1] if assistants else None)
                elapsed = (time.perf_counter() - started) * 1000
                offered = set(decision.tool_subset or [])
                direct = [{"name": name, "args": args} for name, args in decision.direct_calls]
                names = offered | {call["name"] for call in direct}
                expect = case["expect"]
                missing = [group for group in expect["required_tool_groups"] if not names & set(group)]
                bound = [{"name": name, "args": args} for name, args in decision.tool_argument_bindings.items()]
                missing_args = [name for name, args in expect["arguments"].items()
                                if not any(c["name"] == name and subset(args, c["args"]) for c in direct + bound)]
                forbidden_direct = sorted({c["name"] for c in direct} & set(expect["forbidden_tools"]))
                rows.append({"case_id": case["id"], "family": case["family"], "route_ms": elapsed,
                             "diagnostic_pass": not missing and not missing_args and not forbidden_direct,
                             "offered_tools": sorted(offered), "direct_calls": direct,
                             "missing_groups": missing, "missing_argument_bindings": missing_args,
                             "forbidden_direct_calls": forbidden_direct, "decision": decision.as_dict(),
                             "semantic_outcome": "NOT_RUN"})
            except Exception as exc:
                rows.append({"case_id": case["id"], "family": case["family"], "diagnostic_pass": False,
                             "error": f"{type(exc).__name__}: {exc}", "semantic_outcome": "NOT_RUN"})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("validate", "routes", "grade"), default="validate")
    parser.add_argument("--cases", type=Path, default=ROOT / "tests/workflow20/cases")
    parser.add_argument("--observations", type=Path, help="JSON list of adapter observations; grade mode only")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus = load_corpus(args.cases)
    sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True)
    report = {"schema_version": 1, "mode": args.mode, "source_sha": sha, "source_dirty": bool(dirty),
              "fixture_sha256": corpus["sha256"], "coverage": corpus["families"],
              "model_inference": "NOT_RUN", "model_latency": None, "platform": "Mac offline Python"}
    exit_code = 0
    if args.mode == "routes":
        report["rows"] = asyncio.run(diagnose_routes(corpus))
        report["routing_diagnostic_only"] = True
        report["semantic_outcome"] = "NOT_RUN"
        exit_code = int(any(not row["diagnostic_pass"] for row in report["rows"]))
    elif args.mode == "grade":
        if not args.observations:
            parser.error("grade mode requires --observations")
        raw = args.observations.read_bytes()
        observations = json.loads(raw)
        if not isinstance(observations, list):
            parser.error("observations must be a JSON list")
        indexed = {}
        known = {case["id"] for case in corpus["cases"]}
        for observation in observations:
            cid = observation["case_id"]
            if cid in indexed or cid not in known:
                parser.error(f"duplicate/unknown observation: {cid}")
            indexed[cid] = observation
        rows = [grade(c, corpus["scenarios"][c["scenario"]], indexed[c["id"]])
                for c in corpus["cases"] if c["id"] in indexed]
        report.update(rows=rows, families=aggregate(rows), observations_sha256=hashlib.sha256(raw).hexdigest(),
                      unrun=[c["id"] for c in corpus["cases"] if c["id"] not in indexed],
                      observation_execution="External supplied observations; provenance must be independently reviewed")
        exit_code = int(bool(report["unrun"]) or any(not row["outcome_pass"] for row in rows))
    else:
        report["semantic_outcome"] = "NOT_RUN"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"mode": args.mode, "cases": len(corpus["cases"]), "output": str(args.output), "exit_code": exit_code}))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
