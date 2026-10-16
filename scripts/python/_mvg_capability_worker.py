"""Private candidate lifecycles with coordinator-owned durable dispatch reservations."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, parse_model_json

SCHEMA = "newrouge.mvg-capability-worker.v1"


class Mailbox:
    def __init__(self, directory, identity, timeout=60):
        self.directory, self.identity, self.timeout = directory, identity, timeout
        self.sequence = 0
        self.reservation = None

    def request(self, kind, **payload):
        self.sequence += 1
        stem = str(self.sequence)
        atomic_json(self.directory / (stem + ".request.json"), {
            "identity": self.identity, "sequence": self.sequence, "kind": kind, **payload})
        deadline = time.monotonic() + self.timeout
        target = self.directory / (stem + ".response.json")
        while time.monotonic() < deadline:
            if target.is_file():
                response = load_json(target)
                if response.get("identity") != self.identity or response.get("sequence") != self.sequence:
                    raise ValueError("worker_mailbox_response_identity_changed")
                if response.get("error"):
                    from _mvg_capability_append import RunBudgetExhausted, AppendBudgetExhausted
                    error = response["error"]
                    if error["type"] == "RunBudgetExhausted":
                        raise RunBudgetExhausted(error["detail"])
                    if error["type"] == "AppendBudgetExhausted":
                        raise AppendBudgetExhausted(error["detail"])
                    raise ValueError(error["detail"])
                value = response.get("value")
                if kind == "reserve":
                    self.reservation = value
                return value
            time.sleep(.025)
        raise RuntimeError("worker_coordinator_mailbox_timeout")


def runner_invoke(root, run_dir, state, workspace, config, mailbox):
    """A fresh runner sandbox sees only this call's complete relevant payload."""
    import shutil
    import plan_mvg as pm
    from _mvg_capability_generation import preflight_dispatch, dispatch_request_identity
    runner = Path(config["runner"])

    def invoke(prompt, attempt, *, output_name, output_schema_path, output_schema, before_dispatch=None):
        name = Path(output_name)
        sandbox = workspace / "llm-sandbox" / f"attempt-{attempt}" / name.with_suffix("").as_posix().replace("/", "-")
        # Pure request preflight may already have created this sandbox. A model
        # output would indicate an attempted reuse, which is never permitted.
        sandbox.mkdir(parents=True, exist_ok=True)
        output = sandbox / name.name
        if output.exists():
            raise ValueError("worker_model_output_already_exists")
        atomic_json(output_schema_path, output_schema)
        schema = sandbox / "output-schema.json"
        shutil.copyfile(output_schema_path, schema)
        stem = name.with_suffix("").as_posix().replace("/", "-")
        prompt_path = sandbox / f"prompt-{attempt}-{stem}.txt"
        prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
        pm._validate_input_freshness(root, run_dir, state)
        preflight_dispatch(runner, workspace=sandbox, prompt_path=prompt_path, output_path=output,
                           output_schema=schema, timeout_sec=config["timeout_sec"])
        request = dispatch_request_identity(run_dir, runner, workspace=sandbox, prompt_path=prompt_path,
            output_path=output, output_schema=schema, attempt=attempt)
        previous_reservation = mailbox.reservation
        if before_dispatch:
            before_dispatch(request_identity=request)
        reservation = mailbox.reservation
        if not isinstance(reservation, dict) or reservation is previous_reservation:
            raise ValueError("worker_dispatch_requires_parent_reservation")
        try:
            receipt = pm.run_isolated_model(runner, workspace=sandbox, prompt_path=prompt_path,
                output_path=output, output_schema=schema, timeout_sec=config["timeout_sec"])
            parse_model_json(output)
            outcome = {"status": "completed", "completed_at_utc": pm.now(),
                "error_type": None, "output_sha256": file_sha(output)}
        except Exception as exc:
            mailbox.request("outcome", reservation_id=reservation["reservation_id"], outcome={
                "status": "failed", "completed_at_utc": pm.now(),
                "error_type": pm.classify_review_error(exc), "error_class": type(exc).__name__})
            raise
        mailbox.request("outcome", reservation_id=reservation["reservation_id"], outcome=outcome)
        return output, {"attempt": attempt, "invocation": reservation, "backend": config["backend"],
            "backend_info": config["backend_info"], "runner": runner.as_posix(), "returncode": 0, "receipt": receipt}
    return invoke


def execute(job_path):
    from _mvg_capability_generation import generate_append
    job = load_json(job_path)
    binding = job["identity"]
    if job.get("schema_version") != SCHEMA or canonical_sha(job["input"]) != binding:
        raise ValueError("worker_job_identity_changed")
    data = job["input"]
    root, run_dir, workspace = (Path(data[key]) for key in ("root", "run_dir", "workspace"))
    mailbox = Mailbox(job_path.parent / "mailbox", binding)
    state = data["state"]
    result = generate_append(root, state, workspace,
        invoke_factory=lambda target: runner_invoke(root, run_dir, state, target, data["runner"], mailbox),
        before_call=lambda phase, request_identity=None: mailbox.request("reserve", phase=phase,
            request_identity=request_identity),
        checkpoint=lambda progress: atomic_json(job_path.parent / "progress.json", {
            "status": progress["status"], "total_invocations": progress["total_invocations"]}),
        scope_index=data["scope_index"], accepted_seed=data["accepted_seed"],
        selected_records=data["selected_records"],
        cost_budget=lambda phase, **kwargs: mailbox.request("cost", phase=phase, **kwargs))
    # Intermediate drafts and model conversations never cross this boundary.
    output = {"schema_version": SCHEMA, "identity": binding, "pid": os.getpid(),
        "status": result["status"], "total_invocations": result["total_invocations"],
        "errors": result.get("errors", [])}
    if result["status"] == "admitted":
        output["artifacts"] = {name: file_sha(workspace / name) for name in (
            "proposal.json", "admission-review.json", "admission-execution.json")}
    atomic_json(job_path.parent / "result.json", output)


def run_candidate(job_dir, data, *, reserve, cost_budget, outcome, inline=None):
    """Run a real OS child; the optional inline callable is a unit-test seam."""
    job_dir.mkdir(parents=True, exist_ok=False)
    identity = canonical_sha(data)
    job_path = job_dir / "job.json"
    atomic_json(job_path, {"schema_version": SCHEMA, "identity": identity, "input": data})
    mailbox = job_dir / "mailbox"
    mailbox.mkdir()
    sequence = 1
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (job_dir / "worker.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--job", str(job_path)],
            cwd=data["workspace"], stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}, creationflags=flags)
        atomic_json(job_dir / "process.json", {"pid": process.pid, "identity": identity})
        try:
            while True:
                request_path = mailbox / (str(sequence) + ".request.json")
                if request_path.is_file():
                    request = load_json(request_path)
                    if request.get("identity") != identity or request.get("sequence") != sequence:
                        raise ValueError("worker_mailbox_request_identity_changed")
                    response = {"identity": identity, "sequence": sequence}
                    try:
                        kind = request["kind"]
                        if kind == "reserve":
                            value = reserve(request["phase"], request.get("request_identity"))
                        elif kind == "cost":
                            value = cost_budget(request["phase"], known_evidence_calls=request["known_evidence_calls"])
                        elif kind == "outcome":
                            value = outcome(request["reservation_id"], request["outcome"])
                        else:
                            raise ValueError("worker_mailbox_request_kind_invalid")
                        response["value"] = value
                    except (OSError, ValueError, RuntimeError) as exc:
                        response["error"] = {"type": type(exc).__name__, "detail": str(exc)}
                    atomic_json(mailbox / (str(sequence) + ".response.json"), response)
                    sequence += 1
                    continue
                if process.poll() is not None:
                    break
                time.sleep(.025)
            if process.returncode:
                raise RuntimeError("candidate_worker_failed:" + str(process.returncode) + ":" + str(job_dir))
            result = load_json(job_dir / "result.json")
            if (result.get("schema_version") != SCHEMA or result.get("identity") != identity
                    or result.get("pid") != process.pid):
                raise ValueError("candidate_worker_result_identity_changed")
            workspace = Path(data["workspace"])
            if result.get("status") == "admitted":
                expected = {name: file_sha(workspace / name) for name in (
                    "proposal.json", "admission-review.json", "admission-execution.json")}
                if result.get("artifacts") != expected:
                    raise ValueError("candidate_worker_artifacts_changed")
                result["accepted"] = load_json(workspace / "proposal.json")
            return result
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, check=False)
                else:
                    process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    execute(parser.parse_args().job)
