"""Disposable parent/child/grandchild probe; never dispatches a model."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _planning_skill_common import atomic_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("parent", "child", "leaf"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args()
    if args.mode == "parent":
        import _mvg_capability_worker as worker
        from unittest.mock import patch
        original = subprocess.Popen
        def child(command, **kwargs):
            gated = ["--gate"] if "--start-gate" in command else []
            return original([sys.executable, __file__, "child", "--directory", str(args.directory), *gated], **kwargs)
        workspace = args.directory / "workspace"
        workspace.mkdir()
        with patch.object(worker.subprocess, "Popen", side_effect=child):
            worker.run_candidate(args.directory / "job", {"workspace": str(workspace)},
                reserve=lambda *a: None, cost_budget=lambda *a: None, outcome=lambda *a: None)
    elif args.mode == "child":
        # Parent assignment must finish before anything representing paid work.
        if args.gate and sys.stdin.buffer.readline() != b"start\n":
            return
        with subprocess.Popen([sys.executable, __file__, "leaf", "--directory", str(args.directory)],
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as leaf:
            atomic_json(args.directory / "ready.json", {"child": __import__("os").getpid(), "leaf": leaf.pid})
            leaf.wait(timeout=60)
    else:
        time.sleep(60)


if __name__ == "__main__":
    main()
