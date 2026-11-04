"""Task-free 3A source accounting. Writes only exclusive attempt-local logs.

Proposal records are temporary handoff data, never adopted planning identities.
No model, Task closure, apply, publication, or recovery is performed here.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import _b_route_codec as codec
import _b_route_inventory as inventory
import build_source_ledger as native
import project_semantics_from_sources as projection
from validate_semantic_conservation import projection_checks
from _capability_input_integrity import measure_request
from _mvg_evidence_transport import (TRANSPORT_SCHEMA, audit_prompt, audit_schema,
                                     plan_errors, plan_transport)

PREPARED = "newrouge.b-route-sources-prepared.v1"
CANDIDATE = "newrouge.b-route-sources-candidate.v1"
DECLARATION = "newrouge.b-route-sources-declaration.v1"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
PROPOSAL = re.compile(r"proposal:[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def fail(code, entity, expected, actual):
    raise codec.CodecError(codec.Diagnostic(code, codec.Stage.CONTENT, entity, expected, actual))


def require(condition, entity, expected, actual=None):
    if not condition:
        fail(codec.ReasonCode.SEMANTIC_ERROR, entity, expected, actual)


def text_view(raw):
    # Match Path.read_text universal-newline semantics; raw identity stays separate.
    return io.StringIO(raw.decode("utf-8"), newline=None).read()


def checked_path(root, value, *, logs=True):
    inventory.canonical_path(value, allow_logs=logs)
    target = inventory.safe_input(root, value, allow_logs=logs)
    current = root
    for part in value.split("/"):
        if current.is_dir() and (current / part).exists():
            require(part in {p.name for p in current.iterdir()}, value,
                    "exact on-disk spelling; no short-path alias")
        current /= part
    return target


class Observations:
    def __init__(self, root):
        self.root, self.files, self.globs = root, {}, {}

    def read(self, value, *, optional=False):
        path = checked_path(self.root, value)
        if not path.exists():
            if value in self.files and self.files[value] is not None:
                fail(codec.ReasonCode.FILE_CHANGED, value, "original existing file", "missing")
            self.files[value] = None
        if optional and not path.exists():
            raw = None
        else:
            raw = codec.read_reference_bytes(self.root, value)
        if value in self.files and self.files[value] != raw:
            fail(codec.ReasonCode.FILE_CHANGED, value, "unchanged observed bytes", "changed")
        self.files[value] = raw
        return raw

    def json(self, value):
        return self._decode_json(value, self.read(value))

    def _decode_json(self, value, raw):
        try:
            return codec.strict_json_loads(raw)
        except codec.CodecError as error:
            raise codec.CodecError(replace(error.diagnostic, entity_id=value)) from error

    def reader(self, path):
        value = path.relative_to(self.root).as_posix()
        raw = self.read(value)
        if path.suffix.lower() == ".json":
            self._decode_json(value, raw)
        return text_view(raw)

    def members(self, patterns):
        for pattern in patterns:
            inventory.safe_source_pattern(self.root, pattern)
        files, missing = native.resolve_sources(self.root, patterns, True)
        members = [p.relative_to(self.root).as_posix() for p in files]
        for value in members:
            checked_path(self.root, value, logs=False)
        return {"members": members, "missing": missing}

    def watch(self, patterns):
        key = tuple(patterns)
        value = self.members(patterns)
        if key in self.globs:
            require(self.globs[key] == value, "source-members", self.globs[key], value)
        self.globs[key] = value
        return value

    def verify(self):
        for value, original in list(self.files.items()):
            actual = self.read(value, optional=original is None)
            if actual != original:
                fail(codec.ReasonCode.FILE_CHANGED, value, "original bytes/existence", "changed")
        for patterns, expected in self.globs.items():
            actual = self.members(patterns)
            if actual != expected:
                fail(codec.ReasonCode.INPUT_STALE, "source-members", expected, actual)


def write(path, value):
    for ancestor in reversed((path.parent, *path.parent.parents)):
        inventory.no_reparse(ancestor)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8"))


def string_list(value, entity):
    require(isinstance(value, list) and all(type(x) is str and x.strip() and x == x.strip() for x in value)
            and len(value) == len(set(value)), entity, "unique nonempty string list", value)
    return value


def evidence(obs, row):
    require(isinstance(row, dict), "evidence", "byte locator object", row)
    path = row.get("path")
    require(type(path) is str, "evidence.path", "repository path", path)
    raw = obs.read(path)
    start, end = row.get("byte_start"), row.get("byte_end")
    require(row.get("raw_digest") == codec.raw_digest(raw) and type(start) is int
            and type(end) is int and 0 <= start < end <= len(raw), path,
            "matching raw_digest and nonempty byte range", row)
    return row


def effective(obs, args):
    source_set = obs.json(args.source_set)
    require(isinstance(source_set, dict), args.source_set, "source-set object")
    additions, retirements = [], []
    declaration = {"schema_version": DECLARATION, "additions": [], "retirements": []}
    if args.declaration:
        declaration = obs.json(args.declaration)
        require(isinstance(declaration, dict) and declaration.get("schema_version") == DECLARATION
                and set(declaration) == {"schema_version", "additions", "retirements"},
                args.declaration, DECLARATION)
        additions = string_list(declaration["additions"], "additions")
        require(isinstance(declaration["retirements"], list), "retirements", "list")
        for row in declaration["retirements"]:
            require(isinstance(row, dict) and set(row) == {"path", "reason", "evidence"}
                    and type(row.get("reason")) is str and row["reason"].strip(),
                    "retirement", "path, reason and evidence", row)
            inventory.canonical_path(row["path"], pattern=True)
            evidence(obs, row["evidence"])
            retirements.append(row["path"])
        require(len(retirements) == len(set(retirements)), "retirements", "unique paths")
    for pattern in source_set.get("active_patterns", []) + additions:
        inventory.safe_source_pattern(obs.root, pattern)
    for pattern in additions:
        require(not any(native._source_pattern_matches(pattern, row["path"])
                        or pattern == row["path"] for row in source_set.get("retirements", [])),
                pattern, "no resurrection of historical retirements")
    namespace = argparse.Namespace(source_set=args.source_set, mode="add", source_glob=additions,
                                  retire_source=retirements, adopt_baseline=False)
    patterns, _ = native.collect_patterns(obs.root, namespace,
                                         json_reader=lambda p: obs.json(p.relative_to(obs.root).as_posix()))
    all_retired = {row["path"] for row in source_set.get("retirements", [])} | set(retirements)
    addition_members = obs.watch(additions)["members"] if additions else []
    require(not any(native._source_pattern_matches(path, retired) for path in addition_members for retired in all_retired),
            "additions", "no addition/retirement conflict or retired glob resurrection")
    # Watch both original and effective glob membership, including removed sources.
    obs.watch(source_set.get("active_patterns", []))
    obs.watch(patterns)
    for path in source_set.get("active_sources", []):
        obs.read(path, optional=True)
    for row in source_set.get("retirements", []) + declaration["retirements"]:
        if not any(c in row["path"] for c in "*?["):
            obs.read(row["path"], optional=True)
    return source_set, declaration, patterns, all_retired


def probe_for(args):
    def probe(prompt, schema):
        return measure_request(json.dumps({"prompt": prompt, "schema": schema}, ensure_ascii=False),
                               max_bytes=args.transport_max_bytes,
                               max_input_tokens=args.transport_max_input_tokens)
    return probe


def transport_context(obs, manifest):
    return {"chapter5": {}, "evidence": [
        {"path": row["path"], "sha256": row["sha256"],
         "text": obs.read(row["path"]).decode("utf-8")}
        for row in manifest["sources"]]}


def archive_observations(obs, output):
    rows = []
    for ordinal, (path, raw) in enumerate(obs.files.items(), 1):
        row = {"path": path, "raw_digest": codec.raw_digest(raw) if raw is not None else None,
               "archive": None, "byte_count": len(raw) if raw is not None else None}
        if raw is not None:
            row["archive"] = f"raw/{ordinal:06d}.bin"
            target = output / row["archive"]
            for ancestor in reversed((target.parent, *target.parent.parents)):
                inventory.no_reparse(ancestor)
            target.parent.mkdir(exist_ok=True)
            with target.open("xb") as stream:
                stream.write(raw)
        rows.append(row)
    return rows


def load_prepared(obs, value, *, current_sources=True):
    path = checked_path(obs.root, value)
    require(path.name == "prepared.json", value, "prepared.json reference")
    prefix = path.parent.relative_to(obs.root).as_posix()
    require(prefix.startswith("logs/ci/") and "/b-route-sources/" in prefix, value,
            "3A attempt-local prepared reference")
    prepared = obs.json(value)
    require(prepared.get("schema_version") == PREPARED, value, PREPARED)
    event = obs.json(prefix + "/event.json")
    require(event.get("termination_reason") == "prepared" and event.get("stage") == "prepare",
            prefix, "successful prepare event")
    require(event.get("exit_code") == 0 and event.get("event_key") ==
            [prepared.get("run_id"), prepared.get("scope_id"), "prepare", prepared.get("attempt_id")],
            prefix, "matching successful preparation event identity")
    expected_paths = set(event.get("artifacts", {})) | {"event.json"}
    actual_paths = {p.relative_to(path.parent).as_posix() for p in path.parent.rglob("*") if p.is_file()}
    require(expected_paths == actual_paths, prefix, sorted(expected_paths), sorted(actual_paths))
    for relative, digest in event["artifacts"].items():
        raw = obs.read(prefix + "/" + relative)
        require(codec.raw_digest(raw) == digest, relative, digest, codec.raw_digest(raw))
    for row in prepared["observations"]:
        archived = obs.read(prefix + "/" + row["archive"]) if row["archive"] else None
        require((codec.raw_digest(archived) if archived is not None else None) == row["raw_digest"],
                row["path"], "original archived raw identity")
        if not current_sources:
            continue
        raw = obs.read(row["path"], optional=row["raw_digest"] is None)
        actual = codec.raw_digest(raw) if raw is not None else None
        if actual != row["raw_digest"]:
            ledger = obs.json(prefix + "/source-blocks.json")
            fail(codec.ReasonCode.INPUT_STALE, row["path"], row["raw_digest"],
                 {"raw_digest": actual, "affected_block_ids": [b["block_id"] for b in ledger["blocks"]
                                                              if b["source_path"] == row["path"]]})
        if raw is not None:
            archived = obs.read(prefix + "/" + row["archive"])
            require(archived == raw and len(raw) == row["byte_count"], row["path"], "exact original bytes")
    for watch in prepared["glob_observations"] if current_sources else []:
        actual = obs.watch(watch["patterns"])
        require(actual == watch["result"], "source-members", watch["result"], actual)
    return prepared, prefix


def prepare(obs, args, output, result):
    source_set, declaration, patterns, retired = effective(obs, args)
    previous_ledger, prior_sources = None, list(source_set.get("active_sources", []))
    if args.previous:
        previous, prefix = load_prepared(obs, args.previous, current_sources=False)
        old_retirements = previous["source_registration"].get("retirements", [])
        require(all(row in source_set.get("retirements", []) for row in old_retirements),
                args.source_set, "retain prior registered retirement history")
        previous_ledger = obs.json(prefix + "/source-blocks.json")
        prior_sources += [x["path"] for x in obs.json(prefix + "/source-manifest.json")["sources"]]
    manifest, ledger = native.build_ledger(obs.root, patterns, "add", True, previous_ledger,
                                          retired, text_reader=obs.reader, previous_sources=prior_sources)
    write(output / "source-manifest.json", manifest)
    write(output / "source-blocks.json", ledger)
    index, candidate = projection.prepare(ledger, args.max_blocks, output / "batches", args.max_chars)
    candidate["schema_version"] = CANDIDATE
    candidate["capabilities"] = []
    candidate["file_results"] = [{"path": row["path"], "raw_digest": codec.raw_digest(obs.read(row["path"])),
                                  "disposition": "unresolved", "reason": "", "evidence": None}
                                 for row in manifest["sources"] if row["block_count"] == 0]
    candidate["instructions"] = {
        "scope": "Explicit semantic proposals only; no independent audit or adoption authority.",
        "atoms": "Provide proposal_id (proposal: namespace), kind, statement, source_block_ids, acceptance_intent, prior_requirement_ids and non_task_sinks (sink ID strings).",
        "dispositions": "Every non-atom disposition needs reason and source_block_ids; unresolved remains blocking.",
        "completion": "Set batch output_accounted_count after reviewing every block. Counts alone prove no semantics.",
    }
    for row in candidate["block_results"]:
        row.update(disposition="unresolved", reason="", source_block_ids=[row["block_id"]])
    write(output / "batch-index.json", index)
    context = transport_context(obs, manifest)
    plan = plan_transport(context, phase="inspect", probe=probe_for(args), schema_version=TRANSPORT_SCHEMA)
    write(output / "transport.json", plan)
    observations = archive_observations(obs, output)
    prepared = {"schema_version": PREPARED, "run_id": args.run_id, "scope_id": args.scope_id,
                "attempt_id": args.attempt_id, "source_set": args.source_set, "declaration": args.declaration,
                "effective_patterns": patterns, "retired_sources": sorted(retired),
                "source_revision": manifest["source_revision"], "source_manifest_sha256": manifest["manifest_sha256"],
                "source_registration": source_set, "declaration_content": declaration,
                "previous_ledger": previous_ledger, "prior_sources": prior_sources,
                "observations": observations,
                "glob_observations": [{"patterns": list(p), "result": r} for p, r in obs.globs.items()],
                "limits": {k: getattr(args, k) for k in ("max_blocks", "max_chars", "transport_max_bytes", "transport_max_input_tokens")}}
    write(output / "prepared.json", prepared)
    candidate["prepared_ref"] = {"path": (output / "prepared.json").relative_to(obs.root).as_posix(),
                                  "raw_digest": codec.raw_digest((output / "prepared.json").read_bytes())}
    write(output / "candidate.json", candidate)
    result.update(prepared_ref=candidate["prepared_ref"], source_count=len(manifest["sources"]),
                  source_block_count=len(ledger["blocks"]), unresolved=[r["block_id"] for r in ledger["blocks"]],
                  termination_reason="prepared", reuse_reason="previous_ledger_identity" if args.previous else "not_requested")
    return 0


def accountable_candidate(candidate, ledger, unresolved):
    require(candidate.get("schema_version") == CANDIDATE and candidate.get("capabilities") == [],
            "candidate", "3A candidate without Capability definitions")
    native_candidate = deepcopy(candidate)
    proposals = {}
    blocks = {b["block_id"]: b for b in ledger["blocks"]}
    summaries = candidate.get("batch_summaries", [])
    require(len(summaries) == len({x.get("batch_id") for x in summaries}), "batch_summaries", "no duplicate summaries")
    for row in native_candidate.get("block_results", []):
        block_id = row.get("block_id")
        require(block_id in blocks, str(block_id), "known source block")
        if row.get("disposition") == "unresolved" or row.get("delivery_potential") is None:
            unresolved.append({"entity_id": block_id, "reason": "unresolved source disposition"})
            row["delivery_potential"] = True
            row["disposition"] = "unresolved"
        if not row.get("atoms"):
            require(row.get("disposition") != "atomized", block_id, "atomized blocks require explicit proposals")
            refs = string_list(row.get("source_block_ids"), block_id)
            require(block_id in refs and set(refs) <= set(blocks), block_id, "source-backed disposition")
            if not (type(row.get("reason")) is str and row["reason"].strip()):
                unresolved.append({"entity_id": block_id, "reason": "missing disposition rationale"})
            row["decision"] = {"reason": row.get("reason"), "source_block_ids": refs}
        for atom in row.get("atoms", []):
            proposal_id = atom.get("proposal_id")
            require(type(proposal_id) is str and PROPOSAL.fullmatch(proposal_id), block_id,
                    "proposal: namespace; no formal allocation", proposal_id)
            require("requirement_id" not in atom and not atom.get("capability_ids"), proposal_id,
                    "no formal planning identity")
            refs = string_list(atom.get("source_block_ids"), proposal_id)
            require(block_id in refs and set(refs) <= set(blocks), proposal_id, "complete known references including primary block")
            prior = string_list(atom.get("prior_requirement_ids"), proposal_id + ".prior_requirement_ids")
            require(not any(PROPOSAL.fullmatch(x) for x in prior), proposal_id, "old formal identity backlinks only")
            sinks = string_list(atom.get("non_task_sinks"), proposal_id + ".non_task_sinks")
            intent = atom.get("acceptance_intent")
            if type(intent) is not str or not intent.strip():
                unresolved.append({"entity_id": proposal_id, "reason": "missing explicit acceptance intent"})
            body = {"proposal_id": proposal_id, "kind": projection.normalize_kind(atom.get("kind")),
                    "statement": atom.get("statement"), "source_block_ids": refs,
                    "acceptance_intent": intent, "prior_requirement_ids": prior, "non_task_sinks": sinks}
            require(proposal_id not in proposals or proposals[proposal_id] == body, proposal_id,
                    "identical proposal body for shared references")
            proposals[proposal_id] = body
            atom["requirement_id"] = proposal_id
            # Native sink types belong to later Task closure. Keep explicit sink
            # IDs in the B proposal without inventing a classification here.
            atom["non_task_sinks"] = []
            if atom.get("status") == "unresolved" or atom.get("disposition") == "unresolved":
                unresolved.append({"entity_id": proposal_id, "reason": "unresolved proposal"})
    return native_candidate, list(proposals.values())


def account(obs, args, output, result):
    prepared, prefix = load_prepared(obs, args.prepared)
    require(prepared["scope_id"] == args.scope_id, args.prepared, "matching scope_id")
    candidate = obs.json(args.candidate)
    write(output / "candidate.snapshot.json", candidate)
    require(candidate.get("prepared_ref") == {"path": args.prepared, "raw_digest": codec.raw_digest(obs.read(args.prepared))},
            args.candidate, "exact prepared reference and raw identity")
    ledger, manifest = obs.json(prefix + "/source-blocks.json"), obs.json(prefix + "/source-manifest.json")
    # Reparse authoritative bytes through the original owner to verify full block bodies and order.
    fresh_manifest, fresh = native.build_ledger(obs.root, prepared["effective_patterns"], "add", True,
                                               prepared["previous_ledger"], set(prepared["retired_sources"]),
                                               text_reader=obs.reader, previous_sources=prepared["prior_sources"])
    for key in ("blocks", "delta", "parser_inventory", "source_revision", "source_manifest_sha256"):
        require(fresh[key] == ledger[key], "ledger." + key, "original native parse and order")
    require(fresh_manifest["sources"] == manifest["sources"], "source-manifest", "current full native source identity")
    index = obs.json(prefix + "/batch-index.json")
    rebuilt_index, batches = projection.build_batches(ledger, prepared["limits"]["max_blocks"], prepared["limits"]["max_chars"])
    require({k: v for k, v in index.items() if k != "generated_at_utc"} ==
            {k: v for k, v in rebuilt_index.items() if k != "generated_at_utc"}, "batch-index", "complete ordered native index")
    for batch in batches:
        require(obs.json(prefix + "/batches/" + batch["batch_id"].lower() + ".json") == batch,
                batch["batch_id"], "complete original batch objects and context")
    context = transport_context(obs, manifest)
    plan = obs.json(prefix + "/transport.json")
    errors = plan_errors(context, plan)
    require(not errors, "transport", "lossless complete original characters", errors)
    limits = argparse.Namespace(**prepared["limits"])
    probe = probe_for(limits)
    probe(audit_prompt(plan, []), audit_schema(plan, []))
    for batch in plan["batches"]:
        require(probe(audit_prompt(plan, batch["parts"]), audit_schema(plan, batch["parts"])) == batch["input_report"],
                "transport.request", "same complete measured request")
    unresolved = []
    native_candidate, proposals = accountable_candidate(candidate, ledger, unresolved)
    empty = {r["path"] for r in manifest["sources"] if r["block_count"] == 0}
    seen = set()
    for row in candidate.get("file_results", []):
        path = row.get("path")
        require(path in empty and path not in seen, str(path), "exactly one empty-file disposition")
        seen.add(path)
        require(row.get("raw_digest") == codec.raw_digest(obs.read(path)), path, "original file raw identity")
        if row.get("disposition") not in {"context", "rationale", "deferred", "out_of_scope", "adr_owned"} or not str(row.get("reason") or "").strip():
            unresolved.append({"entity_id": path, "reason": "empty/unparsed file requires explicit disposition"})
        else:
            evidence(obs, row.get("evidence"))
    for path in sorted(empty - seen):
        unresolved.append({"entity_id": path, "reason": "missing file disposition"})
    write(output / "requirement-proposals.json", {"source_revision": ledger["source_revision"], "proposals": proposals})
    semantics, _, edges = projection.compile_projection(ledger, index, native_candidate)
    checks = projection_checks(obs.root, ledger, semantics,
                               hash_reader=lambda p: native.sha256_text(obs.reader(p)))
    for key, value in checks.items():
        if isinstance(value, list) and value:
            unresolved.append({"entity_id": key, "reason": value})
    write(output / "source-accounting.json", {"source_accounting": semantics["source_accounting"],
                                             "file_accounting": candidate.get("file_results", []),
                                             "projection_checks": checks, "edges": edges})
    result.update(source_count=len(manifest["sources"]), source_block_count=len(ledger["blocks"]),
                  proposal_count=len(proposals), unresolved=unresolved, accounting_complete=not unresolved,
                  termination_reason="accounted" if not unresolved else "unresolved")
    return 0 if not unresolved else 1


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def register_arguments(parser):
    parser.add_argument("--stage", choices=("prepare", "account"), required=True)
    for option in ("root", "run-id", "scope-id", "attempt-id"):
        parser.add_argument("--" + option, required=True)
    for option in ("source-set", "declaration", "previous", "prepared", "candidate"):
        parser.add_argument("--" + option)
    parser.add_argument("--max-blocks", type=int, default=24)
    parser.add_argument("--max-chars", type=int, default=24000)
    parser.add_argument("--transport-max-bytes", type=int, default=1048576)
    parser.add_argument("--transport-max-input-tokens", type=int, default=96000)


def admission(args):
    inventory.require_runtime()
    original = Path(args.root).absolute()
    for ancestor in reversed((original, *original.parents)):
        inventory.no_reparse(ancestor)
    root = original.resolve(strict=True)
    require(root.is_dir(), "root", "existing directory")
    for field in ("run_id", "scope_id", "attempt_id"):
        value = getattr(args, field)
        require(ID.fullmatch(value), field, "1-96 ASCII identifier", value)
        inventory.canonical_path(value)
    require(all(getattr(args, k) > 0 for k in ("max_blocks", "max_chars", "transport_max_bytes", "transport_max_input_tokens")),
            "limits", "positive capacities")
    if args.stage == "prepare":
        require(args.source_set and not args.prepared and not args.candidate, "arguments", "prepare requires source-set only")
    else:
        require(args.prepared and args.candidate and not any((args.source_set, args.declaration, args.previous)),
                "arguments", "account requires prepared and candidate only")
    for name in ("source_set", "declaration", "previous", "prepared", "candidate"):
        if getattr(args, name):
            checked_path(root, getattr(args, name))
    # Search all dates so replaying an event tomorrow cannot duplicate accounting.
    base = checked_path(root, "logs/ci")
    if base.exists():
        for date in base.iterdir():
            inventory.no_reparse(date)
            if date.is_dir():
                relative = f"logs/ci/{date.name}/b-route-sources/{args.run_id}/{args.attempt_id}/{args.stage}"
                prior = checked_path(root, relative)
                if prior.exists():
                    return root, prior, False
    relative = f"logs/ci/{dt.datetime.now(dt.timezone.utc).date().isoformat()}/b-route-sources/{args.run_id}/{args.attempt_id}/{args.stage}"
    output = checked_path(root, relative)
    current = root
    for component in relative.split("/")[:-1]:
        current /= component
        current.mkdir(exist_ok=True)
        inventory.no_reparse(current)
    output.mkdir(exist_ok=False)
    return root, output, True


def main(argv=None):
    sys.dont_write_bytecode = True
    result = {"schema_version": "newrouge.b-route-sources-report.v1", "accounting_complete": False,
              "satisfied": False, "independent_audit": False, "formal_adoption": False,
              "diagnostics": [], "unresolved": [], "model_dispatch_count": 0,
              "budget_is_billing": False, "billed_cost": "unknown", "reuse_reason": "not_requested"}
    started, output, obs = time.monotonic(), None, None
    try:
        parser = Parser(description="3A prepare/account source proposals; no independent audit or formal adoption authority")
        register_arguments(parser)
        args = parser.parse_args(argv)
        root, admitted, created = admission(args)
        request = {k: v for k, v in vars(args).items() if k != "root"}
        request["root"] = str(root)
        if not created:
            try:
                previous_request = codec.strict_json_loads(codec.read_reference_bytes(root, (admitted / "request.json").relative_to(root).as_posix()))
                event = codec.strict_json_loads(codec.read_reference_bytes(root, (admitted / "event.json").relative_to(root).as_posix()))
                old = codec.strict_json_loads(codec.read_reference_bytes(root, (admitted / "report.json").relative_to(root).as_posix()))
                require(previous_request == request and event["event_key"] == [args.run_id, args.scope_id, args.stage, args.attempt_id],
                        "event", "same completed event and request")
                require(set(event["artifacts"]) | {"event.json"} ==
                        {p.relative_to(admitted).as_posix() for p in admitted.rglob("*") if p.is_file()},
                        "event", "exact completed output inventory")
                for relative, digest in event["artifacts"].items():
                    checked_path(root, (admitted / relative).relative_to(root).as_posix())
                    raw = codec.read_reference_bytes(root, (admitted / relative).relative_to(root).as_posix())
                    require(codec.raw_digest(raw) == digest, relative, digest)
                replay_observations = Observations(root)
                for path, digest in event["observations"].items():
                    raw = replay_observations.read(path, optional=digest is None)
                    require((codec.raw_digest(raw) if raw is not None else None) == digest,
                            path, "same completed event input identity")
                for watch in event["glob_observations"]:
                    require(replay_observations.watch(watch["patterns"]) == watch["result"],
                            "source-members", "same completed event membership")
                replay_observations.verify()
                print(json.dumps(old, ensure_ascii=False))
                return event["exit_code"]
            except (ValueError, OSError, KeyError, TypeError):
                fail(codec.ReasonCode.CONFLICT, "event", "matching complete immutable event", "conflict or partial write")
        output = admitted
        result.update(run_id=args.run_id, scope_id=args.scope_id, stage=args.stage, attempt_id=args.attempt_id,
                      event_key=[args.run_id, args.scope_id, args.stage, args.attempt_id],
                      output_ref=output.relative_to(root).as_posix())
        write(output / "request.json", request)
        obs = Observations(root)
        code = prepare(obs, args, output, result) if args.stage == "prepare" else account(obs, args, output, result)
        obs.verify()
    except (ValueError, OSError, KeyError, TypeError, AttributeError, UnicodeError, RuntimeError) as error:
        code = 1 if output is not None else 2
        diagnostic = error.diagnostic.to_dict() if isinstance(error, codec.CodecError) else codec.Diagnostic(
            codec.ReasonCode.READ_ERROR if isinstance(error, OSError) else codec.ReasonCode.SEMANTIC_ERROR,
            codec.Stage.CONTENT, actual=str(error)).to_dict()
        if output is not None:
            diagnostic["resume_ref"] = str(output / "report.json")
        result.update(accounting_complete=False, termination_reason="blocked" if code == 1 else "admission_rejected")
        result["diagnostics"].append(diagnostic)
        # Even a failed stage must reobserve every input it managed to read.
        if obs is not None:
            try:
                obs.verify()
            except (ValueError, OSError) as drift:
                result["diagnostics"].append(drift.diagnostic.to_dict() if isinstance(drift, codec.CodecError)
                                             else {"reason_code": "input_stale", "actual": str(drift)})
    result.update(active_elapsed_seconds=time.monotonic() - started, exit_code=code)
    if output is not None:
        try:
            write(output / "report.json", result)
            artifacts = {}
            for path in sorted(output.rglob("*")):
                if path.is_file():
                    relative = path.relative_to(root).as_posix()
                    checked_path(root, relative)
                    artifacts[path.relative_to(output).as_posix()] = codec.raw_digest(codec.read_reference_bytes(root, relative))
            write(output / "event.json", {**result, "artifacts": artifacts,
                "observations": {path: codec.raw_digest(raw) if raw is not None else None
                                 for path, raw in obs.files.items()} if obs else {},
                "glob_observations": [{"patterns": list(p), "result": r} for p, r in obs.globs.items()] if obs else []})
        except (OSError, ValueError) as error:
            result.update(exit_code=1, accounting_complete=False, termination_reason="partial_write")
            result["diagnostics"].append({"reason_code": "read_error", "actual": str(error)})
            code = 1
    print(json.dumps(result, ensure_ascii=False))
    return code
