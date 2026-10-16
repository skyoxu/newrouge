"""Schema-driven offline runner for actual MVG worker process integration tests."""
from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _planning_skill_common import RUNNER_SCHEMA, atomic_json, file_sha, load_json
from _mvg_evidence_transport import restore_lossless_context

DESCRIPTION = {"schema_version": RUNNER_SCHEMA, "filesystem_scope": "workspace_only",
    "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
    "model": "offline-mvg-fixture", "model_tools": []}


def render(schema, prompt):
    props = schema["properties"]
    value = {key: prop["const"] for key, prop in props.items() if "const" in prop}
    if value["schema_version"] == "newrouge.mvg-selection-review.v1":
        labels = props["candidate_reviews"]["items"]["properties"]["label"]["enum"]
        value.update(status="selected", selected=labels[0], tradeoffs=["Complete journey"], evidence_refs=[],
            rationale="All increments are admitted", candidate_reviews=[{"label": label, "verdict": "viable",
                "rank": index, "rationale": "Complete owned journey"} for index, label in enumerate(labels, 1)])
    elif value["schema_version"] == "newrouge.mvg-capability-append.v1":
        payload = restore_lossless_context(json.loads(prompt.splitlines()[-1]))
        scope = payload["scope"]
        base = payload["accepted_proposal"]
        cid, rid = scope["capability_id"], scope["requirement_ids"][0]
        flow = next(row for row in base["manifest_candidate"]["flows"] if cid in row["capability_refs"])
        tid = flow["task_ids"][0]
        coverage = {"requirement_id": rid, "flow_id": flow["id"], "capability_ref": cid, "task_id": tid,
            "disposition": "flow", "rationale": "Concrete source-backed journey", "sink_id": None,
            "verification_ref": None, "authority_ref": None, "authority_review": None}
        value.update(flows=[], tests=[], change_reviews=[], gaps=[], notes=[], coverage_table=[coverage],
            requirement_route_memberships=[{"requirement_id": rid, "flow_id": flow["id"],
                "observable_role": "Concrete source-backed journey"}],
            entrypoints=[{"status": "planned", "flow_ids": [flow["id"]], "owner_task": tid,
                "path": "Game.Core/Runtime.cs", "symbol": "Execute", "inputs": "Request", "state": "Ready",
                "assertions": "Consumer state observed", "implementation_acceptance": "Exercise failure recovery"}])
        if "requirement_verification" in props:
            value.update(requirement_verification=[{**deepcopy(coverage), "evidence_ids": []}], requirement_evidence=[])
    else:
        rows = []
        for item in props["requirement_reviews"]["items"]["anyOf"]:
            row = {key: prop["const"] for key, prop in item["properties"].items() if "const" in prop}
            rows.append({**row, "verdict": "covered", "rationale": "Full source supports the journey", "repair_action": "none"})
        value.update(verdict="approved", findings=[], requirement_reviews=rows,
            flow_reviews=[{"flow_id": fid, "verdict": "sound", "rationale": "Owned observable handoff"}
                for fid in props["flow_reviews"]["items"]["properties"]["flow_id"].get("enum", [])])
        if "reopen_reviews" in props:
            value["reopen_reviews"] = []
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--describe", action="store_true")
    for name in ("workspace", "prompt-file", "output", "output-schema", "timeout-sec"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(DESCRIPTION))
    else:
        output = Path(args.output)
        value = render(load_json(Path(args.output_schema)), Path(args.prompt_file).read_text(encoding="utf-8"))
        atomic_json(output, value)
        receipt = {"model": DESCRIPTION["model"], "model_tools": [], "output_sha256": file_sha(output),
            "fixture_pid": os.getpid(), "input_integrity": load_json(Path(args.workspace) / "runner-input-integrity.json", {})}
        print(json.dumps(receipt))
