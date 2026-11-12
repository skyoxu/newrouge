"""Run exactly four existing Windows recovery controls; never invoke a model."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SELECTORS = (
    "test_b_route_commit_recovery.WindowsRecoveryTests",
    "test_b_route_compensation.WindowsCompensationTests",
)


def main():
    output = ROOT / "logs/ci/b-route-deterministic/windows-recovery"
    output.mkdir(parents=True, exist_ok=False)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != os.environ.get("GITHUB_SHA", head):
        raise RuntimeError("Checkout must equal the requested Actions commit")
    source_paths = [p for prefix in ("scripts/python", "scripts/sc")
                    for p in (ROOT / prefix).rglob("*.py")]
    before = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source_paths}
    environment = {
        "head": head, "os_name": os.name, "platform": platform.platform(),
        "python": sys.version, "executable": sys.executable,
        "run_id": os.environ.get("GITHUB_RUN_ID"), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "selectors": SELECTORS, "expected_tests": 4, "source_sha256": before,
        "upstream_admission_and_review": "explicit synthetic fixtures",
        "new_model_calls": 0, "real_model_full_chain_qualification": False,
    }
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        (output / "summary.json").write_text(json.dumps({
            "status": "blocked", "reason": "Native Windows is required; no test executed",
            "tests_run": 0, "new_model_calls": 0,
        }, indent=2) + "\n", encoding="utf-8")
        return 2
    sys.path[:0] = [str(ROOT / "scripts/python"), str(ROOT / "scripts/python/tests"),
                    str(ROOT / "scripts/sc"), str(ROOT)]

    class Result(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.successes = []
            self.timings = []

        def startTest(self, test):
            self.started = time.monotonic()
            super().startTest(test)

        def addSuccess(self, test):
            self.successes.append(test.id())
            super().addSuccess(test)

        def stopTest(self, test):
            self.timings.append({"test": test.id(), "elapsed_seconds": time.monotonic() - self.started})
            super().stopTest(test)

    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in SELECTORS)
    if suite.countTestCases() != 4:
        raise RuntimeError("The fixed selector must collect the four original Windows controls")
    started = time.monotonic()
    with (output / "tests.log").open("x", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(suite)
    changed = [name for name, digest in before.items()
               if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    passed = result.wasSuccessful() and result.testsRun == 4 and not result.skipped and not changed
    summary = {
        "status": "passed" if passed else "failed", "head": head, "tests_run": result.testsRun,
        "passed_tests": result.successes, "failures": [{"test": t.id(), "traceback": text} for t, text in result.failures],
        "errors": [{"test": t.id(), "traceback": text} for t, text in result.errors],
        "skipped": [{"test": t.id(), "reason": reason} for t, reason in result.skipped],
        "test_timings": result.timings, "elapsed_seconds": time.monotonic() - started,
        "changed_source_files": changed, "new_model_calls": 0,
        "upstream_admission_and_review": "explicit synthetic fixtures",
        "real_model_full_chain_qualification": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
