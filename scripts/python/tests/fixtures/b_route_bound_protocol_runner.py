"""Offline transport adapter around the real isolated runner, not a model service.

Only process transport and executable discovery are replaced. Capture, protocol
replay, binding and reservation validators remain production code. The returned
fixture runtime configuration is never real provider/acceptance evidence.
"""
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import codex_isolated_model_runner as runner
import _codex_app_server as server


def main():
    original = subprocess.Popen
    def launch(command, *args, **kwargs):
        if isinstance(command, list) and command[0] == "story25-offline-transport":
            workspace = Path(sys.argv[sys.argv.index("--workspace") + 1])
            command = [sys.executable, "-I", "-S", "-B", str(Path(__file__).with_name("b_route_protocol_child.py")),
                       str(workspace.parents[2] / "fixture-response.json")]
        return original(command, *args, **kwargs)
    runner._codex_executable = lambda: "story25-offline-transport"
    server.subprocess.Popen = launch
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
