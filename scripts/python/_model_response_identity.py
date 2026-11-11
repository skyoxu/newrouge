"""Validate actual Responses API metadata without reading client state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


class ModelResponseEvidenceError(ValueError):
    """An observed response cannot prove a completed, tool-free model call."""


def _field(value: object, name: str) -> Any:
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)


def response_identity(response: object, *, source: str) -> tuple[str, dict[str, str]]:
    """Bind identity to provider metadata, never a request alias or output text."""
    if _field(response, "object") != "response" or _field(response, "status") != "completed":
        raise ModelResponseEvidenceError("actual_model_evidence_invalid:response_not_completed")
    response_id = _field(response, "id")
    if not isinstance(response_id, str) or not response_id or any(c.isspace() for c in response_id):
        raise ModelResponseEvidenceError("actual_model_evidence_invalid:response_id_missing")
    model = _field(response, "model")
    if not isinstance(model, str) or not model.strip():
        raise ModelResponseEvidenceError("actual_model_identity_missing:response.model")
    if any(c.isspace() for c in model) or model.casefold() in {"auto", "default", "environment-default", "codex-cli-default"}:
        raise ModelResponseEvidenceError("actual_model_identity_invalid:response.model")
    output = _field(response, "output")
    if not isinstance(output, list):
        raise ModelResponseEvidenceError("actual_model_evidence_invalid:response.output_missing")
    kinds = []
    for item in output:
        kind = _field(item, "type")
        if kind not in {"message", "reasoning", "compaction"}:
            raise ModelResponseEvidenceError("model_tools_observed:" + str(kind or "unknown_response_output"))
        if kind == "message":
            content = _field(item, "content")
            if _field(item, "role") != "assistant" or not isinstance(content, list):
                raise ModelResponseEvidenceError("actual_model_evidence_invalid:response_message")
            if any(_field(part, "type") not in {"output_text", "refusal"} for part in content):
                raise ModelResponseEvidenceError("model_tools_observed:unknown_message_content")
        kinds.append(kind)
    declared_tools = _field(response, "tools")
    if declared_tools is not None and not isinstance(declared_tools, list):
        raise ModelResponseEvidenceError("actual_model_evidence_invalid:response.tools")
    if declared_tools:
        raise ModelResponseEvidenceError("model_tools_observed:response_declared_tools")
    # The digest covers this explicit metadata projection, not raw HTTP bytes.
    metadata = {"id": response_id, "object": "response", "status": "completed",
                "model": model, "output_types": kinds}
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=False).encode("utf-8")).hexdigest()
    return model, {"source": source, "model": model, "response_id": response_id,
                   "response_object": "response", "response_status": "completed",
                   "response_output_types": json.dumps(kinds, separators=(",", ":")),
                   "response_metadata_sha256": "sha256:" + digest}
