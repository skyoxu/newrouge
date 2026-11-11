"""Synthetic stdio server: no provider, tools, credentials, or saved sessions."""
import json
import os
from pathlib import Path
import sys
import time
import subprocess

mode, log = sys.argv[1], Path(sys.argv[2])
thread_id, turn_id = "fresh-thread", "fresh-turn"

def inherited_holder():
    child = subprocess.Popen([sys.executable, '-I', '-S', '-B', __file__,
        'inherited_pipe_holder', str(log)], stdout=sys.stdout, stderr=sys.stderr,
        stdin=subprocess.DEVNULL, close_fds=False,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    log.with_suffix('.holder-pid.json').write_text(json.dumps({'pid': child.pid}), encoding='utf-8')

if mode == 'inherited_pipe_holder':
    # The supervisor owns the signal; an absolute short lifetime also bounds failure cleanup.
    limit = time.monotonic() + 8
    while not log.with_suffix('.holder-exit').exists() and time.monotonic() < limit:
        time.sleep(0.02)
    log.with_suffix('.holder-done').write_text(str(os.getpid()), encoding='ascii')
    raise SystemExit(0)

if mode == 'outer_inherited_exit':
    sys.stdout.buffer.write(b'captured prefix \xcf\x80\xff\r\n')
    sys.stdout.buffer.flush()
    inherited_holder()
    raise SystemExit(0)

if mode == 'outer_exact_exit':
    Path(sys.argv[sys.argv.index('--output') + 1]).write_text('{}', encoding='utf-8')
    sys.stdout.buffer.write('prefix \u03c0\r\n{"synthetic":true}\r\n'.encode('utf-8'))
    sys.stdout.buffer.flush()
    raise SystemExit(0)

def emit(message):
    print(json.dumps(message, separators=(",", ":")), flush=True)

for line in sys.stdin:
    message = json.loads(line)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"method":message["method"], "id":message.get("id")}) + "\n")
    identifier, method = message.get("id"), message["method"]
    if method == "initialize":
        emit({"id":identifier,"result":{"userAgent":"synthetic-stdio-child"}})
        if mode == "flood":
            for _ in range(64):
                emit({"method":"fixture/noise","params":{"padding":"x"*16000}})
    elif method == "thread/start":
        cwd = message["params"]["cwd"]
        effort = "low" if mode == "reasoning_low" else None if mode == "reasoning_missing" else "medium" if mode == "reasoning_medium" else "high"
        emit({"id":identifier,"result":{"model":"fixture-model","modelProvider":"fixture",
            "reasoningEffort":effort,"cwd":cwd,"sandbox":{"type":"readOnly"},
            "thread":{"id":thread_id,"ephemeral":True,"cwd":cwd,"turns":[],
                      "model":"fixture-model","modelProvider":"fixture"}}})
    elif method == "mcpServerStatus/list":
        result = {"data":[],"nextCursor":None}
        if message.get("params",{}).get("threadId"):
            if mode == "bad_mcp":
                result["data"] = [{"name":"unexpected","runtimeStatus":"connected","tools":{"run":{}}}]
            elif mode == "partial_mcp":
                result["nextCursor"] = "more"
        emit({"id":identifier,"result":result})
        if message.get("params",{}).get("threadId") and mode == "stall":
            time.sleep(30)
    elif method == "turn/start":
        emit({"id":identifier,"result":{"turn":{"id":turn_id,"status":"inProgress","items":[]}}})
        if mode == "host_request":
            emit({"id":99,"method":"item/tool/call","params":{}})
            continue
        emit({"method":"turn/started","params":{"threadId":thread_id,
              "turn":{"id":turn_id,"status":"inProgress"}}})
        if mode in ("max_output_message", "max_output_details", "max_output_rpc"):
            error = {"message": "stream disconnected before completion", "additionalDetails": None}
            error["additionalDetails" if mode == "max_output_details" else "message"] = "Incomplete response: max_output_tokens"
            emit({"id": 99, "error": error} if mode == "max_output_rpc" else
                 {"method": "error", "params": {"threadId": thread_id, "turnId": turn_id, "error": error, "willRetry": True}})
            time.sleep(30)
            continue
        if mode == "legacy_transient":
            emit({"method": "codex/event/error", "params": {"message": "temporary TLS reconnect", "willRetry": True}})
            emit({"method": "fixture/untrusted_text", "params": {"text": "max_output_tokens",
                  "error": {"message": "max_output_tokens"}}})
        item = {"type":"agentMessage","id":"answer","text":'{"status":"ok"}',"phase":"final_answer"}
        emit({"method":"item/completed","params":{"threadId":thread_id,"turnId":turn_id,"item":item}})
        if mode == "tail_deadline":
            time.sleep(1.2)
        emit({"method":"turn/completed","params":{"threadId":thread_id,
              "turn":{"id":turn_id,"status":"completed","items":[item],"error":None}}})

# Shutdown output starts only after the host closes stdin. It must be consumed
# while this child is alive: the bounded host queue plus OS pipe cannot hold it.
if mode.startswith("tail_"):
    if mode == 'tail_inherited_exit':
        inherited_holder()
    elif mode in ("tail_no_exit", "tail_slow_exit"):
        sys.stdout.close()
        os.close(1)
        time.sleep(10.2 if mode == "tail_slow_exit" else 30)
    elif mode == "tail_deadline":
        time.sleep(30)
    else:
        for sequence in range(128):
            emit({"method":"fixture/shutdown","params":{"sequence":sequence,"padding":"x"*8192}})
        if mode == "tail_error":
            emit({"method":"error","params":{"threadId":thread_id,"turnId":turn_id,
                  "error":{"message":"late shutdown error"},"willRetry":False}})
        elif mode == "tail_tool":
            emit({"method":"item/started","params":{"threadId":thread_id,"turnId":turn_id,
                  "item":{"id":"late-tool","type":"commandExecution"}}})
        elif mode == "tail_reroute":
            emit({"method":"model/rerouted","params":{"threadId":thread_id,"turnId":turn_id}})
        elif mode == "tail_max_output":
            emit({"method":"error","params":{"threadId":thread_id,"turnId":turn_id,
                  "error":{"message":"Incomplete response: max_output_tokens"},"willRetry":True}})
            time.sleep(30)
        elif mode == "tail_nonzero":
            raise SystemExit(7)
