"""Private Windows reader transport. Own handles, Job membership and pipe workers.

The stdin gate precedes project execution. This supervises the authenticated
CreateProcess descendant chain, not arbitrary broker processes or the OS.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import threading
import time

from _mvg_worker_lifetime import WindowsWorkerJob
from _planning_skill_common import _stop_owned_pipe_workers


GATE = "import sys\nif sys.stdin.buffer.readline() != b'start\\n': raise SystemExit(2)\n"
HOST_TIMEOUT = 3600
CLEANUP_TIMEOUT = 5.0


class ReaderTransportError(RuntimeError):
    def __init__(self, outcome, *, stdout=b'', stderr=b'', cleanup='unconfirmed', cause=None):
        super().__init__('b_route_reader_transport:' + outcome)
        self.outcome, self.stdout, self.stderr, self.cleanup = outcome, stdout, stderr, cleanup
        self.cause_type = type(cause).__name__ if cause is not None else None


class _DescendantsRemain(RuntimeError):
    pass


class ReaderJob(WindowsWorkerJob):
    """Reuse the worker Job owner; add handle-based termination and accounting."""
    def __init__(self):
        super().__init__()
        self.api.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
            ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        self.api.QueryInformationJobObject.restype = wintypes.BOOL
        self.api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.TerminateJobObject.restype = wintypes.BOOL

    def active(self):
        class Accounting(ctypes.Structure):
            _fields_ = [(name, ctypes.c_longlong) for name in (
                'TotalUserTime', 'TotalKernelTime', 'ThisPeriodTotalUserTime', 'ThisPeriodTotalKernelTime')] + [
                (name, wintypes.DWORD) for name in ('TotalPageFaultCount', 'TotalProcesses',
                                                   'ActiveProcesses', 'TotalTerminatedProcesses')]
        value = Accounting()
        if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(value), ctypes.sizeof(value), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return value.ActiveProcesses

    def terminate(self):
        if not self.api.TerminateJobObject(self.handle, 2):
            raise ctypes.WinError(ctypes.get_last_error())


class _Pipes:
    """Each worker alone closes its stream, including during cancellation."""
    def __init__(self, process):
        self.process = process
        self.parts = {'stdout': [], 'stderr': []}
        self.errors = []
        self.stopping = threading.Event()
        self.workers = []
        self.stream_workers = {}

    def start_readers(self):
        for name in ('stdout', 'stderr'):
            self._start(self._read, (name,), name)

    def _start(self, target, args, name):
        worker = threading.Thread(target=target, args=args, name='b-route-reader-' + name, daemon=True)
        self.workers.append(worker)
        self.stream_workers[name] = worker
        worker.start()

    def _read(self, name):
        stream = getattr(self.process, name)
        try:
            while not self.stopping.is_set():
                data = stream.read1(65536)
                if not data:
                    break
                self.parts[name].append(data)
        except (OSError, ValueError) as error:
            self.errors.append(error)
        finally:
            try:
                stream.close()
            except (OSError, ValueError) as error:
                self.errors.append(error)

    def release(self, payload):
        self._start(self._write, (b'start\n' + payload,), 'stdin')

    def _write(self, payload):
        stream = self.process.stdin
        try:
            if not self.stopping.is_set():
                stream.write(payload)
                stream.flush()
        except (OSError, ValueError) as error:
            self.errors.append(error)
        finally:
            try:
                stream.close()
            except (OSError, ValueError) as error:
                self.errors.append(error)

    def data(self, name):
        return b''.join(self.parts[name])

    def done(self):
        return not any(worker.is_alive() for worker in self.workers)

    def close_unowned(self):
        # Assignment is not writer ownership. A failed Thread.start leaves its
        # pipe parent-owned; never close a buffer still owned by a live worker.
        failures = []
        for name in ('stdin', 'stdout', 'stderr'):
            worker = self.stream_workers.get(name)
            if worker is None or worker.ident is None:
                try:
                    getattr(self.process, name).close()
                except (OSError, ValueError) as error:
                    failures.append(error)
        if failures:
            raise RuntimeError('reader_unowned_pipe_close_failed') from failures[0]


def run_reader(command, *, input, cwd, env, timeout=HOST_TIMEOUT):
    """Release only an assigned reader; return only after confirmed Job quiescence.

    The host deadline never changes native/model budgets. Cleanup uses one fixed
    additional window. API failures are explicitly unconfirmed, never known-empty.
    No taskkill, process inventory, PID lookup, breakaway or unowned fallback.
    """
    if os.name != 'nt':
        raise ReaderTransportError('windows_job_required')
    deadline = time.monotonic() + timeout
    job = process = pipes = None
    primary = None
    cleanup_errors = []
    confirmed = False
    assigned = False
    leftover = False
    try:
        job = ReaderJob()
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=cwd, env=env, close_fds=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        pipes = _Pipes(process)
        pipes.start_readers()
        # The direct child is still blocked before source loading or child spawn.
        job.assign(process)
        assigned = True
        if time.monotonic() >= deadline:
            raise TimeoutError('reader_host_deadline_before_release')
        pipes.release(input)
        direct_exit_seen = None
        while process.poll() is None or not pipes.done():
            if time.monotonic() >= deadline:
                raise TimeoutError('reader_host_deadline')
            if process.poll() is not None:
                direct_exit_seen = direct_exit_seen or time.monotonic()
                if time.monotonic() - direct_exit_seen >= .05 and job.active():
                    raise _DescendantsRemain('reader_descendants_after_exit')
            if pipes.errors:
                raise pipes.errors[0]
            time.sleep(min(.01, max(0, deadline - time.monotonic())))
        if pipes.errors:
            raise pipes.errors[0]
    except BaseException as error:
        primary = error
    finally:
        cleanup_deadline = time.monotonic() + CLEANUP_TIMEOUT
        if job is not None:
            try:
                # Allow exit accounting to settle; it is not evidence of a child
                # outcome. Remaining activity after direct exit is a failed read.
                settle = min(cleanup_deadline, time.monotonic() + .05)
                count = job.active()
                while primary is None and count and time.monotonic() < settle:
                    time.sleep(.005)
                    count = job.active()
                leftover = primary is None and count != 0
                if count or primary is not None:
                    job.terminate()
                while True:
                    if job.active() == 0:
                        confirmed = True
                        break
                    if time.monotonic() >= cleanup_deadline:
                        raise TimeoutError('reader_job_quiescence_unconfirmed')
                    time.sleep(.005)
            except BaseException as error:
                cleanup_errors.append(error)
                # Termination still uses the held Job if accounting failed.
                try:
                    job.terminate()
                except BaseException as error:
                    cleanup_errors.append(error)
        if process is not None:
            try:
                if not assigned and process.poll() is None:
                    # Assignment failed while the gate was closed. Only this
                    # exact retained direct handle can have executed anything.
                    process.terminate()
                process.wait(timeout=max(0, cleanup_deadline - time.monotonic()))
            except BaseException as error:
                cleanup_errors.append(error)
        if pipes is not None:
            try:
                _stop_owned_pipe_workers(pipes.workers, pipes.stopping,
                    timeout=max(0, cleanup_deadline - time.monotonic()))
            except BaseException as error:
                cleanup_errors.append(error)
            try:
                pipes.close_unowned()
            except BaseException as error:
                cleanup_errors.append(error)
        elif process is not None:
            # _Pipes construction launches no worker, so a constructor failure
            # leaves every stream exclusively owned by this parent.
            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    stream.close()
                except BaseException as error:
                    cleanup_errors.append(error)
        if job is not None:
            try:
                job.close()  # sole non-inherited handle; parent-death backstop
            except BaseException as error:
                cleanup_errors.append(error)
    stdout = pipes.data('stdout') if pipes is not None else b''
    stderr = pipes.data('stderr') if pipes is not None else b''
    cleanup = 'confirmed_empty' if confirmed and not cleanup_errors else 'unconfirmed'
    if primary is not None and not isinstance(primary, Exception):
        BaseException.add_note(primary, 'reader_owned_cleanup:' + cleanup)
        raise primary
    if primary is not None or cleanup_errors or leftover or not confirmed:
        outcome = ('timeout' if isinstance(primary, TimeoutError) else 'descendants_after_reader_exit'
                   if isinstance(primary, _DescendantsRemain) else 'transport_failure'
                   if primary is not None else 'descendants_after_reader_exit' if leftover else 'cleanup_unconfirmed')
        error = ReaderTransportError(outcome, stdout=stdout, stderr=stderr, cleanup=cleanup,
                                     cause=primary or (cleanup_errors[0] if cleanup_errors else None))
        if primary is not None:
            raise error from primary
        raise error
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
