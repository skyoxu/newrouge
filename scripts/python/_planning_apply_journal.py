"""Durable roll-forward for a reviewed multi-file planning apply."""
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

from _planning_skill_common import atomic_json, atomic_json_win32_paths_fit, canonical_sha, file_sha, load_json, normalized_file_sha, relative, repo_path, text_sha


def create_journal(root: Path, path: Path, targets: dict[Path, Any], authority: dict[str, Any],
                   result: dict[str, Any], *, mutable_json_keys: dict[Path, list[str]] | None = None) -> dict[str, Any]:
    entries = []
    for target, payload in targets.items():
        raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        entries.append({"path": relative(root, target), "before_sha256": file_sha(target) if target.is_file() else None,
            "before_base64": base64.b64encode(target.read_bytes()).decode() if target.is_file() else None,
            "after_sha256": text_sha(raw), "payload": payload})
        entries[-1]["mutable_json_keys_after_complete"] = (mutable_json_keys or {}).get(target, [])
    journal = {"schema_version": "newrouge.planning-apply-journal.v1", "status": "pending",
        "authority_inputs": authority, "entries": entries, "result": result}
    atomic_json(path, journal)
    return journal


def resume_journal(root: Path, path: Path, writer: Callable) -> dict[str, Any]:
    journal = load_json(path, {})
    if not isinstance(journal, dict) or journal.get("schema_version") != "newrouge.planning-apply-journal.v1":
        raise ValueError("invalid planning apply journal")
    if journal.get("status") not in ("pending", "complete"):
        raise ValueError("invalid planning journal status")
    if not isinstance(journal.get("result"), dict) or not isinstance(journal.get("authority_inputs"), dict):
        raise ValueError("invalid planning journal envelope")
    if not isinstance(journal.get("entries"), list):
        raise ValueError("invalid planning journal entries")
    entries = journal["entries"]
    identities = set()
    for row in entries:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str) or not row["path"]:
            raise ValueError("invalid planning journal target")
        identity = os.path.normcase(str(repo_path(root, row["path"])))
        if identity in identities:
            raise ValueError("duplicate planning journal target")
        identities.add(identity)
        if "before_sha256" not in row or "before_base64" not in row:
            raise ValueError("missing planning journal before image")
        before, encoded = row["before_sha256"], row["before_base64"]
        if before is None:
            if encoded is not None:
                raise ValueError("invalid planning journal before image")
        else:
            if not isinstance(before, str) or not isinstance(encoded, str):
                raise ValueError("invalid planning journal before image")
            try:
                original = base64.b64decode(encoded, validate=True)
            except ValueError as error:
                raise ValueError("invalid planning journal before image") from error
            if "sha256:" + hashlib.sha256(original).hexdigest() != before:
                raise ValueError("planning journal before image identity changed")
        mutable = row.get("mutable_json_keys_after_complete", [])
        if not isinstance(mutable, list) or any(not isinstance(key, str) for key in mutable):
            raise ValueError("invalid planning journal mutable keys")
    owned = {row["path"] for row in entries}
    # Validate the entire transaction before replacing any file. Subsequent user
    # changes are never treated as writes made by this transaction.
    for rel, expected in journal["authority_inputs"].items():
        if rel in owned:
            continue
        target = repo_path(root, rel)
        actual = normalized_file_sha(target) if target.is_file() else None
        raw_actual = file_sha(target) if target.is_file() else None
        if actual != expected and raw_actual != expected:
            raise ValueError(f"planning recovery input drift:{rel}")
    for row in entries:
        if text_sha(json.dumps(row["payload"], ensure_ascii=False, indent=2) + "\n") != row["after_sha256"]:
            raise ValueError("planning journal payload identity changed")
        target = repo_path(root, row["path"])
        actual = file_sha(target) if target.is_file() else None
        allowed = {row["after_sha256"]} if journal["status"] == "complete" else {row["before_sha256"], row["after_sha256"]}
        mutable = row.get("mutable_json_keys_after_complete", [])
        if actual not in allowed and journal["status"] == "complete" and mutable and target.is_file():
            current = load_json(target, {})
            expected = dict(row["payload"])
            for key in mutable:
                current.pop(key, None)
                expected.pop(key, None)
            if canonical_sha(current) == canonical_sha(expected):
                continue
        if actual not in allowed:
            raise ValueError(f"planning recovery target drift:{row['path']}")
    if journal["status"] == "complete":
        return journal["result"]
    for row in entries:
        target = repo_path(root, row["path"])
        if not target.is_file() or file_sha(target) != row["after_sha256"]:
            writer(target, row["payload"])
    journal["status"] = "complete"
    atomic_json(path, journal)
    return journal["result"]


# Auxiliary operation storage is intentionally separate from v1 target replay.
# Its caller owns eligibility, semantic review, allocation and common leases.
OPERATION_SCHEMA = "newrouge.b-route-adoption-operation.v1"
ADOPTION_V2_SCHEMA = "newrouge.b-route-adoption-operation.v2"
ADOPTION_V2_REQUEST = "newrouge.b-route-adoption-request.v2"
COMPENSATION_SCHEMA = "newrouge.b-route-compensation-operation.v2"
COMPENSATION_REQUEST = "newrouge.b-route-compensation-request.v2"
PENDING_SCHEMA = "newrouge.b-route-adoption-pending.v1"
OPERATION_STORE = "logs/ci/b-route-operations"


def _operation_fail(code, expected, actual, *, operation_id=None, resume_ref=None):
    import _b_route_codec as codec
    raise codec.CodecError(codec.Diagnostic(code, codec.Stage.CONTENT,
        entity_id=operation_id, expected=expected, actual=actual, resume_ref=resume_ref))


def _operation_schema(value, definition=None, *, schema_id=None):
    import _b_route_codec as codec
    import _b_route_schema_resources as schemas
    codec.validate_json_value(value)
    if schema_id is None:
        # Frozen has no outer version: its complete request selects its owner.
        subject = value.get('request') if definition == 'Frozen' and type(value) is dict else value
        version = subject.get('schema_version') if type(subject) is dict else None
        if version in (COMPENSATION_SCHEMA, COMPENSATION_REQUEST):
            schema_id = COMPENSATION_SCHEMA
        elif version in (ADOPTION_V2_SCHEMA, ADOPTION_V2_REQUEST):
            schema_id = ADOPTION_V2_SCHEMA
        else:
            schema_id = OPERATION_SCHEMA  # Its strict schema rejects unknown versions.
    validator = schemas.validator(schema_id, auxiliary=True)
    if definition is not None:
        validator = validator.evolve(schema={"$ref": schema_id + "#/$defs/" + definition})
    error = next(validator.iter_errors(value), None)
    if error is not None:
        pointer = "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in error.absolute_path)
        _operation_fail(codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                        {"json_pointer": pointer, "rule": error.validator}, error.message)


def _operation_no_reparse(path):
    import stat
    import _b_route_codec as codec
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        _operation_fail(codec.ReasonCode.PATH_UNPROVABLE, "readable operation topology", type(error).__name__)
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or getattr(info, "st_reparse_tag", 0)):
        _operation_fail(codec.ReasonCode.UNSAFE_PATH, "plain contained operation path", "reparse path")
    return info


def _operation_path(root, reference):
    """Validate even absent targets without following an existing reparse point."""
    import _b_route_codec as codec
    codec.validate_reference_path(reference)
    if any(part in ("", ".", "..") for part in reference.split("/")):
        _operation_fail(codec.ReasonCode.UNSAFE_PATH, "unambiguous relative POSIX path", reference)
    base = Path(root).absolute()
    for path in reversed((base, *base.parents)):
        _operation_no_reparse(path)
    if not base.is_dir():
        _operation_fail(codec.ReasonCode.PATH_UNPROVABLE, "existing repository directory", "missing root")
    result = base
    for part in reference.split("/"):
        result = result / part
        _operation_no_reparse(result)
    if not result.resolve().is_relative_to(base.resolve()):
        _operation_fail(codec.ReasonCode.UNSAFE_PATH, "contained operation path", reference)
    return result


def _operation_key(operation_id):
    import _b_route_codec as codec
    codec.validate_business_id(operation_id)
    try:
        return hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
    except UnicodeError:
        _operation_fail(codec.ReasonCode.INVALID_UTF8, "UTF-8 operation ID", "unpaired surrogate")


def _operation_ref(operation_id):
    return OPERATION_STORE + "/operations/" + _operation_key(operation_id) + "/operation.json"


def _operation_read(root, path):
    import stat
    import _b_route_codec as codec
    info = _operation_no_reparse(path)
    if info is None:
        _operation_fail(codec.ReasonCode.FILE_NOT_FOUND, "existing operation record", "missing record",
                        resume_ref=path.relative_to(Path(root).absolute()).as_posix())
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        _operation_fail(codec.ReasonCode.UNSAFE_PATH, "single plain operation file", "nonregular or aliased file")
    return codec.strict_json_loads(codec.read_reference_bytes(root, path.relative_to(Path(root).absolute()).as_posix()))


def _operation_references(root, references):
    import _b_route_codec as codec
    seen = set()
    for reference in references:
        path = _operation_path(root, reference["path"])
        key = os.path.normcase(str(path))
        if key in seen:
            _operation_fail(codec.ReasonCode.CONFLICT, "unique authority paths", "duplicate authority reference")
        seen.add(key)


def validate_operation_request(value):
    """Validate the single auxiliary request schema without stripping its content."""
    import _b_route_codec as codec
    if type(value) in (bytes, str):
        value = codec.strict_json_loads(value)
    _operation_schema(value, "Request")
    codec.validate_business_id(value["operation_id"])
    # Business alignment/template interpretation belongs to the adoption owner.
    return value


def _operation_validate(root, value):
    import stat
    import _b_route_codec as codec
    _operation_schema(value)
    codec.validate_business_id(value["operation_id"])
    if value["codec_version"] != codec.CODEC_VERSION:
        _operation_fail(codec.ReasonCode.UNKNOWN_CODEC_VERSION, codec.CODEC_VERSION, value["codec_version"])
    try:
        raw = base64.b64decode(value["request_raw_base64"], validate=True)
    except (ValueError, UnicodeError) as error:
        _operation_fail(codec.ReasonCode.INVALID_JSON, "intact base64 request bytes", type(error).__name__)
    request = validate_operation_request(raw)
    if request["operation_id"] != value["operation_id"]:
        _operation_fail(codec.ReasonCode.CONFLICT, "same operation ID", "request/envelope ID mismatch")
    expected_schema = (COMPENSATION_SCHEMA if request['schema_version'] == COMPENSATION_REQUEST else
                       ADOPTION_V2_SCHEMA if request['schema_version'] == ADOPTION_V2_REQUEST else OPERATION_SCHEMA)
    if value['schema_version'] != expected_schema:
        _operation_fail(codec.ReasonCode.SCHEMA_MISMATCH, 'same request/envelope version', value['schema_version'])
    frozen = value["frozen"]
    if (codec.raw_digest(raw) != value["request_raw_digest"]
            or codec.canonical_digest(request) != value["request_digest"]
            or codec.canonical_digest(frozen["request"]) != value["request_digest"]
            or codec.canonical_digest(frozen) != value["frozen_digest"]):
        _operation_fail(codec.ReasonCode.DIGEST_MISMATCH, "complete original request/frozen identities", "digest mismatch")
    scopes = frozen["scope_ids"]
    if scopes != sorted(set(scopes)) or any(not scope.strip() or scope != scope.strip() for scope in scopes):
        _operation_fail(codec.ReasonCode.CONFLICT, "sorted distinct unpadded scopes", scopes)
    _operation_references(root, frozen["authority_refs"])
    if request['schema_version'] == COMPENSATION_REQUEST:
        if value['schema_version'] != COMPENSATION_SCHEMA or frozen['producer'] != 'compensation':
            _operation_fail(codec.ReasonCode.CONFLICT, 'exact compensation producer dispatch', value['schema_version'])
        references = [request['selection']['plan_ref']]
        if request['selection']['binding_ref'] is not None:
            references.append(request['selection']['binding_ref'])
        if 'host_review_ref' in request:
            references.append(request['host_review_ref'])
        if frozen['compensation']['relation'] != request['compensates']:
            _operation_fail(codec.ReasonCode.CONFLICT, 'same exact reviewed compensation relation', value['operation_id'])
    else:
        if value['schema_version'] not in (OPERATION_SCHEMA, ADOPTION_V2_SCHEMA):
            _operation_fail(codec.ReasonCode.CONFLICT, 'exact adoption producer dispatch', value['schema_version'])
        material = request['material']
        references = [request['review_ref'], *([request['host_review_ref']] if 'host_review_ref' in request else []),
                      material['handoff_ref'], material['protection_ref'],
                      *material['authority_refs'], *material['lineage_refs']]
    for reference in references:
        _operation_path(root, reference["path"])
    targets = set()
    for target in frozen["targets"]:
        path = _operation_path(root, target["path"])
        info = _operation_no_reparse(path)
        if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
            _operation_fail(codec.ReasonCode.UNSAFE_PATH, "plain unaliased formal target", target["path"])
        key = os.path.normcase(str(path))
        if key in targets:
            _operation_fail(codec.ReasonCode.CONFLICT, "unique target paths", "duplicate target")
        targets.add(key)
        raw_after = (json.dumps(target["after_payload"], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if codec.raw_digest(raw_after) != target["after_raw_digest"]:
            _operation_fail(codec.ReasonCode.DIGEST_MISMATCH, "original complete after bytes", target["path"])
    return value


def _operation_index_row(value):
    return {"operation_id": value["operation_id"], "directory_key": _operation_key(value["operation_id"]),
            "scope_ids": value["frozen"]["scope_ids"], "frozen_digest": value["frozen_digest"], "state": value["state"]}




def operation_inventory(root):
    """Read the complete store/index pair; never repair an orphan or missing index."""
    import re
    import stat
    import _b_route_codec as codec
    root = Path(root).absolute()
    try:
        home = _operation_path(root, OPERATION_STORE)
        if not home.exists():
            return []
        if not home.is_dir():
            _operation_fail(codec.ReasonCode.IDENTITY_UNPROVABLE, "operation store directory", "not a directory")
        for entry in home.iterdir():
            _operation_no_reparse(entry)
            if entry.name not in {"operations", "pending.json", "locks"}:
                _operation_fail(codec.ReasonCode.IDENTITY_UNPROVABLE, "known complete store entries", entry.name)
            if entry.name in {"operations", "locks"} and not entry.is_dir():
                _operation_fail(codec.ReasonCode.IDENTITY_UNPROVABLE, "plain store directory", entry.name)
        directory = _operation_path(root, OPERATION_STORE + "/operations")
        values = []
        if directory.exists():
            for child in sorted(directory.iterdir()):
                info = _operation_no_reparse(child)
                if not stat.S_ISDIR(info.st_mode) or not re.fullmatch("[0-9a-f]{64}", child.name):
                    _operation_fail(codec.ReasonCode.IDENTITY_UNPROVABLE, "known operation directory key", child.name)
                contents = list(child.iterdir())
                names = {item.name for item in contents}
                if 'operation.json' not in names or not names <= {'operation.json', 'commit.json', 'commit.pending.json'}:
                    _operation_fail(codec.ReasonCode.IDENTITY_UNPROVABLE, "complete single operation file", child.name,
                        resume_ref=child.relative_to(root).as_posix())
                value = _operation_validate(root, _operation_read(root, child / 'operation.json'))
                if _operation_key(value["operation_id"]) != child.name:
                    _operation_fail(codec.ReasonCode.CONFLICT, "directory bound to original operation ID", child.name)
                values.append(value)
                if names != {'operation.json'}:
                    import _b_route_commit as commit
                    commit.validate_local(root, value)
        values.sort(key=lambda value: value["operation_id"])
        if len({value["operation_id"] for value in values}) != len(values):
            _operation_fail(codec.ReasonCode.CONFLICT, "unique operation IDs", "duplicate operation ID")
        index_path = _operation_path(root, OPERATION_STORE + "/pending.json")
        if not index_path.exists() and not values:
            return []
        index = _operation_read(root, index_path)
        _operation_schema(index, "Pending")
        expected = {"schema_version": PENDING_SCHEMA, "operations": [_operation_index_row(value) for value in values]}
        if codec.canonical_digest(index) != codec.canonical_digest(expected):
            _operation_fail(codec.ReasonCode.CONFLICT, "complete exact operation/index pair", "index mismatch",
                            resume_ref=OPERATION_STORE + "/pending.json")
        return values
    except codec.CodecError:
        raise
    except (OSError, ValueError, RuntimeError) as error:
        _operation_fail(codec.ReasonCode.READ_ERROR, "complete readable operation inventory", type(error).__name__,
                        resume_ref=OPERATION_STORE)


def read_operation(root, *, operation_id):
    """Inspect an intact operation without changing any file or allocation."""
    import _b_route_codec as codec
    _operation_key(operation_id)
    for value in operation_inventory(root):
        if value["operation_id"] == operation_id:
            return value
    _operation_fail(codec.ReasonCode.FILE_NOT_FOUND, "existing operation ID", operation_id,
                    operation_id=operation_id, resume_ref=_operation_ref(operation_id))


def _operation_write(root, value, inventory, *, verify=True):
    import _b_route_codec as codec
    path = _operation_path(root, _operation_ref(value["operation_id"]))
    index_path = _operation_path(root, OPERATION_STORE + "/pending.json")
    # Shared actual-final/fixed-temp UTF-16/NUL preflight, before any mkdir.
    if os.name == "nt" and any(not atomic_json_win32_paths_fit(item) for item in (path, index_path)):
        _operation_fail(codec.ReasonCode.UNSAFE_PATH, "Win32 atomic-write path capacity", "operation root too long",
                        operation_id=value["operation_id"], resume_ref=_operation_ref(value["operation_id"]))
    rows = [item for item in inventory if item["operation_id"] != value["operation_id"]] + [value]
    rows.sort(key=lambda item: item["operation_id"])
    try:
        # Ordered separate writes intentionally retain an observable partial state.
        atomic_json(path, value)
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
        atomic_json(index_path, {"schema_version": PENDING_SCHEMA,
                                "operations": [_operation_index_row(item) for item in rows]})
        with index_path.open("r+b") as stream:
            os.fsync(stream.fileno())
    except OSError as error:
        _operation_fail(codec.ReasonCode.CONFLICT, "complete durable operation/index write", type(error).__name__,
                        operation_id=value["operation_id"], resume_ref=_operation_ref(value["operation_id"]))
    if not verify:
        return value
    verified = next(item for item in operation_inventory(root) if item["operation_id"] == value["operation_id"])
    if codec.canonical_digest(verified) != codec.canonical_digest(value):
        _operation_fail(codec.ReasonCode.CONFLICT, "unchanged persisted operation", "post-write drift",
                        operation_id=value["operation_id"], resume_ref=_operation_ref(value["operation_id"]))
    return verified


def draft_operation(root, *, request_raw, frozen, state='prepared'):
    """Validate an auxiliary draft before the caller's short write boundary."""
    import _b_route_codec as codec
    request = validate_operation_request(request_raw)
    version = (COMPENSATION_SCHEMA if request['schema_version'] == COMPENSATION_REQUEST else
               ADOPTION_V2_SCHEMA if request['schema_version'] == ADOPTION_V2_REQUEST else OPERATION_SCHEMA)
    value = {'schema_version': version, 'codec_version': codec.CODEC_VERSION,
        'operation_id': request['operation_id'], 'state': state,
        'request_raw_base64': base64.b64encode(request_raw).decode('ascii'),
        'request_raw_digest': codec.raw_digest(request_raw), 'request_digest': codec.canonical_digest(request),
        'frozen': frozen, 'frozen_digest': codec.canonical_digest(frozen)}
    return _operation_validate(root, value)


def prepare_operation(root, *, operation_id, request_raw, frozen):
    """Persist already-reviewed frozen content; never allocate or apply a target."""
    import _b_route_codec as codec
    _operation_key(operation_id)
    if type(request_raw) is not bytes:
        _operation_fail(codec.ReasonCode.INVALID_TYPE, "complete request bytes", type(request_raw).__name__)
    request = validate_operation_request(request_raw)
    if request["operation_id"] != operation_id:
        _operation_fail(codec.ReasonCode.CONFLICT, "request bound to original operation ID", "operation ID mismatch")
    inventory = operation_inventory(root)
    for value in inventory:
        if value["operation_id"] == operation_id:
            if codec.canonical_digest(request) != value["request_digest"]:
                _operation_fail(codec.ReasonCode.CONFLICT, "same complete request for original operation ID", "different content",
                                operation_id=operation_id, resume_ref=_operation_ref(operation_id))
            return value
    codec.validate_json_value(frozen)
    frozen = codec.strict_json_loads(json.dumps(frozen, ensure_ascii=False))
    version = (COMPENSATION_SCHEMA if request['schema_version'] == COMPENSATION_REQUEST else
               ADOPTION_V2_SCHEMA if request['schema_version'] == ADOPTION_V2_REQUEST else OPERATION_SCHEMA)
    value = {"schema_version": version, "codec_version": codec.CODEC_VERSION,
        "operation_id": operation_id, "state": "prepared",
        "request_raw_base64": base64.b64encode(request_raw).decode("ascii"),
        "request_raw_digest": codec.raw_digest(request_raw), "request_digest": codec.canonical_digest(request),
        "frozen": frozen, "frozen_digest": codec.canonical_digest(frozen)}
    _operation_validate(root, value)
    return _operation_write(root, value, inventory)


def reserve_operation(root, *, operation_id):
    """Advance only the lifecycle state under the caller's common lease."""
    import _b_route_codec as codec
    _operation_key(operation_id)
    inventory = operation_inventory(root)
    for value in inventory:
        if value["operation_id"] == operation_id:
            if value["state"] == "reserved":
                return value
            value = {**value, "state": "reserved"}
            return _operation_write(root, value, inventory)
    _operation_fail(codec.ReasonCode.FILE_NOT_FOUND, "existing prepared operation", operation_id,
                    operation_id=operation_id, resume_ref=_operation_ref(operation_id))


def classify_frozen_target(root, target):
    """Read an exact frozen image without writing, creating or repairing anything.

    This is not apply authorization or a TOCTOU-proof write reservation. The
    commit owner must hold shared leases and call again immediately before any
    replacement. Unknown bytes are preserved and reported as a conflict.
    """
    import stat
    import _b_route_codec as codec
    _operation_schema(target, "Target")
    path = _operation_path(root, target["path"])
    raw_after = (json.dumps(target["after_payload"], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if codec.raw_digest(raw_after) != target["after_raw_digest"]:
        _operation_fail(codec.ReasonCode.DIGEST_MISMATCH, target["after_raw_digest"],
                        "changed frozen payload", resume_ref=target["path"])
    info = _operation_no_reparse(path)
    if info is None:
        actual = None
    else:
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            _operation_fail(codec.ReasonCode.UNSAFE_PATH, "single plain target file", target["path"],
                            resume_ref=target["path"])
        actual = codec.raw_digest(codec.read_reference_bytes(root, target["path"]))
    if actual == target["after_raw_digest"]:
        state = "after"
    elif actual == target["before_raw_digest"]:
        state = "before"
    else:
        _operation_fail(codec.ReasonCode.CONFLICT,
                        {"before": target["before_raw_digest"], "after": target["after_raw_digest"]},
                        actual, resume_ref=target["path"])
    return {"path": target["path"], "state": state, "actual_raw_digest": actual}


def active_operation_inventory(root):
    """Keep all original history; release only certified explicit terminals.

    The original exact operation/index pair stays unchanged. Absence of a
    marker, a receipt or a catalog alone never completes an operation.
    """
    graph = operation_state_graph(root)
    return [value for value in graph['operations'] if value['operation_id'] not in graph['terminals']
            and value['operation_id'] not in graph['resolved_by']]


def operation_state_graph(root):
    """Derive resolution from one immutable inventory and actual terminal proofs.

    Never mutate an old operation, index row, marker, budget or native journal.
    Terminal proof does not call active inventory, so cycles cannot recurse.
    """
    import _b_route_codec as codec
    import _b_route_commit as commit
    import _b_route_compensation as compensation
    operations = operation_inventory(root)
    intents = {row['operation_id']: commit.validate_local(root, row) for row in operations}
    names = {OPERATION_STORE + '/pending.json', 'docs/planning/b-route/catalog.v1.json'}
    for row in operations:
        names.update((_operation_ref(row['operation_id']), *commit._paths(row['operation_id']),
                      'docs/planning/b-route/commits/' + row['operation_id'] + '.json'))
    local_bytes = {}
    for name in names:
        path = _operation_path(root, name)
        local_bytes[name] = path.read_bytes() if path.exists() else None
    graph = {'operations': operations, 'intents': intents, 'terminals': set(), 'resolved_by': {},
             'local_bytes': local_bytes, 'catalog_raw': local_bytes['docs/planning/b-route/catalog.v1.json']}
    claims = {}
    by_id = {row['operation_id']: row for row in operations}
    for row in operations:
        if row['schema_version'] != COMPENSATION_SCHEMA:
            continue
        compensation.validate_relation(row['frozen'], operations)
        previous = row['frozen']['request']['compensates']['operation_id']
        if previous in claims:
            _operation_fail(codec.ReasonCode.CONFLICT, 'one compensation per original claim', previous)
        claims[previous] = row['operation_id']
    for origin in claims:
        seen, current = set(), origin
        while current in claims:
            if current in seen:
                _operation_fail(codec.ReasonCode.CONFLICT, 'acyclic compensation graph', origin)
            seen.add(current)
            current = claims[current]
    for row in operations:
        if commit.terminal_valid(root, row, intents[row['operation_id']], graph=graph):
            graph['terminals'].add(row['operation_id'])
    for previous, successor in claims.items():
        if successor in graph['terminals']:
            compensation.prove_resolution(root, by_id[successor], by_id[previous], graph)
            graph['resolved_by'][previous] = successor
    for name, expected in local_bytes.items():
        path = _operation_path(root, name)
        if (path.read_bytes() if path.exists() else None) != expected:
            _operation_fail(codec.ReasonCode.INPUT_STALE, 'same complete local operation/intent/publication graph', name)
    return graph
