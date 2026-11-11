"""Fixed neutral Windows reader/verifier roles. No native or model invocation."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import time


def duplicate_for_receiver(process, receiver, target):
    # Receiver is this test's still-running supervisor, not a discovered PID.
    # Transfer an actual duplicate of the held child handle, not its PID.
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.DuplicateHandle.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    owner = api.OpenProcess(0x0040, False, receiver)  # PROCESS_DUP_HANDLE only
    if not owner:
        raise ctypes.WinError(ctypes.get_last_error())
    transferred = wintypes.HANDLE()
    try:
        if not api.DuplicateHandle(api.GetCurrentProcess(), int(process._handle), owner,
                ctypes.byref(transferred), 0, False, 2):
            raise ctypes.WinError(ctypes.get_last_error())
        target.write_text(str(transferred.value), encoding='ascii')
    finally:
        api.CloseHandle(owner)


def main():
    role, root = sys.argv[1], Path(sys.argv[2])
    if role == 'verifier':
        (root / 'verifier-started').write_bytes(b'started')
        time.sleep(float(sys.argv[3]))
        return
    if role == 'lock-probe':
        import msvcrt
        descriptor = os.open(root / 'capability-coordinator.lock', os.O_RDWR)
        try:
            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError:
                print('busy')
            else:
                print('acquired')
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(descriptor)
        return
    (root / 'gate-released').write_bytes(b'released')
    sys.stdin.buffer.read()
    sys.stdout.buffer.write(b'reader-stdout\n')
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(b'reader-stderr\n')
    sys.stderr.buffer.flush()
    duration = '.05' if role == 'normal' else '60'
    inherited = role == 'exit-first'
    child = subprocess.Popen([sys.executable, '-I', '-S', '-B', __file__, 'verifier', str(root), duration],
        stdin=subprocess.DEVNULL, stdout=None if inherited else subprocess.PIPE,
        stderr=None if inherited else subprocess.PIPE, close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    duplicate_for_receiver(child, int(os.environ['BR_READER_FIXTURE_RECEIVER']), root / 'verifier-handle')
    if role == 'normal':
        child.wait(timeout=10)
        child.stdout.close()
        child.stderr.close()
    elif role == 'slow':
        time.sleep(60)
    elif role != 'exit-first':
        raise ValueError('unknown_reader_fixture_role')


if __name__ == '__main__':
    main()
