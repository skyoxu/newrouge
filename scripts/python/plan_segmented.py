#!/usr/bin/env python3
"""Explicit versioned host entry for new segmented Capability and MVG runs."""
import argparse
import json
from pathlib import Path
import sys

HOST = "newrouge.b-route-segmented-host.v1"
STAGES = ("plan", "prepare", "execute", "status", "verify", "resume-publication")


def _owners():
    import _b_route_codec as codec
    import _b_route_segmented_candidates as products
    import _b_route_segmented_journal as journal
    import _b_route_segmented_plan as producer
    import _b_route_segmented_runtime as runtime
    import _b_route_segmented_workflow as core
    return codec, products, journal, producer, runtime, core


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--protocol", choices=(HOST,), default=HOST)
    result.add_argument("--root", type=Path, required=True, help="Original governed artifact project, separate from loaded source.")
    result.add_argument("--planner", choices=("capability", "mvg"), required=True)
    result.add_argument("--run-id", required=True)
    result.add_argument("--stage", choices=STAGES, required=True)
    result.add_argument("--planning-contract", help="Original root-relative qualified 3B planning contract; plan/prepare only.")
    result.add_argument("--semantic-catalog", help="Optional root-relative original independently audited source catalog.")
    result.add_argument("--partition", choices=("whole", "audited-components"), default="whole")
    return result


def _require(condition, field):
    if not condition:
        raise ValueError("segmented_host_blocked:" + field)


def _catalog_ref(root, name, runtime):
    if name is None:
        return None
    runtime.role(name)
    raw = runtime.raw(root, name)
    value = runtime.value(root, name)
    _require(type(value) is dict and value.get("schema_version") == runtime.CATALOG, "original_catalog_version")
    # This raw reference alone is not approval: capture_plan_authority requires
    # these very bytes in the actual original independently audited 3A scope.
    return runtime.ref_for(name, runtime.CATALOG, raw)


def _home(root, planner, run_id, runtime):
    prefix = "capability" if planner == "capability" else "mvg"
    return runtime.path(root, "logs/ci/" + prefix + "-planning/" + run_id, missing=True)


def _saved_plan(root, run, runtime, core):
    name = (run / "b/plan.json").relative_to(root).as_posix()
    return core.validate_plan(runtime.value(root, name))


def run(args):
    _require(args.protocol == HOST, "explicit_host_protocol")
    _require(args.stage in STAGES and args.planner in {"capability", "mvg"}, "stage_or_planner")
    _require(args.run_id not in {"c4", "m4"}, "legacy_run_cannot_opt_in")
    root = args.root.absolute()
    _require(root.is_dir(), "original_project_required")
    codec, products, journal, producer, runtime, core = _owners()
    codec.validate_business_id(args.run_id)
    run_dir = _home(root, args.planner, args.run_id, runtime)
    _require(args.partition in producer.PARTITIONS, "partition_policy")
    if args.stage in {"plan", "prepare"}:
        _require(type(args.planning_contract) is str and args.planning_contract, "original_planning_contract_required")
        runtime.role(args.planning_contract)
        catalog = _catalog_ref(root, args.semantic_catalog, runtime)
        authority = runtime.capture_plan_authority(root, run_id=args.run_id, planner=args.planner,
            planning_contract=args.planning_contract, semantic_catalog_ref=catalog)
        plan = producer.build_plan(root, authority, partition_policy=args.partition)
        if args.stage == "plan":
            return {"schema_version": HOST, "status": "plan-declared", "logical_calls": 0,
                    "currentness": "checked-for-this-action-only", "plan": plan,
                    "formal_adoption": False, "readiness": False}
        # prepare_run independently obtains fresh actual source/funding facts and
        # closes the original birth CAS; this token is not a saved approval.
        prepared = runtime.prepare_run(root, run_id=args.run_id, planner=args.planner, plan=plan,
            planning_contract=args.planning_contract, semantic_catalog_ref=catalog)
        return {"schema_version": HOST, "status": "segmented-run-prepared", "preparation": prepared,
                "logical_calls": 0, "formal_adoption": False, "readiness": False}
    _require(args.planning_contract is None and args.semantic_catalog is None and args.partition == "whole",
             "prepared_run_cannot_override_inputs_or_partition")
    plan = _saved_plan(root, run_dir, runtime, core)
    _require(plan["run_id"] == args.run_id and plan["planner"] == args.planner, "original_saved_plan_identity")
    if args.stage == "execute":
        value = core.execute_workflow(root, run_dir=run_dir, plan=plan)
        return {"schema_version": HOST, "status": "segmented-protocol-completed", "completion": value,
                "legacy_native_admission": False, "formal_adoption": False, "readiness": False}
    if args.stage == "verify":
        completion = runtime.value(root, (run_dir / "q/completion.json").relative_to(root).as_posix())
        _require(type(completion) is dict and type(completion.get("candidate_proof")) is dict,
                 "persisted_new_candidate_proof_required")
        actual = products.verify_proof(root, run_dir=run_dir, plan=plan, proof=completion["candidate_proof"])
        return {"schema_version": HOST, "status": "new-segmented-candidate-proof-verified", "proof": actual,
                "logical_calls": 0, "legacy_native_admission": False, "formal_adoption": False, "readiness": False}
    with runtime.verified_run(root, run_dir, plan):
        if args.stage == "resume-publication" or not runtime.path(root,
                (run_dir / "q/state.json").relative_to(root).as_posix(), missing=True).is_file():
            state = runtime.value(root, (run_dir / "run.json").relative_to(root).as_posix())
            witness = runtime.segmented_run_contract(root, state, run_dir, plan_digest=plan["plan_digest"], protocol=core.PROTOCOL)
            history = journal.inspect_native_history(root, run_dir, state)
            if args.stage == "status":
                _require(state["capability_selection"]["calls"] == [], "paid_workflow_cannot_lose_auxiliary_state")
                return {"schema_version": HOST, "status": "segmented-prepared-status", "completed_nodes": [],
                    "funding": witness["funding"], "native_reserved_calls": history["native_reserved_calls"],
                    "charged_or_pending_calls": history["charged_or_pending_calls"],
                    "pending_publications": history["pending_publications"], "logical_calls": 0,
                    "may_redispatch_unknown": False, "formal_adoption": False, "readiness": False}
            _require(len(history["pending_publications"]) == 1
                     and history["pending_publications"][0]["run_id"] == args.run_id,
                     "exact_pending_metadata_publication_required")
        with journal.open_workflow(root, run_dir=run_dir, plan=plan, read_only=args.stage == "status") as session:
            snapshot = session.snapshot() if args.stage == "status" else session.resume()
            return {"schema_version": HOST,
                "status": "segmented-status" if args.stage == "status" else "metadata-publication-resumed",
                "completed_nodes": [item["node_id"] for item in snapshot["completed"]],
                "blocked": snapshot["blocked"], "budget": snapshot["budget"], "logical_calls": 0,
                "may_redispatch_unknown": False, "formal_adoption": False, "readiness": False}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
    except Exception as error:
        # A blocked action never falls through to another backend, request ID,
        # old contract, or retry. KeyboardInterrupt still propagates normally.
        print(json.dumps({"schema_version": HOST, "status": "blocked", "error_type": type(error).__name__,
                          "reason": str(error), "automatic_retry": False}, ensure_ascii=False, allow_nan=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
