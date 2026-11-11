"""Synthetic App Server protocol; no model, credentials, or client state access."""
from pathlib import Path
import json
import base64
from _codex_app_server import thread_config, restricted_catalog, digest, command

def protocol(cwd, prompt="complete input", output='{"answer":"ok"}', schema=None,
             model="fixture-model", provider="fixture"):
    config = thread_config()
    start = {"cwd": str(cwd), "ephemeral": True, "sandbox": "read-only",
        "approvalPolicy": "untrusted", "dynamicTools": [], "environments": [],
        "allowProviderModelFallback": False, "config": config}
    turn = {"threadId": "fresh-thread", "input": [{"type": "text", "text": prompt}]}
    if schema is not None:
        turn["outputSchema"] = schema
    item = {"type": "agentMessage", "id": "answer", "text": output, "phase": "final_answer"}
    messages = [
        ("client", {"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "fixture", "version": "1.0"}}}),
        ("server", {"id": 1, "result": {"userAgent": "fixture"}}),
        ("client", {"method": "initialized"}),
        ("client", {"id": 0, "method": "mcpServerStatus/list", "params": {}}),
        ("server", {"id": 0, "result": {"data": [], "nextCursor": None}}),
        ("client", {"id": 2, "method": "thread/start", "params": start}),
        ("server", {"id": 2, "result": {"cwd": str(cwd), "model": model, "modelProvider": provider,
            "reasoningEffort": "high", "sandbox": {"type": "readOnly"},
            "thread": {"id": "fresh-thread", "ephemeral": True, "turns": [],
                       "cwd": str(cwd), "model": model, "modelProvider": provider}}}),
        ("client", {"id": 3, "method": "mcpServerStatus/list", "params": {"threadId": "fresh-thread"}}),
        ("server", {"id": 3, "result": {"data": [], "nextCursor": None}}),
        ("client", {"id": 4, "method": "turn/start", "params": turn}),
        ("server", {"id": 4, "result": {"turn": {"id": "fresh-turn", "status": "inProgress", "items": []}}}),
        ("server", {"method": "turn/started", "params": {"threadId": "fresh-thread", "turn": {"id": "fresh-turn", "status": "inProgress"}}}),
        ("server", {"method": "item/completed", "params": {"threadId": "fresh-thread", "turnId": "fresh-turn", "item": item}}),
        ("server", {"method": "turn/completed", "params": {"threadId": "fresh-thread", "turn": {"id": "fresh-turn", "status": "completed", "items": [item], "error": None}}}),
    ]
    source = json.dumps({"models":[{"slug":model}]}).encode("utf-8")
    catalog = Path(cwd) / "fixture-catalog.json"
    launch = {"direction":"host","message":{"event":"launch","executable":"fixture",
        "command":command("fixture",catalog),"catalog_path":str(catalog),
        "source_catalog_base64":base64.b64encode(source).decode("ascii"),
        "source_catalog_sha256":digest(source),"restricted_catalog_sha256":digest(restricted_catalog(source))}}
    return [launch, *[{"direction": d, "message": m} for d, m in messages]]

def encoded(records):
    return ("\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records) + "\n").encode("utf-8")

