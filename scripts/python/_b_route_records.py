"""Offline, read-only structural validation of B-route candidate records.

These results describe supplied declarations and references. They do not confer
adoption, publication, Task readiness, runtime acceptance, or historical proof.
"""
from __future__ import annotations

import os
import posixpath
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PureWindowsPath
from typing import Any

import _b_route_codec as codec


BASE = "docs/planning/b-route/"
CATALOG_PATH = BASE + "catalog.v1.json"
PROJECTION_CODEC = "newrouge.b-route-task-definition.v1"
SCHEMA_DIRECTORY = Path(__file__).resolve().parents[2] / BASE / "schemas"


def _fail(code: codec.ReasonCode, *, path: str | None = None,
          pointer: str | None = None, expected: Any = None, actual: Any = None,
          entity_id: str | None = None, stage: codec.Stage = codec.Stage.BUNDLE) -> None:
    location = {"path": path, "json_pointer": pointer}
    raise codec.CodecError(codec.Diagnostic(code, stage, entity_id,
        dict(location, value=expected), dict(location, value=actual), path))


def _key(value: Any) -> str:
    # A comparison key only: payloads and original bytes are never rewritten.
    return codec.canonical_digest(value)


def _path(value: str) -> str:
    codec.validate_reference_path(value)
    normalized = posixpath.normpath(value)
    if normalized == ".":
        _fail(codec.ReasonCode.UNSAFE_PATH, path=value, expected="file path", actual=value)
    return normalized


def _managed_candidate(path: str) -> bool:
    return path in (CATALOG_PATH, BASE + "policy.v1.json", BASE + "task-origins.v1.json") or path.startswith((BASE + "plans/", BASE + "bindings/", BASE + "commits/"))


def _unique(rows: list, *, path: str, pointer: str, key=lambda value: value,
            code: codec.ReasonCode = codec.ReasonCode.MAPPING_MISMATCH) -> dict:
    result = {}
    for row in rows:
        identity = key(row)
        if identity in result:
            _fail(code, path=path, pointer=pointer, expected="unique entries", actual=identity)
        result[identity] = row
    return result


@dataclass(frozen=True)
class RecordValidation:
    ok: bool
    diagnostic: codec.Diagnostic
    schema_validated: bool = False
    content_identity: codec.ContentIdentity | None = None
    entity_id: str | None = None
    revision: int | None = None
    path: str | None = None
    claim: str = "record_structure_only"
    references_validated: bool = False
    monotonicity_checked: bool = False
    target_projection_verified: bool = False

    @property
    def raw_identity(self) -> str | None:
        return self.content_identity.raw_digest if self.content_identity is not None else None

    def to_dict(self) -> dict:
        return {"ok": self.ok, "claim": self.claim, "schema_validated": self.schema_validated,
            "references_validated": self.references_validated,
            "monotonicity_checked": self.monotonicity_checked,
            "target_projection_verified": self.target_projection_verified,
            "diagnostic": self.diagnostic.to_dict(), "entity_id": self.entity_id,
            "revision": self.revision, "path": self.path, "raw_identity": self.raw_identity,
            "content_identity": self.content_identity.to_dict() if self.content_identity else None}


@dataclass(frozen=True)
class BundleValidation:
    ok: bool
    diagnostic: codec.Diagnostic
    schema_validated: bool = False
    references_validated: bool = False
    monotonicity_checked: bool = False
    target_projection_verified: bool = False
    claim: str = "candidate_structure_only"
    historical_targets_not_revalidated: tuple = ()

    def to_dict(self) -> dict:
        return {"ok": self.ok, "claim": self.claim, "schema_validated": self.schema_validated,
            "references_validated": self.references_validated,
            "monotonicity_checked": self.monotonicity_checked,
            "target_projection_verified": self.target_projection_verified,
            "diagnostic": self.diagnostic.to_dict(),
            "historical_targets_not_revalidated": list(self.historical_targets_not_revalidated)}


def record_failure(diagnostic: codec.Diagnostic, *, path: str | None = None) -> RecordValidation:
    return RecordValidation(False, diagnostic, path=path)


def bundle_failure(diagnostic: codec.Diagnostic) -> BundleValidation:
    return BundleValidation(False, diagnostic)


def _schema_validator(schema_id: str):
    try:
        signature = tuple((name, (SCHEMA_DIRECTORY / (name + ".schema.json")).stat().st_mtime_ns,
                           (SCHEMA_DIRECTORY / (name + ".schema.json")).stat().st_size)
                          for name in ("common", "policy", "plan", "binding", "origins", "commit", "catalog"))
    except OSError:
        _fail(codec.ReasonCode.SCHEMA_RESOURCE_ERROR, stage=codec.Stage.SCHEMA,
              expected="seven local schema files", actual="missing schema resource")
    return _cached_schema_validator(schema_id, str(SCHEMA_DIRECTORY), signature)


@lru_cache(maxsize=48)
def _cached_schema_validator(schema_id: str, directory: str, signature: tuple):
    # Keep dependency loading out of the existing stdlib-only identity codec.
    try:
        from jsonschema import Draft202012Validator, validators
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError:
        _fail(codec.ReasonCode.DEPENDENCY_UNAVAILABLE, stage=codec.Stage.SCHEMA,
              expected="jsonschema==4.26.0 and referencing==0.37.0", actual="dependency unavailable")

    def reject_retrieve(uri):
        _fail(codec.ReasonCode.SCHEMA_RESOURCE_ERROR, stage=codec.Stage.SCHEMA,
              expected="registered local schema resource", actual=uri)

    registry = Registry(retrieve=reject_retrieve)
    schemas = {}
    try:
        for name in ("common", "policy", "plan", "binding", "origins", "commit", "catalog"):
            document = codec.strict_json_loads((Path(directory) / (name + ".schema.json")).read_bytes())
            Draft202012Validator.check_schema(document)
            identity = document["$id"]
            if identity in schemas:
                raise ValueError("duplicate schema resource")
            schemas[identity] = document
            registry = registry.with_resource(identity, Resource.from_contents(document, default_specification=DRAFT202012))
        if schema_id not in schemas or schema_id.endswith("common.v1"):
            _fail(codec.ReasonCode.UNKNOWN_SCHEMA, stage=codec.Stage.SCHEMA,
                  expected="one of the six public record schemas", actual=schema_id)
        strict = validators.extend(Draft202012Validator, type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
            "integer", lambda _checker, value: type(value) is int))
        return strict(schemas[schema_id], registry=registry)
    except codec.CodecError:
        raise
    except Exception as error:
        _fail(codec.ReasonCode.SCHEMA_RESOURCE_ERROR, stage=codec.Stage.SCHEMA,
              expected="valid offline schema resources", actual=type(error).__name__)


def _validate_schema(value: dict, path: str | None) -> None:
    schema = value.get("schema_version")
    if type(schema) is not str:
        _fail(codec.ReasonCode.MISSING_REQUIRED_FIELD if "schema_version" not in value else codec.ReasonCode.INVALID_TYPE,
              path=path, pointer="/schema_version", stage=codec.Stage.SCHEMA,
              expected="registered schema string", actual=schema)
    if schema not in codec.SCHEMA_IDENTITY_REGISTRY:
        _fail(codec.ReasonCode.UNKNOWN_SCHEMA, path=path, pointer="/schema_version",
              stage=codec.Stage.SCHEMA, expected="registered schema", actual=schema)
    if codec.SCHEMA_IDENTITY_REGISTRY[schema] is None:
        _fail(codec.ReasonCode.IDENTITY_UNPROVABLE, path=path, stage=codec.Stage.SCHEMA,
              expected="approved record identity adapter", actual=schema)
    validator = _schema_validator(schema)
    try:
        error = next(validator.iter_errors(value), None)
    except codec.CodecError:
        raise
    except Exception as error:
        _fail(codec.ReasonCode.SCHEMA_RESOURCE_ERROR, path=path, stage=codec.Stage.SCHEMA,
              expected="locally resolvable schema", actual=type(error).__name__)
    if error is not None:
        # Closed union branches still report the actual failing field. Choose
        # the branch whose declared discriminators best match the input.
        while error.context and type(error.instance) is dict and ("oneOf" in error.schema or "anyOf" in error.schema):
            branches = error.schema.get("oneOf", error.schema.get("anyOf"))
            def mismatches(index):
                total = 0
                for field, rule in branches[index].get("properties", {}).items():
                    if field in error.instance:
                        total += int("const" in rule and error.instance[field] != rule["const"])
                        total += int("enum" in rule and error.instance[field] not in rule["enum"])
                return total
            indices = {child.schema_path[0] for child in error.context if child.schema_path and type(child.schema_path[0]) is int}
            if not indices:
                break
            selected = min(indices, key=lambda index: (mismatches(index), index))
            error = next(child for child in error.context if child.schema_path and child.schema_path[0] == selected)
        codes = {"required": codec.ReasonCode.MISSING_REQUIRED_FIELD,
                 "additionalProperties": codec.ReasonCode.UNKNOWN_FIELD,
                 "enum": codec.ReasonCode.INVALID_ENUM, "const": codec.ReasonCode.INVALID_ENUM,
                 "type": codec.ReasonCode.INVALID_TYPE,
                 "uniqueItems": codec.ReasonCode.MAPPING_MISMATCH}
        pointer = "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path)
        code = codes.get(error.validator, codec.ReasonCode.SCHEMA_VALIDATION_FAILED)
        if error.validator in ("const", "enum") and error.absolute_path and error.absolute_path[-1] == "schema_version":
            code = codec.ReasonCode.SCHEMA_MISMATCH
        _fail(code,
              path=path, pointer=pointer, stage=codec.Stage.SCHEMA,
              expected={"rule": error.validator, "constraint": error.validator_value}, actual=error.message)


def _managed_path(value: dict) -> str:
    schema, entity_id, revision = codec._record_identity(value)
    kind = schema.removeprefix("newrouge.b-route-").removesuffix(".v1")
    if kind in ("plan", "binding", "commit"):
        if entity_id in (".", "..") or "/" in entity_id:
            _fail(codec.ReasonCode.UNSAFE_PATH, expected="portable identity component", actual=entity_id)
        codec.validate_reference_path(entity_id)
    if kind == "plan":
        return BASE + f"plans/{entity_id}/{revision}.json"
    if kind == "binding":
        return BASE + f"bindings/{entity_id}/{revision}.json"
    if kind == "commit":
        return BASE + f"commits/{entity_id}.json"
    return BASE + {"policy": "policy.v1.json", "origins": "task-origins.v1.json", "catalog": "catalog.v1.json"}[kind]


def _local(value: dict, path: str) -> None:
    kind = value["schema_version"]
    if kind.endswith("plan.v1"):
        requirements = _unique(value["requirements"], path=path, pointer="/requirements", key=lambda row: row["requirement_id"])
        domain = set(requirements)
        verifications = _unique(value["requirement_verification"], path=path, pointer="/requirement_verification", key=lambda row: row["requirement_id"])
        applicable = _unique(value["applicability"], path=path, pointer="/applicability", key=lambda row: row["requirement_id"])
        coverage = _unique(value["coverage_table"], path=path, pointer="/coverage_table", key=lambda row: row["requirement_id"])
        evidence = _unique(value["requirement_evidence"], path=path, pointer="/requirement_evidence", key=lambda row: (row["requirement_id"], row["evidence_id"]))
        if set(verifications) != domain or set(applicable) != domain or set(coverage) != domain:
            _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="complete Requirement domains", actual="different domains")
        for rid, row in verifications.items():
            if coverage[rid] != {key: item for key, item in row.items() if key != "evidence_ids"}:
                _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, pointer="/coverage_table", expected="complete seven-field projection", actual=rid)
            if any(row[key] != applicable[rid][key] for key in ("disposition", "rationale")):
                _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, pointer="/applicability", expected="matching disposition and rationale", actual=rid)
            if row["disposition"] == "other_verification" and row["sink_id"] not in requirements[rid]["non_task_sinks"]:
                _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="declared Requirement sink", actual=row["sink_id"])
            for eid in row["evidence_ids"]:
                if (rid, eid) not in evidence:
                    _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, path=path, expected="same-Requirement evidence", actual=[rid, eid])
        if any(rid not in domain for rid, _eid in evidence):
            _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="known Requirement evidence", actual="unknown Requirement")
        for plural in ("flows", "commands", "states"):
            definitions = _unique(value["definitions"][plural], path=path, pointer="/definitions/" + plural, key=lambda row: row["id"], code=codec.ReasonCode.DUPLICATE_OWNER)
            for definition in definitions.values():
                if not set(definition["requirement_ids"]) <= domain:
                    _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="declared Requirement IDs", actual=definition["id"])
        _unique(value["requirement_route_memberships"], path=path, pointer="/requirement_route_memberships", key=lambda row: (row["requirement_id"], row["flow_id"]))
        previous = value["lineage"]["previous_plan_ref"]
        if previous is not None and (previous["entity_id"] != value["plan_id"] or previous["revision"] >= value["revision"]):
            _fail(codec.ReasonCode.REVISION_MISMATCH, path=path, pointer="/lineage/previous_plan_ref", expected="same plan, older revision", actual=previous)
        for proof in value["adoption_proof_refs"]:
            proof_path = _path(proof["ref"].partition("#")[0])
            if proof_path.startswith(BASE + "commits/") or proof_path == CATALOG_PATH:
                _fail(codec.ReasonCode.DIGEST_CYCLE, path=path, expected="independent planning proof", actual=proof_path)
    elif kind.endswith("binding.v1"):
        if value["plan_id"] != value["plan_ref"]["entity_id"]:
            _fail(codec.ReasonCode.UNKNOWN_ENTITY, path=path, expected=value["plan_id"], actual=value["plan_ref"]["entity_id"])
        _unique(value["task_mappings"], path=path, pointer="/task_mappings", key=lambda row: row["task_id"])
        parts = _unique(value["parts"], path=path, pointer="/parts", key=lambda row: row["kind"])
        applicable_parts = {kind for kind, row in parts.items() if row["applicability"] == "applicable"}
        for index, mapping in enumerate(value["task_mappings"]):
            if not set(mapping["part_kinds"]) <= applicable_parts:
                _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path,
                      pointer=f"/task_mappings/{index}/part_kinds",
                      expected="declared applicable binding responsibilities",
                      actual=sorted(set(mapping["part_kinds"]) - applicable_parts))
        _unique(value["implementation_objects"], path=path, pointer="/implementation_objects", key=lambda row: row["id"])
        _unique(value["obligations"], path=path, pointer="/obligations", key=lambda row: row["id"])


def _reference_syntax(value: dict, path: str) -> None:
    """Validate declared reference spelling without observing any target bytes."""
    reference_fields = {"path", "schema_version", "entity_id", "revision", "digest", "verification_mode", "codec_version"}

    def check_path(candidate: str, pointer: str) -> None:
        try:
            codec.validate_reference_path(candidate)
        except codec.CodecError as error:
            diagnostic = error.diagnostic
            _fail(diagnostic.reason_code, path=path, pointer=pointer,
                  expected=diagnostic.expected, actual=candidate,
                  stage=diagnostic.stage or codec.Stage.PATH)

    def visit(item: Any, pointer: str) -> None:
        if type(item) is dict:
            if set(item) == reference_fields:
                try:
                    codec.TypedReference.from_value(item)
                except codec.CodecError as error:
                    diagnostic = error.diagnostic
                    _fail(diagnostic.reason_code, path=path, pointer=pointer + "/path",
                          expected=diagnostic.expected, actual=item["path"],
                          entity_id=item["entity_id"], stage=diagnostic.stage or codec.Stage.REFERENCE)
            elif "path" in item:
                check_path(item["path"], pointer + "/path")
            if set(item) == {"owner", "ref", "files"} and item["owner"] != "contract":
                check_path(item["ref"].partition("#")[0], pointer + "/ref")
            if "target_paths" in item:
                for index, target in enumerate(item["target_paths"]):
                    check_path(target, pointer + f"/target_paths/{index}")
            for key, child in item.items():
                component = key.replace("~", "~0").replace("/", "~1")
                visit(child, pointer + "/" + component)
        elif type(item) is list:
            for index, child in enumerate(item):
                visit(child, pointer + "/" + str(index))

    visit(value, "")


def validate_record(data: bytes | str | dict, *, path: str | None = None) -> RecordValidation:
    try:
        value, identity = codec._decode_content(data)
        if type(value) is not dict:
            _fail(codec.ReasonCode.INVALID_TYPE, path=path, stage=codec.Stage.SCHEMA, expected="record object", actual=type(value).__name__)
        _validate_schema(value, path)
        schema, entity_id, revision = codec._record_identity(value)
        expected_path = _managed_path(value)
        if path is not None and (codec.validate_reference_path(path) != expected_path):
            _fail(codec.ReasonCode.INVALID_REFERENCE, path=path, stage=codec.Stage.PATH, expected=expected_path, actual=path)
        _reference_syntax(value, path or expected_path)
        _local(value, path or expected_path)
        return RecordValidation(True, codec.Diagnostic(codec.ReasonCode.OK, codec.Stage.SCHEMA, entity_id),
                                True, identity, entity_id, revision, path)
    except codec.CodecError as error:
        return record_failure(error.diagnostic, path=path)


@dataclass(frozen=True)
class TaskJoinContext:
    master: Any
    back: Any
    gameplay: Any

    def indexes(self) -> tuple[dict, dict]:
        def located(diagnostic: codec.Diagnostic, context: str, pointer: str) -> None:
            location = {"context": "task_join." + context, "json_pointer": pointer}
            raise codec.CodecError(codec.Diagnostic(
                diagnostic.reason_code, diagnostic.stage, diagnostic.entity_id,
                dict(location, value=diagnostic.expected), dict(location, value=diagnostic.actual),
                diagnostic.resume_ref))

        def checked(function, value: Any, context: str, pointer: str):
            try:
                return function(value)
            except codec.CodecError as error:
                located(error.diagnostic, context, pointer)

        def invalid(code: codec.ReasonCode, context: str, pointer: str,
                    expected: Any, actual: Any) -> None:
            located(codec.Diagnostic(code, codec.Stage.BUNDLE, expected=expected, actual=actual),
                    context, pointer)

        values = []
        for name, value in (("master", self.master), ("back", self.back), ("gameplay", self.gameplay)):
            if type(value) in (bytes, str):
                value = checked(codec.strict_json_loads, value, name, "/task_join/" + name)
            checked(codec.validate_json_value, value, name, "/task_join/" + name)
            values.append(value)
        master, back, gameplay = values
        if type(master) is not dict or type(master.get("master")) is not dict or type(master["master"].get("tasks")) is not list:
            pointer = "/task_join/master"
            if type(master) is dict:
                pointer += "/master"
                if type(master.get("master")) is dict:
                    pointer += "/tasks"
            invalid(codec.ReasonCode.INVALID_TYPE, "master", pointer,
                    "master.tasks array", "invalid Taskmaster shape")
        tasks = {}
        for row_index, row in enumerate(master["master"]["tasks"]):
            pointer = f"/task_join/master/master/tasks/{row_index}"
            if type(row) is not dict:
                invalid(codec.ReasonCode.INVALID_TYPE, "master", pointer,
                        "master Task object", type(row).__name__)
            task_id = checked(codec.validate_task_id, row.get("id"), "master", pointer + "/id")
            if task_id in tasks:
                invalid(codec.ReasonCode.MAPPING_MISMATCH, "master", pointer + "/id",
                        "unique master Task IDs", task_id)
            tasks[task_id] = row
        views = {}
        for name, rows in (("back", back), ("gameplay", gameplay)):
            if type(rows) is not list:
                invalid(codec.ReasonCode.INVALID_TYPE, name, "/task_join/" + name,
                        "business-view array", name)
            index = {}
            task_seen = set()
            for row_index, row in enumerate(rows):
                pointer = f"/task_join/{name}/{row_index}"
                if type(row) is not dict:
                    invalid(codec.ReasonCode.INVALID_TYPE, name, pointer,
                            "business Task object", type(row).__name__)
                business_id = checked(codec.validate_business_id, row.get("id"), name, pointer + "/id")
                task_id = checked(codec.validate_task_id, row.get("taskmaster_id"), name, pointer + "/taskmaster_id")
                if business_id in index or task_id in task_seen or task_id not in tasks:
                    invalid(codec.ReasonCode.MAPPING_MISMATCH, name, pointer,
                            "unique view/master join", [name, business_id, task_id])
                index[business_id] = task_id
                task_seen.add(task_id)
            views[name] = index
        return tasks, views


class _Bytes:
    def __init__(self, records: Mapping[str, bytes], root: Path | None):
        if not isinstance(records, Mapping):
            _fail(codec.ReasonCode.INVALID_TYPE, expected="path to original bytes mapping", actual=type(records).__name__)
        self.root = Path(root) if root is not None else None
        if self.root is not None and not self.root.is_dir():
            _fail(codec.ReasonCode.PATH_UNPROVABLE, expected="repository directory", actual="invalid root")
        self.candidates = {}
        self.original_paths = {}
        self.observed = {}
        self.aliases = {}
        self.addresses = {}
        for path, data in records.items():
            key = self.lookup(path)
            if type(data) is not bytes:
                _fail(codec.ReasonCode.INVALID_TYPE, path=path, expected="original bytes", actual=type(data).__name__)
            if key in self.candidates:
                _fail(codec.ReasonCode.CONFLICT, path=path, expected="one candidate per path", actual=key)
            self._contained(path)
            self.candidates[key] = data
            self.original_paths[key] = path

    def _contained(self, path: str) -> Path | None:
        if self.root is None:
            return None
        try:
            base = self.root.resolve(strict=True)
            base_spellings = [base]
            spelling = str(base)
            alternate = None
            if base.drive:
                if spelling.upper().startswith("\\\\?\\UNC\\"):
                    alternate = Path("\\\\" + spelling[8:])
                elif spelling.startswith("\\\\?\\") and len(base.drive) == 6 and base.drive[-1] == ":":
                    alternate = Path(spelling[4:])
                elif base.drive.startswith("\\\\") and not spelling.startswith("\\\\?\\"):
                    alternate = Path("\\\\?\\UNC\\" + spelling[2:])
                elif len(base.drive) == 2 and base.drive[-1] == ":":
                    alternate = Path("\\\\?\\" + spelling)
            # Only the fully existing repository root gets another comparison
            # spelling, proven by object identity. Never rewrite a missing tail.
            if alternate is not None:
                if not alternate.samefile(base):
                    _fail(codec.ReasonCode.PATH_UNPROVABLE, path=path, stage=codec.Stage.PATH,
                          expected="equivalent existing root spelling", actual=str(alternate))
                base_spellings.append(alternate.resolve(strict=True))
            active_links = set()
            steps = 0

            def link_kind(info) -> bool:
                tag = getattr(info, "st_reparse_tag", 0)
                attributes = getattr(info, "st_file_attributes", 0)
                known = tag in (getattr(stat, "IO_REPARSE_TAG_SYMLINK", -1),
                                getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", -2))
                if (tag or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)) and not known:
                    _fail(codec.ReasonCode.PATH_UNPROVABLE, path=path, stage=codec.Stage.PATH,
                          expected="supported symlink or junction tag", actual={"tag": tag, "attributes": attributes})
                return stat.S_ISLNK(info.st_mode) or known

            def walk(current: Path, parts: tuple[str, ...]) -> Path:
                nonlocal steps
                for part in parts:
                    steps += 1
                    if steps > 4096:
                        _fail(codec.ReasonCode.PATH_UNPROVABLE, path=path, stage=codec.Stage.PATH,
                              expected="at most 4096 path steps", actual="step limit exceeded")
                    if part in ("", "."):
                        continue
                    if part == "..":
                        current = current.parent
                    else:
                        try:
                            parent_info = current.lstat()
                        except FileNotFoundError:
                            parent_info = None
                        if parent_info is not None:
                            link_kind(parent_info)
                            if not stat.S_ISDIR(parent_info.st_mode):
                                _fail(codec.ReasonCode.PATH_UNPROVABLE, path=path, stage=codec.Stage.PATH,
                                      expected="directory prefix", actual=str(current))
                        candidate = current / part
                        try:
                            info = candidate.lstat()
                        except FileNotFoundError:
                            current = candidate
                            continue
                        if link_kind(info):
                            if candidate in active_links or len(active_links) >= 64:
                                _fail(codec.ReasonCode.PATH_UNPROVABLE, path=path, stage=codec.Stage.PATH,
                                      expected="acyclic link expansion within 64 active links", actual=str(candidate))
                            active_links.add(candidate)
                            try:
                                raw_target = os.readlink(candidate)
                                if raw_target.startswith("\\\\?\\"):
                                    try:
                                        if "/" in raw_target:
                                            raise ValueError("namespace-dependent separator")
                                        native = PureWindowsPath(raw_target)
                                        tail = raw_target[len(native.anchor):]
                                        for component in tail.split("\\"):
                                            if component:
                                                if component in (".", ".."):
                                                    raise ValueError("namespace-dependent component")
                                                codec.validate_reference_path(component)
                                    except (codec.CodecError, ValueError):
                                        _fail(codec.ReasonCode.PATH_UNPROVABLE, path=path, stage=codec.Stage.PATH,
                                              expected="portable extended link suffix", actual=raw_target)
                                target = Path(raw_target)
                                if target.anchor:
                                    if not target.is_absolute():
                                        if target.drive:
                                            _fail(codec.ReasonCode.PATH_UNPROVABLE, path=path, stage=codec.Stage.PATH,
                                                  expected="absolute or relative link target", actual=str(target))
                                        target = candidate.parent / target
                                    current = walk(Path(target.anchor), target.parts[1:])
                                else:
                                    current = walk(candidate.parent, target.parts)
                            finally:
                                active_links.remove(candidate)
                        else:
                            current = candidate.resolve(strict=True)
                return current

            current = base
            for part in path.split("/"):
                current = walk(current, (part,))
                # Native Path equality retains Windows case rules without
                # enumerating every ancestor of a long missing suffix.
                matched = next((spelling for spelling in base_spellings
                                if len(current.parts) >= len(spelling.parts)
                                and Path(*current.parts[:len(spelling.parts)]) == spelling), None)
                if matched is None:
                    _fail(codec.ReasonCode.UNSAFE_PATH, path=path, stage=codec.Stage.PATH,
                          expected="root-contained public segment target", actual=str(current))
            return base / current.relative_to(matched)
        except codec.CodecError:
            raise
        except (OSError, RuntimeError, ValueError, RecursionError) as error:
            _fail(codec.ReasonCode.PATH_UNPROVABLE, path=path, stage=codec.Stage.PATH,
                  expected="provable candidate path", actual=type(error).__name__)

    def read(self, path: str) -> bytes:
        key = self.lookup(path)
        self._contained(path)
        if key in self.candidates:
            return self.candidates[key]
        if key in self.observed:
            return self.observed[key]
        if self.root is None:
            _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, path=path, expected="required original bytes", actual="missing candidate and root")
        data = codec.read_reference_bytes(self.root, path)
        self.observed[key] = data
        return data

    def lookup(self, path: str) -> str:
        original = _path(path)
        key = original
        resolved = self._contained(path)
        if resolved is not None:
            base = self.root.resolve(strict=True)
            key = resolved.relative_to(base).as_posix()
        # Path equality follows the native host's path comparison rules, even
        # when the candidate file does not exist. Keep the first spelling as the
        # address; entity IDs, managed logical paths and bytes retain their case.
        key = self.addresses.setdefault(Path(key), key)
        if key != original:
            self.aliases[path] = key
        return key

    def stable(self) -> None:
        for spelling, key in list(self.aliases.items()):
            if self.lookup(spelling) != key:
                _fail(codec.ReasonCode.FILE_CHANGED, path=spelling, expected=key, actual="lookup target changed")
        for path, data in self.observed.items():
            if codec.read_reference_bytes(self.root, path) != data:
                _fail(codec.ReasonCode.FILE_CHANGED, path=path, expected="same observed original bytes", actual="changed bytes")

    def contracts(self) -> dict[str, bytes]:
        prefix = "Game.Core/Contracts/"
        physical_directory = Path(self.lookup(prefix.rstrip("/")))
        names = set()
        for address, original in self.original_paths.items():
            logical = _path(original)
            if logical.startswith(prefix) and logical.endswith(".cs"):
                names.add(logical)
            elif Path(address).is_relative_to(physical_directory) and address.endswith(".cs"):
                names.add(prefix + Path(address).relative_to(physical_directory).as_posix())
        if self.root is not None:
            directory = self.root / "Game.Core/Contracts"
            if directory.exists() or directory.is_symlink():
                seen = set()
                pending = ["Game.Core/Contracts"]
                while pending:
                    current = pending.pop()
                    actual = codec.resolve_reference_path(self.root, current)
                    if actual in seen:
                        continue
                    seen.add(actual)
                    for child in sorted(actual.iterdir()):
                        logical = current + "/" + child.name
                        target = codec.resolve_reference_path(self.root, logical)
                        if target.is_dir():
                            pending.append(logical)
                        elif child.suffix == ".cs":
                            names.add(logical)
        return {name: self.read(name) for name in sorted(names)}


def _walk(value: Any):
    if type(value) is dict:
        yield value
        for child in value.values():
            yield from _walk(child)
    elif type(value) is list:
        for child in value:
            yield from _walk(child)


class _Bundle:
    def __init__(self, records, root, catalog_path, baseline, task_join):
        self.bytes = _Bytes(records, root)
        self.catalog_path = self.bytes.lookup(catalog_path)
        self.records = {}
        self.references = {}
        self.baseline = baseline
        self.task_join = task_join
        self.owners = {}
        self.definitions = {}
        self.historical_targets_not_revalidated = []
        self.active = set()
        self.current_receipts = set()

    def load(self, path: str) -> dict:
        key = self.bytes.lookup(path)
        if key in self.records:
            return self.records[key]
        data = self.bytes.read(path)
        value = codec.strict_json_loads(data)
        preliminary = validate_record(value)
        if not preliminary.ok:
            raise codec.CodecError(preliminary.diagnostic)
        managed_path = _managed_path(value)
        # Physical addresses own the byte cache; logical managed paths own the
        # record contract, including when their parent is an internal junction.
        if self.bytes.lookup(managed_path) != key:
            _fail(codec.ReasonCode.INVALID_REFERENCE, path=path, expected=managed_path, actual="lookup does not address managed record")
        result = validate_record(data, path=managed_path)
        if not result.ok:
            raise codec.CodecError(result.diagnostic)
        self.records[key] = value
        return value

    def reference(self, value: dict) -> dict:
        ref = codec.TypedReference.from_value(value)
        target = self.load(ref.path)
        schema, entity_id, revision = codec._record_identity(target)
        for actual, expected, code in ((schema, ref.schema_version, codec.ReasonCode.SCHEMA_MISMATCH),
                                      (entity_id, ref.entity_id, codec.ReasonCode.UNKNOWN_ENTITY),
                                      (revision, ref.revision, codec.ReasonCode.REVISION_MISMATCH)):
            if actual != expected:
                _fail(code, path=ref.path, expected=expected, actual=actual, entity_id=entity_id)
        data = self.bytes.read(ref.path)
        digest = codec.raw_digest(data) if ref.verification_mode == "raw" else codec.canonical_digest(target)
        if digest != ref.digest:
            _fail(codec.ReasonCode.DIGEST_MISMATCH, path=ref.path, expected=ref.digest, actual=digest, entity_id=entity_id)
        self.references[_key(value)] = target
        return target

    def expand(self) -> None:
        expanded = set()
        while set(self.records) - expanded:
            for path in sorted(set(self.records) - expanded):
                value = self.records[path]
                expanded.add(path)
                for child in _walk(value):
                    if set(child) == {"path", "schema_version", "entity_id", "revision", "digest", "verification_mode", "codec_version"}:
                        self.reference(child)

    def external(self, paths: set[str]) -> None:
        from _b_route_record_owners import resolve_owned_ref
        for path in sorted(paths):
            value = self.load(path)
            for child in _walk(value):
                if set(child) == {"owner", "ref", "files"}:
                    resolve_owned_ref(child, read_bytes=self.bytes.read, contract_sources=self.bytes.contracts,
                                      path_key=self.bytes.lookup)
            if value["schema_version"].endswith("plan.v1"):
                self.source(value, path)
                self.evidence(value, path)

    def refset(self, refs: list, path: str, pointer: str) -> dict:
        result = _unique(refs, path=path, pointer=pointer, key=_key)
        _unique(refs, path=path, pointer=pointer, key=lambda row: self.bytes.lookup(row["path"]))
        return result

    def definition_map(self, rows: list, path: str) -> dict:
        result = _unique(rows, path=path, pointer="/definition_owners", key=lambda row: (row["kind"], row["definition_id"]), code=codec.ReasonCode.DUPLICATE_OWNER)
        for (kind, definition_id), row in result.items():
            plan = self.reference(row["plan_ref"])
            definitions = plan["definitions"][{"flow": "flows", "command": "commands", "state": "states"}[kind]]
            if not any(definition["id"] == definition_id for definition in definitions):
                _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, path=path, expected="owner plan declares definition", actual=[kind, definition_id])
        return result

    def closure(self, plan_refs: list, binding_refs: list, owners: dict, path: str) -> dict:
        seeds = list(plan_refs)
        seeds.extend(self.reference(ref)["plan_ref"] for ref in binding_refs)
        fields = {"kind", "definition_id", "owner_plan_id", "owner_revision"}
        pending = []
        for plan_ref in seeds:
            pending.extend(use for use in _walk(self.reference(plan_ref)) if set(use) == fields)
        visited = set()
        resolved = {}
        while pending:
            use = pending.pop()
            key = use["kind"], use["definition_id"]
            if key not in owners:
                _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, path=path, expected="explicit definition owner", actual=list(key))
            owner = owners[key]
            ref = owner["plan_ref"]
            if ref["entity_id"] != use["owner_plan_id"] or ref["revision"] != use["owner_revision"]:
                _fail(codec.ReasonCode.REVISION_MISMATCH, path=path, expected=[use["owner_plan_id"], use["owner_revision"]], actual=[ref["entity_id"], ref["revision"]])
            resolved[key] = owner
            identity = key, _key(ref)
            if identity in visited:
                continue
            visited.add(identity)
            plan = self.reference(ref)
            plural = {"flow": "flows", "command": "commands", "state": "states"}[key[0]]
            definition = next((row for row in plan["definitions"][plural] if row["id"] == key[1]), None)
            if definition is None:
                _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, path=path, expected="declared owner definition", actual=list(key))
            pending.extend(child for child in _walk(definition) if set(child) == fields)
            pending.extend(plan["logical_references"])
        return resolved

    def relationships(self, catalog: dict) -> None:
        path = self.catalog_path
        heads = _unique(catalog["scope_heads"], path=path, pointer="/scope_heads", key=lambda row: row["scope_id"])
        owners = self.definition_map(catalog["definition_owners"], path)
        current_plans, current_bindings = {}, {}
        active = {self.bytes.lookup(catalog["policy_ref"]["path"]), self.bytes.lookup(catalog["origins_ref"]["path"])}
        for head in heads.values():
            plans = self.refset(head["plan_refs"], path, "/scope_heads/plan_refs")
            bindings = self.refset(head["binding_refs"], path, "/scope_heads/binding_refs")
            receipt = self.reference(head["receipt_ref"])
            self.current_receipts.add(self.bytes.lookup(head["receipt_ref"]["path"]))
            receipt_plans = self.refset(receipt["plan_refs"], head["receipt_ref"]["path"], "/plan_refs")
            receipt_bindings = self.refset(receipt["binding_refs"], head["receipt_ref"]["path"], "/binding_refs")
            if head["scope_id"] not in receipt["scopes"] or head["scope_id"] not in receipt["result"]["scope_ids"]:
                _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="scope in receipt scopes/result", actual=head["scope_id"])
            if not set(plans) <= set(receipt_plans) or not set(bindings) <= set(receipt_bindings):
                _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="head selections belong to its receipt", actual=head["scope_id"])
            current_plans.update(plans)
            current_bindings.update(bindings)
            for binding_ref in bindings.values():
                binding = self.reference(binding_ref)
                current_plans[_key(binding["plan_ref"])] = binding["plan_ref"]
            related = self.closure(list(plans.values()), list(bindings.values()), owners, path)
            frozen = self.definition_map(receipt["resolved_definitions"], head["receipt_ref"]["path"])
            for key, owner in related.items():
                if key not in frozen or owner != frozen[key]:
                    _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="current relevant owner matches frozen receipt", actual=list(key))
            active.update(self.bytes.lookup(row["plan_ref"]["path"]) for row in related.values())
        active.update(self.bytes.lookup(ref["path"]) for ref in current_plans.values())
        active.update(self.bytes.lookup(ref["path"]) for ref in current_bindings.values())
        self.active = active | {self.catalog_path} | self.current_receipts
        expected_owners = {}
        for plan_ref in current_plans.values():
            plan = self.reference(plan_ref)
            for kind, plural in (("flow", "flows"), ("command", "commands"), ("state", "states")):
                for definition in plan["definitions"][plural]:
                    key = kind, definition["id"]
                    owner = {"kind": kind, "definition_id": definition["id"], "plan_ref": plan_ref}
                    if key in expected_owners and expected_owners[key] != owner:
                        _fail(codec.ReasonCode.DUPLICATE_OWNER, path=path, expected="one current definition owner", actual=list(key))
                    expected_owners[key] = owner
        if owners != expected_owners:
            _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, pointer="/definition_owners", expected="exact current plan definition domain and references", actual="owner mismatch")
        for record_path, value in list(self.records.items()):
            if value["schema_version"].endswith("commit.v1"):
                frozen = self.definition_map(value["resolved_definitions"], record_path)
                actual = self.closure(value["plan_refs"], value["binding_refs"], frozen, record_path)
                if actual != frozen:
                    _fail(codec.ReasonCode.MAPPING_MISMATCH, path=record_path, pointer="/resolved_definitions", expected="exact recursive owner closure", actual="extra or missing owner")
                self.receipt(value, record_path, active)
        # Resolving frozen maps above can add historic records. Always finish the
        # immutable B-reference closure, while external source checks stay active.
        self.expand()
        self.external(active)
        for plan_ref in current_plans.values():
            self.routes(self.reference(plan_ref), plan_ref["path"], owners)
        self.tasks(catalog, current_bindings, owners)

    def routes(self, plan: dict, path: str, owners: dict) -> None:
        requirements = {row["requirement_id"]: row for row in plan["requirements"]}
        flows = {}
        for (kind, fid), owner in owners.items():
            if kind == "flow":
                owner_plan = self.reference(owner["plan_ref"])
                flows[fid] = next(row for row in owner_plan["definitions"]["flows"] if row["id"] == fid)
        pairs = set()
        for row in plan["requirement_route_memberships"]:
            rid, fid = row["requirement_id"], row["flow_id"]
            if rid not in requirements or fid not in flows or rid not in flows[fid]["requirement_ids"]:
                _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="declared Requirement/Flow membership", actual=[rid, fid])
            pairs.add((rid, fid))
        for row in plan["requirement_verification"]:
            if row["disposition"] == "flow" and (row["requirement_id"], row["flow_id"]) not in pairs:
                _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="Flow verification route membership", actual=row["requirement_id"])
        for row in plan["requirement_evidence"]:
            if not set(row["flow_ids"]) <= set(flows):
                _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, path=path, expected="declared/catalog-resolved evidence Flow", actual=row["flow_ids"])

    def receipt(self, receipt: dict, path: str, active: set[str]) -> None:
        targets = _unique(receipt["targets"], path=path, pointer="/targets", key=lambda row: self.bytes.lookup(row["path"]))
        authority = _unique(receipt["authority"], path=path, pointer="/authority", key=lambda row: self.bytes.lookup(row["path"]))
        projection_targets = None
        result_paths = receipt["result"]["target_paths"]
        _unique(result_paths, path=path, pointer="/result/target_paths", key=self.bytes.lookup)
        for result_path in map(self.bytes.lookup, result_paths):
            if result_path in (path, self.catalog_path):
                _fail(codec.ReasonCode.DIGEST_CYCLE, path=path, expected="result excluding receipt/catalog", actual=result_path)
        if set(map(self.bytes.lookup, result_paths)) != set(targets) or set(receipt["scopes"]) != set(receipt["result"]["scope_ids"]):
            _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="matching receipt result target paths/scopes", actual="different result")
        for target_path, target in targets.items():
            if target_path in (path, self.catalog_path):
                _fail(codec.ReasonCode.DIGEST_CYCLE, path=path, expected="target excluding receipt/catalog", actual=target_path)
            if target_path in authority and any(target[field] != authority[target_path][field] for field in ("before_digest", "after_digest")):
                _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, expected="same target/authority images", actual=target_path)
            if target["verification_mode"] == "task_definition_projection":
                if projection_targets is None:
                    projection_targets = {self.bytes.lookup(target) for target in (
                        ".taskmaster/tasks/tasks.json", ".taskmaster/tasks/tasks_back.json",
                        ".taskmaster/tasks/tasks_gameplay.json")}
                if (target_path not in projection_targets or target_path in self.records
                        or _managed_candidate(_path(target["path"]))
                        or any(Path(target_path) == Path(self.bytes.lookup(BASE + name))
                               for name in ("policy.v1.json", "task-origins.v1.json", "catalog.v1.json"))
                        or any(Path(target_path).is_relative_to(Path(self.bytes.lookup(BASE + name)))
                               for name in ("plans", "bindings", "commits"))):
                    _fail(codec.ReasonCode.INVALID_REFERENCE, path=path, pointer="/targets",
                          expected="Taskmaster or business-view triplet projection target",
                          actual=target["path"])
            if target["verification_mode"] == "immutable_bytes":
                if target["projection_digest"] != target["after_digest"]:
                    _fail(codec.ReasonCode.DIGEST_MISMATCH, path=path, expected=target["after_digest"], actual=target["projection_digest"])
                mutable_governance = target_path in (self.bytes.lookup(BASE + "policy.v1.json"), self.bytes.lookup(BASE + "task-origins.v1.json"))
                # An older receipt can share an unchanged head with a later
                # operation. A different receipt must actually bind the current
                # after-image before treating this target as historical.
                replaced = any(other_path != path and other_path in self.current_receipts
                    and other["schema_version"] == "newrouge.b-route-commit.v1"
                    and any(self.bytes.lookup(row["path"]) == target_path and row["after_digest"] == codec.raw_digest(self.bytes.read(target_path))
                            for row in other["targets"])
                    for other_path, other in self.records.items()) if mutable_governance else False
                if mutable_governance and replaced and codec.raw_digest(self.bytes.read(target_path)) != target["after_digest"]:
                    self.historical_targets_not_revalidated.append({"operation_id": receipt["operation_id"], "path": target["path"]})
                else:
                    digest = codec.raw_digest(self.bytes.read(target_path))
                    if digest != target["after_digest"]:
                        _fail(codec.ReasonCode.DIGEST_MISMATCH, path=target_path, expected=target["after_digest"], actual=digest)
        for authority_path, row in authority.items():
            if authority_path == path or (authority_path == self.catalog_path and row["after_digest"] is not None):
                _fail(codec.ReasonCode.DIGEST_CYCLE, path=path, expected="no receipt/catalog after-image", actual=authority_path)
        # A declared immutable target must agree with each given public identity;
        # canonical refs retain their separate canonical digest meaning.
        for ref in receipt["plan_refs"] + receipt["binding_refs"]:
            target = targets.get(self.bytes.lookup(ref["path"]))
            if target is not None:
                actual = codec.raw_digest(self.bytes.read(ref["path"]))
                if target["after_digest"] != actual:
                    _fail(codec.ReasonCode.DIGEST_MISMATCH, path=path, expected=target["after_digest"], actual=actual)

    def tasks(self, catalog: dict, current_bindings: dict, owners: dict) -> None:
        expected = {}
        task_maps = []
        for binding_ref in current_bindings.values():
            binding = self.reference(binding_ref)
            plan = self.reference(binding["plan_ref"])
            requirement_ids = {row["requirement_id"] for row in plan["requirements"]}
            flow_ids = {fid for kind, fid in owners if kind == "flow"}
            obligation_ids = {row["id"] for row in binding["obligations"]}
            mapped_ids = {row["task_id"] for row in binding["task_mappings"]}
            for obj in binding["implementation_objects"]:
                if not set(obj["responsible_task_ids"]) <= mapped_ids:
                    _fail(codec.ReasonCode.MAPPING_MISMATCH, path=binding_ref["path"], expected="mapped responsible Tasks", actual=obj["responsible_task_ids"])
            for row in binding["obligations"]:
                if not set(row["requirement_ids"]) <= requirement_ids or not set(row["flow_ids"]) <= flow_ids:
                    _fail(codec.ReasonCode.MAPPING_MISMATCH, path=binding_ref["path"], expected="known obligation Requirement/Flow", actual=row["id"])
            for row in binding["task_mappings"]:
                if (not set(row["requirement_ids"]) <= requirement_ids or not set(row["flow_ids"]) <= flow_ids
                        or not set(row["obligation_ids"]) <= obligation_ids):
                    _fail(codec.ReasonCode.MAPPING_MISMATCH, path=binding_ref["path"], expected="known Task mapping declarations", actual=row["task_id"])
                task_maps.append(row)
                task = expected.setdefault(row["task_id"], {"plan_refs": {}, "binding_refs": {}})
                task["plan_refs"][_key(binding["plan_ref"])] = binding["plan_ref"]
                task["binding_refs"][_key(binding_ref)] = binding_ref
        origins = self.reference(catalog["origins_ref"])
        for label, rows in (("origins.tasks", origins["tasks"]), ("catalog.task_index", catalog["task_index"])):
            index = _unique(rows, path=self.catalog_path, pointer="/" + label, key=lambda row: row["task_id"])
            if set(index) != set(expected):
                _fail(codec.ReasonCode.MAPPING_MISMATCH, path=self.catalog_path, expected="complete current Task domain", actual=label)
            for task_id, row in index.items():
                for field in ("plan_refs", "binding_refs"):
                    actual = self.refset(row[field], self.catalog_path, "/" + label + "/" + field)
                    if actual != expected[task_id][field]:
                        _fail(codec.ReasonCode.MAPPING_MISMATCH, path=self.catalog_path, expected="exact current binding reverse projection", actual=[label, task_id, field])
        if task_maps:
            if type(self.task_join) is not TaskJoinContext:
                _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, expected="TaskJoinContext for nonempty mappings", actual="missing join context")
            master, views = self.task_join.indexes()
            for row in task_maps:
                if row["task_id"] not in master:
                    _fail(codec.ReasonCode.MAPPING_MISMATCH, expected="mapped master Task", actual=row["task_id"])
                _unique(row["view_refs"], path=self.catalog_path, pointer="/view_refs", key=lambda item: item["view"])
                for view in row["view_refs"]:
                    if views[view["view"]].get(view["business_id"]) != row["task_id"]:
                        _fail(codec.ReasonCode.MAPPING_MISMATCH, expected="exact master/view business join", actual=view)

    def source(self, plan: dict, path: str) -> None:
        source = plan["source_identity"]
        # These owner locators can select fragments; native source identities
        # themselves always come from the complete owning document.
        manifest_path = source["manifest_ref"]["ref"].partition("#")[0]
        ledger_path = source["ledger_ref"]["ref"].partition("#")[0]
        manifest = codec.strict_json_loads(self.bytes.read(manifest_path))
        ledger = codec.strict_json_loads(self.bytes.read(ledger_path))
        if type(manifest) is not dict or type(ledger) is not dict:
            _fail(codec.ReasonCode.INVALID_TYPE, path=path, expected="native source objects", actual="invalid source document")
        revision = source["source_revision"]
        digest = source["source_manifest_digest"]
        if manifest.get("source_revision") != revision or ledger.get("source_revision") != revision:
            _fail(codec.ReasonCode.REVISION_MISMATCH, path=path, expected=revision,
                  actual=[manifest.get("source_revision"), ledger.get("source_revision")])
        if manifest.get("manifest_sha256") != digest or ledger.get("source_manifest_sha256") != digest:
            _fail(codec.ReasonCode.DIGEST_MISMATCH, path=path, expected=digest,
                  actual=[manifest.get("manifest_sha256"), ledger.get("source_manifest_sha256")])
        blocks = ledger.get("blocks")
        if type(blocks) is not list or any(type(row) is not dict or type(row.get("block_id")) is not str for row in blocks):
            _fail(codec.ReasonCode.INVALID_TYPE, path=ledger_path, expected="native ledger.blocks", actual="invalid blocks")
        block_ids = _unique(blocks, path=ledger_path, pointer="/blocks", key=lambda row: row["block_id"])
        for requirement in plan["requirements"]:
            if not set(requirement["source_block_ids"]) <= set(block_ids):
                _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, path=path, expected="ledger block IDs", actual=requirement["source_block_ids"])

    def evidence(self, plan: dict, path: str) -> None:
        refs = _unique(plan["evidence_source_refs"], path=path, pointer="/evidence_source_refs", key=lambda row: (row["owner"], row["ref"]))
        used = set()
        locators = []
        for row in plan["requirement_evidence"]:
            owners = ("implementation_reference", "contract") if row["kind"] == "implementation_reference" else (row["kind"],)
            locators.append((owners, row["source_ref"]))
        for row in plan["requirement_verification"]:
            for field, owner in (("verification_ref", "other_verification"), ("authority_ref", "authority")):
                if row[field] is not None:
                    locators.append(((owner,), row[field]))
        for owners, locator in locators:
            matching = {(owner, locator) for owner in owners if (owner, locator) in refs}
            if len(matching) != 1:
                _fail(codec.ReasonCode.UNRESOLVED_REFERENCE, path=path, pointer="/evidence_source_refs", expected="exactly one owner/locator binding", actual=locator)
            used.update(matching)
        if used != set(refs):
            _fail(codec.ReasonCode.MAPPING_MISMATCH, path=path, pointer="/evidence_source_refs", expected="only referenced descriptions", actual=sorted(set(refs) - used))
        for proof in plan["adoption_proof_refs"]:
            target = self.bytes.lookup(proof["ref"].partition("#")[0])
            commit_dir = self.bytes.lookup(BASE + "commits")
            if target.startswith(commit_dir + "/") or target == self.catalog_path:
                _fail(codec.ReasonCode.DIGEST_CYCLE, path=path, expected="independent planning proof", actual=target)

    def baseline_check(self) -> None:
        if self.baseline is None:
            return
        old = _Bytes(self.baseline, None)
        maximum = {}
        for path, data in old.candidates.items():
            if not path.startswith(BASE) or path.startswith(BASE + "schemas/") or not path.endswith(".json"):
                continue
            try:
                value = codec.strict_json_loads(data)
            except codec.CodecError:
                if _managed_candidate(path):
                    raise
                continue
            if not _managed_candidate(path) and (type(value) is not dict or value.get("schema_version") not in codec.SCHEMA_IDENTITY_REGISTRY):
                continue
            result = validate_record(data, path=path)
            if not result.ok:
                raise codec.CodecError(result.diagnostic)
            schema, entity, revision = codec._record_identity(value)
            maximum[(schema, entity)] = max(revision, maximum.get((schema, entity), 0))
            address = self.bytes.lookup(path)
            if address in self.records and self.bytes.read(path) != data and schema in (
                    "newrouge.b-route-plan.v1", "newrouge.b-route-binding.v1", "newrouge.b-route-commit.v1"):
                _fail(codec.ReasonCode.CONFLICT, path=path, expected="unchanged immutable baseline bytes", actual="changed bytes")
        for path, value in self.records.items():
            schema, entity, revision = codec._record_identity(value)
            previous = maximum.get((schema, entity))
            logical = _managed_path(value)
            changed = logical not in old.candidates or old.candidates[logical] != self.bytes.read(path)
            if path in self.active and previous is not None and changed and revision <= previous:
                _fail(codec.ReasonCode.REVISION_MISMATCH, path=path, expected={"greater_than": previous}, actual=revision)


def validate_bundle(records: Mapping[str, bytes], *, root: Path | None = None,
                    catalog_path: str = CATALOG_PATH, baseline: Mapping[str, bytes] | None = None,
                    task_join: TaskJoinContext | None = None) -> BundleValidation:
    try:
        bundle = _Bundle(records, root, catalog_path, baseline, task_join)
        # Validate every supplied B record before resolving the candidate closure.
        for path, data in bundle.bytes.candidates.items():
            managed = _managed_candidate(_path(bundle.bytes.original_paths[path]))
            is_record = False
            if path.endswith(".json"):
                try:
                    value = codec.strict_json_loads(data)
                    is_record = type(value) is dict and value.get("schema_version") in codec.SCHEMA_IDENTITY_REGISTRY
                except codec.CodecError:
                    if managed:
                        raise
            if managed or is_record:
                result = validate_record(data, path=bundle.bytes.original_paths[path])
                if not result.ok:
                    raise codec.CodecError(result.diagnostic)
                bundle.load(path)
        catalog = bundle.load(catalog_path)
        if catalog["schema_version"] != "newrouge.b-route-catalog.v1":
            _fail(codec.ReasonCode.SCHEMA_MISMATCH, path=catalog_path, expected="catalog", actual=catalog["schema_version"])
        bundle.expand()
        bundle.relationships(catalog)
        bundle.baseline_check()
        bundle.bytes.stable()
        return BundleValidation(True, codec.Diagnostic(codec.ReasonCode.OK, codec.Stage.BUNDLE),
                                True, True, baseline is not None,
                                historical_targets_not_revalidated=tuple(bundle.historical_targets_not_revalidated))
    except codec.CodecError as error:
        return bundle_failure(error.diagnostic)
    except (OSError, RuntimeError, ValueError, RecursionError) as error:
        return bundle_failure(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.BUNDLE,
            expected="readable supported candidate input", actual=type(error).__name__))
