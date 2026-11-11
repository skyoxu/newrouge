"""Deterministic synthetic stdio transport; no provider, credentials or network."""
import json
import os
from pathlib import Path
import sys

response = Path(sys.argv[1]).read_text(encoding="utf-8")
fixture_effort = os.environ.get("NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT", "medium")
if fixture_effort not in ("medium", "high"):
    raise ValueError("Unsupported synthetic reasoning fixture")
thread, turn = "offline-thread", "offline-turn"


def emit(value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)


for line in sys.stdin:
    request = json.loads(line)
    identifier, method = request.get("id"), request["method"]
    if method == "initialize":
        emit({"id": identifier, "result": {"userAgent": "story25-synthetic-transport"}})
    elif method == "mcpServerStatus/list":
        emit({"id": identifier, "result": {"data": [], "nextCursor": None}})
    elif method == "thread/start":
        cwd = request["params"]["cwd"]
        emit({"id": identifier, "result": {"model": "fixture-model", "modelProvider": "fixture",
            "cwd": cwd, "reasoningEffort": fixture_effort, "sandbox": {"type": "readOnly"},
            "thread": {"id": thread, "ephemeral": True, "cwd": cwd, "turns": [],
                       "model": "fixture-model", "modelProvider": "fixture"}}})
    elif method == "turn/start":
        emit({"id": identifier, "result": {"turn": {"id": turn, "status": "inProgress", "items": []}}})
        emit({"method": "turn/started", "params": {"threadId": thread,
            "turn": {"id": turn, "status": "inProgress"}}})
        item = {"type": "agentMessage", "id": "fixture-output", "phase": "final_answer", "text": response}
        emit({"method": "item/completed", "params": {"threadId": thread, "turnId": turn, "item": item}})
        emit({"method": "turn/completed", "params": {"threadId": thread,
            "turn": {"id": turn, "status": "completed", "items": [item], "error": None}}})
