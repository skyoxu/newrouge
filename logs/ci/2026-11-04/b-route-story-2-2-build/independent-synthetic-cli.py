"""Independent synthetic CLI exercise; never actual model semantic evidence."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
repository = Path.cwd()
output = Path(sys.argv[1]).absolute()
output.mkdir(parents=True, exist_ok=False)
cases = []


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fixture(name, mode="clean"):
    root = output / name
    (root / "docs").mkdir(parents=True)
    (root / "docs/first.md").write_bytes(b"# Synthetic obligation\r\n\r\nPreserve input order.  \r\n")
    (root / "docs/second.md").write_bytes(b"# Synthetic handoff\r\n\r\nReturn to map when the action completes.\r\n")
    paths = ["docs/first.md", "docs/second.md"]
    save(root / "docs/source-set.json", {"schema_version": "chapter3.source-set.v1", "active_patterns": paths,
                                       "active_sources": paths, "retirements": []})
    source = (repository / "scripts/python/tests/fixtures/b_route_audit_synthetic_runner.py").read_text(encoding="utf-8")
    (root / "runner.py").write_text(source.replace('MODE = "clean"', "MODE = " + repr(mode)), encoding="utf-8")
    return root


def call(root, run, stage, attempt, expected, extra, *, public=True):
    before = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in root.rglob("*") if p.is_file() and not p.relative_to(root).as_posix().startswith("logs/")}
    command = [sys.executable, str(repository / "scripts/python/dev_cli.py"), "b-route-sources"] if public else [
        sys.executable, str(repository / "scripts/python/account_b_route_sources.py")]
    command += ["--root", str(root), "--run-id", run, "--scope-id", "synthetic-scope", "--attempt-id", attempt, "--stage", stage, *extra]
    proc = subprocess.run(command, cwd=repository, capture_output=True, text=True, encoding="utf-8", errors="strict", timeout=180)
    name = f"{len(cases) + 1:03d}-" + root.name + "-" + stage + "-" + attempt
    (output / (name + ".stdout")).write_text(proc.stdout, encoding="utf-8")
    (output / (name + ".stderr")).write_text(proc.stderr, encoding="utf-8")
    assert proc.stderr == "", (name, proc.stderr)
    assert len(proc.stdout.splitlines()) == 1, (name, proc.stdout)
    value = json.loads(proc.stdout)
    assert proc.returncode == expected and value["exit_code"] == expected, (name, proc.returncode, value)
    assert value["formal_adoption"] is False and value["budget_is_billing"] is False, (name, value)
    if stage in {"audit", "verify"}:
        assert value["planning_eligible"] is False, (name, value)
        count = value["model_dispatch_count"]
        assert count == 0 or (count == "unknown" and expected != 0 and not value["execution_complete"] and value["runner_dispatch_count"] > 0), (name, value)
    assert all((root / p).is_file() and hashlib.sha256((root / p).read_bytes()).hexdigest() == h for p, h in before.items()), name
    assert not (root / ".taskmaster").exists(), name
    cases.append({"case": name, "exit_code": proc.returncode, "synthetic_only": True,
                  "original_bytes_unchanged": True, "model_dispatch_count": value["model_dispatch_count"]})
    return value


def accounted(root):
    run = root.name
    prepared = call(root, run, "prepare", "prepare", 0, ["--source-set", "docs/source-set.json"], public=False)
    value = json.loads((root / prepared["output_ref"] / "candidate.json").read_bytes())
    for index, row in enumerate(value["block_results"]):
        row.update(delivery_potential=False, disposition="context", reason="Synthetic context for the independent orchestration fixture.", atoms=[])
        if index == 0:
            row.update(delivery_potential=True, disposition="atomized", atoms=[{
                "proposal_id": "proposal:preserve-order", "kind": "functional", "statement": "Preserve input order.",
                "source_block_ids": [row["block_id"]], "acceptance_intent": "The input order remains observable.",
                "prior_requirement_ids": [], "non_task_sinks": []}])
    for row in value["batch_summaries"]:
        row["output_accounted_count"] = row["input_block_count"]
    save(root / "docs/candidate.json", value)
    return call(root, run, "account", "account", 0, ["--prepared", prepared["prepared_ref"]["path"], "--candidate", "docs/candidate.json"])


def audit(root, report, attempt, expected=0, extra=()):
    return call(root, root.name, "audit", attempt, expected, ["--accounted", report["output_ref"] + "/report.json",
        "--runner", "runner.py", "--expected-model", "synthetic/source-audit-v1", *extra])


root = fixture("clean")
account = accounted(root)
complete = audit(root, account, "fresh")
assert complete["execution_complete"] and complete["synthetic_dispatch_count"] == 3
ref = complete["output_ref"] + "/report.json"
verified = call(root, root.name, "verify", "verify", 0, ["--audit-ref", ref, "--runner", "runner.py", "--expected-model", "synthetic/source-audit-v1"], public=False)
assert verified["runner_dispatch_count"] == 0
reused = audit(root, account, "reuse", extra=["--audit-ref", ref])
assert reused["runner_dispatch_count"] == 0 and reused["reuse_reason"] == "complete_identity_and_original_proof_match"
assert audit(root, account, "fresh") == complete
bad = call(root, root.name, "verify", "missing-proof", 1, ["--audit-ref", "missing/report.json", "--runner", "runner.py", "--expected-model", "synthetic/source-audit-v1"])
capacity_root = fixture("capacity")
capacity = audit(capacity_root, accounted(capacity_root), "capacity", 1, ["--transport-max-input-tokens", "20"])
assert capacity["runner_dispatch_count"] == 0 and capacity["termination_reason"] == "capacity_blocked"
for mode in ("omission", "conflict", "bad-quote", "fake-pass", "tools"):
    root = fixture(mode, mode)
    report = audit(root, accounted(root), "negative", 1)
    assert not report["planning_eligible"]
    if mode in {"omission", "conflict"}:
        assert report["execution_complete"] and report["semantic_blockers"]
    else:
        assert not report["execution_complete"]
root = fixture("budget")
account = accounted(root)
blocked = audit(root, account, "first", 1, ["--request-budget", "1"])
assert blocked["termination_reason"] == "budget_blocked" and blocked["synthetic_dispatch_count"] == 1
again = audit(root, account, "second", 1, ["--request-budget", "1"])
assert again["termination_reason"] == "budget_blocked" and again["runner_dispatch_count"] == 0
save(output / "cli-summary.json", {"cases": cases, "passed_cli_invocations": len(cases), "synthetic_only": True,
                                   "actual_model_semantics_verified": False, "production_inputs_used": False})
print(json.dumps({"passed_cli_invocations": len(cases), "synthetic_only": True}, indent=2))
