"""Actual Windows parent-death checks for the ADR-0039 worker tree."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _planning_skill_common import load_json


@unittest.skipUnless(os.name == "nt", "Windows Job Object lifetime contract")
class WorkerParentExitTests(unittest.TestCase):
    def test_abrupt_parent_exit_terminates_worker_and_grandchild(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = (root / "parent.log").open("w", encoding="utf-8")
            process = subprocess.Popen([sys.executable, str(Path(__file__).parent / "fixtures/mvg_worker_lifetime_probe.py"),
                "parent", "--directory", str(root)], stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            handles, pids = [], []
            try:
                deadline = time.monotonic() + 15
                while not (root / "ready.json").is_file() and time.monotonic() < deadline:
                    if process.poll() is not None:
                        log.flush()
                        self.fail("Probe parent exited: " + (root / "parent.log").read_text(encoding="utf-8"))
                    time.sleep(.025)
                self.assertTrue((root / "ready.json").is_file(), "Worker did not reach its gated dispatch")
                pids = list(load_json(root / "ready.json").values())
                handles = [kernel.OpenProcess(0x00100000, False, pid) for pid in pids]
                self.assertTrue(all(handles), "Both descendants must be live before parent termination")
                process.kill()
                process.wait(timeout=10)
                for handle in handles:
                    self.assertEqual(0, kernel.WaitForSingleObject(handle, 5000),
                                     "A model-like descendant survived abrupt coordinator termination")
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
                for pid, handle in zip(pids, handles):
                    if handle and kernel.WaitForSingleObject(handle, 0) != 0:
                        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                            creationflags=subprocess.CREATE_NO_WINDOW)
                    if handle:
                        kernel.CloseHandle(handle)
                log.close()


if __name__ == "__main__":
    unittest.main()
