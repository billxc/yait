"""Global lockfile for serializing YAIT write operations."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


class LockError(Exception):
    """Base exception for lock-related errors."""


class LockTimeout(LockError):
    """Raised when lock acquisition times out."""


class YaitLock:
    """Context manager that serializes write access via a lockfile.

    Uses ``os.open(path, O_CREAT | O_EXCL | O_WRONLY)`` for atomic creation.
    Stale locks are detected by PID liveness and timestamp timeout.
    """

    def __init__(
        self,
        root: Path,
        command: str = "",
        timeout: float = 30.0,
        stale_timeout: float = 60.0,
    ) -> None:
        self.lock_path = root / ".yait" / "yait.lock"
        self.command = command
        self.timeout = timeout
        self.stale_timeout = stale_timeout

    def __enter__(self) -> "YaitLock":
        self._acquire()
        return self

    def __exit__(self, *exc) -> None:
        self._release()

    # ------------------------------------------------------------------

    def _acquire(self) -> None:
        deadline = time.monotonic() + self.timeout
        delay = 0.05  # 50 ms initial backoff

        while True:
            try:
                fd = os.open(
                    str(self.lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                if self._try_break_stale():
                    continue  # stale lock removed, retry immediately
                if time.monotonic() >= deadline:
                    raise LockTimeout(
                        f"Could not acquire lock within {self.timeout}s: {self.lock_path}"
                    )
                time.sleep(delay)
                delay = min(delay * 2, 0.5)
                continue

            # Lock created successfully — write metadata and close fd.
            try:
                payload = json.dumps({
                    "pid": os.getpid(),
                    "timestamp": time.time(),
                    "command": self.command,
                })
                os.write(fd, payload.encode())
            finally:
                os.close(fd)
            return

    def _release(self) -> None:
        try:
            os.unlink(str(self.lock_path))
        except FileNotFoundError:
            pass

    # ------------------------------------------------------------------

    def _try_break_stale(self) -> bool:
        """Return True if a stale lock was detected and removed."""
        try:
            data = self.lock_path.read_text()
        except (FileNotFoundError, OSError):
            return False

        try:
            info = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            # Corrupted lock file — treat as stale.
            self._force_remove()
            return True

        pid = info.get("pid")
        timestamp = info.get("timestamp")

        # Check PID liveness first (fast path).
        if pid is not None and not self._pid_alive(pid):
            self._force_remove()
            return True

        # Fallback: timestamp-based timeout.
        if timestamp is not None and (time.time() - timestamp) > self.stale_timeout:
            self._force_remove()
            return True

        return False

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we can't signal it — still alive.
            return True
        return True

    def _force_remove(self) -> None:
        try:
            os.unlink(str(self.lock_path))
        except FileNotFoundError:
            pass
