"""Pure replay of captured isolated-runner completion and model protocol.

The 3A wrapper supplies its historical request/schema locations unchanged. 3B
supplies the exact final runner wrapper captured before its durable reservation.
Requested configuration never stands in for a returned model identity.
"""
from __future__ import annotations

import base64
from pathlib import Path

import _b_route_codec as codec
import _b_route_sources as sources


def receipt_from(execution):
    raw = base64.b64decode(execution["stdout_base64"], validate=True)
    sources.require(raw.decode("utf-8") == execution["stdout"], "execution.stdout", "exact captured original stdout bytes")
    for line in reversed(execution["stdout"].splitlines()):
        if line.strip().startswith("{"):
            try:
                value = codec.strict_json_loads(line.encode("utf-8"))
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    return {}


def validate_execution(workspace, execution, receipt, expected_model, output, *, prompt, schema,
                       require_runtime=False, expected_reasoning_effort=None):
    workspace = Path(workspace)
    sources.require(execution["status"] == "completed" and type(execution["returncode"]) is int
        and execution["returncode"] == 0 and execution["runner_dispatch_count"] == 1,
        "execution", "successful captured OS runner completion")
    sources.require(codec.canonical_digest(receipt) == codec.canonical_digest(receipt_from(execution)),
                    "receipt", "coordinator-captured stdout receipt")
    runtime_scope = receipt.get("model_identity_scope") == "runtime_configuration"
    if expected_reasoning_effort is not None:
        sources.require(expected_reasoning_effort in ("low", "high") and runtime_scope,
                        "receipt.reasoning_effort", "captured expected runtime reasoning configuration")
    if require_runtime:
        sources.require(runtime_scope and not receipt.get("synthetic"), "receipt.scope", "real replayable runtime configuration")
    if runtime_scope:
        import _codex_app_server as app_server
        sources.require(receipt.get("evidence_policy") == app_server.POLICY
            and receipt.get("runtime_identity_verified") is True
            and receipt.get("model_identity_verified") is False
            and receipt.get("provider_identity_verified") is False
            and receipt.get("provider_reported_model") is None
            and receipt.get("provider_dispatch_count") == "unknown"
            and receipt.get("model_identity_source") == app_server.SOURCE,
            "receipt.scope", "explicit runtime configuration proof; provider model remains unknown")
        evidence = receipt.get("model_identity_evidence")
        sources.require(isinstance(evidence, list) and len(evidence) == 1,
                        "receipt.evidence", "one complete bound App Server turn")
        proof = evidence[0]
        sources.require(isinstance(proof, dict) and isinstance(proof.get("protocol_jsonl_base64"), str),
                        "receipt.evidence", "complete captured protocol bytes")
        actual_output, rebuilt = app_server.replay(base64.b64decode(proof["protocol_jsonl_base64"], validate=True),
                                                   prompt=prompt, schema=schema)
        if expected_reasoning_effort is not None:
            sources.require(rebuilt.get("requested_reasoning_effort") == expected_reasoning_effort
                and rebuilt.get("runtime_reasoning_effort") == expected_reasoning_effort,
                "receipt.reasoning_effort", "captured requested and returned " + expected_reasoning_effort)
        sources.require(codec.canonical_digest(rebuilt) == codec.canonical_digest(proof)
            and actual_output.encode("utf-8") == output
            and proof["model"] == receipt.get("model")
            and proof["model_provider"] == receipt.get("model_provider"),
            "receipt.evidence", "exact host protocol, frozen request, schema, output and runtime configuration")
    sources.require(receipt.get("schema_version") == "newrouge.isolated-model-runner-receipt.v1"
        and (runtime_scope or receipt.get("model_identity_verified") is True) and receipt.get("model_tools") == []
        and receipt.get("request_count_observable") is True
        and type(receipt.get("model_request_count")) is int and receipt["model_request_count"] == 1
        and type(receipt.get("runner_invocations")) is int and receipt["runner_invocations"] == 1,
        "receipt", "verified identity in its declared scope, no tools and one completed runner turn")
    automatic = {"auto", "automatic", "codex-cli-default", "environment-default"}
    actual_model = receipt.get("model")
    model_matches = (isinstance(actual_model, str) and actual_model not in {"", "environment-default", "default"})
    if require_runtime:
        model_matches = model_matches and (expected_model.lower() in automatic
            or expected_model in {actual_model, receipt.get("model_identity")})
        model_matches = model_matches and receipt.get("model_identity") == receipt.get("model_provider", "") + "/" + actual_model
    else:
        model_matches = model_matches and receipt.get("model_identity") == expected_model
    sources.require(model_matches, "receipt.model_identity", expected_model, receipt.get("model_identity"))
    sources.require(receipt.get("model_identity_evidence") and receipt.get("model_identity_source")
        and receipt.get("workspace") == workspace.as_posix()
        and receipt.get("output_chars") == len(output.decode("utf-8")),
        "receipt", "actual identity evidence, exact workspace and output length")
    sources.require(type(execution["active_elapsed_seconds"]) in {float, int}
        and execution["active_elapsed_seconds"] >= 0, "execution.time", "observed monotonic elapsed seconds")
