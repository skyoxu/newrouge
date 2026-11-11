"""Exact final-input rendering for the explicit shared segmented protocol.

This module grants no semantic, native, execution or retry authority. The engine
owns dependency closure and fairness; this boundary checks literal bindings,
fresh workspace inputs and the complete serialized request's two size limits.
"""
from collections.abc import Mapping
from copy import deepcopy
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import weakref


PROTOCOL = "newrouge.b-route-segmented-workflow.v1"
ENVELOPE = "newrouge.b-route-segmented-envelope.v1"
ARCHIVE = "newrouge.b-route-segmented-input-archive.v1"
INPUT_WIRE = "newrouge.b-route-segmented-wire-input.v1"
INPUT_CODEC = "newrouge.b-route-compact-literal.v2"
INPUT_TOKEN_LIMIT = 70000
CONTEXT_TOKEN_LIMIT = 96000
MAX_REQUEST_BYTES = 1024 * 1024
_INPUT_NAMES = frozenset({"prompt.txt", "input.json", "output-schema.json"})
_WIRE_KEYS = ("schema_version", "codec", "original_json_raw_digest", "literal")
_WIRE_FIELDS = frozenset(_WIRE_KEYS)
_ARCHIVE_FIELDS = frozenset({"schema_version", "protocol", "workspace", "archive", "inputs", "request_sha256",
    "envelope_digest", "schema_digest", "model_prompt_digest", "measurement"})
_ARCHIVE_REQUEST_FIELDS = frozenset({"protocol", "plan_digest", "node_id", "phase", "request_sha256",
    "input_measurement", "output_reserve", "source_hashes", "schema_digest", "request_ref", "schema_ref",
    "timeout_sec", "input_archive_ref"})
_ENVELOPE_FIELDS = frozenset({"schema_version", "protocol", "run_id", "plan_digest", "manifest_digest",
    "node_id", "phase", "ordinal", "candidate_labels", "dimensions", "segment_refs", "citation_catalog", "global_constraints",
    "original_segments", "predecessors", "obligations", "dependency_edges", "output_reserve", "final",
    "candidate_contract", "candidate_products"})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SENSITIVE = frozenset({".git", ".ssh", ".aws", ".codex", ".env", "auth.json", "credentials",
    "credentials.json", "sessions", "archived_sessions", "id_rsa", "id_ed25519"})
_SEAL = object()
_ISSUED = weakref.WeakKeyDictionary()


def _fail(code):
    raise ValueError("segmented_request_" + code)


def _json_text(value):
    active = set()
    def check(node):
        kind = type(node)
        if kind in (dict, list):
            if id(node) in active:
                _fail("cyclic_json")
            active.add(id(node))
            if kind is dict:
                if any(type(key) is not str for key in node):
                    _fail("nonstring_json_key")
                for child in node.values():
                    check(child)
            else:
                for child in node:
                    check(child)
            active.remove(id(node))
        elif node is not None and kind not in (str, int, bool, float):
            _fail("non_json_value")
        elif kind is float and not math.isfinite(node):
            _fail("nonfinite_json")
    check(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _raw_digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _identity(value):
    _json_text(value)
    return _raw_digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _text(value, label):
    if type(value) is not str or not value:
        _fail(label)
    value.encode("utf-8", errors="strict")
    return value


def _digest(value, label):
    if type(value) is not str or not _DIGEST.fullmatch(value):
        _fail(label)


def _closed(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        _fail(label)


def _strings(value, label, *, empty=False):
    if type(value) is not list or not empty and not value:
        _fail(label)
    for item in value:
        _text(item, label)
    if len(set(value)) != len(value):
        _fail(label + "_duplicate")


def _reference(row):
    _closed(row, {"segment_id", "material_id", "start", "end", "raw_digest", "order", "parent_digest"}, "segment_ref_fields")
    ident = _text(row["segment_id"], "segment_id")
    _text(row["material_id"], "material_id")
    for field in ("start", "end", "order"):
        if type(row[field]) is not int or row[field] < 0:
            _fail("segment_" + field)
    if row["end"] < row["start"]:
        _fail("segment_range")
    _digest(row["raw_digest"], "segment_digest")
    _digest(row["parent_digest"], "segment_parent_digest")
    return ident


def _candidate_json(value, label):
    """Validate syntax while retaining the original JSON string byte-for-byte."""
    raw = _text(value, label).encode("utf-8", errors="strict")
    def pairs(rows):
        result = {}
        for key, child in rows:
            if key in result:
                _fail("duplicate_candidate_json_key")
            result[key] = child
        return result
    parsed = json.loads(value, object_pairs_hook=pairs,
        parse_constant=lambda _constant: _fail("nonfinite_candidate_json"))
    _json_text(parsed).encode("utf-8", errors="strict")
    return raw


def _candidate_products(value):
    """Check literal product carriage, never source/schema/semantic authority."""
    if value["candidate_contract"] is not None and type(value["candidate_contract"]) is not dict:
        _fail("candidate_contract")
    if type(value["candidate_products"]) is not list:
        _fail("candidate_products")
    labels, identities = set(), set()
    for row in value["candidate_products"]:
        _closed(row, {"candidate_label", "candidate_id", "stage", "content_digest", "slots", "object_domain",
            "review_result_digests"}, "candidate_product_fields")
        label = _text(row["candidate_label"], "candidate_label")
        ident = _text(row["candidate_id"], "candidate_id")
        if (label not in value["candidate_labels"] or label in labels or ident in identities
                or ident != _identity({"plan_digest": value["plan_digest"], "blind_label": label})):
            _fail("candidate_product_identity")
        labels.add(label)
        identities.add(ident)
        expected_stage = {"generation": "generation-fragments", "synthesis": "synthesis-inputs",
            "independent-review": "assembled-original", "selection": "assembled-original"}[value["phase"]]
        if row["stage"] != expected_stage:
            _fail("candidate_product_stage")
        if row["stage"] == "assembled-original":
            _digest(row["content_digest"], "candidate_content_digest")
        elif row["content_digest"] is not None:
            _fail("unassembled_candidate_content_digest")
        if type(row["object_domain"]) is not dict or type(row["slots"]) is not list:
            _fail("candidate_product_domain_or_slots")
        _strings(row["review_result_digests"], "candidate_review_results", empty=True)
        for digest in row["review_result_digests"]:
            _digest(digest, "candidate_review_digest")
        slots = set()
        for slot in row["slots"]:
            _closed(slot, {"slot_id", "target", "value_json", "raw_digest", "generation_value_json",
                "generation_raw_digest", "generation_result_digest", "synthesis_result_digest"}, "candidate_slot_fields")
            slot_id = _text(slot["slot_id"], "candidate_slot_id")
            if slot_id in slots:
                _fail("duplicate_candidate_slot")
            slots.add(slot_id)
            _text(slot["target"], "candidate_slot_target")
            raw = _candidate_json(slot["value_json"], "candidate_slot_json")
            for field in ("raw_digest", "generation_raw_digest", "generation_result_digest"):
                _digest(slot[field], "candidate_slot_" + field)
            if row["stage"] == "generation-fragments" and slot["synthesis_result_digest"] is not None:
                _fail("generation_fragment_has_synthesis")
            if row["stage"] == "assembled-original" or slot["synthesis_result_digest"] is not None:
                _digest(slot["synthesis_result_digest"], "candidate_slot_synthesis_result_digest")
            if _raw_digest(raw) != slot["raw_digest"]:
                _fail("candidate_slot_raw_binding")
            unchanged = slot["generation_raw_digest"] == slot["raw_digest"]
            if slot["synthesis_result_digest"] is None and not unchanged:
                _fail("unsynthesized_slot_changed_generation")
            if unchanged:
                if slot["generation_value_json"] is not None:
                    _fail("unchanged_slot_has_generation_copy")
            else:
                if slot["generation_value_json"] is None:
                    _fail("changed_slot_missing_generation_json")
                original = _candidate_json(slot["generation_value_json"], "candidate_generation_json")
                if _raw_digest(original) != slot["generation_raw_digest"]:
                    _fail("candidate_generation_raw_binding")


def _envelope(value, reserve):
    _closed(value, _ENVELOPE_FIELDS, "envelope_fields")
    if value["schema_version"] != ENVELOPE or value["protocol"] != PROTOCOL:
        _fail("protocol")
    if value["phase"] not in ("generation", "synthesis", "independent-review", "selection"):
        _fail("phase")
    if type(value["final"]) is not bool or value["final"] and value["phase"] != "selection":
        _fail("final_phase")
    for name in ("run_id", "node_id"):
        _text(value[name], name)
    for name in ("plan_digest", "manifest_digest"):
        _digest(value[name], name)
    if type(value["ordinal"]) is not int or value["ordinal"] < 0:
        _fail("ordinal")
    if type(reserve) is not int or not 1 <= reserve <= CONTEXT_TOKEN_LIMIT:
        _fail("output_reserve")
    if type(value["output_reserve"]) is not int or value["output_reserve"] != reserve:
        _fail("output_reserve_binding")
    _strings(value["candidate_labels"], "candidate_labels")
    _strings(value["dimensions"], "dimensions")
    _candidate_products(value)
    for name in ("segment_refs", "citation_catalog", "original_segments", "global_constraints", "predecessors", "obligations", "dependency_edges"):
        if type(value[name]) is not list:
            _fail(name)
    catalog = {}
    for row in value["citation_catalog"]:
        ident = _reference(row)
        if ident in catalog:
            _fail("duplicate_citation_catalog_segment")
        catalog[ident] = row
    segments = {}
    for row in value["original_segments"]:
        _closed(row, {"segment_id", "text"}, "original_segment_fields")
        ident = _text(row["segment_id"], "segment_id")
        if ident in segments or type(row["text"]) is not str:
            _fail("original_segment_duplicate_or_text")
        segments[ident] = row["text"].encode("utf-8", errors="strict")
    refs = []
    for row in value["segment_refs"]:
        ident = _reference(row)
        if ident not in catalog or _identity(row) != _identity(catalog[ident]):
            _fail("segment_citation_catalog_binding")
        if (ident not in segments or len(segments[ident]) != row["end"] - row["start"]
                or _raw_digest(segments[ident]) != row["raw_digest"]):
            _fail("segment_bytes_binding")
        refs.append(ident)
    if refs != list(segments) or len(set(refs)) != len(refs):
        _fail("segment_order_or_coverage")
    globals_seen = set()
    for row in value["global_constraints"]:
        _closed(row, {"material_id", "raw_digest", "text"}, "global_fields")
        ident = _text(row["material_id"], "global_material_id")
        if ident in globals_seen or type(row["text"]) is not str:
            _fail("global_duplicate_or_text")
        globals_seen.add(ident)
        if _raw_digest(row["text"].encode("utf-8", errors="strict")) != row["raw_digest"]:
            _fail("global_bytes_binding")
        matches = [ref for ref in catalog.values() if ref["material_id"] == ident]
        if (len(matches) != 1 or matches[0]["start"] != 0
                or matches[0]["end"] != len(row["text"].encode("utf-8"))
                or matches[0]["raw_digest"] != row["raw_digest"]):
            _fail("global_complete_citation_binding")
    prior = set()
    for row in value["predecessors"]:
        _closed(row, {"node_id", "result_digest", "output"}, "predecessor_fields")
        ident = _text(row["node_id"], "predecessor_id")
        if ident in prior or type(row["output"]) is not dict:
            _fail("predecessor_duplicate_or_output")
        prior.add(ident)
        _digest(row["result_digest"], "predecessor_digest")
    obligations = set()
    for row in value["obligations"]:
        _closed(row, {"obligation_id", "segment_ids", "dependency_ids", "kind"}, "obligation_fields")
        ident = _text(row["obligation_id"], "obligation_id")
        if ident in obligations:
            _fail("duplicate_obligation")
        obligations.add(ident)
        _strings(row["segment_ids"], "obligation_segments", empty=True)
        _strings(row["dependency_ids"], "obligation_dependencies", empty=True)
        _text(row["kind"], "obligation_kind")
    edges = set()
    for edge in value["dependency_edges"]:
        if type(edge) is not list or len(edge) != 2:
            _fail("dependency_edge")
        for item in edge:
            _text(item, "dependency_endpoint")
        if tuple(edge) in edges:
            _fail("duplicate_dependency_edge")
        edges.add(tuple(edge))
    _json_text(value)


def _location(root, workspace):
    root, workspace = Path(root), Path(workspace)
    # Role checks happen before lstat, resolve, mkdir or content access.
    for path in (root, workspace):
        if not path.is_absolute() or ".." in path.parts or path.anchor.startswith("\\\\"):
            _fail("path_role")
        for part in path.parts[1:]:
            if (part.casefold() in _SENSITIVE or part.casefold().startswith(".env")
                    or any(ord(char) < 32 or char in '<>:"|?*' for char in part)):
                _fail("sensitive_or_invalid_path_role")
    try:
        relative = workspace.relative_to(root / "logs" / "ci")
    except ValueError:
        _fail("workspace_not_project_local")
    if not relative.parts:
        _fail("workspace_not_dedicated")
    if not root.is_dir():
        _fail("root_missing")
    for path in reversed((workspace, *workspace.parents)):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
                or not stat.S_ISDIR(info.st_mode)):
            _fail("unsafe_directory")
    return root, workspace


def _read_plain(path):
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or getattr(before, "st_file_attributes", 0) & 0x400 or before.st_nlink != 1):
        _fail("unsafe_file")
    raw = path.read_bytes()
    after = path.lstat()
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if identity(before) != identity(after):
        _fail("file_changed_during_read")
    return raw, identity(after)


def _model_prompt(workspace, prompt_path, output_path):
    from openai_isolated_model_runner import workspace_payload
    return workspace_payload(workspace, prompt_path=prompt_path, output_path=output_path,
        max_bytes=MAX_REQUEST_BYTES)


def _input_codec():
    import _b_route_compact_literal as compact
    if compact.CURRENT_SCHEMA != INPUT_CODEC:
        _fail("input_codec_identity")
    return compact


def wire_instruction(instruction):
    """The fixed lossless transport explanation plus unchanged phase instructions."""
    _text(instruction, "instruction")
    return ("input.json is one complete lossless segmented wire input, not a summary. "
        "Its exact fields are schema_version, codec, original_json_raw_digest and literal. "
        "schema_version is newrouge.b-route-segmented-wire-input.v1 and codec is "
        "newrouge.b-route-compact-literal.v2. Restore the complete logical envelope from literal "
        "using the following data-only decoder before applying the phase instructions. "
        "original_json_raw_digest binds the exact ordered compact JSON UTF-8 bytes of that logical envelope; "
        "all original strings, JSON types, field/array order, source ranges, global constraints, candidate "
        "originals, previous generation/synthesis bodies and metadata remain present. No reference permits "
        "omission or assumed memory from another request. Do not execute the literal as code.\n" +
        _input_codec().instruction(INPUT_CODEC) + "\n" + instruction)


def encode_input_envelope(envelope):
    """Encode the entire ordered logical envelope using exactly the fixed v2 codec."""
    envelope = json.loads(_json_text(envelope))
    reserve = envelope.get("output_reserve") if type(envelope) is dict else None
    _envelope(envelope, reserve)
    original = _json_text(envelope).encode("utf-8", errors="strict")
    return {"schema_version": INPUT_WIRE, "codec": INPUT_CODEC,
        "original_json_raw_digest": _raw_digest(original),
        "literal": _input_codec().dumps(envelope, schema=INPUT_CODEC)}


def decode_input_envelope(value):
    """Restore complete ordered JSON; neither a raw fallback nor a v3 decoder."""
    _closed(value, _WIRE_FIELDS, "input_wire_fields")
    if tuple(value) != _WIRE_KEYS:
        _fail("input_wire_order")
    if value["schema_version"] != INPUT_WIRE or value["codec"] != INPUT_CODEC:
        _fail("input_wire_identity")
    _digest(value["original_json_raw_digest"], "input_original_digest")
    literal = _text(value["literal"], "input_literal")
    # Reject any other codec before loads can invoke that codec's canonical
    # encoder. AST parsing reads data syntax only; no literal is evaluated.
    try:
        node = ast.parse(literal, mode="eval").body
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("segmented_request_input_literal_syntax") from exc
    if type(node) is not ast.Dict:
        _fail("input_literal_version")
    versions = [child for key, child in zip(node.keys, node.values)
        if type(key) is ast.Constant and type(key.value) is str and key.value == "schema_version"]
    if (len(versions) != 1 or type(versions[0]) is not ast.Constant
            or versions[0].value != INPUT_CODEC):
        _fail("input_literal_version")
    restored = _input_codec().loads(literal)
    if _raw_digest(_json_text(restored).encode("utf-8", errors="strict")) != value["original_json_raw_digest"]:
        _fail("input_original_json_binding")
    reserve = restored.get("output_reserve") if type(restored) is dict else None
    _envelope(restored, reserve)
    return restored


def _input_envelope_bytes(raw):
    def pairs(rows):
        result = {}
        for key, child in rows:
            if key in result:
                _fail("duplicate_input_json_key")
            result[key] = child
        return result
    value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
        parse_constant=lambda _constant: _fail("nonfinite_input_json"))
    if (_json_text(value) + "\n").encode("utf-8", errors="strict") != raw:
        _fail("input_wire_noncanonical_json")
    return decode_input_envelope(value)


def read_input_envelope(root, workspace):
    """Read only fixed input.json, closing its plain bytes and directory identity."""
    root, workspace = _location(root, workspace)
    directories = {}
    for path in (root, workspace):
        info = path.lstat()
        directories[path] = (info.st_dev, info.st_ino)
    members = tuple(sorted(path.name for path in workspace.iterdir()))
    raw, identity = _read_plain(workspace / "input.json")
    envelope = _input_envelope_bytes(raw)
    after, after_identity = _read_plain(workspace / "input.json")
    if raw != after or identity != after_identity:
        _fail("input_changed_during_read")
    _location(root, workspace)
    if tuple(sorted(path.name for path in workspace.iterdir())) != members:
        _fail("input_workspace_membership_changed")
    for path, expected in directories.items():
        info = path.lstat()
        if (info.st_dev, info.st_ino) != expected:
            _fail("input_directory_replaced")
    return envelope


def _measure(full_request, reserve):
    from _capability_input_integrity import measure_request
    return measure_request(full_request, max_bytes=MAX_REQUEST_BYTES,
        max_input_tokens=CONTEXT_TOKEN_LIMIT, reserved_tokens=reserve)


def _measurement(report, request, reserve):
    if type(report) is not dict:
        _fail("measurement_missing")
    expected = {"request_sha256": _raw_digest(request.encode("utf-8")), "request_chars": len(request),
        "request_bytes": len(request.encode("utf-8")), "max_bytes": MAX_REQUEST_BYTES,
        "max_input_tokens": CONTEXT_TOKEN_LIMIT, "reserved_continuation_tokens": reserve,
        "truncation_allowed": False}
    for key, value in expected.items():
        if type(report.get(key)) is not type(value) or report[key] != value:
            _fail("measurement_binding_" + key)
    tokens = report.get("input_token_estimate")
    if type(tokens) is not int or tokens < 0:
        _fail("measurement_tokens")
    if report.get("token_counter") not in ("max(o200k_base,cl100k_base)+10_percent", "utf8_byte_upper_bound"):
        _fail("measurement_counter")
    counts = report.get("token_counts")
    if report["token_counter"] == "utf8_byte_upper_bound":
        if type(counts) is not dict or counts or tokens != len(request.encode("utf-8")):
            _fail("measurement_byte_counter_binding")
    elif (type(counts) is not dict or set(counts) != {"o200k_base", "cl100k_base"}
            or any(type(count) is not int or count < 0 for count in counts.values())
            or tokens != (max(counts.values()) * 11 + 9) // 10):
        _fail("measurement_token_counter_binding")
    if len(request) > MAX_REQUEST_BYTES or len(request.encode("utf-8")) > MAX_REQUEST_BYTES:
        _fail("final_wrapper_bytes")
    if tokens > INPUT_TOKEN_LIMIT:
        _fail("input_over_70000")
    if tokens + reserve > CONTEXT_TOKEN_LIMIT:
        _fail("input_plus_output_over_96000")


class RenderedRequest(Mapping):
    """In-process issuer-bound request, never reconstructible from journal JSON."""
    __slots__ = ("_data", "__weakref__")
    __hash__ = object.__hash__
    __eq__ = object.__eq__

    def __init__(self, seal, data):
        if seal is not _SEAL:
            _fail("request_not_issued")
        object.__setattr__(self, "_data", deepcopy(data))

    def __setattr__(self, name, value):
        _fail("immutable_request")

    def __getitem__(self, name):
        return deepcopy(self._data[name])

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


def render_request(root, *, envelope, schema, instruction, workspace, output_reserve):
    """Create three new input files and bound the exact native JSON wrapper."""
    # Take a JSON snapshot before deriving any file, digest or measurement.
    envelope = json.loads(_json_text(envelope))
    schema = json.loads(_json_text(schema))
    _envelope(envelope, output_reserve)
    if type(schema) is not dict:
        _fail("schema_not_object")
    _text(instruction, "instruction")
    root, workspace = _location(root, workspace)
    if workspace.exists():
        _fail("workspace_already_exists")
    inputs = {"prompt.txt": wire_instruction(instruction).encode("utf-8"),
        "input.json": (_json_text(encode_input_envelope(envelope)) + "\n").encode("utf-8"),
        "output-schema.json": (_json_text(schema) + "\n").encode("utf-8")}
    workspace.mkdir(parents=True, exist_ok=False)
    _location(root, workspace)
    for name, raw in inputs.items():
        with (workspace / name).open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    prompt_path, schema_path, output_path = (workspace / name for name in
        ("prompt.txt", "output-schema.json", "output.json"))
    if {path.name for path in workspace.iterdir()} != _INPUT_NAMES:
        _fail("unexpected_workspace_member")
    pins = {}
    for name, raw in inputs.items():
        observed, identity = _read_plain(workspace / name)
        if observed != raw:
            _fail("input_changed")
        pins[name] = (raw, identity)
    model_prompt = _model_prompt(workspace, prompt_path, output_path)
    _text(model_prompt, "model_prompt")
    full_request = _json_text({"prompt": model_prompt, "output_schema": schema})
    report = _measure(full_request, output_reserve)
    _measurement(report, full_request, output_reserve)
    value = RenderedRequest(_SEAL, {"workspace": workspace, "prompt_path": prompt_path,
        "output_path": output_path, "schema_path": schema_path, "model_prompt": model_prompt,
        "full_request": full_request, "request_sha256": _raw_digest(full_request.encode("utf-8")),
        "measurement": report, "envelope_digest": _identity(envelope), "schema_digest": _identity(schema)})
    directories = {}
    for path in (root, workspace):
        info = path.lstat()
        directories[path] = (info.st_dev, info.st_ino)
    _ISSUED[value] = {"root": root, "workspace": workspace, "pins": pins,
        "schema": deepcopy(schema), "reserve": output_reserve, "directories": directories}
    verify_rendered_request(root, value)
    return value


def verify_rendered_request(root, request, *, execution_close=None):
    """Close original inputs; post-execution files require the core's typed grant."""
    if type(request) is not RenderedRequest or request not in _ISSUED:
        _fail("request_not_issued")
    state = _ISSUED[request]
    root, workspace = _location(root, state["workspace"])
    if root != state["root"]:
        _fail("request_root_changed")
    for path, identity in state["directories"].items():
        current = path.lstat()
        if (current.st_dev, current.st_ino) != identity:
            _fail("request_directory_replaced")
    artifact = None
    if execution_close is not None:
        from _b_route_segmented_workflow import verify_execution_close
        artifact = verify_execution_close(root, execution_close, workspace=workspace)
        if (type(artifact) is not dict or type(artifact.get("files")) is not dict
                or artifact.get("request_sha256") != request["request_sha256"]):
            _fail("execution_close_binding")
    extra = {} if artifact is None else artifact["files"]
    if (any(type(name) is not str or Path(name).name != name or name in _INPUT_NAMES
            for name in extra) or artifact is not None and "output.json" not in extra):
        _fail("execution_close_file_roles")
    if artifact is not None:
        for name in ("binding_digest", "receipt_digest", "output_digest"):
            _digest(artifact.get(name), "execution_close_" + name)
        if artifact["output_digest"] != extra["output.json"]:
            _fail("execution_close_output_binding")
    expected = _INPUT_NAMES | set(extra)
    if {path.name for path in workspace.iterdir()} != expected:
        _fail("unexpected_workspace_member")
    for name, (raw, identity) in state["pins"].items():
        current, current_identity = _read_plain(workspace / name)
        if current != raw or current_identity != identity:
            _fail("input_changed")
    for name, expected_digest in extra.items():
        _digest(expected_digest, "execution_close_digest")
        current, _identity_value = _read_plain(workspace / name)
        if _raw_digest(current) != expected_digest:
            _fail("execution_artifact_changed")
    if artifact is None:
        current_prompt = _model_prompt(workspace, request["prompt_path"], request["output_path"])
        if current_prompt != request["model_prompt"]:
            _fail("model_prompt_changed")
    current_request = _json_text({"prompt": request["model_prompt"], "output_schema": state["schema"]})
    if current_request != request["full_request"]:
        _fail("final_wrapper_changed")
    _measurement(request["measurement"], current_request, state["reserve"])
    if {path.name for path in workspace.iterdir()} != expected:
        _fail("workspace_membership_changed")
    return deepcopy(artifact)


def _archive_paths(root, workspace):
    root, workspace = _location(root, workspace)
    archive = workspace.parent / "i"
    manifest = workspace.parent / "input-archive.json"
    if workspace in (archive, manifest):
        _fail("archive_workspace_role")
    _location(root, archive)
    return root, workspace, archive, manifest


def _archive_json(raw):
    def pairs(rows):
        result = {}
        for key, child in rows:
            if key in result:
                _fail("duplicate_archive_json_key")
            result[key] = child
        return result
    value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
        parse_constant=lambda _constant: _fail("nonfinite_archive_json"))
    _json_text(value).encode("utf-8", errors="strict")
    return value


def _write_archive_file(path, raw):
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _archive_observation(root, archive_ref, workspace):
    """Observe literal inputs; this does not authorize any model-workspace output."""
    _closed(archive_ref, {"path", "schema_version", "raw_digest"}, "archive_reference_fields")
    if archive_ref["schema_version"] != ARCHIVE:
        _fail("archive_reference_schema")
    _digest(archive_ref["raw_digest"], "archive_reference_digest")
    try:
        expected_locator = (Path(workspace).parent / "input-archive.json").relative_to(Path(root)).as_posix()
    except ValueError:
        _fail("archive_reference_locator")
    if archive_ref["path"] != expected_locator:
        _fail("archive_reference_locator")
    root, workspace, archive, manifest_path = _archive_paths(root, workspace)
    # A caller locator never selects a different file, even for metadata access.
    if archive_ref["path"] != manifest_path.relative_to(root).as_posix():
        _fail("archive_reference_locator")
    manifest_raw, manifest_identity = _read_plain(manifest_path)
    if _raw_digest(manifest_raw) != archive_ref["raw_digest"]:
        _fail("archive_manifest_raw_binding")
    manifest = _archive_json(manifest_raw)
    _closed(manifest, _ARCHIVE_FIELDS, "archive_manifest_fields")
    if (manifest["schema_version"] != ARCHIVE or manifest["protocol"] != PROTOCOL
            or manifest["workspace"] != workspace.relative_to(root).as_posix()
            or manifest["archive"] != archive.relative_to(root).as_posix()):
        _fail("archive_manifest_locations")
    rows = manifest["inputs"]
    if type(rows) is not list or len(rows) != 3:
        _fail("archive_input_inventory")
    for row in rows:
        _closed(row, {"name", "raw_digest", "byte_length"}, "archive_input_fields")
        _digest(row["raw_digest"], "archive_input_digest")
        if type(row["byte_length"]) is not int or row["byte_length"] < 0:
            _fail("archive_input_length")
    if [row["name"] for row in rows] != sorted(_INPUT_NAMES):
        _fail("archive_input_order_or_membership")
    if {path.name for path in archive.iterdir()} != _INPUT_NAMES:
        _fail("archive_not_input_only")
    # Record all actual members without granting or masking a single sidecar.
    # Core must still authenticate the entire real output inventory separately.
    members = tuple(sorted(path.name for path in workspace.iterdir()))
    if not _INPUT_NAMES <= set(members):
        _fail("archive_actual_inputs_missing")
    directories = {}
    for directory in (root, workspace, archive, manifest_path.parent):
        info = directory.lstat()
        directories[directory] = (info.st_dev, info.st_ino)
    observed, pins, input_files = {}, {}, {}
    for row in rows:
        name = row["name"]
        data, identity = _read_plain(archive / name)
        actual, actual_identity = _read_plain(workspace / name)
        if (len(data) != row["byte_length"] or _raw_digest(data) != row["raw_digest"] or actual != data):
            _fail("archive_original_input_bytes_changed")
        observed[name] = data
        pins[archive / name] = (data, identity)
        pins[workspace / name] = (actual, actual_identity)
        input_files[name] = {"raw_digest": row["raw_digest"], "byte_length": row["byte_length"]}
    schema = _archive_json(observed["output-schema.json"])
    envelope = _input_envelope_bytes(observed["input.json"])
    if type(schema) is not dict:
        _fail("archive_schema_not_object")
    reserve = manifest["measurement"].get("reserved_continuation_tokens") if type(manifest["measurement"]) is dict else None
    _envelope(envelope, reserve)
    model_prompt = _model_prompt(archive, archive / "prompt.txt", archive / "output.json")
    _text(model_prompt, "archive_model_prompt")
    full_request = _json_text({"prompt": model_prompt, "output_schema": schema})
    expected = {"request_sha256": _raw_digest(full_request.encode("utf-8")), "schema_digest": _identity(schema),
        "envelope_digest": _identity(envelope), "model_prompt_digest": _raw_digest(model_prompt.encode("utf-8"))}
    for key, digest in expected.items():
        if manifest[key] != digest:
            _fail("archive_" + key + "_binding")
    _measurement(manifest["measurement"], full_request, reserve)
    for path, (before, identity) in pins.items():
        after, after_identity = _read_plain(path)
        if before != after or identity != after_identity:
            _fail("archive_inputs_changed_during_observation")
    after_manifest, after_identity = _read_plain(manifest_path)
    if after_manifest != manifest_raw or after_identity != manifest_identity:
        _fail("archive_manifest_changed_during_observation")
    if ({path.name for path in archive.iterdir()} != _INPUT_NAMES
            or tuple(sorted(path.name for path in workspace.iterdir())) != members):
        _fail("archive_membership_changed_during_observation")
    _location(root, workspace)
    _location(root, archive)
    for directory, identity in directories.items():
        info = directory.lstat()
        if (info.st_dev, info.st_ino) != identity:
            _fail("archive_directory_changed_during_observation")
    paths = {"workspace": workspace, "prompt_path": workspace / "prompt.txt",
        "schema_path": workspace / "output-schema.json", "output_path": workspace / "output.json"}
    return {**paths, "paths": paths, "archive_ref": deepcopy(archive_ref), "archive_path": archive,
        "manifest_digest": archive_ref["raw_digest"], "model_prompt": model_prompt, "full_request": full_request,
        "request_sha256": expected["request_sha256"], "schema": schema, "envelope": envelope,
        "measurement": deepcopy(manifest["measurement"]), "envelope_digest": expected["envelope_digest"],
        "schema_digest": expected["schema_digest"], "input_files": input_files, "workspace_members": members}


def archive_request_inputs(root, rendered_request):
    """Permanently copy exactly three issued inputs outside the model workspace."""
    verify_rendered_request(root, rendered_request)
    root, workspace, archive, manifest_path = _archive_paths(root, rendered_request["workspace"])
    if os.path.lexists(archive) or os.path.lexists(manifest_path):
        _fail("input_archive_already_exists")
    state = _ISSUED[rendered_request]
    archive.mkdir(exist_ok=False)
    _location(root, archive)
    rows = []
    for name in sorted(_INPUT_NAMES):
        data = state["pins"][name][0]
        _write_archive_file(archive / name, data)
        rows.append({"name": name, "raw_digest": _raw_digest(data), "byte_length": len(data)})
    manifest = {"schema_version": ARCHIVE, "protocol": PROTOCOL,
        "workspace": workspace.relative_to(root).as_posix(), "archive": archive.relative_to(root).as_posix(),
        "inputs": rows, "request_sha256": rendered_request["request_sha256"],
        "envelope_digest": rendered_request["envelope_digest"], "schema_digest": rendered_request["schema_digest"],
        "model_prompt_digest": _raw_digest(rendered_request["model_prompt"].encode("utf-8")),
        "measurement": rendered_request["measurement"]}
    encoded = (_json_text(manifest) + "\n").encode("utf-8")
    _write_archive_file(manifest_path, encoded)
    reference = {"path": manifest_path.relative_to(root).as_posix(), "schema_version": ARCHIVE,
        "raw_digest": _raw_digest(encoded)}
    actual = _archive_observation(root, reference, workspace)
    if (actual["full_request"] != rendered_request["full_request"]
            or actual["schema_digest"] != rendered_request["schema_digest"]
            or actual["envelope_digest"] != rendered_request["envelope_digest"]):
        _fail("issued_request_archive_changed")
    verify_rendered_request(root, rendered_request)
    return reference


def verify_request_archive(root, *, archive_ref, workspace, request_identity):
    """Rebuild cold input from permanent bytes and compare the original claim.

    The core calls this owner directly with its actual immutable reservation.
    This fresh literal observation is not execution/output/semantic authority.
    """
    _closed(request_identity, _ARCHIVE_REQUEST_FIELDS, "archive_request_identity_fields")
    _json_text(request_identity)
    if _identity(request_identity["input_archive_ref"]) != _identity(archive_ref):
        _fail("archive_claim_reference")
    # Claim locators are role assertions, never caller-selected read targets.
    for key, name, version in (("request_ref", "prompt.txt", "newrouge.b-route-segmented-prompt.v1"),
            ("schema_ref", "output-schema.json", "newrouge.b-route-segmented-output-schema.v1")):
        reference = request_identity[key]
        _closed(reference, {"path", "schema_version", "raw_digest"}, "archive_claim_input_reference")
        try:
            expected = (Path(workspace) / name).relative_to(Path(root)).as_posix()
        except ValueError:
            _fail("archive_claim_input_path_or_bytes")
        if reference["path"] != expected or reference["schema_version"] != version:
            _fail("archive_claim_input_path_or_bytes")
        _digest(reference["raw_digest"], "archive_claim_input_digest")
    actual = _archive_observation(root, archive_ref, workspace)
    envelope = actual["envelope"]
    for key in ("protocol", "plan_digest", "node_id", "phase"):
        if request_identity[key] != envelope[key]:
            _fail("archive_claim_" + key)
    if (request_identity["request_sha256"] != actual["request_sha256"]
            or request_identity["schema_digest"] != actual["schema_digest"]
            or _identity(request_identity["input_measurement"]) != _identity(actual["measurement"])):
        _fail("archive_claim_wrapper_schema_or_measurement")
    reserve = request_identity["output_reserve"]
    if type(reserve) is not int or reserve != envelope["output_reserve"]:
        _fail("archive_claim_output_reserve")
    for key, name, version in (("request_ref", "prompt.txt", "newrouge.b-route-segmented-prompt.v1"),
            ("schema_ref", "output-schema.json", "newrouge.b-route-segmented-output-schema.v1")):
        reference = request_identity[key]
        _closed(reference, {"path", "schema_version", "raw_digest"}, "archive_claim_input_reference")
        expected = (actual["workspace"] / name).relative_to(Path(root)).as_posix()
        if (reference["path"] != expected or reference["schema_version"] != version
                or reference["raw_digest"] != actual["input_files"][name]["raw_digest"]):
            _fail("archive_claim_input_path_or_bytes")
    _measurement(request_identity["input_measurement"], actual["full_request"], reserve)
    return actual
