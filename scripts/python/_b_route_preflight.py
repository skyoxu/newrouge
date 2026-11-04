"""Read-only migration preview over original bytes and explicit external intents.

No normalization, ID allocation, semantic approval, publication or recovery runs
here. The five Story 1.5 authorization fields always remain false.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Any, Callable

import _b_route_codec as codec
import _b_route_inventory as inventory
import _b_route_protection as protection
import _b_route_records as records
from _b_route_record_owners import resolve_owned_ref

SCHEMA = "newrouge.b-route-migration-preflight.v1"
INTENTS_VERSION = "newrouge.b-route-preflight-intents.v1"
PROTECTION_VERSION = "newrouge.b-route-protection-input.v1"
ADR = "docs/adr/ADR-0040-b-route-stages-authority-and-activation.md"
GOVERNANCE = ("docs/planning/b-route/policy.v1.json", records.CATALOG_PATH,
              "docs/planning/b-route/task-origins.v1.json")
PENDING = "docs/planning/semantic-topology/capability-apply.pending.json"


def fail(code, path, expected, actual, entity=None):
    raise codec.CodecError(codec.Diagnostic(code, codec.Stage.BUNDLE,
        str(entity) if entity is not None else None,
        {"path": path, "value": expected}, {"path": path, "value": actual}, path))


def shape(value, fields, path):
    if type(value) is not dict or set(value) != set(fields):
        fail(codec.ReasonCode.INVALID_TYPE, path, sorted(fields), "missing or unknown fields")


def text(value, path):
    if type(value) is not str or not value.strip() or value != value.strip():
        fail(codec.ReasonCode.INVALID_TYPE, path, "nonempty unpadded string", value)
    return value


def path(value):
    try:
        inventory.canonical_path(value, allow_logs=True)
    except (TypeError, ValueError):
        fail(codec.ReasonCode.UNSAFE_PATH, str(value), "canonical repository-relative POSIX path", value)
    return value


def digest(value, location):
    return protection._checked_digest(value, location)


class Observations:
    """Cache every successful or absent observation and re-read before output."""
    def __init__(self, root):
        self.root = Path(root).absolute()
        self.values: dict[str, bytes | None] = {}
        self.errors: dict[str, dict] = {}
        self.directories: dict[str, list[str]] = {}

    def read(self, source, *, optional=False):
        source = path(source)
        try:
            inventory.safe_input(self.root, source, allow_logs=True)
            data = codec.read_reference_bytes(self.root, source)
        except codec.CodecError as error:
            # Only a proved missing path is a legal absence observation.
            if error.diagnostic.reason_code == codec.ReasonCode.FILE_NOT_FOUND:
                data = None
                if source in self.values and self.values[source] is not None:
                    fail(codec.ReasonCode.FILE_CHANGED, source, "original bytes", "now missing")
                self.values[source] = None
                if optional:
                    return None
            self.errors[source] = error.diagnostic.to_dict()
            raise
        except (OSError, ValueError) as error:
            fail(codec.ReasonCode.UNSAFE_PATH, source, "safe contained regular file", type(error).__name__)
        if source in self.values and self.values[source] != data:
            fail(codec.ReasonCode.FILE_CHANGED, source, "same original bytes", "changed on repeated read")
        self.values[source] = data
        return data

    def json(self, source):
        return codec.strict_json_loads(self.read(source))

    def scan(self, directory):
        """Record membership too, so newly added governance cannot evade drift."""
        directory = path(directory)
        result = []
        candidate = inventory.safe_input(self.root, directory, allow_logs=True)
        # safe_input checked the caller's spelling and every original ancestor
        # before resolving the physical anchor (including Windows 8.3 aliases).
        physical_root = self.root.resolve(strict=True)
        if candidate.exists():
            inventory.no_reparse(candidate)
            if not candidate.is_dir():
                fail(codec.ReasonCode.INVALID_TYPE, directory, "directory", "non-directory")
            def traversal_error(error):
                fail(codec.ReasonCode.READ_ERROR, directory, "readable complete directory membership", type(error).__name__)
            for current, dirs, files in os.walk(candidate, followlinks=False, onerror=traversal_error):
                for name in dirs + files:
                    inventory.no_reparse(Path(current, name))
                for name in files:
                    source = (Path(current) / name).relative_to(physical_root).as_posix()
                    result.append(source)
        result.sort()
        if directory in self.directories and self.directories[directory] != result:
            fail(codec.ReasonCode.FILE_CHANGED, directory, self.directories[directory], result)
        self.directories[directory] = result
        return result

    def finish(self):
        diagnostics = []
        for source, before in list(self.values.items()):
            try:
                after = self.read(source, optional=before is None)
                if after != before:
                    fail(codec.ReasonCode.FILE_CHANGED, source, "original observation", "changed")
            except codec.CodecError as error:
                diagnostics.append(error.diagnostic.to_dict())
        for source in list(self.errors):
            if source in self.values:
                continue
            try:
                self.read(source, optional=True)
            except codec.CodecError as error:
                if error.diagnostic.to_dict() == self.errors[source]:
                    continue
            diagnostics.append(codec.Diagnostic(codec.ReasonCode.FILE_CHANGED, codec.Stage.BUNDLE,
                expected={"path": source, "value": "same failed observation"},
                actual="changed observation", resume_ref=source).to_dict())
        for directory in list(self.directories):
            try:
                self.scan(directory)
            except (codec.CodecError, OSError, ValueError) as error:
                diagnostics.append(error.diagnostic.to_dict() if isinstance(error, codec.CodecError)
                    else codec.Diagnostic(codec.ReasonCode.FILE_CHANGED, codec.Stage.BUNDLE,
                        expected=directory, actual="directory changed", resume_ref=directory).to_dict())
        return diagnostics

    def identities(self):
        return [{"path": key, "exists": value is not None,
                 "raw_digest": codec.raw_digest(value) if value is not None else None}
                for key, value in sorted(self.values.items())]


def owned(value, observations):
    def contracts():
        return {source: observations.read(source) for source in observations.scan("Game.Core/Contracts")
                if source.endswith(".cs")}
    return resolve_owned_ref(value, read_bytes=observations.read, contract_sources=contracts, path_key=path)


def _binding(value, observations, *, allow_missing=False):
    shape(value, {"path", "raw_digest"}, "input binding")
    source = path(value["path"])
    expected = value["raw_digest"]
    data = observations.read(source, optional=allow_missing)
    if expected is not None:
        digest(expected, source)
    if expected is None and not allow_missing:
        fail(codec.ReasonCode.INVALID_DIGEST, source, "original raw digest", None)
    actual = codec.raw_digest(data) if data is not None else None
    if expected != actual:
        fail(codec.ReasonCode.INPUT_STALE, source, expected, actual)
    return source


def _load_protection(observations, source, epics, diagnostics):
    value = observations.json(source)
    if type(value) is not dict or value.get("document_version") != PROTECTION_VERSION:
        fail(codec.ReasonCode.UNKNOWN_SCHEMA, source, PROTECTION_VERSION,
             value.get("document_version") if type(value) is dict else type(value).__name__)
    definition = value.get("definition", {})
    if (definition.get("projection_codec") != codec.PROJECTION_CODEC
            or definition.get("content_codec") != codec.CODEC_VERSION
            or definition.get("mutable_allowlist") != ["Task.status", "Task.subtasks[].status"]):
        fail(codec.ReasonCode.UNKNOWN_CODEC_VERSION, source, "Story 1.5 exact definition projection", definition)
    if not protection._same_json(value.get("authorization"), protection.AUTHORIZATION):
        fail(codec.ReasonCode.CONFLICT, source, protection.AUTHORIZATION, value.get("authorization"))
    for key in ("inventory_ref", "snapshot_ref", "task_definitions_ref", "triplet_definition_ref",
                "raw_archive_index_ref", "frozen_a_candidates_ref", "historical_inventory_ref"):
        if key in value:
            owned(value[key], observations)
    for key in ("manifest_refs",):
        if type(value.get(key)) is not list:
            fail(codec.ReasonCode.INVALID_TYPE, source, key + " array", value.get(key))
        for reference in value[key]:
            owned(reference, observations)
    for reference in value.get("rules_refs", []):
        if type(reference) is not dict or not {"path", "raw_digest"} <= set(reference):
            fail(codec.ReasonCode.INVALID_REFERENCE, source, "rule identity", reference)
        _binding({key: reference[key] for key in ("path", "raw_digest")}, observations)
    if type(value.get("review")) is not dict or "evidence_ref" not in value["review"]:
        fail(codec.ReasonCode.INVALID_REFERENCE, source, "external review locator", "missing review")
    owned(value["review"]["evidence_ref"], observations)
    snapshot_ref, inv_ref = value.get("snapshot_ref"), value.get("inventory_ref")
    if snapshot_ref is None or inv_ref is None:
        fail(codec.ReasonCode.MISSING_REQUIRED_FIELD, source, "snapshot and inventory references", None)
    snapshot_path = snapshot_ref["ref"].split("#", 1)[0]
    snapshot, report, _raw = protection._load_snapshot(observations.root, snapshot_path)
    parent = snapshot_path.rsplit("/", 1)[0]
    observations.read(parent + "/inventory.json")
    for row in snapshot["raw_files"]:
        if row["exists"]:
            archived = observations.read(parent + "/" + row["artifact"])
            if codec.raw_digest(archived) != row["raw_digest"]:
                fail(codec.ReasonCode.DIGEST_MISMATCH, row["path"], row["raw_digest"], codec.raw_digest(archived))
    if report.get("epics") != epics or snapshot["inventory"]["raw_digest"] != inv_ref["files"][0]["raw_digest"]:
        fail(codec.ReasonCode.CONFLICT, source, "same explicit epics and archived inventory", "different bound inputs")
    for row in report["inputs"]:
        data = observations.read(row["path"], optional=True)
        actual = codec.raw_digest(data) if data is not None else None
        # Status progress is allowed; all other current differences are displayed
        # separately. Historical incomplete evidence remains a real blocker.
        if actual != row["raw_sha256"] and row["exists"] and data is None:
            diagnostics.append(codec.Diagnostic(codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.BUNDLE,
                expected={"path": row["path"], "value": row["raw_sha256"]},
                actual="required original missing", resume_ref=row["path"]).to_dict())
    zero_task_manifest_absence = (not snapshot["tasks"] and not snapshot["cumulative"]
        and bool(report["diagnostics"]) and all(row.get("severity") != "error" or row.get("code") == "missing-manifests"
            for row in report["diagnostics"]))
    if snapshot["capture_complete"] is not True and not zero_task_manifest_absence:
        diagnostics.append(codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE, codec.Stage.BUNDLE,
            expected="complete protection capture", actual=report["diagnostics"], resume_ref=snapshot_path).to_dict())
    for row in report["inputs"]:
        if row["exists"] is False and any(item.get("severity") == "error" and item.get("location", "").split("#", 1)[0] == row["path"] for item in report["diagnostics"]):
            diagnostics.append(codec.Diagnostic(codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.BUNDLE,
                expected={"path": row["path"], "value": "required historical original"},
                actual=None, resume_ref=row["path"]).to_dict())
    return value, snapshot, report


def _carrier(observations, source):
    value = observations.json(source)
    shape(value, {"records"}, source)
    if type(value["records"]) is not list:
        fail(codec.ReasonCode.INVALID_TYPE, source, "records array", value["records"])
    result, sources, seen = {}, {}, set()
    for row in value["records"]:
        shape(row, {"path", "source_path"}, source)
        logical, original = path(row["path"]), path(row["source_path"])
        if logical.casefold() in seen:
            fail(codec.ReasonCode.CONFLICT, source, "unique logical paths ignoring case", logical)
        seen.add(logical.casefold())
        # A carrier describes bytes only. Registered sources can live outside
        # docs; containment is enforced without inventing a private source root.
        result[logical] = observations.read(original)
        sources[logical] = original
    return result, sources


def _references(observations, candidate):
    """Collect the explicit candidate reference closure through observed reads.

    The unique record service still owns typed-reference and bundle validation.
    Pre-catalog single records do not claim cross-record consistency.
    """
    visited = set()
    def read(source):
        source = path(source)
        observations.read(source, optional=True)  # The current target is observed even for a new candidate.
        return candidate[source] if source in candidate else observations.read(source)
    def contracts():
        paths = set(observations.scan("Game.Core/Contracts")) | set(candidate)
        return {source: read(source) for source in paths
                if source.startswith("Game.Core/Contracts/") and source.endswith(".cs")}
    def visit(source):
        if source in visited:
            return
        visited.add(source)
        raw = read(source)
        if not records._managed_candidate(source):
            return
        result = records.validate_record(raw, path=source)
        if not result.ok:
            raise codec.CodecError(result.diagnostic)
        for child in records._walk(codec.strict_json_loads(raw)):
            if type(child) is not dict:
                continue
            if set(child) == {"owner", "ref", "files"}:
                resolve_owned_ref(child, read_bytes=read, contract_sources=contracts, path_key=path)
            elif set(child) == {"path", "schema_version", "entity_id", "revision", "digest", "verification_mode", "codec_version"}:
                visit(child["path"])
    for source in candidate:
        if records._managed_candidate(source):
            visit(source)


def _task_entities(documents, locations):
    tasks, _views = protection._join(documents)
    result = {}
    for task_id, task in tasks.items():
        definition, state, locators = {}, {}, []
        for name, document in documents.items():
            rows = document["master"]["tasks"] if name == "master" else document
            selected = [(index, row) for index, row in enumerate(rows)
                        if (row["id"] if name == "master" else row["taskmaster_id"]) == task_id]
            definition[name] = [protection.task_definition_projection(row) for _, row in selected]
            state[name] = [protection._task_state(row, master=name == "master") for _, row in selected]
            for index, _row in selected:
                locators.append({"path": inventory.TRIPLET[name], "json_pointer":
                    ("/master/tasks/" if name == "master" else "/") + str(index),
                    "raw_digest": codec.raw_digest(locations[name])})
        result[task_id] = {"definition": definition, "state": state, "locators": locators}
    return result


def _state_preserved(before, after):
    if after is None:
        return False
    for view, old_rows in before.items():
        new_rows = after.get(view, [])
        if len(new_rows) < len(old_rows):
            return False
        for old, new in zip(old_rows, new_rows):
            if old["status"] != new["status"] or not protection._same_json(new["subtasks"][:len(old["subtasks"])], old["subtasks"]):
                return False
    return True


def _file_locator(source, data):
    return [] if data is None else [{"path": source, "json_pointer": "", "raw_digest": codec.raw_digest(data)}]


def _change(kind, entity, left, right, before, after, category):
    operation = "new" if left is None else "retire" if right is None else (
        "reuse" if codec.canonical_digest(left) == codec.canonical_digest(right) else "update")
    return {"entity_type": kind, "entity_id": entity, "category": category, "operation": operation,
        "before": before, "after": after,
        "before_definition_digest": codec.canonical_digest(left) if left is not None else None,
        "after_definition_digest": codec.canonical_digest(right) if right is not None else None}


def _changes(observations, candidate):
    before_raw = {name: observations.read(source) for name, source in inventory.TRIPLET.items()}
    provided = set(candidate) & set(inventory.TRIPLET.values())
    if provided and provided != set(inventory.TRIPLET.values()):
        fail(codec.ReasonCode.MAPPING_MISMATCH, None, "all three complete candidate Task files", sorted(provided))
    after_raw = {name: candidate.get(source, before_raw[name]) for name, source in inventory.TRIPLET.items()}
    before_docs = {name: codec.strict_json_loads(raw) for name, raw in before_raw.items()}
    after_docs = {name: codec.strict_json_loads(raw) for name, raw in after_raw.items()}
    old, new = _task_entities(before_docs, before_raw), _task_entities(after_docs, after_raw)
    changes, diagnostics = [], []
    for task_id in sorted(set(old) | set(new)):
        left, right = old.get(task_id), new.get(task_id)
        row = _change("task", task_id, left["definition"] if left else None, right["definition"] if right else None,
                      left["locators"] if left else [], right["locators"] if right else [], "task")
        row["before_state"] = left["state"] if left else None
        row["after_state"] = right["state"] if right else None
        changes.append(row)
        if left is not None and not _state_preserved(left["state"], right["state"] if right else None):
            diagnostics.append(codec.Diagnostic(codec.ReasonCode.CONFLICT, codec.Stage.BUNDLE, str(task_id),
                {"value": "preserved mature identity and every current Task/subtask status", "state": left["state"]},
                right["state"] if right else "mature Task removed", inventory.TRIPLET["master"]).to_dict())
        if left and right:
            for name in inventory.TRIPLET:
                a, b = left["definition"][name], right["definition"][name]
                # Business IDs and joins remain stable for every mature row.
                for original in a:
                    target = next((item for item in b if item["id"] == original["id"]), None)
                    if target is None:
                        diagnostics.append(codec.Diagnostic(codec.ReasonCode.MAPPING_MISMATCH, codec.Stage.BUNDLE,
                            str(task_id), original["id"], "mature business identity removed", inventory.TRIPLET[name]).to_dict())
                        continue
                    for field in ("history", "history_refs", "evidence_refs"):
                        if field in original:
                            old_value, new_value = original[field], target.get(field)
                            retained = (type(old_value) is list and type(new_value) is list
                                and (protection._same_json(new_value[:len(old_value)], old_value) if field == "history"
                                    else all(any(protection._same_json(item, candidate) for candidate in new_value) for item in old_value))) or protection._same_json(old_value, new_value)
                            if not retained:
                                diagnostics.append(codec.Diagnostic(codec.ReasonCode.CONFLICT, codec.Stage.BUNDLE,
                                    str(task_id), {"field": field, "value": old_value}, new_value, inventory.TRIPLET[name]).to_dict())
    # Envelope/order changes are definitions as well, never normalized away.
    old_projection = protection.triplet_definition_projection(before_docs)
    new_projection = protection.triplet_definition_projection(after_docs)
    old_envelope = {name: value for name, value in old_projection.items()}
    new_envelope = {name: value for name, value in new_projection.items()}
    for env, docs in ((old_envelope, before_docs), (new_envelope, after_docs)):
        env["master"] = {key: value for key, value in env["master"].items() if key != "master"} | {
            "master": {key: value for key, value in env["master"]["master"].items() if key != "tasks"}}
        env["order"] = {name: [item["id"] for item in
            (doc["master"]["tasks"] if name == "master" else doc)] for name, doc in docs.items()}
        env.pop("back"); env.pop("gameplay")
    if not protection._same_json(old_envelope, new_envelope):
        changes.append(_change("file", "task-triplet-envelope", old_envelope, new_envelope,
            [_file_locator(source, before_raw[name])[0] for name, source in inventory.TRIPLET.items()],
            [_file_locator(source, after_raw[name])[0] for name, source in inventory.TRIPLET.items()], "task-envelope"))
    for source, raw in sorted(candidate.items()):
        if source in inventory.TRIPLET.values():
            continue
        current = observations.read(source, optional=True)
        def decode(data):
            return codec.strict_json_loads(data) if source.endswith(".json") else data.decode("utf-8", errors="strict")
        category = "manifest" if source.startswith("docs/testing/mvg/") else "object" if records._managed_candidate(source) else "source"
        if category == "manifest" or source == inventory.SOURCE_SET:
            native = decode(raw)
            expected_schema = "newrouge.mvg-integration.v1" if category == "manifest" else "chapter3.source-set.v1"
            if type(native) is not dict or native.get("schema_version") != expected_schema:
                fail(codec.ReasonCode.UNKNOWN_SCHEMA, source, expected_schema,
                     native.get("schema_version") if type(native) is dict else type(native).__name__)
        if category == "object" and current is not None and not protection._same_json(decode(current), decode(raw)):
            old_schema, old_id, old_revision = codec._record_identity(decode(current))
            new_schema, new_id, new_revision = codec._record_identity(decode(raw))
            immutable = source.startswith(tuple(records.BASE + kind + "/" for kind in ("plans", "bindings", "commits")))
            if immutable or old_schema != new_schema or old_id != new_id or new_revision <= old_revision:
                diagnostics.append(codec.Diagnostic(codec.ReasonCode.CONFLICT, codec.Stage.BUNDLE, str(old_id),
                    {"value": "immutable revisions; mutable governance retains identity and advances revision", "path": source,
                     "revision": old_revision}, {"immutable": immutable, "entity_id": new_id, "revision": new_revision}, source).to_dict())
        changes.append(_change("file", source, decode(current) if current is not None else None, decode(raw),
            _file_locator(source, current), _file_locator(source, raw), category))
        if category == "manifest":
            before_manifest, after_manifest = decode(current) if current is not None else {}, decode(raw)
            if type(after_manifest) is not dict:
                fail(codec.ReasonCode.INVALID_TYPE, source, "manifest object", type(after_manifest).__name__)
            for section in ("flows", "tests"):
                indexed = []
                for document in (before_manifest, after_manifest):
                    values = document.get(section, [])
                    if type(values) is not list or any(type(item) is not dict or type(item.get("id")) is not str
                            or not item["id"] for item in values):
                        fail(codec.ReasonCode.INVALID_TYPE, source, "manifest rows with explicit string IDs", section)
                    if len({item["id"] for item in values}) != len(values):
                        fail(codec.ReasonCode.CONFLICT, source, "unique cumulative obligation IDs", section)
                    indexed.append({item["id"]: (index, item) for index, item in enumerate(values)})
                left_rows, right_rows = indexed
                for entity in sorted(set(left_rows) | set(right_rows)):
                    left, right = left_rows.get(entity), right_rows.get(entity)
                    if left and right and protection._same_json(left[1], right[1]):
                        continue
                    def locator(row, data):
                        return [] if row is None else [{"path": source, "json_pointer": "/" + section + "/" + str(row[0]),
                            "raw_digest": codec.raw_digest(data)}]
                    changes.append(_change("obligation", source + "#/" + section + "/" + entity,
                        left[1] if left else None, right[1] if right else None,
                        locator(left, current), locator(right, raw), "cumulative-" + section))
        if source == inventory.SOURCE_SET and current is not None:
            before_sources, after_sources = decode(current), decode(raw)
            removed = sorted(set(before_sources.get("active_sources", [])) - set(after_sources.get("active_sources", [])))
            if removed:
                diagnostics.append(codec.Diagnostic(codec.ReasonCode.SEMANTIC_ERROR, codec.Stage.BUNDLE,
                    source, "independent source-backed source retirement review", removed, source).to_dict())
    return changes, diagnostics, before_docs, after_docs


def _intents(observations, source, epics, protection_input, inventory_path, candidate, changes):
    value = observations.json(source)
    shape(value, {"document_version", "scope_id", "inputs", "changes", "unresolved"}, source)
    if value["document_version"] != INTENTS_VERSION:
        fail(codec.ReasonCode.UNKNOWN_SCHEMA, source, INTENTS_VERSION, value["document_version"])
    scope = text(value["scope_id"], source)
    shape(value["inputs"], {"epics", "protection_input", "inventory", "targets"}, source)
    for key, expected in (("epics", epics), ("protection_input", protection_input), ("inventory", inventory_path)):
        if _binding(value["inputs"][key], observations) != expected:
            fail(codec.ReasonCode.CONFLICT, source, expected, value["inputs"][key])
    targets = value["inputs"]["targets"]
    if type(targets) is not list:
        fail(codec.ReasonCode.INVALID_TYPE, source, "target bindings array", targets)
    seen = set()
    for binding in targets:
        target = _binding(binding, observations, allow_missing=True)
        if target.casefold() in seen:
            fail(codec.ReasonCode.CONFLICT, source, "unique target bindings", target)
        seen.add(target.casefold())
    required = set(candidate) | set(inventory.TRIPLET.values())
    if seen != {item.casefold() for item in required}:
        fail(codec.ReasonCode.MAPPING_MISMATCH, source, sorted(required), sorted(seen))
    if type(value["changes"]) is not list or type(value["unresolved"]) is not list:
        fail(codec.ReasonCode.INVALID_TYPE, source, "changes/unresolved arrays", "invalid arrays")
    index = {(row["entity_type"], row["entity_id"]): row for row in changes}
    found, reviews, diagnostics = set(), [], []
    for intent in value["changes"]:
        shape(intent, {"scope_id", "entity_type", "entity_id", "operation", "before", "after",
                       "source_refs", "reason", "review_ref", "unresolved"}, source)
        if intent["scope_id"] != scope or intent["entity_type"] not in ("task", "file", "obligation"):
            fail(codec.ReasonCode.INVALID_REFERENCE, source, "same scope and task/file/obligation entity", intent)
        entity = intent["entity_id"]
        if intent["entity_type"] == "task":
            codec.validate_task_id(entity)
        else:
            text(entity, source)
        key = (intent["entity_type"], entity)
        if key in found or key not in index:
            fail(codec.ReasonCode.CONFLICT, source, "one declaration per actual entity", entity, entity)
        found.add(key)
        actual = index[key]
        if intent["operation"] not in ("reuse", "update", "new", "retire") or intent["operation"] != actual["operation"]:
            fail(codec.ReasonCode.CONFLICT, source, actual["operation"], intent["operation"], entity)
        for field in ("before", "after"):
            if not protection._same_json(intent[field], actual[field]):
                fail(codec.ReasonCode.DIGEST_MISMATCH, source, actual[field], intent[field], entity)
        text(intent["reason"], source)
        if type(intent["source_refs"]) is not list or not intent["source_refs"] or type(intent["unresolved"]) is not list:
            fail(codec.ReasonCode.INVALID_REFERENCE, source, "nonempty sources and unresolved array", intent, entity)
        for reference in intent["source_refs"]:
            owned(reference, observations)
        owned(intent["review_ref"], observations)
        reviews.append({"entity_type": key[0], "entity_id": entity, "operation": intent["operation"],
            "reason": intent["reason"], "source_refs": intent["source_refs"], "review_ref": intent["review_ref"],
            "locator_and_digest_verified": True, "source_semantics_verified": False,
            "external_review_verified": False, "unresolved": intent["unresolved"]})
        if intent["unresolved"]:
            diagnostics.append(codec.Diagnostic(codec.ReasonCode.SEMANTIC_ERROR, codec.Stage.BUNDLE,
                str(entity), "resolved external intent", intent["unresolved"], source).to_dict())
    mandatory = {key for key, row in index.items() if row["operation"] != "reuse"}
    # Candidate-supplied reuse must be declared; unaffected current Tasks need not.
    mandatory |= {key for key, row in index.items() if row["entity_type"] == "file"
                  or any(loc["path"] in candidate for loc in row["after"])}
    if not mandatory <= found:
        fail(codec.ReasonCode.MISSING_REQUIRED_FIELD, source, "declarations for every actual candidate change",
             sorted([str(key) for key in mandatory - found]))
    if value["unresolved"]:
        diagnostics.append(codec.Diagnostic(codec.ReasonCode.SEMANTIC_ERROR, codec.Stage.BUNDLE,
            scope, "resolved external input", value["unresolved"], source).to_dict())
    return scope, reviews, diagnostics


def _governance(observations, candidate, documents):
    current = {source: observations.read(source, optional=True) for source in GOVERNANCE}
    discovered = observations.scan("docs/planning/b-route")
    traces = [source for source in discovered if records._managed_candidate(source)]
    for source in traces:
        observations.read(source)
    task_trace = any(type(row) is dict and any("b_route" in key or key in ("plan_refs", "binding_refs")
                     for key in row) for docs in documents.values()
                     for row in (docs["master"]["tasks"] if type(docs) is dict else docs))
    adr = observations.read(ADR, optional=True)
    authority_body = "\n".join(line for _, line in inventory.markdown_status_lines(
        adr.decode("utf-8", errors="strict"))) if adr is not None else ""
    statuses = []
    for line in authority_body.splitlines():
        declaration = re.match(r"^\s*(?:[-*]\s+)?(?:\*\*)?(?:status|状态)(?:\*\*)?\s*[:：]\s*(.+?)\s*$", line, re.I)
        if declaration:
            statuses.append(declaration[1].strip("* ").casefold())
    explicit = set(statuses) == {"accepted"} and all(fragment in authority_body for fragment in
        ("本文不冻结 A、不切换默认 B、不退出 A", "迁移启用前沿显式原入口执行当前 A"))
    diagnostics = []
    if not traces and not task_trace and all(raw is None for raw in current.values()) and explicit:
        state = "explicitly_not_enabled"
    elif any(raw is None for raw in current.values()):
        state = "unknown_or_damaged"
        for source, raw in current.items():
            if raw is None:
                diagnostics.append(codec.Diagnostic(codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
                    codec.Stage.BUNDLE, expected={"path": source, "value": "governance required after traces"},
                    actual=None, resume_ref=source).to_dict())
    else:
        state = "structure_valid_publication_unverified"
        for source in traces:
            result = records.validate_record(observations.read(source), path=source)
            if not result.ok:
                diagnostics.append(result.diagnostic.to_dict())
                state = "unknown_or_damaged"
    if not explicit and not traces and not task_trace:
        state = "unknown_or_damaged"
        diagnostics.append(codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE, codec.Stage.BUNDLE,
            expected="explicit not-enabled authority", actual="authority unavailable", resume_ref=ADR).to_dict())
    if state == "unknown_or_damaged":
        for source in traces:
            check = records.validate_record(observations.read(source), path=source)
            if not check.ok:
                diagnostics.append(check.diagnostic.to_dict())
    if state == "structure_valid_publication_unverified":
        originals = {source: observations.read(source) for source in traces}
        _references(observations, originals)
        closure = {source: raw for source, raw in observations.values.items() if raw is not None}
        checked = records.validate_bundle(closure, root=None, task_join=records.TaskJoinContext(**documents))
        if not checked.ok:
            state = "unknown_or_damaged"
            diagnostics.append(checked.diagnostic.to_dict())
    origin_path = GOVERNANCE[2]
    if current[origin_path] is not None and origin_path in candidate:
        old, new = codec.strict_json_loads(current[origin_path]), codec.strict_json_loads(candidate[origin_path])
        for original in old.get("tasks", []):
            after = next((row for row in new.get("tasks", []) if row.get("task_id") == original["task_id"]), None)
            for field in ("source_refs", "plan_refs", "binding_refs"):
                if after is None or not set(codec.canonical_digest(item) for item in original[field]) <= set(
                        codec.canonical_digest(item) for item in after[field]):
                    diagnostics.append(codec.Diagnostic(codec.ReasonCode.MAPPING_MISMATCH, codec.Stage.BUNDLE,
                        str(original["task_id"]), {"value": "retained B membership", "field": field},
                        after, origin_path).to_dict())
    return {"state": state, "authority_ref": ADR if explicit else None,
            "governance_traces": traces, "committed_verified": False, "activation_authorized": False}, diagnostics


def _current_inventory(observations, epics, *, zero_task_manifest_absence):
    """Reuse the Story 1.1 owner for the current closure, not the old archive.

    Snapshot owns epics/source-set resolution, Task locators, discovery and
    cumulative manifest validation. The preflight only adapts its observations
    and diagnostics to the shared six-field interface.
    """
    current = inventory.Snapshot(observations.root, epics).collect()
    diagnostics = []
    for row in current["inputs"]:
        try:
            raw = observations.read(row["path"], optional=True)
            actual = codec.raw_digest(raw) if raw is not None else None
            if actual != row["raw_sha256"]:
                fail(codec.ReasonCode.FILE_CHANGED, row["path"], row["raw_sha256"], actual)
        except codec.CodecError as error:
            diagnostics.append(error.diagnostic.to_dict())
    locations = {}
    for row in current["task_and_manifest_references"]:
        if row.get("path"):
            locations.setdefault(row["path"], []).append((row["owner_file"], row["json_pointer"],
                row.get("master_id") if row.get("master_id") is not None else row.get("task_id")))
    for index, source in enumerate(current["canonical_inputs"] or []):
        locations.setdefault(source, []).append((epics, "/frontmatter/inputDocuments/" + str(index), None))
    source_set = current["source_set"]["document"]
    if type(source_set) is dict and type(source_set.get("active_sources")) is list:
        for index, source in enumerate(source_set["active_sources"]):
            if type(source) is str:
                locations.setdefault(source, []).append((inventory.SOURCE_SET, "/active_sources/" + str(index), None))
    lawful_absence = (zero_task_manifest_absence and not current["manifests"]
        and not protection._join(current["tasks"]["documents"])[0])
    for issue in current["diagnostics"]:
        if issue["severity"] != "error" or lawful_absence and issue["code"] == "missing-manifests":
            continue
        reason = {"missing-input": codec.ReasonCode.FILE_NOT_FOUND,
            "invalid-json": codec.ReasonCode.INVALID_JSON,
            "invalid-reference": codec.ReasonCode.INVALID_REFERENCE,
            "invalid-reference-locator": codec.ReasonCode.UNRESOLVED_REFERENCE,
            "unsafe-or-unreadable-input": codec.ReasonCode.READ_ERROR,
            "git-drift-within-pass": codec.ReasonCode.FILE_CHANGED}.get(
                issue["code"], codec.ReasonCode.SCHEMA_VALIDATION_FAILED)
        source = issue["location"]
        for owner, pointer, entity in locations.get(source, [(source, "", None)]):
            diagnostics.append(codec.Diagnostic(reason, codec.Stage.BUNDLE,
                str(entity) if entity is not None else None,
                {"path": source, "owner_file": owner, "json_pointer": pointer,
                 "value": "valid current input under the Story 1.1 owning rules"},
                {"code": issue["code"], "message": issue["message"]},
                owner + ("#" + pointer if pointer else "")).to_dict())
    closure = {"inputs": [{"path": row["path"], "exists": row["exists"], "raw_digest": row["raw_sha256"]}
                          for row in current["inputs"]],
        "discovery": [list(row) for row in current["discovery"]], "canonical_inputs": current["canonical_inputs"],
        "source_set": current["source_set"], "references": current["task_and_manifest_references"],
        "manifest_paths": [row["path"] for row in current["manifests"]]}
    summary = {"content_identity": codec.canonical_digest(closure),
        "input_paths": [row["path"] for row in current["inputs"]],
        "canonical_source_paths": current["canonical_inputs"],
        "active_source_paths": current["source_set"]["resolved_active_sources"],
        "manifest_paths": closure["manifest_paths"], "references": closure["references"],
        "lawful_absences": ["no cumulative Task manifest in a verified original zero-Task repository"]
            if lawful_absence else [], "owning_diagnostics": current["diagnostics"]}
    return current, summary, diagnostics


def _pending(observations):
    raw = observations.read(PENDING, optional=True)
    if raw is None:
        return {"state": "absent", "scope": None, "resume_ref": None}, []
    marker = codec.strict_json_loads(raw)
    shape(marker, {"run_id", "journal_path"}, PENDING)
    run_id = text(marker["run_id"], PENDING)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", run_id) is None:
        fail(codec.ReasonCode.INVALID_ARGUMENT, PENDING, "portable original Capability run ID", run_id)
    journal_path = path(marker["journal_path"])
    journal = observations.json(journal_path)
    if type(journal) is not dict or journal.get("schema_version") != "newrouge.planning-apply-journal.v1":
        fail(codec.ReasonCode.UNKNOWN_SCHEMA, journal_path, "newrouge.planning-apply-journal.v1", "unknown old journal")
    # The old journal does not contain scope_id. Inspect every original target
    # and authority but never invent scope or call its recovery writer.
    if type(journal.get("entries")) is not list or type(journal.get("authority_inputs")) is not dict:
        fail(codec.ReasonCode.INVALID_TYPE, journal_path, "old journal entries and authority inputs", "damaged journal")
    for row in journal["entries"]:
        if type(row) is not dict or "path" not in row:
            fail(codec.ReasonCode.INVALID_TYPE, journal_path, "old target row", row)
        observations.read(path(row["path"]), optional=True)
    for source in journal["authority_inputs"]:
        observations.read(path(source), optional=True)
    resume = "py -3 scripts/python/dev_cli.py plan-capabilities --stage apply --run-id " + run_id + " --confirm"
    diagnostic = codec.Diagnostic(codec.ReasonCode.PENDING, codec.Stage.BUNDLE, run_id,
        "resolved original Capability apply; old journal has no scope_id",
        {"marker": PENDING, "journal_path": journal_path, "scope": "unknown"}, resume).to_dict()
    return {"state": "pending_unknown_scope", "scope": None, "run_id": run_id,
            "journal_path": journal_path, "resume_ref": resume}, [diagnostic]


def preflight(root: Path, epics: str, protection_input: str, candidate_path: str, intents_path: str,
              *, before_reread: Callable[[], None] | None = None) -> dict:
    """Return a preview; the optional callback is an explicit fault-test seam."""
    observations = Observations(root)
    current_inventory = None
    zero_task_manifest_absence = False
    result = {"schema_version": SCHEMA, "ok": False, "claim": "read_only_migration_preview",
        "scope_id": None, "changes": [], "cumulative_changes": [], "protection_to_current": None,
        "governance": None, "pending": None, "candidate_validation": None, "semantic_review_inputs": [],
        "diagnostics": [], "observations": [], "stable": False, "difference_identity": None,
        "old_done_satisfies_new_obligations": False, "authorization": dict(protection.AUTHORIZATION),
        "not_implemented_or_enabled": ["formal publication and journal recovery", "Task implementation gate",
                                      "game acceptance", "default B activation"],
        "verification_limits": ["Locator/digest checks do not prove source support or external review approval.",
                                "Structure does not prove committed governance or runtime acceptance.",
                                "Double reading detects observed drift; it supplies no filesystem isolation."]}
    try:
        observations.read(path(epics))
        value, snapshot, report = _load_protection(observations, path(protection_input), epics, result["diagnostics"])
        candidate, sources = _carrier(observations, path(candidate_path))
        result["protection_validation"] = {"archive_integrity_verified": True,
            "capture_complete": snapshot["capture_complete"],
            "lawful_absences": ["no cumulative Task manifest in a verified original zero-Task repository"]
                if not snapshot["tasks"] and not snapshot["cumulative"] else []}
        result["candidate_sources"] = sources
        changes, diagnostics, before_docs, after_docs = _changes(observations, candidate)
        result["changes"] = changes
        result["diagnostics"].extend(diagnostics)
        zero_task_manifest_absence = not snapshot["tasks"] and not snapshot["cumulative"]
        current_inventory, summary, diagnostics = _current_inventory(observations, epics,
            zero_task_manifest_absence=zero_task_manifest_absence)
        result["current_inventory"] = summary
        result["diagnostics"].extend(diagnostics)
        inv_path = value["inventory_ref"]["ref"].split("#", 1)[0]
        scope, reviews, diagnostics = _intents(observations, path(intents_path), epics, protection_input,
                                             inv_path, candidate, changes)
        result.update(scope_id=scope, semantic_review_inputs=reviews)
        result["diagnostics"].extend(diagnostics)
        current_projection = protection.triplet_definition_projection(before_docs)
        result["protection_to_current"] = {
            "triplet_definition_changed": not protection._same_json(snapshot["triplet"]["definition"], current_projection),
            "raw_changes": [{"path": row["path"], "before_raw_digest": row["raw_digest"],
                             "current_raw_digest": codec.raw_digest(observations.values[row["path"]])
                                if observations.values.get(row["path"]) is not None else None}
                            for row in snapshot["raw_files"] if row["path"] in observations.values and
                            row["raw_digest"] != (codec.raw_digest(observations.values[row["path"]])
                                if observations.values[row["path"]] is not None else None)]}
        governance, diagnostics = _governance(observations, candidate, before_docs)
        result["governance"] = governance
        result["diagnostics"].extend(diagnostics)
        pending, diagnostics = _pending(observations)
        result["pending"] = pending
        result["diagnostics"].extend(diagnostics)
        current_manifests, after_manifests = [], []
        manifest_paths = {row["path"] for row in snapshot["cumulative"]} | {
            row["path"] for row in current_inventory["manifests"]} | {
            source for source in candidate if source.startswith("docs/testing/mvg/")}
        for source in sorted(manifest_paths):
            raw = observations.read(source, optional=True)
            if raw is not None:
                current = codec.strict_json_loads(raw)
                current_manifests.append({"path": source, "document": current, "canonical_digest": codec.canonical_digest(current)})
            after = codec.strict_json_loads(candidate.get(source, raw))
            after_manifests.append({"path": source, "document": after, "canonical_digest": codec.canonical_digest(after)})
        result["cumulative_changes"] = protection._manifest_changes(current_manifests, after_manifests)
        for change in result["cumulative_changes"]:
            if change["weakening_detected"]:
                result["diagnostics"].append(codec.Diagnostic(codec.ReasonCode.SEMANTIC_ERROR, codec.Stage.BUNDLE,
                    change["path"], "independent source-backed weakening review; locator alone cannot authorize",
                    {key: change[key] for key in ("removed_obligations", "weakened_obligations", "manual_limits_changed")},
                    change["path"]).to_dict())
        _references(observations, candidate)
        validations = []
        for source, raw in sorted(candidate.items()):
            if records._managed_candidate(source):
                check = records.validate_record(raw, path=source)
                validations.append(check.to_dict())
                if not check.ok:
                    result["diagnostics"].append(check.diagnostic.to_dict())
        if records.CATALOG_PATH in candidate:
            # Supply the full observed overlay, never fall back to unobserved disk.
            closure = {source: raw for source, raw in observations.values.items() if raw is not None}
            closure.update(candidate)
            baseline = {source: raw for source, raw in observations.values.items()
                        if raw is not None and records._managed_candidate(source)}
            bundle = records.validate_bundle(closure, root=None, baseline=baseline or None,
                                             task_join=records.TaskJoinContext(**after_docs))
            result["candidate_validation"] = bundle.to_dict()
            if not bundle.ok:
                result["diagnostics"].append(bundle.diagnostic.to_dict())
        else:
            result["candidate_validation"] = {"mode": "single_records_only", "records": validations,
                "relationships_verified": False, "committed_verified": False,
                "limitation": "No candidate catalog: cross-record relationships remain unverified."}
    except codec.CodecError as error:
        result["diagnostics"].append(error.diagnostic.to_dict())
    except (KeyError, TypeError, ValueError, OSError, UnicodeError, RecursionError, AttributeError) as error:
        result["diagnostics"].append(codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE, codec.Stage.BUNDLE,
            expected="complete supported original inputs", actual=type(error).__name__, resume_ref=protection_input).to_dict())
    if before_reread is not None:
        before_reread()
    if current_inventory is not None:
        try:
            final_inventory, final_summary, diagnostics = _current_inventory(observations, epics,
                zero_task_manifest_absence=zero_task_manifest_absence)
            result["diagnostics"].extend(diagnostics)
            if final_summary["content_identity"] != result["current_inventory"]["content_identity"]:
                initial_rows = {row["path"]: row["raw_sha256"] for row in current_inventory["inputs"]}
                final_rows = {row["path"]: row["raw_sha256"] for row in final_inventory["inputs"]}
                result["diagnostics"].append(codec.Diagnostic(codec.ReasonCode.FILE_CHANGED, codec.Stage.BUNDLE,
                    expected={"path": epics, "value": result["current_inventory"]["content_identity"]},
                    actual={"content_identity": final_summary["content_identity"],
                        "added_inputs": sorted(set(final_rows) - set(initial_rows)),
                        "removed_inputs": sorted(set(initial_rows) - set(final_rows)),
                        "changed_inputs": sorted(source for source in set(initial_rows) & set(final_rows)
                                                 if initial_rows[source] != final_rows[source])},
                    resume_ref=epics).to_dict())
        except codec.CodecError as error:
            result["diagnostics"].append(error.diagnostic.to_dict())
        except (KeyError, TypeError, ValueError, OSError, UnicodeError, AttributeError) as error:
            result["diagnostics"].append(codec.Diagnostic(codec.ReasonCode.FILE_CHANGED, codec.Stage.BUNDLE,
                expected="same complete current inventory closure", actual=type(error).__name__, resume_ref=epics).to_dict())
    drift = observations.finish()
    result["diagnostics"].extend(drift)
    result["stable"] = not drift and not any(row["reason_code"] == codec.ReasonCode.FILE_CHANGED.value
        for row in result["diagnostics"])
    result["observations"] = observations.identities()
    result["ok"] = not result["diagnostics"] and result["stable"]
    result["conclusion_valid"] = result["stable"]
    result["difference_identity"] = codec.canonical_digest({key: result[key] for key in
        ("scope_id", "changes", "cumulative_changes", "protection_to_current", "governance", "pending",
         "candidate_validation", "semantic_review_inputs", "diagnostics", "observations", "stable")}
        | {"current_inventory": result.get("current_inventory")})
    return result


def create_run_directory(root, run_id):
    if type(run_id) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", run_id) is None:
        fail(codec.ReasonCode.INVALID_ARGUMENT, None, "1-96 ASCII run-id characters", run_id)
    root = Path(root).absolute()
    relative = "logs/ci/" + dt.datetime.now(dt.timezone.utc).date().isoformat() + "/b-route-preflight/" + run_id
    try:
        if not root.is_dir():
            fail(codec.ReasonCode.INVALID_ARGUMENT, str(root), "existing explicit root directory", "missing root")
        inventory.no_reparse(root)
        target = inventory.safe_input(root, relative, allow_logs=True)
        current = root
        for component in relative.split("/")[:-1]:
            current /= component
            current.mkdir(exist_ok=True)
            inventory.no_reparse(current)
        target.mkdir(exist_ok=False)
        inventory.no_reparse(target)
        return target
    except (OSError, ValueError) as error:
        fail(codec.ReasonCode.CONFLICT if isinstance(error, FileExistsError) else codec.ReasonCode.UNSAFE_PATH,
             relative, "new contained logs directory", type(error).__name__)
