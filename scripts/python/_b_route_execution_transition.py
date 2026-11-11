"""Explicit committed-source transition with unchanged native historical proof.

Every load launches the original verifier in a fresh offline Python process.
Old prepared bytes, descriptor and runtime identity are never repaired, re-signed
or relabelled as current-rule evidence. This is not native acceptance or dispatch
permission. The recovery owner separately authenticates the historical state and
binds this transition digest into each new execution.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
import ast
import base64
import math
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys

import _b_route_codec as codec


SCHEMA = "newrouge.b-route-execution-transition.v1"
EPOCH_SCHEMA = "newrouge.b-route-source-epoch.v1"
EPOCH_V2_SCHEMA = "newrouge.b-route-source-epoch.v2"
MVG_EPOCH_SCHEMA = "newrouge.b-route-mvg-source-epoch.v1"
MVG_PRIOR_COMMIT = "dc245b3b3d14abd512879369b30692536dfac4fd"
SELECTOR_EPOCH_SCHEMA = "newrouge.b-route-selector-source-epoch.v1"
SELECTOR_PRIOR_COMMIT = "1d126b85b908ba1eea4b27ceeb8a9669a771e6f3"
_ACTIVE_VERIFICATION = ContextVar("b_route_source_epoch_verification", default=None)
ORIGINAL_COMMIT = "988022094381c2b190b30c7702ed77aadda3805a"
ORIGINAL_RUN_SCHEMA = "newrouge.b-route-planning-run.v1"
CURRENT_RUN_SCHEMA = "newrouge.b-route-planning-run.v2"
_SOURCE_ROOT = Path(__file__).absolute().parents[2]
_ALLOWED = frozenset({"scripts/python/_b_route_planning_runtime.py",
                      "scripts/python/_mvg_capability_selection.py",
                      "scripts/python/_mvg_capability_worker.py",
                      "scripts/python/_b_route_execution_transition.py",
                      "scripts/python/_b_route_review_recovery.py",
                      "scripts/python/_b_route_synthesis_recovery.py",
                      "scripts/python/_b_route_partial_generation_recovery.py",
                      "scripts/python/_b_route_input_path_recovery.py",
                      "scripts/python/_b_route_mvg_synthesis_recovery.py",
                      "scripts/python/_b_route_selector_recovery.py",
                      "scripts/python/_b_route_planning_wire.py",
                      "scripts/python/_b_route_compact_literal.py",
                      "scripts/python/_mvg_capability_append.py"})
_FIELDS = frozenset({"schema_version", "original_source_root", "original_commit",
                     "current_source_root", "current_commit", "artifact_root", "original_run_schema",
                     "prepared_ref", "prepared_raw_digest", "frozen_sha256",
                     "original_runtime_identity", "original_runtime_rules",
                     "original_tracked_sources", "current_tracked_sources", "transition_digest"})
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class TransitionError(ValueError):
    """Unprovable original proof, source change, unsafe path or stale transition."""


def _require(condition, message):
    if not condition:
        raise TransitionError(message)


def _canonical(value):
    codec.validate_json_value(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _same(left, right):
    return _canonical(left) == _canonical(right)


def _no_reparse(path, *, directory=False):
    value = path.lstat()
    _require(not stat.S_ISLNK(value.st_mode) and not (getattr(value, "st_file_attributes", 0) & 0x400),
             "execution_transition_reparse_forbidden")
    _require(stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode),
             "execution_transition_filesystem_type")
    if not directory:
        _require(value.st_nlink == 1, "execution_transition_hardlink_forbidden")
    return value


def _root(value):
    path = Path(value)
    _require(path.is_absolute() and ".." not in path.parts, "execution_transition_absolute_root_required")
    for item in reversed((path, *path.parents)):
        _no_reparse(item, directory=True)
    return path.resolve(strict=True)


def _path(root, reference):
    _require(type(reference) is str and bool(reference) and "\\" not in reference
             and not reference.startswith("/") and ":" not in reference,
             "execution_transition_safe_reference_required")
    parts = reference.split("/")
    _require(all(part and part not in (".", "..") and part[-1] not in (".", " ")
                 and not any(ord(c) < 32 or c in '<>"|?*' for c in part) for part in parts),
             "execution_transition_safe_reference_required")
    _require(not any(part.lower() in {"sessions", "archived_sessions", ".aws"} for part in parts)
             and parts[-1].lower() not in {"auth.json", "credentials", "credentials.json", "credentials.toml"},
             "execution_transition_credentials_or_sessions_forbidden")
    target = root.joinpath(*parts)
    _require(target.is_relative_to(root), "execution_transition_path_escape")
    for parent in reversed(target.parents):
        if parent == root or parent.is_relative_to(root):
            _no_reparse(parent, directory=True)
    _no_reparse(target)
    return target


def _git(root, *arguments, input_bytes=None):
    executable = shutil.which("git")
    _require(executable is not None, "execution_transition_git_unavailable")
    result = subprocess.run([executable, "--no-optional-locks", "-c", "core.fsmonitor=false",
                             "-C", str(root), *arguments], input=input_bytes, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=60, check=False,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    _require(result.returncode == 0, "execution_transition_git_read_failed")
    return result.stdout


def _production(path):
    parts = PurePosixPath(path).parts
    if not parts or parts[0] in {"logs", ".git"} or any(p in {"tests", "__pycache__"} for p in parts):
        return False
    return (parts[-1] == ".gitattributes" or path.endswith(".py")
            or path.startswith("scripts/sc/") or path.endswith(".schema.json")
            or ("schemas" in parts and path.endswith(".json")))


def _tracked_tree(root, commit):
    result = {}
    for entry in _git(root, "ls-tree", "-rz", "--full-tree", commit).split(b"\x00"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        name = raw_name.decode("utf-8", errors="strict")
        if not _production(name):
            continue
        mode, kind, object_id = metadata.decode("ascii").split(" ")
        _require(kind == "blob" and mode in {"100644", "100755"}, "execution_transition_nonregular_source")
        result[name] = (mode, object_id)
    return result


def _source_manifest(root, commit):
    _require(type(commit) is str and _COMMIT.fullmatch(commit) is not None,
             "execution_transition_full_commit_required")
    _require(_git(root, "rev-parse", "--verify", commit + "^{commit}").decode("ascii").strip() == commit,
             "execution_transition_frozen_commit_missing")
    tracked = _tracked_tree(root, commit)
    _require(bool(tracked) and _tracked_tree(root, "HEAD") == tracked,
             "execution_transition_tracked_production_membership_changed")
    attributes = {}
    names = b"\x00".join(name.encode("utf-8") for name in sorted(tracked)) + b"\x00"
    rows = _git(root, "check-attr", "--source=" + commit, "--stdin", "-z", "text", "eol", "filter",
                "working-tree-encoding", "ident", input_bytes=names).split(b"\x00")
    _require(rows[-1] == b"" and (len(rows) - 1) % 3 == 0, "execution_transition_git_attributes_invalid")
    for index in range(0, len(rows) - 1, 3):
        name, key, value = (item.decode("utf-8", errors="strict") for item in rows[index:index + 3])
        attributes.setdefault(name, {})[key] = value
    result = {}
    for name, (mode, object_id) in tracked.items():
        source = _path(root, name)
        raw = source.read_bytes()
        blob = lambda value: hashlib.sha1(b"blob " + str(len(value)).encode("ascii") + b"\x00" + value).hexdigest()
        conversion = "none"
        if blob(raw) != object_id:
            attrs = attributes.get(name, {})
            normalized = raw.replace(b"\r\n", b"\n")
            permitted = (set(attrs) == {"text", "eol", "filter", "working-tree-encoding", "ident"}
                and attrs["text"] in {"set", "auto"} and attrs["eol"] == "crlf"
                and all(attrs[key] in {"unspecified", "unset"} for key in ("filter", "working-tree-encoding", "ident")))
            _require(permitted and normalized.replace(b"\n", b"\r\n") == raw and blob(normalized) == object_id,
                     "execution_transition_uncommitted_source:" + name)
            conversion = "explicit-git-attribute-crlf"
        result[name] = {"raw_digest": codec.raw_digest(raw), "git_blob": object_id, "git_mode": mode,
                        "checkout_conversion": conversion, "git_attributes": attributes[name]}
    _require(bool(result), "execution_transition_empty_source_manifest")
    others = _git(root, "ls-files", "--others", "-z")
    _require(not any(_production(name.decode("utf-8", errors="strict"))
                     for name in others.split(b"\x00") if name), "execution_transition_untracked_production_source")
    return result


def _allowed_delta(original, current):
    changed = {name for name in set(original) | set(current) if original.get(name) != current.get(name)}
    _require(changed and changed <= _ALLOWED, "execution_transition_source_change_outside_allowlist")
    module = "scripts/python/_b_route_execution_transition.py"
    _require(module not in original and module in current, "execution_transition_new_module_not_committed")
    _require(not (set(original) - set(current)), "execution_transition_source_removal_forbidden")
    return sorted(changed)


def _semantic_unchanged(original_root, current_root):
    names = {"review_schema", "review_issues", "obligations", "machine", "qualified_sources",
             "generation_schema", "generation_schemas", "generation_target"}
    snapshots = []
    for root in (original_root, current_root):
        text = _path(root, "scripts/python/_b_route_planning_runtime.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        selected = {node.name: ast.get_source_segment(text, node) for node in tree.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names}
        _require(set(selected) == names, "execution_transition_semantic_owner_missing")
        snapshots.append(selected)
    _require(_same(*snapshots), "execution_transition_canonical_semantics_changed")
    return {name: codec.raw_digest(value.encode("utf-8")) for name, value in snapshots[0].items()}


def _legacy_view(state):
    _require(type(state) is dict and state.get("schema_version") in {ORIGINAL_RUN_SCHEMA, CURRENT_RUN_SCHEMA},
             "execution_transition_run_schema_invalid")
    value = deepcopy(state)
    value["schema_version"] = ORIGINAL_RUN_SCHEMA
    value.pop("b_route_execution_transition", None)
    return value


_CHILD = r'''
import contextlib, hashlib, io, json, os, pathlib, subprocess, sys
request=json.loads(sys.stdin.buffer.read().decode('utf-8'))
original=pathlib.Path(request['original_source_root'])
root=pathlib.Path(request['artifact_root'])
sys.path[:0]=[str(original/'scripts/python'),str(original/'scripts/sc'),*request['dependency_paths']]
sys.dont_write_bytecode=True
def blocked(event,args):
    if event in ('socket.connect','socket.connect_ex','socket.getaddrinfo','socket.bind'):
        raise RuntimeError('execution_transition_network_forbidden')
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        value=os.fsdecode(args[0]).replace(chr(92),'/').lower()
        parts=value.split('/')
        if any(x in ('sessions','archived_sessions','.aws') for x in parts) or parts[-1] in ('auth.json','credentials','credentials.json','credentials.toml'):
            raise RuntimeError('execution_transition_credentials_or_sessions_forbidden')
        flags=args[2]
        if isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
            raise RuntimeError('execution_transition_read_only_verification')
    if event=='subprocess.Popen':
        command=args[1]
        script=str(original/'scripts/python/codex_isolated_model_runner.py')
        commands=[['git','-C',str(root),'rev-parse','HEAD'],
                  [sys.executable,script,'--describe'],[sys.executable,'-B',script,'--describe']]
        allowed=any((isinstance(command,(tuple,list)) and list(command)==expected)
                    or (isinstance(command,str) and command==subprocess.list2cmdline(expected))
                    for expected in commands)
        if not allowed:
            raise RuntimeError('execution_transition_subprocess_dispatch_forbidden')
sys.addaudithook(blocked)
with contextlib.redirect_stdout(io.StringIO()):
    import _b_route_codec as codec
    import _b_route_planning_input as planning
    import _b_route_planning_runtime as runtime
    assert pathlib.Path(planning.__file__).resolve()==original/'scripts/python/_b_route_planning_input.py'
    assert pathlib.Path(runtime.__file__).resolve()==original/'scripts/python/_b_route_planning_runtime.py'
    state=request['legacy_state']
    desc=runtime.descriptor(state)
    assert runtime.same_json(runtime.rules_identity(),desc['rules']), 'execution_transition_original_runtime_rules_changed'
    frozen=planning.load_prepared(root,desc['prepared_ref'],revalidate=True)
    assert runtime.same_json(frozen['input_identity'],desc['input_identity'])
    assert codec.canonical_digest(frozen)==desc['frozen_sha256']
    prepared=planning.sources.checked_path(root,desc['prepared_ref'])
    result={'frozen':frozen,'prepared_raw_digest':codec.raw_digest(prepared.read_bytes()),
            'runtime_rules':runtime.rules_identity(),'runtime_identity':state['runtime_identity'],
            'frozen_sha256':codec.canonical_digest(frozen)}
    if request['mode']=='generation':
        import _mvg_capability_selection as selection
        bindings,proposal=request['bindings'],request['proposal']
        drafts=proposal['provenance']['draft_chain']
        assert proposal['provenance']['kind']=='model_draft' and len(bindings)==len(drafts)==len(frozen['transport']['batches'])+1
        run=runtime.run_location(root,desc['planner'],state['run_id'])
        scopes=runtime.scopes(state,run/'analysis-input')
        ledger=state['capability_selection']
        selected=ledger.get('selected',[])
        base=runtime.seed(state,run/'analysis-input')
        if selected:
            verified=selection.verified_prefix(root,run,state,recover_counters=False)
            base=verified[1]
        index=len(selected)
        assert index<len(scopes)
        previous=[]
        shared=None
        for binding,draft in zip(bindings,drafts):
            assert runtime.same_json(runtime.decode_generation_carrier(runtime.verify_call(binding)),draft)
            materials=runtime.bound_materials(binding,state,frozen)
            expected=json.loads(runtime.request_attempt(frozen,batch=draft['ordinal'] if draft['stage']=='batch' else None,
                drafts=previous,delivery=runtime.wire_delivery(state))['payload'])
            assert materials['phase']=='generation' and runtime.same_json(materials['root_request'],expected)
            assert runtime.same_json(materials['accepted_seed'],base)
            slot,context,generation,execution=(materials[k] for k in ('slot','lineage_context','generation','execution'))
            assert slot in runtime.labels(state) and all(type(v) is int and v>=1 for v in (context,generation,execution))
            lineage=runtime.lineage_identity(state,base,slot,context,generation,execution)
            assert materials['lineage_identity']==lineage
            current=(slot,context,generation,execution,lineage)
            assert shared is None or shared==current
            shared=current
            workspace=selection.scope_workspace(run,slot,index,generation,execution)
            output=pathlib.Path(binding['output_path'])
            assert output.is_relative_to(run)
            matches=[row for row in ledger['calls'] if row.get('request_identity',{}).get('output_path')==output.relative_to(run).as_posix()]
            assert len(matches)==1
            call=matches[0]
            number=call['request_identity']['attempt']
            assert type(number) is int and number>=1
            call_root=workspace/'capability-append'/('c'+str(number))
            sandbox=call_root/'llm-sandbox'/('attempt-'+str(number))/'r'
            assert pathlib.Path(binding['prompt_path'])==sandbox/('prompt-'+str(number)+'-r.txt')
            assert pathlib.Path(binding['schema_path'])==sandbox/'output-schema.json'
            phase='repair' if materials['repair_issue'] is not None else 'generate'
            row=runtime.verify_bound_reservation(run,state,binding,candidate_slot=slot,scope_id=scopes[index]['capability_id'],
                phase=phase,generation=generation,execution=execution,expected_workspace=sandbox,expected_output=sandbox/'r.json')
            identity=row['request_identity']
            assert identity['fresh_lineage_identity']==lineage
            assert identity['execution_binding_path']==(call_root/('execution-binding-'+str(number)+'-r.json')).relative_to(run).as_posix()
            local=json.loads((workspace/'capability-append/append-ledger.json').read_text(encoding='utf-8'))
            assert any(item.get('reservation_id')==row['reservation_id'] and item.get('number')==number
                and item.get('context')==context and item.get('phase')==phase for item in local.get('calls',[]))
            previous.append(draft)
            planning.validate_draft_chain(frozen,previous)
        expected_proposal={'schema_version':runtime.candidate.SCHEMA,'input_stage':'3b','input_identity':frozen['input_identity'],
            'provenance':{'kind':'model_draft','declaration':'Complete original model draft chain; execution separately replayed',
                'upstream_model_history':'declared_model','draft_chain':drafts,'final_draft_identity':codec.canonical_digest(drafts[-1])},
            'content':drafts[-1]['content']}
        assert runtime.same_json(proposal,expected_proposal), 'execution_transition_original_proposal_changed'
        result['historical_generation']={'generation_count':len(bindings),'proposal_sha256':codec.canonical_digest(proposal),
            'frozen_sha256':codec.canonical_digest(frozen),'bindings_sha256':codec.canonical_digest(bindings)}
print(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False))
'''


def _run_original(original_root, artifact_root, legacy_state, *, bindings=None, proposal=None):
    dependencies = []
    for item in sys.path:
        if item and Path(item).name.lower() in {"site-packages", "story22-tokenizer-deps"}:
            path = str(Path(item).resolve(strict=True))
            if path not in dependencies:
                dependencies.append(path)
    request = {"mode": "generation" if bindings is not None else "prepared",
               "original_source_root": str(original_root), "artifact_root": str(artifact_root),
               "legacy_state": legacy_state, "dependency_paths": dependencies,
               "bindings": bindings, "proposal": proposal}
    environment = dict(os.environ)
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                       PYTHONPATH=os.pathsep.join([str(original_root / "scripts/python"),
                                                  str(original_root / "scripts/sc"), *dependencies]))
    completed = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", _CHILD], input=_canonical(request),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=original_root, env=environment, timeout=300,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
    if completed.returncode:
        error = TransitionError("execution_transition_original_native_verifier_failed:" + str(completed.returncode))
        error.diagnostic = completed.stderr.decode("utf-8", errors="replace")[-2400:]
        raise error
    result = codec.strict_json_loads(completed.stdout)
    _require(type(result) is dict, "execution_transition_original_result_invalid")
    return result


@contextmanager
def _verification_transaction():
    """Bounded read-only scans and one fresh witness; no caller writes/model I/O."""
    active = _ACTIVE_VERIFICATION.get()
    if active is not None:
        yield active
        return
    context = {"request": None, "expected": None, "key": None, "sources": {}, "active": set(),
               "frames": {}, "artifacts": {}}
    token = _ACTIVE_VERIFICATION.set(context)
    try:
        yield context
        if context["request"] is not None:
            original_root, artifact_root, view = context["request"]
            # One real original verifier runs after historical frames agree on
            # exact input/rules. External 3A currentness is fresh at closure.
            result = _run_original(original_root, artifact_root, view)
            _require(_same(result, context["expected"]), "execution_transition_shared_native_witness_changed")
            path, raw = context["prepared"]
            checked = _path(artifact_root, view["planning_runtime"]["prepared_ref"])
            _require(checked == path and checked.read_bytes() == raw, "execution_transition_prepared_raw_changed")
        for (source_root, commit), expected in context["sources"].items():
            _require(_source_manifest(Path(source_root), commit) == expected,
                     "execution_transition_source_changed_during_transaction")
        _check_artifact_pins(context["artifacts"])
    finally:
        _ACTIVE_VERIFICATION.reset(token)


def _remember_source(context, root, commit, manifest):
    if context is not None:
        key = (str(root), commit)
        _require(key not in context["sources"] or context["sources"][key] == manifest,
                 "execution_transition_source_changed_during_transaction")
        context["sources"][key] = deepcopy(manifest)


def _transaction_source(root, commit):
    context = _ACTIVE_VERIFICATION.get()
    key = (str(root), commit)
    if context is not None and key in context["sources"]:
        return deepcopy(context["sources"][key])
    value = _source_manifest(root, commit)
    _remember_source(context, root, commit, value)
    return value


def _check_artifact_pins(pins):
    for (artifact_root, reference), expected in pins.items():
        _require(codec.raw_digest(_path(Path(artifact_root), reference).read_bytes()) == expected,
                 "execution_epoch_historical_artifact_changed")


def _collect(root, state, original_root, current_commit, *, current_root=None):
    artifact_root, original_root, current_root = _root(root), _root(original_root), _root(current_root or _SOURCE_ROOT)
    _require(original_root != current_root and current_commit != ORIGINAL_COMMIT,
             "execution_transition_distinct_source_identity_required")
    original = _transaction_source(original_root, ORIGINAL_COMMIT)
    current = _transaction_source(current_root, current_commit)
    context = _ACTIVE_VERIFICATION.get()
    _allowed_delta(original, current)
    _semantic_unchanged(original_root, current_root)
    view = _legacy_view(state)
    desc = view.get("planning_runtime")
    _require(type(desc) is dict and view.get("runtime_identity") == codec.canonical_digest(desc),
             "execution_transition_original_descriptor_changed")
    prepared_ref = desc["prepared_ref"]
    raw = _path(artifact_root, prepared_ref).read_bytes()
    if context is None:
        result = _run_original(original_root, artifact_root, view)
    else:
        key = codec.canonical_digest({"artifact_root": str(artifact_root), "original_root": str(original_root),
            "original_commit": ORIGINAL_COMMIT, "descriptor": desc, "runtime_identity": view["runtime_identity"],
            "prepared_raw_digest": codec.raw_digest(raw), "original_sources": original})
        _require(context["key"] in (None, key), "execution_transition_nested_original_binding_changed")
        expected = {"frozen": codec.strict_json_loads(raw), "prepared_raw_digest": codec.raw_digest(raw),
                    "runtime_rules": deepcopy(desc["rules"]), "runtime_identity": view["runtime_identity"],
                    "frozen_sha256": desc["frozen_sha256"]}
        if context["key"] is None:
            context.update(key=key, request=(original_root, artifact_root, deepcopy(view)), expected=expected,
                           prepared=(_path(artifact_root, prepared_ref), raw))
        _require(_same(context["expected"], expected), "execution_transition_nested_native_witness_changed")
        result = expected
    # Subprocess JSON is an identity witness, not the materialization source:
    # sorted transport keys preserve canonical identity but change native
    # lossless-request bytes. Preserve every original insertion order instead.
    frozen = codec.strict_json_loads(raw)
    _require(_same(frozen, result["frozen"]), "execution_transition_verified_prepared_content_changed")
    _require(result["prepared_raw_digest"] == codec.raw_digest(raw)
             and _path(artifact_root, prepared_ref).read_bytes() == raw,
             "execution_transition_prepared_raw_changed")
    _require(codec.canonical_digest(frozen) == desc["frozen_sha256"] == result["frozen_sha256"]
             and _same(frozen["input_identity"], desc["input_identity"])
             and _same(result["runtime_rules"], desc["rules"])
             and result["runtime_identity"] == view["runtime_identity"],
             "execution_transition_original_native_identity_changed")
    _require(_transaction_source(original_root, ORIGINAL_COMMIT) == original
             and _transaction_source(current_root, current_commit) == current,
             "execution_transition_source_changed_during_validation")
    body = {"schema_version": SCHEMA, "original_source_root": str(original_root),
            "original_commit": ORIGINAL_COMMIT, "current_source_root": str(current_root),
            "current_commit": current_commit, "artifact_root": str(artifact_root),
            "original_run_schema": ORIGINAL_RUN_SCHEMA, "prepared_ref": prepared_ref,
            "prepared_raw_digest": codec.raw_digest(raw), "frozen_sha256": desc["frozen_sha256"],
            "original_runtime_identity": view["runtime_identity"], "original_runtime_rules": deepcopy(desc["rules"]),
            "original_tracked_sources": original, "current_tracked_sources": current}
    return body, frozen


def build_transition(root, state, original_root, current_commit):
    """Return a freshly verified explicit new identity; never modify state/files."""
    _require(state.get("schema_version") == ORIGINAL_RUN_SCHEMA
             and "b_route_execution_transition" not in state, "execution_transition_original_v1_state_required")
    body, _ = _collect(root, state, original_root, current_commit)
    return {**body, "transition_digest": codec.canonical_digest(body)}


def _validated(root, state):
    with _verification_transaction() as context:
        return _validate_frame(root, state, context)


def _validate_frame(root, state, context):
    _require(type(state) is dict and state.get("schema_version") == CURRENT_RUN_SCHEMA,
             "execution_transition_explicit_v2_state_required")
    value = state.get("b_route_execution_transition")
    selector = type(value) is dict and value.get("schema_version") == SELECTOR_EPOCH_SCHEMA
    epoch = type(value) is dict and value.get("schema_version") in {EPOCH_SCHEMA, EPOCH_V2_SCHEMA, MVG_EPOCH_SCHEMA, SELECTOR_EPOCH_SCHEMA}
    fields = _FIELDS | {"prior_transition", "previous_run", "historical_artifacts"} if epoch else _FIELDS
    if selector:
        fields |= {"selector_anchor_identity"}
    _require(type(value) is dict and set(value) == fields
             and value["schema_version"] in {SCHEMA, EPOCH_SCHEMA, EPOCH_V2_SCHEMA, MVG_EPOCH_SCHEMA, SELECTOR_EPOCH_SCHEMA}
             and value["original_commit"] == ORIGINAL_COMMIT and value["original_run_schema"] == ORIGINAL_RUN_SCHEMA,
             "execution_transition_closed_record_required")
    body = {key: item for key, item in value.items() if key != "transition_digest"}
    _require(value["transition_digest"] not in context["active"], "execution_epoch_parent_cycle")
    try:
        body_digest = codec.canonical_digest(body)
    except RecursionError as exc:
        raise TransitionError("execution_epoch_parent_cycle") from exc
    _require(value["transition_digest"] == body_digest, "execution_transition_digest_changed")
    artifact_root = _root(root)
    prepared_path = _path(artifact_root, value["prepared_ref"])
    try:
        state_digest = codec.canonical_digest(state)
    except (codec.CodecError, RecursionError) as exc:
        raise TransitionError("execution_epoch_frame_state_invalid") from exc
    frame_key = (str(artifact_root), state_digest, codec.raw_digest(prepared_path.read_bytes()))
    if frame_key in context["frames"]:
        cached = context["frames"][frame_key]
        _check_artifact_pins(cached["pins"])
        return value["transition_digest"], deepcopy(cached["frozen"])
    # Read validation names the actual committed epoch root, never the imported root.
    actual, frozen = _collect(root, state, value["original_source_root"], value["current_commit"],
                              current_root=value["current_source_root"])
    expected = {key: body[key] for key in _FIELDS if key != "transition_digest"}
    expected["schema_version"] = SCHEMA
    _require(_same(actual, expected), "execution_transition_frozen_binding_changed")
    if epoch:
        context["active"].add(value["transition_digest"])
        try:
            if selector:
                _validate_selector_epoch(root, state, value)
            elif value["schema_version"] == MVG_EPOCH_SCHEMA:
                _validate_mvg_epoch(root, state, value)
            else:
                _validate_epoch(root, state, value)
        finally:
            context["active"].remove(value["transition_digest"])
    else:
        _require(not state.get("b_route_execution_history"), "execution_transition_unbound_history")
    context["frames"][frame_key] = {"frozen": deepcopy(frozen), "pins": deepcopy(context["artifacts"])}
    return value["transition_digest"], frozen


def _previous_state(value):
    image = value["previous_run"]
    _require(type(image) is dict and set(image) == {"raw_digest", "bytes_base64"},
             "execution_epoch_previous_run_invalid")
    raw = base64.b64decode(image["bytes_base64"], validate=True)
    _require(codec.raw_digest(raw) == image["raw_digest"], "execution_epoch_previous_run_changed")
    return codec.strict_json_loads(raw)


def _closed_paid_prefix(state):
    ledger = state["capability_selection"]
    calls = ledger["calls"]
    count = 8 if state.get("b_route_execution_transition", {}).get("schema_version") in {EPOCH_SCHEMA, EPOCH_V2_SCHEMA} else 6
    _require(type(calls) is list and len(calls) == count and ledger["total_invocations"] == count
             and [row["number"] for row in calls] == list(range(1, count + 1))
             and len({row["reservation_id"] for row in calls}) == count
             and all(row["outcome"]["status"] == "completed" for row in calls[:5])
             and calls[5]["outcome"]["status"] == "failed"
             and all(row["outcome"]["status"] == "completed" for row in calls[6:]),
             "execution_epoch_unknown_duplicate_or_wrong_paid_prefix")
    elapsed = state.get("active_elapsed_seconds")
    _require(type(elapsed) in {int, float} and math.isfinite(elapsed) and elapsed >= 0,
             "execution_epoch_invalid_clock")
    return calls


def _artifact_manifest(root, state):
    root = _root(root)
    desc = state["planning_runtime"]
    run = root / "logs/ci" / ("capability-planning" if desc["planner"] == "capabilities" else "mvg-planning") / state["run_id"]
    references = {row["request_identity"]["execution_binding_path"]
                  for row in state["capability_selection"]["calls"] if row["outcome"]["status"] == "completed"}
    # Membership comes from the archived paid state, not a live glob: future
    # R8 admissions must not become retrospective R7 evidence.
    admissions = state["capability_selection"].get("current", {}).get("admissions", {})
    for admission in admissions.values():
        if admission.get("status") == "admitted":
            references.update(admission[key] for key in ("proof_path", "proposal_path", "execution_path") if key in admission)
    result = {(run / name).relative_to(root).as_posix(): codec.raw_digest(_path(run, name).read_bytes())
              for name in sorted(references)}
    context = _ACTIVE_VERIFICATION.get()
    if context is not None:
        for reference, digest in result.items():
            key = (str(root), reference)
            _require(key not in context["artifacts"] or context["artifacts"][key] == digest,
                     "execution_epoch_historical_artifact_changed")
            context["artifacts"][key] = digest
    return result


def _closed_mvg_paid_prefix(state):
    """Exact known terminal seven-completed MVG prefix, never the Cap gate."""
    desc = state.get("planning_runtime")
    _require(type(desc) is dict and desc.get("planner") == "mvg" and desc.get("profile") == "3b-mvg-v1"
             and state.get("run_id") == "m4" and type(state.get("mvg.run_invocation_limit")) is int
             and state["mvg.run_invocation_limit"] == 192,
             "execution_mvg_epoch_original_run_required")
    ledger = state.get("capability_selection")
    _require(type(ledger) is dict, "execution_mvg_epoch_paid_ledger_required")
    calls = ledger.get("calls")
    _require(type(calls) is list and len(calls) == 7 and type(ledger.get("total_invocations")) is int
             and ledger["total_invocations"] == 7
             and _same(ledger.get("lineage_invocations"), {"candidate-1": 5, "candidate-2": 2, "candidate-3": 0})
             and all(type(count) is int for count in ledger["lineage_invocations"].values())
             and all(type(row) is dict and type(row.get("request_identity")) is dict
                     and type(row.get("outcome")) is dict for row in calls),
             "execution_mvg_epoch_seven_paid_required")
    expected = (("candidate-1", "generate", 1, False), ("candidate-1", "generate", 2, True),
                ("candidate-1", "repair", 3, False), ("candidate-1", "repair", 4, True),
                ("candidate-1", "semantic", 5, False), ("candidate-2", "generate", 1, False),
                ("candidate-2", "generate", 2, True))
    for number, (row, (label, phase, attempt, synthesis)) in enumerate(zip(calls, expected), 1):
        request = row["request_identity"]
        _require(type(row.get("number")) is int and row["number"] == number
                 and row.get("reservation_id") == "m4:dispatch:" + str(number)
                 and row.get("candidate") == label and row.get("phase") == phase
                 and type(row.get("generation")) is int and row["generation"] == 1
                 and type(row.get("execution")) is int and row["execution"] == 1
                 and type(request.get("attempt")) is int and request["attempt"] == attempt
                 and request.get("synthesis") is synthesis and row["outcome"].get("status") == "completed",
                 "execution_mvg_epoch_unknown_duplicate_or_wrong_paid_prefix")
    current = ledger.get("current")
    _require(type(current) is dict and type(current.get("order_index")) is int and current["order_index"] == 0
             and type(current.get("execution")) is int and current["execution"] == 1
             and _same(current.get("selection_attempts"), []) and _same(ledger.get("selected"), [])
             and ledger.get("terminal") is True and state.get("selection_status") == "blocked",
             "execution_mvg_epoch_terminal_scope_required")
    admissions = current.get("admissions")
    _require(type(admissions) is dict and type(admissions.get("candidate-1")) is dict
             and type(admissions.get("candidate-2")) is dict
             and admissions["candidate-1"].get("status") == "admitted"
             and type(admissions["candidate-1"].get("total_invocations")) is int
             and admissions["candidate-1"]["total_invocations"] == 5
             and admissions["candidate-2"].get("status") == "blocked"
             and type(admissions["candidate-2"].get("total_invocations")) is int
             and admissions["candidate-2"]["total_invocations"] == 2,
             "execution_mvg_epoch_candidate_history_required")
    _require(not state.get("b_route_mvg_synthesis_recovery"), "execution_mvg_epoch_recovery_already_present")
    elapsed = state.get("active_elapsed_seconds")
    _require(type(elapsed) in {int, float} and math.isfinite(elapsed) and elapsed >= 0,
             "execution_mvg_epoch_invalid_clock")
    return calls


def _validate_mvg_epoch(root, state, value):
    previous = _previous_state(value)
    prior = value["prior_transition"]
    _require(type(prior) is dict and prior.get("schema_version") == SCHEMA
             and prior.get("current_commit") == MVG_PRIOR_COMMIT
             and _same(previous.get("b_route_execution_transition"), prior),
             "execution_mvg_epoch_prior_identity_changed")
    expected_history = {**previous.get("b_route_execution_history", {}), prior["transition_digest"]: prior}
    _require(value["transition_digest"] not in expected_history
             and _same(state.get("b_route_execution_history"), expected_history),
             "execution_mvg_epoch_history_changed")
    _require(prior["current_source_root"] != value["current_source_root"]
             and prior["current_commit"] != value["current_commit"], "execution_mvg_epoch_same_source")
    _validated(root, previous)
    calls = _closed_mvg_paid_prefix(previous)
    current = state.get("capability_selection")
    _require(type(current) is dict and type(current.get("calls")) is list
             and _same(current["calls"][:7], calls) and type(current.get("total_invocations")) is int
             and current["total_invocations"] == len(current["calls"]) and 7 <= current["total_invocations"] <= 192
             and all(type(row) is dict for row in current["calls"])
             and all(type(row.get("number")) is int for row in current["calls"])
             and _same([row.get("number") for row in current["calls"]], list(range(1, len(current["calls"]) + 1)))
             and [row.get("reservation_id") for row in current["calls"]]
                 == ["m4:dispatch:" + str(number) for number in range(1, len(current["calls"]) + 1)],
             "execution_mvg_epoch_paid_history_changed")
    labels = {"candidate-1", "candidate-2", "candidate-3"}
    costs = current.get("lineage_invocations")
    _require(type(costs) is dict and set(costs) == labels
             and all(type(costs[label]) is int and 0 <= costs[label] <= 64 and costs[label] == sum(row.get("candidate") == label
                     for row in current["calls"]) and costs[label] >= previous["capability_selection"]["lineage_invocations"][label]
                     for label in labels), "execution_mvg_epoch_refunded_lineage")
    for key in ("run_id", "input_stage", "runtime_identity", "planning_runtime", "analysis_identity_sha256",
                "mvg.run_invocation_limit", "mvg.run_invocation_limit_source", "b_route_campaign_funding",
                "checkpoint_strategy", "checkpoint_schema_version", "runner_configuration", "recovery",
                "b_route_output_schema_policy", "b_route_input_compact_policy", "b_route_review_recovery",
                "b_route_synthesis_recovery", "b_route_partial_generation_recovery", "b_route_input_path_recovery"):
        _require(_same(state.get(key), previous.get(key)), "execution_mvg_epoch_retained_identity_changed:" + key)
    elapsed = state.get("active_elapsed_seconds")
    _require(type(elapsed) in {int, float} and math.isfinite(elapsed)
             and elapsed >= previous["active_elapsed_seconds"], "execution_mvg_epoch_clock_reduced")
    _require(_same(value["historical_artifacts"], _artifact_manifest(root, previous)),
             "execution_mvg_epoch_historical_artifact_changed")


def build_mvg_synthesis_transition(root, state, original_root, current_commit, prior_source_root, prior_commit):
    """One explicit MVG epoch; original seven calls/source/proofs stay actual."""
    with _verification_transaction():
        prior = state.get("b_route_execution_transition")
        _require(type(prior) is dict and prior.get("schema_version") == SCHEMA
                 and prior_commit == prior.get("current_commit") == MVG_PRIOR_COMMIT
                 and _root(prior_source_root) == _root(prior["current_source_root"]),
                 "execution_mvg_epoch_prior_source_mismatch")
        _validated(root, state)
        _closed_mvg_paid_prefix(state)
        run_ref = "logs/ci/mvg-planning/m4/run.json"
        raw = _path(_root(root), run_ref).read_bytes()
        _require(_same(codec.strict_json_loads(raw), state), "execution_mvg_epoch_live_run_changed")
        body, _ = _collect(root, state, original_root, current_commit)
        body.update(schema_version=MVG_EPOCH_SCHEMA, prior_transition=deepcopy(prior),
                    previous_run={"raw_digest": codec.raw_digest(raw), "bytes_base64": base64.b64encode(raw).decode("ascii")},
                    historical_artifacts=_artifact_manifest(root, state))
        result = {**body, "transition_digest": codec.canonical_digest(body)}
        active = deepcopy(state)
        active["b_route_execution_transition"] = result
        active["b_route_execution_history"] = {**deepcopy(state.get("b_route_execution_history", {})),
            prior["transition_digest"]: deepcopy(prior)}
        _validated(root, active)
        return result


def _validate_epoch(root, state, value):
    previous = _previous_state(value)
    prior = value["prior_transition"]
    permitted = {SCHEMA} if value["schema_version"] == EPOCH_SCHEMA else {EPOCH_SCHEMA, EPOCH_V2_SCHEMA}
    _require(type(prior) is dict and prior.get("schema_version") in permitted
             and previous.get("b_route_execution_transition") == prior,
             "execution_epoch_prior_identity_changed")
    expected_history = {**previous.get("b_route_execution_history", {}), prior["transition_digest"]: prior}
    _require(value["transition_digest"] not in expected_history
             and state.get("b_route_execution_history") == expected_history,
             "execution_epoch_history_changed")
    _require(prior["current_source_root"] != value["current_source_root"]
             and prior["current_commit"] != value["current_commit"], "execution_epoch_same_source")
    _validated(root, previous)
    calls = _closed_paid_prefix(previous)
    current = state["capability_selection"]
    _require(current["calls"][:len(calls)] == calls and current["total_invocations"] >= len(calls)
             and current["lineage_invocations"].keys() == previous["capability_selection"]["lineage_invocations"].keys()
             and all(current["lineage_invocations"][key] >= count for key, count in
                     previous["capability_selection"]["lineage_invocations"].items()), "execution_epoch_paid_history_changed")
    for key in ("run_id", "runtime_identity", "planning_runtime", "mvg.run_invocation_limit", "b_route_campaign_funding",
                "b_route_review_recovery", "b_route_review_worker_attempt"):
        _require(state.get(key) == previous.get(key), "execution_epoch_retained_identity_changed:" + key)
    if value["schema_version"] == EPOCH_V2_SCHEMA:
        _require(state.get("b_route_synthesis_recovery") == previous.get("b_route_synthesis_recovery")
                 and state.get("b_route_output_schema_policy") == previous.get("b_route_output_schema_policy"),
                 "execution_epoch_prior_recovery_changed")
        for field in ("b_route_partial_generation_recovery", "b_route_input_path_recovery", "b_route_input_compact_policy"):
            if field in previous:
                _require(state.get(field) == previous[field], "execution_epoch_retained_identity_changed:" + field)
    elapsed = state.get("active_elapsed_seconds")
    _require(type(elapsed) in {int, float} and math.isfinite(elapsed)
             and elapsed >= previous["active_elapsed_seconds"], "execution_epoch_clock_reduced")
    _require(value["historical_artifacts"] == _artifact_manifest(root, previous),
             "execution_epoch_historical_artifact_changed")


def _closed_selector_paid_prefix(state):
    """Only the actual R19 twelve-completed, three-admitted preflight stop."""
    desc, ledger = state.get("planning_runtime"), state.get("capability_selection")
    _require(type(desc) is dict and desc.get("planner") == "mvg" and desc.get("profile") == "3b-mvg-v1"
             and state.get("run_id") == "m4" and type(state.get("mvg.run_invocation_limit")) is int
             and state["mvg.run_invocation_limit"] == 192 and type(ledger) is dict,
             "execution_selector_epoch_original_m4_required")
    calls = ledger.get("calls")
    _require(type(calls) is list and len(calls) == 12 and type(ledger.get("total_invocations")) is int
             and ledger["total_invocations"] == 12
             and _same(ledger.get("lineage_invocations"), {"candidate-1": 5, "candidate-2": 4, "candidate-3": 3}),
             "execution_selector_epoch_twelve_paid_required")
    expected = (("candidate-1", "generate", 1, False), ("candidate-1", "generate", 2, True),
                ("candidate-1", "repair", 3, False), ("candidate-1", "repair", 4, True),
                ("candidate-1", "semantic", 5, False), ("candidate-2", "generate", 1, False),
                ("candidate-2", "generate", 2, True), ("candidate-2", "generate", 3, True),
                ("candidate-2", "semantic", 4, False), ("candidate-3", "generate", 1, False),
                ("candidate-3", "generate", 2, True), ("candidate-3", "semantic", 3, False))
    for number, (row, (slot, phase, attempt, synthesis)) in enumerate(zip(calls, expected), 1):
        _require(type(row) is dict and type(row.get("request_identity")) is dict
                 and type(row.get("outcome")) is dict, "execution_selector_epoch_closed_paid_row_required")
        request = row["request_identity"]
        _require(type(row.get("number")) is int and row["number"] == number
                 and row.get("reservation_id") == "m4:dispatch:" + str(number)
                 and row.get("candidate") == slot and row.get("phase") == phase
                 and type(row.get("generation")) is int and row["generation"] == 1
                 and type(row.get("execution")) is int and row["execution"] == 1
                 and type(request.get("attempt")) is int and request["attempt"] == attempt
                 and request.get("synthesis") is synthesis and row["outcome"].get("status") == "completed",
                 "execution_selector_epoch_unknown_or_changed_paid_row")
    current = ledger.get("current")
    _require(type(current) is dict and type(current.get("order_index")) is int and current["order_index"] == 0
             and type(current.get("execution")) is int and current["execution"] == 1
             and current.get("stage") == "selection-preparing" and _same(current.get("selection_attempts"), [])
             and _same(ledger.get("selected"), []) and ledger.get("terminal") is True
             and state.get("selection_status") == "blocked"
             and _same(current.get("aliases"), {"A": "candidate-2", "B": "candidate-3", "C": "candidate-1"}),
             "execution_selector_epoch_original_preparation_stop_required")
    admissions = current.get("admissions")
    _require(type(admissions) is dict and set(admissions) == {"candidate-1", "candidate-2", "candidate-3"},
             "execution_selector_epoch_all_admissions_required")
    for slot, count in (("candidate-1", 5), ("candidate-2", 4), ("candidate-3", 3)):
        admission = admissions[slot]
        _require(type(admission) is dict and admission.get("status") == "admitted"
                 and type(admission.get("total_invocations")) is int and admission["total_invocations"] == count
                 and admission.get("retryable") is False and admission.get("append_terminal") is False,
                 "execution_selector_epoch_admission_changed")
    elapsed = state.get("active_elapsed_seconds")
    _require(type(elapsed) in {int, float} and math.isfinite(elapsed) and elapsed >= 0,
             "execution_selector_epoch_invalid_clock")
    _require(bool(state.get("b_route_mvg_synthesis_recovery")) and not state.get("b_route_selector_recovery"),
             "execution_selector_epoch_original_m1_reference_required")
    return calls


def _validate_selector_epoch(root, state, value):
    """Original admission qualification is a genuine sealed owner fact, not replayed here."""
    import _b_route_selector_recovery as recovery
    previous = _previous_state(value)
    prior = value["prior_transition"]
    _require(type(prior) is dict and prior.get("schema_version") == MVG_EPOCH_SCHEMA
             and prior.get("current_commit") == SELECTOR_PRIOR_COMMIT
             and _same(previous.get("b_route_execution_transition"), prior),
             "execution_selector_epoch_prior_source_changed")
    capture = recovery.capture_retained_selector(root)
    original = recovery.verify_retained_selector_capture(root, capture, current_state=state)
    _require(_same(original, previous) and _same(capture["anchor_identity"], value["selector_anchor_identity"]),
             "execution_selector_epoch_actual_anchor_changed")
    _validated(root, previous)
    calls = _closed_selector_paid_prefix(previous)
    history = {**previous.get("b_route_execution_history", {}), prior["transition_digest"]: prior}
    _require(value["transition_digest"] not in history and _same(state.get("b_route_execution_history"), history)
             and prior["current_commit"] != value["current_commit"]
             and prior["current_source_root"] != value["current_source_root"],
             "execution_selector_epoch_history_changed")
    ledger = state.get("capability_selection")
    current_calls = ledger.get("calls") if type(ledger) is dict else None
    _require(type(current_calls) is list and 12 <= len(current_calls) <= 13
             and _same(current_calls[:12], calls) and type(ledger.get("total_invocations")) is int
             and ledger["total_invocations"] == len(current_calls)
             and _same(ledger.get("lineage_invocations"), previous["capability_selection"]["lineage_invocations"]),
             "execution_selector_epoch_paid_prefix_changed")
    if len(current_calls) == 13:
        row = current_calls[12]
        _require(type(row) is dict and type(row.get("number")) is int and row["number"] == 13
                 and row.get("reservation_id") == "m4:dispatch:13" and row.get("phase") == "selection"
                 and row.get("candidate") is None and type(row.get("generation")) is int and row["generation"] == 1
                 and type(row.get("execution")) is int and row["execution"] == 1
                 and type(row.get("request_identity")) is dict
                 and type(row["request_identity"].get("attempt")) is int and row["request_identity"]["attempt"] == 1
                 and row["request_identity"].get("selector_transport_policy") == "newrouge.b-route-compact-literal.v3",
                 "execution_selector_epoch_only_one_selector_reservation")
    for key in ("run_id", "input_stage", "runtime_identity", "planning_runtime", "analysis_identity_sha256",
                "mvg.run_invocation_limit", "mvg.run_invocation_limit_source", "b_route_campaign_funding",
                "checkpoint_strategy", "checkpoint_schema_version", "runner_configuration", "recovery",
                "b_route_output_schema_policy", "b_route_input_compact_policy", "b_route_mvg_synthesis_recovery"):
        _require(_same(state.get(key), previous.get(key)), "execution_selector_epoch_retained_identity_changed:" + key)
    elapsed = state.get("active_elapsed_seconds")
    _require(type(elapsed) in {int, float} and math.isfinite(elapsed)
             and elapsed >= previous["active_elapsed_seconds"], "execution_selector_epoch_clock_reduced")
    _require(_same(value["historical_artifacts"], _artifact_manifest(root, previous)),
             "execution_selector_epoch_historical_artifact_changed")


def build_mvg_selector_transition(root, state, original_root, current_commit, prior_source_root, prior_commit, *, retained_capture):
    """Construct source identity only; the recovery owner publishes its separate mandatory reference."""
    import _b_route_selector_recovery as recovery
    with _verification_transaction():
        prior = state.get("b_route_execution_transition")
        _require(type(prior) is dict and prior.get("schema_version") == MVG_EPOCH_SCHEMA
                 and prior_commit == prior.get("current_commit") == SELECTOR_PRIOR_COMMIT
                 and _root(prior_source_root) == _root(prior["current_source_root"]),
                 "execution_selector_epoch_prior_source_mismatch")
        original = recovery.verify_retained_selector_capture(root, retained_capture, current_state=state)
        _require(_same(original, state), "execution_selector_epoch_original_anchor_required")
        _validated(root, state)
        _closed_selector_paid_prefix(state)
        raw = _path(_root(root), "logs/ci/mvg-planning/m4/run.json").read_bytes()
        _require(_same(codec.strict_json_loads(raw), state), "execution_selector_epoch_live_run_changed")
        body, _ = _collect(root, state, original_root, current_commit)
        body.update(schema_version=SELECTOR_EPOCH_SCHEMA, prior_transition=deepcopy(prior),
                    previous_run={"raw_digest": codec.raw_digest(raw), "bytes_base64": base64.b64encode(raw).decode("ascii")},
                    historical_artifacts=_artifact_manifest(root, state),
                    selector_anchor_identity=deepcopy(retained_capture["anchor_identity"]))
        result = {**body, "transition_digest": codec.canonical_digest(body)}
        recovery.verify_retained_selector_capture(root, retained_capture, current_state=state)
        # No active temporary state: its mandatory recovery record/ref is not
        # published yet. Returning this envelope never authorizes dispatch.
        return result


def build_successor_transition(root, state, original_root, current_commit, prior_source_root, prior_commit):
    """Build one explicit successor, retaining original six/eight-call proof."""
    with _verification_transaction():
        return _build_successor(root, state, original_root, current_commit, prior_source_root, prior_commit)


def _build_successor(root, state, original_root, current_commit, prior_source_root, prior_commit):
    prior = state.get("b_route_execution_transition")
    _require(type(prior) is dict and prior.get("schema_version") in {SCHEMA, EPOCH_SCHEMA, EPOCH_V2_SCHEMA}
             and _root(prior_source_root) == _root(prior["current_source_root"])
             and prior_commit == prior["current_commit"], "execution_epoch_prior_source_mismatch")
    _validated(root, state)
    _closed_paid_prefix(state)
    desc = state["planning_runtime"]
    run_ref = "logs/ci/" + ("capability-planning" if desc["planner"] == "capabilities" else "mvg-planning") + "/" + state["run_id"] + "/run.json"
    raw = _path(_root(root), run_ref).read_bytes()
    _require(_same(codec.strict_json_loads(raw), state), "execution_epoch_live_run_changed")
    body, _ = _collect(root, state, original_root, current_commit)
    schema = EPOCH_SCHEMA if prior["schema_version"] == SCHEMA else EPOCH_V2_SCHEMA
    body.update(schema_version=schema, prior_transition=deepcopy(prior),
                previous_run={"raw_digest": codec.raw_digest(raw), "bytes_base64": base64.b64encode(raw).decode("ascii")},
                historical_artifacts=_artifact_manifest(root, state))
    result = {**body, "transition_digest": codec.canonical_digest(body)}
    active = deepcopy(state)
    active["b_route_execution_transition"] = result
    active["b_route_execution_history"] = {**deepcopy(state.get("b_route_execution_history", {})), prior["transition_digest"]: deepcopy(prior)}
    _validated(root, active)
    return result


def historical_state(root, state, digest):
    """Resolve the actual archived state of any explicitly retained ancestor."""
    _validated(root, state)
    current = state
    seen = set()
    while True:
        value = current["b_route_execution_transition"]
        _require(value["transition_digest"] not in seen, "execution_epoch_parent_cycle")
        seen.add(value["transition_digest"])
        if digest == value["transition_digest"]:
            return current
        _require(value["schema_version"] in {EPOCH_SCHEMA, EPOCH_V2_SCHEMA, MVG_EPOCH_SCHEMA, SELECTOR_EPOCH_SCHEMA},
                 "execution_epoch_unbound_source")
        current = _previous_state(value)


def source_state_for_materials(root, state, materials, binding):
    """Historical proof may use only an exactly pinned completed paid binding."""
    value = state.get("b_route_execution_transition")
    digest = materials.get("execution_source_transition")
    if not value or digest is None or digest == value["transition_digest"]:
        return state  # Existing recovery owns the strictly pinned R5 exception.
    previous = historical_state(root, state, digest)
    planner = previous["planning_runtime"]["planner"]
    _require(planner in {"capabilities", "mvg"}, "execution_epoch_historical_planner_changed")
    run = _root(root) / "logs/ci" / ("capability-planning" if planner == "capabilities" else "mvg-planning") / previous["run_id"]
    output_value = binding.get("output_path")
    _require(type(output_value) is str and bool(output_value), "execution_epoch_invalid_output_path")
    output = Path(output_value)
    _require(output.is_absolute() and ".." not in output.parts and output.is_relative_to(run),
             "execution_epoch_invalid_output_path")
    matches = [row for row in previous["capability_selection"]["calls"]
               if row.get("outcome", {}).get("status") == "completed"
               and run / row["request_identity"]["output_path"] == output]
    _require(len(matches) == 1, "execution_epoch_historical_binding_not_paid")
    path = _path(run, matches[0]["request_identity"]["execution_binding_path"])
    _require(_same(codec.strict_json_loads(path.read_bytes()), binding), "execution_epoch_historical_binding_changed")
    return previous


def source_state_for_proof(root, state, proof):
    """Use the stored admission's actual source; never re-sign it as R8."""
    envelope = proof.get("execution_source_transition")
    value = state.get("b_route_execution_transition")
    if not value or envelope == value:
        return state
    _require(type(envelope) is dict, "execution_epoch_proof_source_missing")
    previous = historical_state(root, state, envelope.get("transition_digest"))
    _require(envelope == previous["b_route_execution_transition"], "execution_epoch_proof_source_changed")
    artifacts = value["historical_artifacts"]
    matches = [reference for reference in artifacts if reference.endswith("/admission-review.json")
               and _same(codec.strict_json_loads(_path(_root(root), reference).read_bytes()), proof)]
    _require(len(matches) == 1, "execution_epoch_unpinned_historical_proof")
    return previous


def validate_transition(root, state):
    """Recheck both committed source trees and the real original verifier now."""
    return _validated(root, state)[0]


def load_prepared(root, state):
    """Return only the original revalidated frozen object, without stale caching."""
    return _validated(root, state)[1]


def verify_historical_generation(root, original_state, bindings, proposal, original_root):
    """Replay old generation proof under unchanged r5 native rules, not new rules."""
    artifact_root, original_root = _root(root), _root(original_root)
    original = _source_manifest(original_root, ORIGINAL_COMMIT)
    _require(original_state.get("schema_version") == ORIGINAL_RUN_SCHEMA
             and "b_route_execution_transition" not in original_state,
             "execution_transition_original_v1_generation_state_required")
    _require(type(bindings) is list and bool(bindings) and type(proposal) is dict,
             "execution_transition_original_generation_evidence_required")
    desc = original_state["planning_runtime"]
    raw = _path(artifact_root, desc["prepared_ref"]).read_bytes()
    result = _run_original(original_root, artifact_root, deepcopy(original_state), bindings=bindings, proposal=proposal)
    _require(result["prepared_raw_digest"] == codec.raw_digest(raw)
             and _path(artifact_root, desc["prepared_ref"]).read_bytes() == raw
             and _source_manifest(original_root, ORIGINAL_COMMIT) == original,
             "execution_transition_original_generation_inputs_changed")
    report = result["historical_generation"]
    _require(report == {"generation_count": len(bindings), "proposal_sha256": codec.canonical_digest(proposal),
                        "frozen_sha256": desc["frozen_sha256"], "bindings_sha256": codec.canonical_digest(bindings)},
             "execution_transition_historical_generation_result_changed")
    return report
