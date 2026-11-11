"""One ephemeral official App Server turn; runtime configuration is not provider attestation."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

SOURCE = "codex-app-server-runtime-configuration"
POLICY = "official-codex-runtime-bound.v1"
MAX_TRANSCRIPT_BYTES = 32 * 1024 * 1024

# Only capability restrictions: no credential, provider, network, or sandbox bypass settings.
RESTRICTIONS = {
    "mcp_servers": {},
    "agents.enabled": False,
    "tools.update_plan.enabled": False,
    "tools.experimental_request_user_input.enabled": False,
    "web_search": "disabled",
}
DISABLED = (
    "shell_tool", "unified_exec", "unified_exec_tty", "shell_snapshot",
    "apps", "plugins", "remote_plugin", "browser_use", "browser_use_external",
    "computer_use", "image_generation", "in_app_browser", "view_image",
    "multi_agent", "multi_agent_v2", "code_mode", "code_mode_host",
    "default_mode_request_user_input", "goals", "sleep_tool", "tool_suggest",
    "auth_elicitation", "skill_search", "in_app_local_automation",
    "in_app_chat", "in_app_dictation", "in_app_updates", "realtime_conversation",
    "deferred_executor", "send_message_to_user_async", "request_permissions_tool",
    "token_budget", "current_time_reminder",
)
TOOL_CATALOG_OVERRIDES = {"tool_mode": "direct", "shell_type": "disabled",
    "apply_patch_tool_type": None, "experimental_supported_tools": [], "multi_agent_version": None}

def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()

def command(executable: str, catalog_path: Path | None = None) -> list[str]:
    result = [executable]
    for name in DISABLED:
        result.extend(["--disable", name])
    for name, value in RESTRICTIONS.items():
        result.extend(["-c", name + "=" + json.dumps(value, separators=(",", ":"))])
    if catalog_path is not None:
        result.extend(["-c", "model_catalog_json=" + json.dumps(str(catalog_path))])
    return [*result, "app-server", "--stdio"]


def restricted_catalog(cache_raw: bytes) -> bytes:
    """Preserve model metadata/instructions; restrict only client tool capabilities."""
    cache = json.loads(cache_raw)
    models = cache.get("models")
    _require(isinstance(models, list) and bool(models), "model_catalog_unavailable")
    result = copy.deepcopy(models)
    for model in result:
        _require(isinstance(model, dict) and isinstance(model.get("slug"), str), "invalid_model_catalog")
        model.update(TOOL_CATALOG_OVERRIDES)
    return json.dumps({"models": result}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError("codex_app_server_" + reason)


def requested_reasoning_effort():
    value = os.environ.get("NEWROGUE_CODEX_REASONING_EFFORT")
    _require(value in (None, "high"), "unsupported_requested_reasoning_effort")
    return value


def check_reasoning_effort(config, runtime):
    if "model_reasoning_effort" in config:
        requested = config["model_reasoning_effort"]
        _require(requested in ("low", "high"), "unsupported_requested_reasoning_effort")
        _require(runtime.get("reasoningEffort") == requested, "requested_reasoning_effort_mismatch")


def thread_config(mcp_names=(), *, reasoning_effort=None) -> dict:
    """RPC config is a nested object; CLI -c overrides use dotted TOML keys."""
    flat = {**RESTRICTIONS, **{"features." + name: False for name in DISABLED},
            **{"mcp_servers." + name + ".enabled": False for name in mcp_names}}
    result = {}
    for key, value in flat.items():
        target = result
        parts = key.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value.copy() if isinstance(value, dict) else value
    if reasoning_effort is not None:
        _require(reasoning_effort == "high", "unsupported_requested_reasoning_effort")
        result["model_reasoning_effort"] = reasoning_effort
    return result


def setting(config: dict, key: str):
    value = config
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value

def _identity(value: object) -> str:
    _require(isinstance(value, str) and bool(value) and not any(c.isspace() for c in value)
             and value.casefold() not in {"auto", "default", "environment-default", "codex-cli-default"},
             "runtime_identity_missing")
    return value

def _item(item: dict) -> None:
    _require(isinstance(item, dict) and item.get("type") in {
        "userMessage", "agentMessage", "reasoning", "contextCompaction",
    }, "model_tools_observed")


def _no_mcp_tools(inventory: dict) -> None:
    _require(isinstance(inventory.get("data"), list) and not inventory.get("nextCursor")
             and all(server.get("runtimeStatus") == "disabled" and not server.get("tools")
                     and not server.get("resources") and not server.get("resourceTemplates")
                     for server in inventory["data"]), "mcp_tools_available")

def replay(raw: bytes, *, prompt: str | None = None, schema: dict | None = None) -> tuple[str, dict]:
    try:
        return _replay(raw, prompt=prompt, schema=schema)
    except (KeyError, TypeError, AttributeError, UnicodeError) as error:
        raise ValueError("codex_app_server_invalid_transcript") from error


def _replay(raw: bytes, *, prompt: str | None = None, schema: dict | None = None) -> tuple[str, dict]:
    """Revalidate captured host I/O. Assistant text is never parsed as protocol evidence."""
    _require(0 < len(raw) <= MAX_TRANSCRIPT_BYTES, "invalid_transcript_size")
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
    client, responses, events, launch = {}, {}, [], []
    request_order, initialized = [], 0
    for record in records:
        _require(set(record) == {"direction", "message"} and isinstance(record["message"], dict),
                 "invalid_transcript")
        message = record["message"]
        if record["direction"] == "host":
            _require(message.get("event") == "launch", "invalid_host_record")
            launch.append(message)
        elif record["direction"] == "client":
            if "id" in message:
                _require(message["id"] not in client, "duplicate_request")
                client[message["id"]] = message
                request_order.append(message["id"])
            else:
                _require(message == {"method": "initialized"}, "unexpected_client_notification")
                _require(1 in responses and not initialized, "invalid_initialization_order")
                initialized += 1
        elif record["direction"] == "server":
            _require(not ("id" in message and "method" in message), "server_tool_or_auth_request")
            if "id" in message:
                _require("error" not in message and "result" in message, "rpc_failed")
                _require(message["id"] in client and message["id"] not in responses, "response_id_mismatch")
                responses[message["id"]] = message["result"]
            else:
                if message.get("method", "").startswith(("item/", "turn/", "model/")):
                    _require(4 in client and 2 in responses, "notification_before_turn_request")
                events.append(message)
        else:
            raise ValueError("codex_app_server_invalid_direction")
    _require(set(client) == {0, 1, 2, 3, 4} and set(responses) == set(client), "incomplete_rpc")
    _require(request_order == [1, 0, 2, 3, 4] and initialized == 1, "invalid_rpc_order")
    _require(len(launch) == 1, "missing_tool_catalog_proof")
    source_catalog = base64.b64decode(launch[0]["source_catalog_base64"], validate=True)
    catalog = restricted_catalog(source_catalog)
    _require(launch[0].get("source_catalog_sha256") == digest(source_catalog)
             and launch[0].get("restricted_catalog_sha256") == digest(catalog)
             and launch[0].get("command") == command(launch[0]["executable"], Path(launch[0]["catalog_path"])),
             "tool_catalog_mismatch")
    _require(client[1]["method"] == "initialize", "missing_initialize")
    _require(client[0]["method"] == "mcpServerStatus/list"
             and not client[0]["params"].get("threadId")
             and not responses[0].get("nextCursor"), "incomplete_mcp_preflight")
    start = client[2]
    _require(start["method"] == "thread/start", "missing_thread_start")
    params = start["params"]
    _require(set(params) <= {"cwd", "ephemeral", "sandbox", "approvalPolicy", "allowProviderModelFallback",
                            "dynamicTools", "environments", "config", "model"}
             and params.get("approvalPolicy") == "untrusted"
             and params.get("ephemeral") is True and params.get("dynamicTools") == []
             and params.get("sandbox") == "read-only" and params.get("environments") == []
             and params.get("allowProviderModelFallback") is False,
             "unsafe_thread_settings")
    for key, value in RESTRICTIONS.items():
        if key != "mcp_servers":
            _require(setting(params.get("config", {}), key) == value, "missing_tool_restriction")
    _require(all(setting(params.get("config", {}), "features." + name) is False for name in DISABLED),
             "missing_tool_restriction")
    for server in responses[0]["data"]:
        _require(isinstance(server.get("name"), str)
                 and setting(params["config"], "mcp_servers." + server["name"] + ".enabled") is False,
                 "missing_mcp_restriction")
    runtime = responses[2]
    check_reasoning_effort(params.get("config", {}), runtime)
    thread = runtime.get("thread", {})
    thread_id = thread.get("id")
    _require(isinstance(thread_id, str) and bool(thread_id) and thread.get("ephemeral") is True
             and not thread.get("forkedFromId") and not thread.get("turns"), "thread_not_fresh")
    _require(Path(thread.get("cwd", "")).resolve() == Path(params["cwd"]).resolve()
             and Path(runtime.get("cwd", "")).resolve() == Path(params["cwd"]).resolve(),
             "workspace_mismatch")
    _require(runtime.get("sandbox", {}).get("type") == "readOnly", "sandbox_not_read_only")
    model = _identity(runtime.get("model"))
    _require(any(row["slug"] == model for row in json.loads(catalog)["models"]), "runtime_model_not_in_catalog")
    provider = _identity(runtime.get("modelProvider"))
    if thread.get("model") is not None:
        _require(thread["model"] == model, "runtime_model_conflict")
    _require(thread.get("modelProvider") == provider, "runtime_provider_conflict")
    _require(client[3]["method"] == "mcpServerStatus/list"
             and client[3]["params"].get("threadId") == thread_id,
             "missing_mcp_inventory")
    _no_mcp_tools(responses[3])
    turn_start = client[4]
    _require(turn_start["method"] == "turn/start", "missing_turn_start")
    turn_params = turn_start["params"]
    _require(set(turn_params) <= {"threadId", "input", "outputSchema"} and
             turn_params.get("threadId") == thread_id, "turn_override_or_thread_mismatch")
    inputs = turn_params.get("input")
    _require(isinstance(inputs, list) and len(inputs) == 1
             and inputs[0].get("type") == "text" and isinstance(inputs[0].get("text"), str),
             "invalid_complete_input")
    text = inputs[0]["text"]
    if prompt is not None:
        _require(text == prompt, "input_mismatch")
    if schema is not None:
        _require(turn_params.get("outputSchema") == schema, "output_schema_mismatch")
    turn = responses[4].get("turn", {})
    turn_id = turn.get("id")
    _require(isinstance(turn_id, str) and bool(turn_id) and turn.get("status") == "inProgress",
             "invalid_turn_start")
    for item in turn.get("items", []):
        _item(item)
    started, completed, messages = 0, [], {}
    for event in events:
        method, value = event.get("method", ""), event.get("params", {})
        _require(isinstance(method, str) and isinstance(value, dict), "invalid_notification")
        if method in {"model/rerouted", "thread/settings/updated", "thread/realtime/started"}:
            raise ValueError("codex_app_server_runtime_configuration_changed")
        if method.startswith(("item/", "turn/", "model/")) or (method.startswith("thread/") and "threadId" in value):
            _require(value.get("threadId") == thread_id, "notification_thread_mismatch")
        if method == "turn/started":
            _require(value.get("turn", {}).get("id") == turn_id, "notification_turn_mismatch")
            started += 1
        elif method == "turn/completed":
            done = value.get("turn", {})
            _require(done.get("id") == turn_id and done.get("status") == "completed"
                     and not done.get("error"), "turn_failed_or_incomplete")
            for item in done.get("items", []):
                _item(item)
                if item["type"] == "agentMessage" and item.get("phase") != "commentary":
                    _require(item.get("id") in messages and messages[item["id"]] == item.get("text"),
                             "completion_output_mismatch")
            completed.append(done)
        elif method in {"item/started", "item/completed"}:
            _require(not completed and value.get("turnId") == turn_id, "late_or_wrong_turn_item")
            item = value.get("item")
            _item(item)
            if method == "item/completed" and item["type"] == "agentMessage" and item.get("phase") != "commentary":
                _require(isinstance(item.get("id"), str) and isinstance(item.get("text"), str)
                         and item["id"] not in messages, "invalid_or_duplicate_output")
                messages[item["id"]] = item["text"]
        elif method.startswith("item/") and method not in {
            "item/agentMessage/delta", "item/reasoning/summaryTextDelta",
            "item/reasoning/textDelta", "item/reasoning/summaryPartAdded",
        }:
            raise ValueError("codex_app_server_model_tools_observed")
        elif method == "error":
            raise ValueError("codex_app_server_execution_error")
        elif method.startswith("codex/event/"):
            # Legacy events duplicate v2 notifications and are never identity evidence.
            kind = value.get("msg", {}).get("type", "")
            _require(not any(word in kind for word in ("exec", "tool_call", "patch", "web_search")),
                     "model_tools_observed")
    _require(started == 1 and len(completed) == 1 and len(messages) == 1, "incomplete_or_multiple_turns")
    output = next(iter(messages.values()))
    _require(bool(output.strip()), "empty_output")
    return output, {
        "source": SOURCE, "evidence_policy": POLICY, "model": model, "model_provider": provider,
        "runtime_reasoning_effort": runtime.get("reasoningEffort"),
        "thread_id": thread_id, "turn_id": turn_id,
        "runtime_identity_verified": True, "model_identity_scope": "runtime_configuration",
        "provider_reported_model": None, "provider_identity_verified": False,
        "provider_dispatch_count": "unknown", "model_tools": [],
        "client_tool_catalog_sha256": digest(catalog),
        "client_tool_overrides": TOOL_CATALOG_OVERRIDES,
        "prompt_sha256": digest(text.encode("utf-8")), "output_sha256": digest(output.encode("utf-8")),
        "protocol_sha256": digest(raw), "protocol_jsonl_base64": base64.b64encode(raw).decode("ascii"),
        **({"requested_reasoning_effort": params["config"]["model_reasoning_effort"]}
           if "model_reasoning_effort" in params.get("config", {}) else {}),
    }

def run_request(executable: str, *, cwd: Path, prompt: str, schema: dict | None,
                timeout_sec: int, journal_path: Path | None = None) -> tuple[str, dict]:
    """Do not expose a listening socket, read stored threads, or service host tool requests."""
    from _planning_skill_common import _terminate_process_tree, _cancel_owned_pipe_io
    reasoning_effort = requested_reasoning_effort()
    records, incoming, stderr = [], queue.Queue(maxsize=8), []
    stopping = threading.Event()
    limit = [0]
    journal = None
    def record(direction, message):
        row = {"direction": direction, "message": message}
        records.append(row)
        if journal is not None:
            journal.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            journal.flush()
    # Model catalog metadata is neither credential material nor saved session history.
    cache_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    cache_raw = (cache_home / "models_cache.json").read_bytes()
    catalog_raw = restricted_catalog(cache_raw)
    catalog_path = cwd / "no-tools-model-catalog.json"
    catalog_path.write_bytes(catalog_raw)
    launch_command = command(executable, catalog_path)
    journal = journal_path.open("x", encoding="utf-8") if journal_path is not None else None
    record("host", {"event": "launch", "executable": executable,
        "command": launch_command, "catalog_path": str(catalog_path),
        "source_catalog_base64": base64.b64encode(cache_raw).decode("ascii"),
        "source_catalog_sha256": digest(cache_raw), "restricted_catalog_sha256": digest(catalog_raw)})
    try:
        proc = subprocess.Popen(launch_command, cwd=cwd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="strict", bufsize=1, start_new_session=os.name != "nt")
    except BaseException:
        if journal is not None:
            journal.close()
        raise
    deadline = time.monotonic() + max(1, timeout_sec)
    def enqueue(value):
        while not stopping.is_set():
            try:
                incoming.put(value, timeout=0.05)
                return
            except queue.Full:
                pass
    def read_stdout():
        received_bytes = 0
        try:
            while not stopping.is_set():
                line = proc.stdout.readline(MAX_TRANSCRIPT_BYTES + 1)
                if not line:
                    break
                received_bytes += len(line.encode("utf-8"))
                _require(received_bytes <= MAX_TRANSCRIPT_BYTES, "transcript_too_large")
                enqueue(line)
        except Exception as error:
            enqueue(error)
        finally:
            enqueue(None)
            proc.stdout.close()
    def read_stderr():
        try:
            for line in proc.stderr:
                if sum(map(len, stderr)) < 2 * 1024 * 1024:
                    stderr.append(line)
        except (OSError, ValueError):
            if not stopping.is_set():
                raise
        finally:
            proc.stderr.close()
    workers = [threading.Thread(target=read_stdout, daemon=True), threading.Thread(target=read_stderr, daemon=True)]
    for worker in workers:
        worker.start()
    def send(message):
        record("client", message)
        finished = queue.Queue(maxsize=1)
        def write():
            try:
                proc.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
                proc.stdin.flush()
                finished.put(None)
            except Exception as error:
                finished.put(error)
        writer = threading.Thread(target=write, daemon=True)
        workers.append(writer)
        writer.start()
        try:
            error = finished.get(timeout=max(0.001, deadline - time.monotonic()))
        except queue.Empty as error:
            raise TimeoutError("Codex App Server input write timed out") from error
        if error is not None:
            raise error
    def receive(*, allow_eof=False):
        timeout_message = ("Codex App Server output did not close" if allow_eof else
                           "Codex App Server turn timed out")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(timeout_message)
        try:
            line = incoming.get(timeout=remaining)
        except queue.Empty as error:
            raise TimeoutError(timeout_message) from error
        if isinstance(line, Exception):
            if isinstance(line, ValueError):
                raise line
            raise ValueError("codex_app_server_invalid_encoding") from line
        if line is None:
            _require(allow_eof, "unexpected_eof:" + "".join(stderr)[-1200:])
            return None
        limit[0] += len(line.encode("utf-8"))
        _require(limit[0] <= MAX_TRANSCRIPT_BYTES, "transcript_too_large")
        message = json.loads(line)
        _require(isinstance(message, dict), "invalid_message")
        record("server", message)
        params = message.get("params")
        error = (params.get("error") if message.get("method") == "error" and isinstance(params, dict) else
                 message.get("error") if "id" in message and "method" not in message else None)
        if isinstance(error, dict):
            _require(not any(isinstance(error.get(key), str) and "max_output_tokens" in error[key].lower()
                for key in ("message", "additionalDetails")), "max_output_tokens")
        _require(not ("method" in message and "id" in message), "server_tool_or_auth_request")
        method = message.get("method", "")
        if method in {"item/started", "item/completed"}:
            _item(message.get("params", {}).get("item"))
        _require(method != "model/rerouted", "runtime_configuration_changed")
        return message
    def rpc(identifier, method, params):
        send({"id": identifier, "method": method, "params": params})
        while True:
            message = receive()
            if message.get("id") == identifier:
                _require("error" not in message, "rpc_error:" + str(message.get("error"))[:1200])
                return message["result"]
    try:
        rpc(1, "initialize", {"clientInfo": {"name": "newrouge_source_audit", "version": "1.0"},
                             "capabilities": {"experimentalApi": True}})
        send({"method": "initialized"})
        configured_mcp = rpc(0, "mcpServerStatus/list", {"detail": "toolsAndAuthOnly", "limit": 100})
        _require(isinstance(configured_mcp.get("data"), list) and not configured_mcp.get("nextCursor"),
                 "incomplete_mcp_preflight")
        names = []
        for server in configured_mcp["data"]:
            name = server.get("name")
            _require(isinstance(name, str) and bool(name) and not any(c in name for c in '."\\\n\r'),
                     "invalid_mcp_server_name")
            names.append(name)
        settings = thread_config(names, reasoning_effort=reasoning_effort)
        runtime = rpc(2, "thread/start", {"cwd": str(cwd), "ephemeral": True,
            "sandbox": "read-only", "approvalPolicy": "untrusted",
            "allowProviderModelFallback": False, "dynamicTools": [], "environments": [], "config": settings})
        thread_id = runtime.get("thread", {}).get("id")
        _identity(runtime.get("model"))
        _identity(runtime.get("modelProvider"))
        _require(isinstance(thread_id, str) and bool(thread_id)
                 and runtime["thread"].get("modelProvider") == runtime["modelProvider"]
                 and runtime["thread"].get("model", runtime["model"]) in {None, runtime["model"]}
                 and Path(runtime["thread"].get("cwd", "")).resolve() == cwd.resolve()
                 and Path(runtime.get("cwd", "")).resolve() == cwd.resolve(), "runtime_configuration_mismatch")
        _require(runtime.get("thread", {}).get("ephemeral") is True
                 and not runtime["thread"].get("turns") and not runtime["thread"].get("forkedFromId")
                 and runtime.get("sandbox", {}).get("type") == "readOnly", "unsafe_runtime_thread")
        check_reasoning_effort(settings, runtime)
        # This is inventory from the new in-memory thread, never stored session history.
        inventory = rpc(3, "mcpServerStatus/list", {"threadId": thread_id, "detail": "toolsAndAuthOnly", "limit": 100})
        _no_mcp_tools(inventory)
        params = {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]}
        if schema is not None:
            params["outputSchema"] = schema
        rpc(4, "turn/start", params)
        if not any(row["message"].get("method") == "turn/completed" for row in records if row["direction"] == "server"):
            while receive().get("method") != "turn/completed":
                pass
        proc.stdin.close()
        # Keep consuming until stdout EOF while the child can still write. Waiting
        # first can fill the bounded queue and pipe, blocking the child's exit.
        # Use the live decoder so late errors/tools/reroutes are still rejected.
        while receive(allow_eof=True) is not None:
            pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Codex App Server did not exit after completed turn")
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("Codex App Server did not exit after completed turn") from error
        _require(proc.returncode == 0, "process_failed:" + "".join(stderr)[-1200:])
        raw = ("\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records) + "\n").encode("utf-8")
        return replay(raw, prompt=prompt, schema=schema)
    finally:
        stopping.set()
        if proc.poll() is None:
            _terminate_process_tree(proc)
        _cancel_owned_pipe_io(workers)
        for worker in workers:
            worker.join(timeout=0.5)
        cleanup_incomplete = any(worker.is_alive() for worker in workers)
        if not cleanup_incomplete:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream and not stream.closed:
                    stream.close()
        if journal is not None:
            journal.close()
        if journal_path is not None:
            journal_path.with_suffix(".stderr.txt").write_text("".join(stderr), encoding="utf-8")
        if cleanup_incomplete:
            raise RuntimeError("Codex App Server pipe cleanup incomplete")

