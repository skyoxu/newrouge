"""Read-only mature Task protection candidates; never a policy or write permit.

Raw archives are original file bytes. Definitions exclude only actual Task and
direct subtask status fields. Master remains the sole Task status authority.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import _b_route_codec as codec
import _b_route_inventory as inventory
from _b_route_records import TaskJoinContext
from update_mvg_baseline import _weakens_baseline


SCHEMA = "newrouge.b-route-protection-snapshot.v2"
DEFAULT_EPICS = "_bmad-output/planning-artifacts/b-route/epics.md"
AUTHORIZATION = {
    "formal_protection_baseline": False,
    "frozen_a": False,
    "write": False,
    "policy_bootstrap": False,
    "target_projection_verified": False,
}
_INVENTORY_ENVELOPE = frozenset({
    "content_identity", "second_pass_identity", "drift", "collection", "stable",
    "adoptable", "status", "verification_limits",
})
_OPERATIONS = (
    ("implement", "scripts/python/run_single_task_chapter6_lane.py"),
    ("resume", "scripts/python/resume_task.py"),
    ("route", "scripts/python/chapter6_route.py"),
)


def _diagnostic(code: codec.ReasonCode, path: str | None, expected: Any,
                actual: Any, *, entity_id: str | None = None,
                stage: codec.Stage = codec.Stage.BUNDLE) -> dict:
    return codec.Diagnostic(code, stage, entity_id,
        {"path": path, "value": expected}, {"path": path, "value": actual}, path).to_dict()


def _fail(code: codec.ReasonCode, path: str | None, expected: Any,
          actual: Any, *, entity_id: str | None = None) -> None:
    value = _diagnostic(code, path, expected, actual, entity_id=entity_id)
    raise codec.CodecError(codec.Diagnostic(code, codec.Stage.BUNDLE,
        value["entity_id"], value["expected"], value["actual"], path))


def _json_bytes(value: Any) -> bytes:
    codec.validate_json_value(value)
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _same_json(left: Any, right: Any) -> bool:
    """Use the existing codec, retaining JSON number/boolean distinctions."""
    return codec.canonical_digest(left) == codec.canonical_digest(right)


def _read(root: Path, path: str) -> bytes:
    # Inventory's stricter no-reparse/case checks also apply to logs archives.
    try:
        inventory.safe_input(root, path, allow_logs=True)
        return codec.read_reference_bytes(root, path)
    except codec.CodecError:
        raise
    except (OSError, ValueError) as error:
        code = codec.ReasonCode.READ_ERROR if isinstance(error, OSError) else codec.ReasonCode.UNSAFE_PATH
        _fail(code, path, "readable canonical contained regular file", type(error).__name__)


def _checked_digest(value: Any, path: str | None) -> str:
    if type(value) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        _fail(codec.ReasonCode.INVALID_DIGEST, path, "sha256:<64 lowercase hex digits>", value)
    return value


def _task_shape(task: Any) -> None:
    codec.validate_json_value(task)
    if type(task) is not dict:
        _fail(codec.ReasonCode.INVALID_TYPE, None, "Task object", type(task).__name__)
    if "subtasks" in task and (type(task["subtasks"]) is not list
            or any(type(row) is not dict for row in task["subtasks"])):
        _fail(codec.ReasonCode.INVALID_TYPE, None, "direct subtasks array of objects", "invalid subtasks")


def task_definition_projection(task: Any) -> dict:
    """Copy a Task, excluding only its status and direct subtasks[].status."""
    _task_shape(task)
    result = copy.deepcopy(task)
    result.pop("status", None)
    for subtask in result.get("subtasks", []):
        subtask.pop("status", None)
    return result


def _task_state(task: dict, *, master: bool) -> dict:
    _task_shape(task)
    allowed = inventory.MASTER_STATES if master else inventory.VIEW_STATES
    if type(task.get("status")) is not str or task["status"] not in allowed:
        _fail(codec.ReasonCode.INVALID_ENUM, None, "original valid Task status", task.get("status"))
    result = {"status": task["status"], "subtasks": []}
    for index, subtask in enumerate(task.get("subtasks", [])):
        # A missing direct subtask status is retained as missing, never defaulted.
        if "status" in subtask and (type(subtask["status"]) is not str
                                   or subtask["status"] not in inventory.VIEW_STATES):
            _fail(codec.ReasonCode.INVALID_ENUM, None, "original valid subtask status", subtask["status"])
        result["subtasks"].append({"index": index, "id": subtask.get("id"),
            "status_present": "status" in subtask, "status": subtask.get("status")})
    return result


def _join(documents: Any) -> tuple[dict, dict]:
    if type(documents) is not dict or set(documents) != set(inventory.TRIPLET):
        _fail(codec.ReasonCode.INVALID_TYPE, None, "complete master/back/gameplay documents", "invalid triplet")
    tasks, views = TaskJoinContext(**documents).indexes()
    mapped = set(views["back"].values()) | set(views["gameplay"].values())
    missing = sorted(set(tasks) - mapped)
    if missing:
        _fail(codec.ReasonCode.MAPPING_MISMATCH, inventory.TRIPLET["master"],
              "every master Task mapped by at least one business view", missing)
    return tasks, views


def triplet_definition_projection(documents: Any) -> dict:
    """Project only real Task rows, preserving envelopes, unknowns and order."""
    _join(documents)
    result = copy.deepcopy(documents)
    result["master"]["master"]["tasks"] = [task_definition_projection(row)
        for row in documents["master"]["master"]["tasks"]]
    for name in ("back", "gameplay"):
        result[name] = [task_definition_projection(row) for row in documents[name]]
    return result


def _inventory_rows(report: Any) -> dict[str, dict]:
    if type(report) is not dict or report.get("schema_version") != inventory.SCHEMA:
        _fail(codec.ReasonCode.UNKNOWN_SCHEMA, None, inventory.SCHEMA,
              report.get("schema_version") if type(report) is dict else type(report).__name__)
    if type(report.get("inputs")) is not list or not report["inputs"]:
        _fail(codec.ReasonCode.MISSING_REQUIRED_FIELD, None, "nonempty complete inventory inputs", "missing inputs")
    rows = {}
    for row in report["inputs"]:
        if type(row) is not dict or type(row.get("exists")) is not bool:
            _fail(codec.ReasonCode.INVALID_TYPE, None, "inventory input observation", row)
        path = row.get("path")
        try:
            inventory.canonical_path(path, allow_logs=True)
        except ValueError:
            _fail(codec.ReasonCode.UNSAFE_PATH, str(path), "canonical inventory path", path)
        if path.casefold() in {key.casefold() for key in rows}:
            _fail(codec.ReasonCode.CONFLICT, path, "unique inventory input path", path)
        if row["exists"]:
            _checked_digest(row.get("raw_sha256"), path)
        elif row.get("raw_sha256") is not None:
            _fail(codec.ReasonCode.INVALID_DIGEST, path, "null identity for absent bytes", row.get("raw_sha256"))
        rows[path] = row
    if not set(inventory.TRIPLET.values()) <= set(rows):
        _fail(codec.ReasonCode.MISSING_REQUIRED_FIELD, None, "all three original Task files in inventory", "incomplete triplet")
    return rows


def _inventory_identity(report: dict) -> None:
    _inventory_rows(report)
    # A v2 label and self-consistent hashes do not establish which rules the
    # report claims. Support one exact installed policy, without a legacy shim.
    # This does not authenticate the collection event or prove current inputs.
    rules = inventory.rule_identity()
    if type(report.get("rules")) is not dict or not _same_json(report["rules"], rules):
        _fail(codec.ReasonCode.UNKNOWN_CODEC_VERSION, None,
              {"supported_inventory_rules": rules}, {"inventory_rules": report.get("rules")})
    for field in ("content_identity", "second_pass_identity"):
        _checked_digest(report.get(field), None)
    diagnostics = report.get("diagnostics")
    if type(diagnostics) is not list or any(type(row) is not dict
            or row.get("severity") not in ("error", "warning") for row in diagnostics):
        _fail(codec.ReasonCode.INVALID_TYPE, None, "inventory diagnostic array with error or warning severity", diagnostics)
    if (report.get("stable") is not True or report["content_identity"] != report["second_pass_identity"]
            or any(row.get("code") in ("git-drift-within-pass", "unstable-inputs") for row in diagnostics)):
        _fail(codec.ReasonCode.FILE_CHANGED, None, "stable double-read inventory", "unstable inventory")
    # These collector-derived fields are excluded from content_identity. Check
    # their original contract before accepting even a consistently rehashed copy.
    has_errors = any(row["severity"] == "error" for row in diagnostics)
    expected = {"adoptable": not has_errors, "status": "invalid" if has_errors else "stable"}
    actual_metadata = {key: report.get(key) for key in expected}
    if report.get("adoptable") is not expected["adoptable"] or report.get("status") != expected["status"]:
        _fail(codec.ReasonCode.CONFLICT, None, expected, actual_metadata)
    expected_drift = {"added_inputs": [], "removed_inputs": [], "changed_inputs": [],
                      "git_changed": False, "rules_changed": False}
    if codec.canonical_digest(report.get("drift")) != codec.canonical_digest(expected_drift):
        _fail(codec.ReasonCode.CONFLICT, None, expected_drift, report.get("drift"))
    body = {key: value for key, value in report.items() if key not in _INVENTORY_ENVELOPE}
    actual = codec.canonical_digest(body)
    if actual != report["content_identity"]:
        _fail(codec.ReasonCode.DIGEST_MISMATCH, None, report["content_identity"], actual)


class _ArchivedReferences:
    """Reuse Story 1.1's Task/locator rules with archive bytes and no disk fallback."""
    json = inventory.Snapshot.json
    reference = inventory.Snapshot.reference

    def __init__(self, raw_files: dict[str, bytes]):
        self.raw_files, self.references = raw_files, []
        self.requests, self.diagnostics = [], []

    def diagnostic(self, code: str, location: str, message: str, severity: str = "error") -> None:
        self.diagnostics.append({"code": code, "location": location, "message": message, "severity": severity})

    def read(self, path: str, _role: str, *, required: bool = True,
             evidence: bool = False) -> bytes | None:
        try:
            inventory.canonical_path(path, allow_logs=evidence)
        except ValueError:
            self.requests.append({"path": path, "required": required, "allowed": False, "available": False})
            return None
        data = self.raw_files.get(path)
        self.requests.append({"path": path, "required": required, "allowed": True, "available": data is not None})
        if data is None:
            self.diagnostic("missing-input", path, "Archived file is missing",
                            "error" if required else "warning")
        return data


def _reference_closure(documents: dict, report: dict, raw_files: dict[str, bytes],
                       reader: _ArchivedReferences | None = None) -> list:
    reader = reader if reader is not None else _ArchivedReferences(raw_files)
    for name in inventory.TRIPLET:
        rows = documents["master"]["master"]["tasks"] if name == "master" else documents[name]
        for index, task in enumerate(rows):
            pointer = ("/master/tasks/" if name == "master" else "/") + str(index)
            for field in ("source_refs", "test_refs", "evidence_refs"):
                if field not in task:
                    continue
                if type(task[field]) is not list:
                    _fail(codec.ReasonCode.INVALID_TYPE, inventory.TRIPLET[name] + "#" + pointer + "/" + field,
                          "original reference array", type(task[field]).__name__)
                for ref_index, value in enumerate(task[field]):
                    reader.reference(inventory.TRIPLET[name], pointer + "/" + field + "/" + str(ref_index),
                        task["id"], task["id"] if name == "master" else task["taskmaster_id"], field, value)
    manifest_paths = []
    for role, path in report["discovery"]:
        if role != "manifest":
            continue
        document = reader.json(path, "cumulative-manifest")
        if not isinstance(document, dict):
            reader.diagnostic("invalid-manifest", path, "Manifest must be an object")
            continue
        # Story 1.1 retains every object whose reference traversal succeeds,
        # including objects with static validation errors. Rebuild that set
        # from discovery and raw bytes, rather than from the claimed projection.
        try:
            for index, test in enumerate(document.get("tests", [])):
                reader.reference(path, f"/tests/{index}/path", test.get("id"), None,
                    "manifest-test", test["path"], required=test.get("state") != "planned")
            for index, flow in enumerate(document.get("flows", [])):
                for source_index, source in enumerate(flow.get("source_paths", [])):
                    reader.reference(path, f"/flows/{index}/source_paths/{source_index}", flow.get("id"), None,
                        "manifest-source", source)
                for edge_index, edge in enumerate(flow.get("handoffs", [])):
                    reader.reference(path, f"/flows/{index}/handoffs/{edge_index}/contract_ref", flow.get("id"), None,
                        "manifest-contract", edge["contract_ref"])
            manifest_paths.append(path)
        except (KeyError, TypeError, ValueError, AttributeError, OSError) as error:
            reader.diagnostic("invalid-manifest", path, str(error))
    if not _same_json([row["path"] for row in report["manifests"]], manifest_paths):
        _fail(codec.ReasonCode.DIGEST_MISMATCH, None,
              "manifest membership rebuilt from archived discovery and original bytes", "different inventory manifest projection")
    if not manifest_paths:
        reader.diagnostic("missing-manifests", "docs/testing/mvg", "No cumulative manifest could be inventoried")
    return reader.references


def _archive_closure(report: dict, rows: dict, reader: _ArchivedReferences) -> None:
    """Recheck declared read membership and owner-required failures, archive only."""
    epics = report["epics"]
    raw_epics = reader.read(epics, "epics")
    header = {}
    try:
        header = inventory.frontmatter(raw_epics) if raw_epics is not None else {}
        if header.get("status") != "final":
            raise ValueError("Epics status must be final")
        sources = header.get("inputDocuments")
        if type(sources) is not list or len(sources) != 10:
            raise ValueError("Epics must declare ten canonical sources")
        seen = set()
        for path in sources:
            inventory.canonical_path(path)
            if path.casefold() in seen or Path(path).suffix.lower() not in inventory.SUPPORTED_SUFFIXES:
                raise ValueError("Canonical sources must be distinct and supported")
            seen.add(path.casefold())
            data = reader.read(path, "canonical-source")
            if data is not None:
                data.decode("utf-8-sig")
                if Path(path).suffix.lower() == ".json":
                    inventory.strict_json(data)
    except (ValueError, UnicodeError, TypeError):
        reader.diagnostic("invalid-epics", epics, "Archived epics declaration is invalid")
    expected = {"canonical_inputs": header.get("inputDocuments"),
                "declared_code_baseline": header.get("codeBaselineCommit"),
                "declared_input_snapshot": header.get("inputSnapshotCommit")}
    if not _same_json({key: report.get(key) for key in expected}, expected):
        _fail(codec.ReasonCode.DIGEST_MISMATCH, epics, "source declarations from original epics bytes", "different inventory declarations")

    source_set = reader.json(inventory.SOURCE_SET, "source-set")
    projected = report.get("source_set")
    if (type(projected) is not dict or projected.get("path") != inventory.SOURCE_SET
            or not _same_json(projected.get("document"), source_set)):
        _fail(codec.ReasonCode.DIGEST_MISMATCH, inventory.SOURCE_SET, "original source-set document", "different source projection")
    try:
        if (type(source_set) is not dict or source_set.get("schema_version") != "chapter3.source-set.v1"
                or type(source_set.get("active_patterns")) is not list or not source_set["active_patterns"]
                or type(source_set.get("active_sources")) is not list):
            raise ValueError("Invalid source-set declaration")
        for path in source_set["active_sources"]:
            reader.read(path, "declared-active-source")
        for path in projected["resolved_active_sources"]:
            reader.read(path, "resolved-active-source")
        if sorted(source_set["active_sources"]) != sorted(projected["resolved_active_sources"]):
            reader.diagnostic("source-set-mismatch", inventory.SOURCE_SET, "Declared active_sources differ from resolved active_patterns")
        for retirement in source_set.get("retirements", []):
            reader.read(retirement["path"], "historical-retired-source", required=False)
    except (ValueError, TypeError, KeyError):
        reader.diagnostic("invalid-source-set", inventory.SOURCE_SET, "Archived source-set declaration is invalid")

    for _category, _responsibility, _difference, _epic, entries in inventory.GROUPS:
        for path, _symbol in entries:
            reader.read(path, "consumer")
    for path in inventory.REQUIRED_CHAPTER_SKILLS:
        reader.read(path, "required-chapter-skill")
    for path in (".agents/skills/plan-capabilities/SKILL.md", ".agents/skills/plan-mvg/SKILL.md"):
        reader.read(path, "required-planning-skill")
    for path in ("docs/architecture/ADR_INDEX_GODOT.md", "DELIVERY_PROFILE.md",
                 "docs/workflows/run-protocol.md", "docs/workflows/local-hard-checks.md"):
        reader.read(path, "authority")
    for role, path in report["discovery"]:
        reader.read(path, role)
    for manifest in report["manifests"]:
        reader.read(manifest["path"], "cumulative-manifest")

    diagnostics = report["diagnostics"]
    for request in reader.requests:
        path = request["path"]
        if type(path) is not str or path not in rows:
            _fail(codec.ReasonCode.MISSING_REQUIRED_FIELD, path, "observation for every declared owner read", "missing inventory path binding")
        if not request["allowed"] or (request["required"] and not request["available"]):
            if not any(item.get("location") == path and item.get("severity") == "error"
                       and item.get("code") in ("missing-input", "unsafe-or-unreadable-input") for item in diagnostics):
                _fail(codec.ReasonCode.DIGEST_MISMATCH, path, "retained owner error for unavailable required input", "missing required error diagnostic")
    for diagnostic in reader.diagnostics:
        if not any(
                all(_same_json(item.get(key), diagnostic[key]) for key in ("code", "location", "severity"))
                for item in diagnostics):
            _fail(codec.ReasonCode.DIGEST_MISMATCH, diagnostic["location"],
                  "retained raw-derived owner diagnostic", diagnostic["code"])


def _materials(report: dict, raw_files: dict[str, bytes]) -> tuple[dict, list, list, dict]:
    rows = _inventory_rows(report)
    documents = {name: codec.strict_json_loads(raw_files[path]) for name, path in inventory.TRIPLET.items()}
    tasks, _views = _join(documents)
    projected = triplet_definition_projection(documents)
    references = report.get("task_and_manifest_references")
    if type(references) is not list:
        _fail(codec.ReasonCode.INVALID_TYPE, None, "original reference closure array", references)
    reader = _ArchivedReferences(raw_files)
    if not _same_json(references, _reference_closure(documents, report, raw_files, reader)):
        _fail(codec.ReasonCode.DIGEST_MISMATCH, None, "reference closure rebuilt from original bytes", "different inventory reference closure")
    task_entries, candidates = [], []
    for task_id, task in tasks.items():
        definition = {"master": task_definition_projection(task), "back": [], "gameplay": []}
        state = {"master": _task_state(task, master=True), "back": [], "gameplay": []}
        locators = [{"view": "master", "path": inventory.TRIPLET["master"],
                     "json_pointer": "/master/tasks/" + str(list(tasks).index(task_id))}]
        for name in ("back", "gameplay"):
            for index, row in enumerate(documents[name]):
                if row["taskmaster_id"] == task_id:
                    definition[name].append(task_definition_projection(row))
                    state[name].append({"id": row["id"], **_task_state(row, master=False)})
                    locators.append({"view": name, "path": inventory.TRIPLET[name], "json_pointer": "/" + str(index)})
        owned_refs = [copy.deepcopy(row) for row in references if type(row) is dict and row.get("master_id") == task_id]
        sources = [row for row in owned_refs if row.get("field") == "source_refs"]
        definition_digest, state_digest = codec.canonical_digest(definition), codec.canonical_digest(state)
        task_entries.append({"task_id": task_id, "definition": definition, "definition_digest": definition_digest,
            "state": state, "state_digest": state_digest, "locators": locators,
            "source_test_history_references": owned_refs})
        source_set = rows.get(inventory.SOURCE_SET)
        source_scope = {"source_set": {"path": inventory.SOURCE_SET,
            "raw_digest": source_set.get("raw_sha256") if source_set else None}, "task_source_references": sources}
        blockers = ["committed_reverse_governance_not_proven"]
        if not sources or any(row.get("state") != "present" for row in sources):
            blockers.append("task_source_scope_not_proven")
        if any(row.get("state") != "present" for row in owned_refs if row.get("field") == "evidence_refs"):
            blockers.append("historical_evidence_not_proven")
        candidates.append({"task_id": task_id, "definition_digest": definition_digest,
            "projection_codec": codec.PROJECTION_CODEC, "source_scope": source_scope,
            "old_operation_candidates": [{"operation": operation, "entrypoint": path,
                "raw_digest": rows.get(path, {}).get("raw_sha256"), "authorized": False} for operation, path in _OPERATIONS],
            "review_basis": {"epics": report["epics"], "epics_raw_digest": rows.get(report["epics"], {}).get("raw_sha256"),
                "review_status": "candidate_requires_external_review",
                "source_test_history_references": owned_refs},
            "status": "blocked", "blocking_reasons": blockers, "a_eligible": False})
    cumulative = []
    for row in report.get("manifests", []):
        path = row["path"]
        document = codec.strict_json_loads(raw_files[path])
        if not _same_json(document, row["document"]):
            _fail(codec.ReasonCode.DIGEST_MISMATCH, path, "inventory manifest object", "different raw document")
        cumulative.append({"path": path, "raw_digest": codec.raw_digest(raw_files[path]),
            "canonical_digest": codec.canonical_digest(document), "document": document,
            "execution_claim": "not-run; retained obligations do not prove acceptance"})
    task_summary = inventory.Snapshot.tasks(reader)
    if codec.canonical_digest(report.get("tasks")) != codec.canonical_digest(task_summary):
        _fail(codec.ReasonCode.DIGEST_MISMATCH, None, "Task summary rebuilt by Story 1.1 from archived triplet bytes",
              "different inventory Task documents, counts, status authority or status differences")
    _archive_closure(report, rows, reader)
    triplet = {"documents": documents, "definition": projected, "definition_digest": codec.canonical_digest(projected),
        "state_digest": codec.canonical_digest([row["state"] for row in task_entries]),
        "counts": copy.deepcopy(task_summary["counts"]),
        "status_differences": copy.deepcopy(task_summary["status_differences"])}
    frozen = {"task_set": "populated" if tasks else "verified-empty", "candidate_count": len(candidates),
              "candidates": candidates, "classification_authorized": False}
    return triplet, task_entries, cumulative, frozen


@dataclass(frozen=True)
class ProtectionCapture:
    snapshot: dict
    inventory: dict
    raw_files: dict[str, bytes]
    root: Path


def _historical(root: Path, path: str, raw_files: dict[str, bytes], diagnostics: list[dict]) -> dict:
    result = {"path": path, "raw_digest": None, "integrity_verified": False,
              "current_proof": False, "input_comparison": [], "diagnostics": []}
    try:
        data = _read(root, path)
        raw_files[path] = data
        result["raw_digest"] = codec.raw_digest(data)
        report = codec.strict_json_loads(data)
        _inventory_identity(report)
        result["integrity_verified"] = True
        result["content_identity"] = report["content_identity"]
        result["original_adoptable"] = report.get("adoptable") is True
        result["original_diagnostics"] = copy.deepcopy(report.get("diagnostics", []))
        for original, row in _inventory_rows(report).items():
            try:
                current = _read(root, original)
                if original in raw_files and raw_files[original] != current:
                    diagnostics.append(_diagnostic(codec.ReasonCode.FILE_CHANGED, original,
                        codec.raw_digest(raw_files[original]), codec.raw_digest(current)))
                raw_files.setdefault(original, current)
                actual = codec.raw_digest(current)
                state = "unchanged" if row["raw_sha256"] == actual else "changed"
                result["input_comparison"].append({"path": original, "expected_raw_digest": row["raw_sha256"],
                    "current_raw_digest": actual, "state": state})
            except codec.CodecError as error:
                if original in raw_files:
                    diagnostics.append(_diagnostic(codec.ReasonCode.FILE_CHANGED, original,
                        codec.raw_digest(raw_files[original]), error.diagnostic.reason_code.value))
                elif error.diagnostic.reason_code != codec.ReasonCode.FILE_NOT_FOUND:
                    diagnostics.append(error.diagnostic.to_dict())
                result["input_comparison"].append({"path": original, "expected_raw_digest": row["raw_sha256"],
                    "current_raw_digest": None, "state": "missing-or-unreadable", "diagnostic": error.diagnostic.to_dict()})
    except codec.CodecError as error:
        diagnostic = error.diagnostic.to_dict()
        result["diagnostics"].append(diagnostic)
        diagnostics.append(diagnostic)
    return result


def collect_protection(root: Path, epics: str, *, historical_inventory: str | None = None,
                       between_reads: Callable[[], None] | None = None) -> ProtectionCapture:
    """Reuse Story 1.1, recollect its entire raw closure, then check it again.

    The observer has no project lock and never claims isolation or A eligibility.
    Invalid inventory still yields an honest candidate with its unresolved items.
    """
    root = Path(root).absolute()
    # The Story 1.1 in-process report contains discovery tuples. Its persisted
    # JSON contract uses arrays; convert that derived report, never input bytes.
    report = codec.strict_json_loads(json.dumps(inventory.collect_inventory(root, epics), ensure_ascii=False))
    diagnostics, raw_files = [], {}
    rows = _inventory_rows(report)
    try:
        _inventory_identity(report)
    except codec.CodecError as error:
        diagnostics.append(error.diagnostic.to_dict())
    for path, row in rows.items():
        try:
            data = _read(root, path)
            raw_files[path] = data
            actual = codec.raw_digest(data)
            if actual != row["raw_sha256"] or not row["exists"]:
                diagnostics.append(_diagnostic(codec.ReasonCode.FILE_CHANGED, path, row["raw_sha256"], actual))
        except codec.CodecError as error:
            if row["exists"] or error.diagnostic.reason_code != codec.ReasonCode.FILE_NOT_FOUND:
                diagnostics.append(error.diagnostic.to_dict())
    historical = _historical(root, historical_inventory, raw_files, diagnostics) if historical_inventory is not None else None
    if between_reads is not None:
        between_reads()
    for path, data in list(raw_files.items()):
        try:
            current = _read(root, path)
            if current != data:
                diagnostics.append(_diagnostic(codec.ReasonCode.FILE_CHANGED, path, codec.raw_digest(data), codec.raw_digest(current)))
        except codec.CodecError as error:
            diagnostics.append(error.diagnostic.to_dict())
    # Previously absent files are observations too: creation during collection is drift.
    for path, row in rows.items():
        if not row["exists"] and path in raw_files:
            diagnostics.append(_diagnostic(codec.ReasonCode.FILE_CHANGED, path, None, codec.raw_digest(raw_files[path])))
        if row["exists"] or path in raw_files:
            continue
        try:
            data = _read(root, path)
            diagnostics.append(_diagnostic(codec.ReasonCode.FILE_CHANGED, path, None, codec.raw_digest(data)))
        except codec.CodecError as error:
            if error.diagnostic.reason_code != codec.ReasonCode.FILE_NOT_FOUND:
                diagnostics.append(error.diagnostic.to_dict())
    historical_paths = set()
    if historical is not None:
        historical_paths = {item["path"] for item in historical["input_comparison"]}
        for item in historical["input_comparison"]:
            path = item["path"]
            if item["current_raw_digest"] is not None or path in rows:
                continue
            try:
                current = _read(root, path)
                diagnostics.append(_diagnostic(codec.ReasonCode.FILE_CHANGED, path, None, codec.raw_digest(current)))
            except codec.CodecError as error:
                before_code = item.get("diagnostic", {}).get("reason_code")
                if error.diagnostic.reason_code.value != before_code:
                    diagnostics.append(_diagnostic(codec.ReasonCode.FILE_CHANGED, path, before_code, error.diagnostic.reason_code.value))
    try:
        git_end = inventory.git_identity(root)
        if not _same_json(git_end, report.get("git")):
            # Inventory's private blob index is omitted from its public report.
            if not _same_json({k: v for k, v in git_end.items() if k != "blobs"}, report.get("git")):
                diagnostics.append(_diagnostic(codec.ReasonCode.FILE_CHANGED, "git", report.get("git"),
                    {k: v for k, v in git_end.items() if k != "blobs"}))
    except (OSError, ValueError) as error:
        diagnostics.append(_diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE, "git", "stable current Git observation", str(error)))
    triplet, tasks, cumulative = None, [], []
    frozen = {"task_set": "unproven", "candidate_count": None, "candidates": [], "classification_authorized": False}
    try:
        triplet, tasks, cumulative, frozen = _materials(report, raw_files)
    except codec.CodecError as error:
        diagnostics.append(error.diagnostic.to_dict())
    except (KeyError, TypeError, ValueError) as error:
        diagnostics.append(_diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE, None, "complete raw materialization", type(error).__name__))
    archived = []
    for path in sorted(set(rows) | set(raw_files) | historical_paths):
        data = raw_files.get(path)
        digest = codec.raw_digest(data) if data is not None else None
        canonical = None
        if data is not None and path.endswith(".json"):
            try:
                canonical = codec.canonical_digest(codec.strict_json_loads(data))
            except codec.CodecError:
                pass  # Original invalid bytes are still preserved and diagnosed by their owner.
        archived.append({"path": path, "exists": data is not None, "raw_digest": digest,
            "canonical_digest": canonical, "size_bytes": len(data) if data is not None else None,
            "artifact": "raw/" + digest[7:] + ".bin" if digest is not None else None,
            "roles": rows.get(path, {}).get("roles", ["historical-backlink"] )})
    stable = report.get("stable") is True and not diagnostics
    snapshot = {"schema_version": SCHEMA, "content_codec": codec.CODEC_VERSION,
        "projection_codec": codec.PROJECTION_CODEC, "status_authority": inventory.TRIPLET["master"],
        "collection": copy.deepcopy(report.get("collection")),
        "inventory": {"artifact": "inventory.json", "raw_digest": codec.raw_digest(_json_bytes(report)),
            "content_identity": report.get("content_identity"), "adoptable": report.get("adoptable") is True,
            "diagnostics": copy.deepcopy(report.get("diagnostics", []))},
        "raw_files": archived, "triplet": triplet, "tasks": tasks, "cumulative": cumulative,
        "frozen_a": frozen, "historical_inventory": historical, "diagnostics": diagnostics,
        "stable": stable, "capture_complete": stable and report.get("adoptable") is True and triplet is not None,
        "authorization": dict(AUTHORIZATION),
        "verification_limits": ["Read-only candidate, not a formal protection baseline or frozen-A policy.",
            "Missing historical debug attachments remain unresolved observations, not operation prerequisites; old done never satisfies new obligations.",
            "No committed reverse-governance proof is implemented; every Task candidate is blocked.",
            "Double-read observations do not isolate against external concurrent writers.",
            "Receipt target projections, policy bootstrap, journal and publication are not implemented."]}
    snapshot["snapshot_digest"] = codec.canonical_digest(snapshot)
    return ProtectionCapture(snapshot, report, raw_files, root)


def create_run_directory(root: Path, run_id: str) -> Path:
    inventory.require_runtime()
    if type(run_id) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", run_id) is None:
        _fail(codec.ReasonCode.INVALID_ARGUMENT, None, "1-96 ASCII run-id characters", run_id)
    inventory.canonical_path(run_id)
    root = Path(root).absolute()
    relative = "logs/ci/" + dt.datetime.now(dt.timezone.utc).date().isoformat() + "/b-route-protection/" + run_id
    try:
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
        _fail(codec.ReasonCode.CONFLICT if isinstance(error, FileExistsError) else codec.ReasonCode.UNSAFE_PATH,
              relative, "new contained logs directory without links or aliases", type(error).__name__)


def _output_relative_path(root: Path, output: Path) -> str:
    """Compare existing physical identities without discarding original links."""
    root, output = Path(root).absolute(), Path(output).absolute()
    try:
        for original in (root, output):
            for ancestor in reversed((original, *original.parents)):
                inventory.no_reparse(ancestor)
        for anchor in (output, *output.parents):
            if anchor.samefile(root):
                relative = output.relative_to(anchor).as_posix()
                break
        else:
            raise ValueError("Output has no physical repository root ancestor")
        if not relative.startswith("logs/ci/"):
            _fail(codec.ReasonCode.UNSAFE_PATH, relative, "new logs/ci run directory", relative)
        target = inventory.safe_input(root, relative, allow_logs=True)
        physical_relative = target.resolve(strict=True).relative_to(root.resolve(strict=True)).as_posix()
        if physical_relative != relative or not target.samefile(output):
            raise ValueError("Output physical identity or descendant spelling differs")
        return relative
    except codec.CodecError:
        raise
    except (OSError, ValueError) as error:
        _fail(codec.ReasonCode.UNSAFE_PATH, str(output), "contained logs output without link ancestors", type(error).__name__)


def write_capture(output: Path, capture: ProtectionCapture) -> None:
    """Write only an already-created empty run; never overwrite any evidence."""
    output = Path(output).absolute()
    _output_relative_path(capture.root, output)
    if not output.is_dir() or any(output.iterdir()):
        _fail(codec.ReasonCode.CONFLICT, str(output), "empty new run directory", "missing or nonempty directory")
    (output / "raw").mkdir(exist_ok=False)
    seen = set()
    for data in capture.raw_files.values():
        digest = codec.raw_digest(data)[7:]
        if digest not in seen:
            with (output / "raw" / (digest + ".bin")).open("xb") as stream:
                stream.write(data)
            seen.add(digest)
    for name, payload in (("inventory.json", capture.inventory), ("snapshot.json", capture.snapshot)):
        with (output / name).open("xb") as stream:
            stream.write(_json_bytes(payload))


def _load_snapshot(root: Path, path: str) -> tuple[dict, dict, dict[str, bytes]]:
    data = _read(root, path)
    observed = {path: data}
    def read_artifact(source: str) -> bytes:
        raw = _read(root, source)
        if source in observed and observed[source] != raw:
            _fail(codec.ReasonCode.FILE_CHANGED, source, codec.raw_digest(observed[source]), codec.raw_digest(raw))
        observed[source] = raw
        return raw
    snapshot = codec.strict_json_loads(data)
    if type(snapshot) is not dict or snapshot.get("schema_version") != SCHEMA:
        _fail(codec.ReasonCode.UNKNOWN_SCHEMA, path, SCHEMA,
              snapshot.get("schema_version") if type(snapshot) is dict else type(snapshot).__name__)
    if snapshot.get("content_codec") != codec.CODEC_VERSION or snapshot.get("projection_codec") != codec.PROJECTION_CODEC:
        _fail(codec.ReasonCode.UNKNOWN_CODEC_VERSION, path, [codec.CODEC_VERSION, codec.PROJECTION_CODEC],
              [snapshot.get("content_codec"), snapshot.get("projection_codec")])
    if not _same_json(snapshot.get("authorization"), AUTHORIZATION):
        _fail(codec.ReasonCode.CONFLICT, path, AUTHORIZATION, snapshot.get("authorization"))
    expected = _checked_digest(snapshot.get("snapshot_digest"), path)
    actual = codec.canonical_digest({key: value for key, value in snapshot.items() if key != "snapshot_digest"})
    if actual != expected:
        _fail(codec.ReasonCode.DIGEST_MISMATCH, path, expected, actual)
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    def artifact(name: str) -> str:
        return parent + "/" + name if parent else name
    inv_ref = snapshot.get("inventory")
    if type(inv_ref) is not dict or inv_ref.get("artifact") != "inventory.json":
        _fail(codec.ReasonCode.INVALID_REFERENCE, path, "inventory.json artifact", inv_ref)
    inv_data = read_artifact(artifact("inventory.json"))
    if codec.raw_digest(inv_data) != inv_ref.get("raw_digest"):
        _fail(codec.ReasonCode.DIGEST_MISMATCH, artifact("inventory.json"), inv_ref.get("raw_digest"), codec.raw_digest(inv_data))
    report = codec.strict_json_loads(inv_data)
    _inventory_identity(report)
    if (inv_ref.get("content_identity") != report["content_identity"]
            or inv_ref.get("adoptable") is not (report.get("adoptable") is True)
            or not _same_json(inv_ref.get("diagnostics"), report.get("diagnostics"))):
        _fail(codec.ReasonCode.DIGEST_MISMATCH, path, "original inventory metadata", "different snapshot metadata")
    original = _inventory_rows(report)
    raw_files, observations = {}, {}
    if type(snapshot.get("raw_files")) is not list:
        _fail(codec.ReasonCode.INVALID_TYPE, path, "complete raw archive index", snapshot.get("raw_files"))
    for row in snapshot["raw_files"]:
        if type(row) is not dict:
            _fail(codec.ReasonCode.INVALID_TYPE, path, "raw archive observation", row)
        source = row.get("path")
        try:
            inventory.canonical_path(source, allow_logs=True)
        except ValueError:
            _fail(codec.ReasonCode.UNSAFE_PATH, str(source), "original canonical path", source)
        if source.casefold() in {key.casefold() for key in observations}:
            _fail(codec.ReasonCode.CONFLICT, source, "unique archived original paths", source)
        observations[source] = row
        if row.get("exists") is False:
            if any(row.get(field) is not None for field in ("raw_digest", "canonical_digest", "size_bytes", "artifact")):
                _fail(codec.ReasonCode.INVALID_REFERENCE, source, "no fabricated identity for missing bytes", row)
            continue
        if row.get("exists") is not True:
            _fail(codec.ReasonCode.INVALID_TYPE, source, "boolean exists", row.get("exists"))
        digest = _checked_digest(row.get("raw_digest"), source)
        if row.get("artifact") != "raw/" + digest[7:] + ".bin":
            _fail(codec.ReasonCode.UNSAFE_PATH, source, "content-addressed raw archive path", row.get("artifact"))
        raw = read_artifact(artifact(row["artifact"]))
        if codec.raw_digest(raw) != digest or not _same_json(len(raw), row.get("size_bytes")):
            _fail(codec.ReasonCode.DIGEST_MISMATCH, source, digest, codec.raw_digest(raw))
        canonical = None
        if source.endswith(".json"):
            try:
                canonical = codec.canonical_digest(codec.strict_json_loads(raw))
            except codec.CodecError:
                pass
        if canonical != row.get("canonical_digest"):
            _fail(codec.ReasonCode.DIGEST_MISMATCH, source, row.get("canonical_digest"), canonical)
        raw_files[source] = raw
    if not set(original) <= set(observations):
        _fail(codec.ReasonCode.MISSING_REQUIRED_FIELD, path, "full original inventory archive index", sorted(set(original) - set(observations)))
    for source, row in original.items():
        archived = observations[source]
        if (archived["exists"] is not row["exists"] or archived.get("raw_digest") != row["raw_sha256"]
                or not _same_json(archived.get("roles"), row.get("roles"))):
            _fail(codec.ReasonCode.DIGEST_MISMATCH, source, row, archived)
    triplet, tasks, cumulative, frozen = _materials(report, raw_files)
    for field, actual_value in (("triplet", triplet), ("tasks", tasks), ("cumulative", cumulative), ("frozen_a", frozen)):
        if not _same_json(snapshot.get(field), actual_value):
            _fail(codec.ReasonCode.DIGEST_MISMATCH, path, "raw-derived " + field, "different " + field)
    if snapshot.get("status_authority") != inventory.TRIPLET["master"]:
        _fail(codec.ReasonCode.CONFLICT, path, inventory.TRIPLET["master"], snapshot.get("status_authority"))
    if snapshot.get("stable") is not True or not _same_json(snapshot.get("diagnostics"), []):
        _fail(codec.ReasonCode.FILE_CHANGED, path, "stable raw collection without capture errors", "invalid or unstable snapshot")
    if snapshot.get("capture_complete") is not (report.get("adoptable") is True):
        _fail(codec.ReasonCode.CONFLICT, path, "capture completeness derived from inventory", snapshot.get("capture_complete"))
    history = snapshot.get("historical_inventory")
    allowed_extra = set()
    if history is not None:
        if type(history) is not dict or history.get("current_proof") is not False:
            _fail(codec.ReasonCode.INVALID_REFERENCE, path, "historical backlink without current proof", history)
        source = history.get("path")
        if source not in raw_files or codec.raw_digest(raw_files[source]) != history.get("raw_digest"):
            _fail(codec.ReasonCode.DIGEST_MISMATCH, source, "archived historical report", "missing or mismatched report")
        previous = codec.strict_json_loads(raw_files[source])
        _inventory_identity(previous)
        if (history.get("integrity_verified") is not True
                or history.get("content_identity") != previous["content_identity"]
                or history.get("original_adoptable") is not previous["adoptable"]
                or not _same_json(history.get("original_diagnostics"), previous["diagnostics"])
                or not _same_json(history.get("diagnostics"), [])):
            _fail(codec.ReasonCode.DIGEST_MISMATCH, source, "historical metadata rebuilt from archived report", "different historical metadata")
        allowed_extra = set(_inventory_rows(previous)) | {source}
        comparisons = history.get("input_comparison")
        if type(comparisons) is not list or len(comparisons) != len(previous["inputs"]):
            _fail(codec.ReasonCode.MISSING_REQUIRED_FIELD, source, "complete historical input comparison", "incomplete comparison")
        previous_rows = _inventory_rows(previous)
        seen = set()
        for item in comparisons:
            original_path = item.get("path") if type(item) is dict else None
            if original_path not in previous_rows or original_path in seen:
                _fail(codec.ReasonCode.INVALID_REFERENCE, source, "unique historical input comparison", original_path)
            seen.add(original_path)
            archived_raw = raw_files.get(original_path)
            current_digest = codec.raw_digest(archived_raw) if archived_raw is not None else None
            expected_digest = previous_rows[original_path]["raw_sha256"]
            expected_state = "missing-or-unreadable" if archived_raw is None else ("unchanged" if current_digest == expected_digest else "changed")
            if (item.get("expected_raw_digest") != expected_digest or item.get("current_raw_digest") != current_digest
                    or item.get("state") != expected_state):
                _fail(codec.ReasonCode.DIGEST_MISMATCH, source, "raw-derived historical difference", item)
    if set(observations) - set(original) - allowed_extra:
        _fail(codec.ReasonCode.INVALID_REFERENCE, path, "only current and historical raw closure", "unexplained archived inputs")
    for source, original_data in observed.items():
        current_data = _read(root, source)
        if current_data != original_data:
            _fail(codec.ReasonCode.FILE_CHANGED, source, codec.raw_digest(original_data), codec.raw_digest(current_data))
    return snapshot, report, raw_files


def _verification_summary(snapshot_path: str, snapshot: dict | None = None) -> dict:
    result = {"ok": snapshot is not None, "claim": "protection_archive_integrity_only", "path": snapshot_path,
        "snapshot_digest": None, "diagnostics": [], "authorization": dict(AUTHORIZATION)}
    if snapshot is not None:
        result.update(snapshot_digest=snapshot["snapshot_digest"], capture_complete=snapshot["capture_complete"],
            unresolved_inventory_diagnostics=snapshot["inventory"]["diagnostics"])
    return result


def verify_protection(root: Path, snapshot_path: str) -> dict:
    """Rebuild from archived bytes, not from a snapshot's self-reported hashes."""
    result = _verification_summary(snapshot_path)
    try:
        snapshot, _report, _raw = _load_snapshot(Path(root).absolute(), snapshot_path)
        result = _verification_summary(snapshot_path, snapshot)
    except codec.CodecError as error:
        result["diagnostics"].append(error.diagnostic.to_dict())
    except (KeyError, TypeError, ValueError, OSError) as error:
        result["diagnostics"].append(_diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE, snapshot_path,
            "complete supported protection archive", type(error).__name__))
    return result


def _changes(before: dict, after: dict) -> dict:
    return {"added": sorted(after.keys() - before.keys()), "removed": sorted(before.keys() - after.keys()),
            "changed": sorted(key for key in before.keys() & after.keys() if not _same_json(before[key], after[key]))}


def _manifest_changes(before: list[dict], after: list[dict]) -> list[dict]:
    old, new = {row["path"]: row for row in before}, {row["path"]: row for row in after}
    changes = []
    for path in sorted(set(old) | set(new)):
        left, right = old.get(path), new.get(path)
        if left is not None and right is not None and _same_json(left["document"], right["document"]):
            continue
        a, b = (left or {}).get("document", {}), (right or {}).get("document", {})
        for document in (a, b):
            if type(document) is not dict or type(document.get("coverage", {})) is not dict:
                _fail(codec.ReasonCode.INVALID_TYPE, path, "manifest object and coverage object", "malformed cumulative input")
            for section in ("flows", "tests"):
                values = document.get(section, [])
                if type(values) is not list or any(type(row) is not dict or type(row.get("id")) is not str
                                                  or not row["id"] for row in values):
                    _fail(codec.ReasonCode.INVALID_TYPE, path + "#/" + section,
                          "original manifest rows with nonempty string IDs", "malformed cumulative rows")
        removed, weakened, added = [], [], []
        for section in ("flows", "tests"):
            old_rows = {row["id"]: row for row in a.get(section, [])}
            new_rows = {row["id"]: row for row in b.get(section, [])}
            removed.extend(section + "/" + str(key) for key in old_rows.keys() - new_rows.keys())
            added.extend(section + "/" + str(key) for key in new_rows.keys() - old_rows.keys())
            weakened.extend(section + "/" + str(key) for key in old_rows.keys() & new_rows.keys()
                            if _weakens_baseline(old_rows[key], new_rows[key]))
        manual_changed = not _same_json(a.get("coverage", {}).get("excluded_claims"), b.get("coverage", {}).get("excluded_claims"))
        coverage_weakened = _weakens_baseline(a.get("coverage", {}), b.get("coverage", {}))
        changes.append({"path": path, "before_digest": left["canonical_digest"] if left else None,
            "after_digest": right["canonical_digest"] if right else None,
            "removed_obligations": sorted(removed), "added_obligations": sorted(added),
            "weakened_obligations": sorted(weakened), "manual_limits_changed": manual_changed,
            "weakening_detected": bool(removed or weakened or coverage_weakened or (left is not None and right is None)),
            "source_backed_review_required": left is not None,
            "source_backed_review_verified": False, "apply_authorized": False})
    return changes


@dataclass(frozen=True)
class ProtectionComparison:
    current: ProtectionCapture
    report: dict


def compare_protection(root: Path, baseline_path: str, epics: str, *,
                       historical_inventory: str | None = None) -> ProtectionComparison:
    """Capture current state even if the old archive is corrupt; never restore it."""
    current = collect_protection(root, epics, historical_inventory=historical_inventory)
    baseline, previous = _verification_summary(baseline_path), None
    try:
        previous, _inventory_report, _raw = _load_snapshot(Path(root).absolute(), baseline_path)
        baseline = _verification_summary(baseline_path, previous)
    except codec.CodecError as error:
        baseline["diagnostics"].append(error.diagnostic.to_dict())
    except (KeyError, TypeError, ValueError, OSError) as error:
        baseline["diagnostics"].append(_diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE, baseline_path,
            "complete supported protection archive", type(error).__name__))
    report = {"ok": False, "claim": "read_only_protection_comparison", "baseline": baseline,
        "current_snapshot_digest": current.snapshot["snapshot_digest"], "changes": None,
        "old_done_satisfies_new_obligations": False, "authorization": dict(AUTHORIZATION), "diagnostics": []}
    if baseline["ok"]:
        try:
            now = current.snapshot
            if now["triplet"] is None:
                _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, None, "current complete triplet", "invalid current inputs")
            report["changes"] = {
                "task_definitions": _changes({row["task_id"]: row["definition_digest"] for row in previous["tasks"]},
                                             {row["task_id"]: row["definition_digest"] for row in now["tasks"]}),
                "task_states": _changes({row["task_id"]: row["state_digest"] for row in previous["tasks"]},
                                        {row["task_id"]: row["state_digest"] for row in now["tasks"]}),
                "raw_files": _changes({row["path"]: row["raw_digest"] for row in previous["raw_files"]},
                                      {row["path"]: row["raw_digest"] for row in now["raw_files"]}),
                "triplet_definition_changed": previous["triplet"]["definition_digest"] != now["triplet"]["definition_digest"],
                "manifests": _manifest_changes(previous["cumulative"], now["cumulative"]),
                "source_test_history_references_changed": _changes(
                    {row["task_id"]: row["source_test_history_references"] for row in previous["tasks"]},
                    {row["task_id"]: row["source_test_history_references"] for row in now["tasks"]})}
            report["ok"] = now["capture_complete"] is True
            if not report["ok"]:
                report["diagnostics"].append(_diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE, None,
                    "complete current capture", "current inventory has unresolved input errors"))
        except codec.CodecError as error:
            report["diagnostics"].append(error.diagnostic.to_dict())
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            report["diagnostics"].append(_diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE, baseline_path,
                "complete comparable current cumulative inputs", type(error).__name__))
    else:
        report["diagnostics"] = copy.deepcopy(baseline["diagnostics"])
    return ProtectionComparison(current, report)
