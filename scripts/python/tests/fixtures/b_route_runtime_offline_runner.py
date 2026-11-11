"""Local OS-runner fixture; explicitly synthetic, no provider or network calls.

Its schema-valid draft lets the production 3B worker exercise reservation and
capture. The production execution validator must reject this synthetic receipt.
"""
import argparse
import json
from pathlib import Path


DESCRIPTION = {"schema_version": "newrouge.isolated-model-runner.v1", "filesystem_scope": "prompt_only",
    "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
    "model": "offline-3b-synthetic-fixture", "model_tools": []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--workspace")
    parser.add_argument("--prompt-file")
    parser.add_argument("--output")
    args, _ = parser.parse_known_args()
    if args.describe:
        print(json.dumps(DESCRIPTION))
        return
    materials = json.loads(Path(args.prompt_file).read_text(encoding="utf-8").split("\n", 1)[1])
    request = materials["root_request"]["input"]
    output = {"schema_version": "newrouge.b-route-planning-draft.v1", "input_identity": materials["root_input_identity"],
        "stage": request["stage"], "ordinal": request["ordinal"],
        "parent_draft_identities": [row["identity"] for row in request["prior_drafts"]], "content": {}}
    raw = json.dumps(output, separators=(",", ":"))
    Path(args.output).write_text(raw, encoding="utf-8", newline="\n")
    print(json.dumps({"schema_version": "newrouge.isolated-model-runner-receipt.v1", "synthetic": True,
        "model": DESCRIPTION["model"], "model_tools": [], "model_identity_scope": "synthetic_fixture",
        "runner_invocations": 1, "model_request_count": 1, "request_count_observable": True,
        "workspace": Path(args.workspace).as_posix(), "output_chars": len(raw)}))


if __name__ == "__main__":
    main()
