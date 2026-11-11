"""Stdlib-only isolated tests; OS contention runs on the actual host platform."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_operation_leases as leases


class OperationLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix="operation-leases-" + uuid.uuid4().hex + "-",
            dir=Path(__file__).resolve().parent,
        )
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.meta = self.root / "metadata"
        self.a = self.root / "a"
        self.b = self.root / "b"
        for directory in (self.meta, self.a, self.b):
            directory.mkdir()
        self.scopes = {"task:b": self.b, "task:a": self.a}

    def operation(self, callback=lambda: None, **kwargs):
        return leases.operation_leases(
            kwargs.get("root", self.root), kwargs.get("meta", self.meta),
            kwargs.get("scopes", self.scopes), prepare_under_lease=callback,
        )

    def child(self, *args):
        return subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(Path(__file__).resolve()), *map(str, args)],
            capture_output=True, text=True, timeout=15, check=True, cwd=self.root,
        ).stdout.strip()

    def probe(self, directory):
        return self.child("--probe", directory)

    def assert_available(self):
        for directory in (self.meta, self.a, self.b):
            self.assertEqual(self.probe(directory), "available")

    def test_sorted_acquisition_and_callback_boundary(self):
        events = []
        active = set()

        @contextmanager
        def observed(directory):
            active.add(directory)
            events.append(("enter", directory.name))
            try:
                yield
            finally:
                active.remove(directory)
                events.append(("exit", directory.name))

        sentinel = object()

        def prepare():
            self.assertEqual(active, {self.meta, self.a, self.b})
            events.append(("prepare", "all"))
            return sentinel

        with patch.object(leases, "coordinator_lock", observed):
            with self.operation(prepare) as result:
                self.assertIs(result, sentinel)
                self.assertEqual(active, {self.a, self.b})
                events.append(("yield", "scopes"))
        self.assertEqual(events, [
            ("enter", "metadata"), ("enter", "a"), ("enter", "b"),
            ("prepare", "all"), ("exit", "metadata"), ("yield", "scopes"),
            ("exit", "b"), ("exit", "a"),
        ])

    def test_real_callback_and_yield_lock_boundaries(self):
        sentinel = {"caller_result": [1, 2]}

        def prepare():
            for directory in (self.meta, self.a, self.b):
                self.assertEqual(self.probe(directory), "busy")
            return sentinel

        with self.operation(prepare) as result:
            self.assertIs(result, sentinel)
            self.assertEqual(self.probe(self.meta), "available")
            for directory in (self.a, self.b):
                self.assertEqual(self.probe(directory), "busy")
        self.assert_available()

    def test_partial_scope_contention_releases_metadata_and_prior_scope(self):
        with leases.coordinator_lock(self.b):
            with self.assertRaisesRegex(ValueError, "^capability_coordinator_busy$"):
                with self.operation(lambda: self.fail("prepare ran during contention")):
                    self.fail("yield ran during contention")
            self.assertEqual(self.probe(self.meta), "available")
            self.assertEqual(self.probe(self.a), "available")
            self.assertEqual(self.probe(self.b), "busy")
        self.assert_available()

    def test_metadata_contention_does_not_attempt_scopes(self):
        with leases.coordinator_lock(self.meta):
            with self.assertRaisesRegex(ValueError, "^capability_coordinator_busy$"):
                with self.operation(lambda: self.fail("prepare ran")):
                    self.fail("yield ran")
            self.assertEqual(self.probe(self.a), "available")
            self.assertEqual(self.probe(self.b), "available")

    def test_callback_and_body_exceptions_release_all_locks(self):
        class PrepareInterrupted(BaseException):
            pass

        error = PrepareInterrupted("prepare failed")

        def prepare():
            raise error

        with self.assertRaises(PrepareInterrupted) as caught:
            with self.operation(prepare):
                self.fail("yield ran")
        self.assertIs(caught.exception, error)
        self.assert_available()
        with self.assertRaisesRegex(RuntimeError, "long work failed"):
            with self.operation():
                raise RuntimeError("long work failed")
        self.assert_available()

    def test_acquisition_exception_rolls_back_prior_locks(self):
        active = set()

        @contextmanager
        def failing(directory):
            if directory == self.b:
                raise OSError("scope open failed")
            active.add(directory)
            try:
                yield
            finally:
                active.remove(directory)

        with patch.object(leases, "coordinator_lock", failing):
            with self.assertRaisesRegex(OSError, "scope open failed"):
                with self.operation():
                    self.fail("yield ran")
        self.assertEqual(active, set())

    def test_real_process_contention_and_crash_release_without_unlink(self):
        process = subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", str(Path(__file__).resolve()), "--hold", str(self.root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            # A daemon reader lets the finally block kill an unresponsive child.
            ready_lines = queue.Queue()
            reader = threading.Thread(target=lambda: ready_lines.put(process.stdout.readline()), daemon=True)
            reader.start()
            ready = ready_lines.get(timeout=15)
            self.assertEqual(ready.strip(), "ready")
            self.assertEqual(self.probe(self.meta), "available")
            with self.assertRaisesRegex(ValueError, "^capability_coordinator_busy$"):
                with self.operation():
                    self.fail("yield ran")
            for directory in (self.a, self.b):
                self.assertEqual(self.probe(directory), "busy")
            paths = [directory / leases._LOCK_NAME for directory in (self.meta, self.a, self.b)]
            identities = [path.stat().st_ino for path in paths]
            process.kill()
            process.communicate(timeout=15)
            self.assertNotEqual(process.returncode, 0)
            self.assert_available()
            self.assertEqual([path.stat().st_ino for path in paths], identities)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=15)

    def test_invalid_paths_and_keys_fail_before_lock_acquisition(self):
        file_path = self.root / "file"
        file_path.write_text("fixture", encoding="utf-8")
        cases = [
            {"root": self.root / "missing"}, {"meta": self.root / "missing"},
            {"meta": file_path}, {"meta": Path("relative")},
            {"meta": self.meta / ".." / "metadata"}, {"meta": self.root.parent},
            {"scopes": {}}, {"scopes": []}, {"scopes": {"Task:a": self.a}},
            {"scopes": {" task:a": self.a}}, {"scopes": {"task/a": self.a}},
            {"scopes": {1: self.a}}, {"scopes": {"x" * 129: self.a}},
            {"scopes": {"a": self.meta}}, {"scopes": {"a": self.a, "b": self.a}},
            {"scopes": {"a": self.root / "missing"}},
            {"scopes": {"a": self.root.parent}},
            {"scopes": {"a": self.root / "metadata."}},
            {"scopes": {"a": self.root / "a:stream"}},
            {"scopes": {"a": self.root / "CON.txt"}},
            {"scopes": {"a": self.root / "COM\u00b9.txt"}},
        ]
        if os.name == "nt":
            cases.append({"scopes": {"a": self.a, "b": Path(str(self.a).upper())}})
        with patch.object(leases, "coordinator_lock", side_effect=AssertionError("lock attempted")):
            for kwargs in cases:
                with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, OSError)):
                    with self.operation(**kwargs):
                        self.fail("yield ran")
            with self.assertRaises(TypeError):
                with self.operation(None):
                    self.fail("yield ran")

    def test_existing_unsafe_lock_file_is_rejected_without_locks(self):
        lock = self.a / leases._LOCK_NAME
        lock.mkdir()
        with patch.object(leases, "coordinator_lock", side_effect=AssertionError("lock attempted")):
            with self.assertRaisesRegex(ValueError, "operation_lease_lock_path_invalid"):
                with self.operation():
                    self.fail("yield ran")
        lock.rmdir()
        lock.write_bytes(b"0")
        os.link(lock, self.root / "lock-alias")
        with self.assertRaisesRegex(ValueError, "operation_lease_lock_path_invalid"):
            with self.operation():
                self.fail("yield ran")

    def test_reparse_directory_and_ancestor_are_rejected(self):
        alias = self.root / "alias"
        if os.name == "nt":
            result = subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(alias), str(self.a)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            alias.symlink_to(self.a, target_is_directory=True)
        self.addCleanup(lambda: alias.rmdir() if os.name == "nt" else alias.unlink())
        nested = self.a / "nested"
        nested.mkdir()
        cases = [
            {"meta": alias}, {"scopes": {"a": alias}},
            {"scopes": {"a": alias / "nested"}},
            {"root": alias, "meta": alias / "nested", "scopes": {"a": self.b}},
        ]
        with patch.object(leases, "coordinator_lock", side_effect=AssertionError("lock attempted")):
            for kwargs in cases:
                with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "reparse"):
                    with self.operation(**kwargs):
                        self.fail("yield ran")

    def test_only_existing_coordinator_files_are_written(self):
        formal = self.root / ".taskmaster" / "tasks"
        formal.mkdir(parents=True)
        (formal / "tasks.json").write_bytes(b'{"unchanged":true}\n')
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(self.child("--import-only"), "imported")
        self.assertEqual(
            {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before,
        )
        with self.operation(lambda: "caller result") as result:
            self.assertEqual(result, "caller result")
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for name, raw in before.items():
            self.assertEqual(after.pop(name), raw)
        self.assertEqual(after, {
            Path("metadata") / leases._LOCK_NAME: b"0",
            Path("a") / leases._LOCK_NAME: b"0",
            Path("b") / leases._LOCK_NAME: b"0",
        })


def _worker():
    if sys.argv[1] == "--probe":
        try:
            with leases.coordinator_lock(Path(sys.argv[2])):
                print("available")
        except ValueError as error:
            if str(error) != "capability_coordinator_busy":
                raise
            print("busy")
    elif sys.argv[1] == "--import-only":
        print("imported")
    elif sys.argv[1] == "--hold":
        root = Path(sys.argv[2])
        with leases.operation_leases(root, root / "metadata", {"b": root / "b", "a": root / "a"},
                                     prepare_under_lease=lambda: None):
            print("ready", flush=True)
            sys.stdin.readline()
    else:
        raise ValueError("unknown worker mode")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith("--"):
        _worker()
    else:
        print(json.dumps({"platform": sys.platform, "os_name": os.name,
                          "python": sys.version, "executable": sys.executable}), flush=True)
        unittest.main(verbosity=2)
