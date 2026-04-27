"""Tests for yait.lock — global lockfile concurrency protection."""
from __future__ import annotations

import json
import multiprocessing
import os
import time
from pathlib import Path

import pytest

from yait.lock import LockError, LockTimeout, YaitLock
from yait.store import init_store


# ── helpers ────────────────────────────────────────────────────


def _lock_path(root: Path) -> Path:
    return root / ".yait" / "yait.lock"


def _worker_acquire_lock(root_str: str, hold_seconds: float, result_queue):
    """Multiprocessing worker: acquire lock, hold it, then release."""
    root = Path(root_str)
    try:
        with YaitLock(root, "worker", timeout=10.0):
            result_queue.put(("acquired", os.getpid()))
            time.sleep(hold_seconds)
        result_queue.put(("released", os.getpid()))
    except Exception as exc:
        result_queue.put(("error", str(exc)))


# ── basic acquire / release ───────────────────────────────────


class TestBasicLock:
    def test_acquire_and_release(self, initialized_root):
        with YaitLock(initialized_root, "test"):
            assert _lock_path(initialized_root).exists()
        assert not _lock_path(initialized_root).exists()

    def test_lock_file_content(self, initialized_root):
        with YaitLock(initialized_root, "test-cmd"):
            data = json.loads(_lock_path(initialized_root).read_text())
            assert data["pid"] == os.getpid()
            assert data["command"] == "test-cmd"
            assert isinstance(data["timestamp"], float)

    def test_enter_returns_self(self, initialized_root):
        lock = YaitLock(initialized_root, "test")
        with lock as ctx:
            assert ctx is lock

    def test_exception_in_with_block_releases_lock(self, initialized_root):
        with pytest.raises(RuntimeError, match="boom"):
            with YaitLock(initialized_root, "test"):
                raise RuntimeError("boom")
        assert not _lock_path(initialized_root).exists()


# ── stale lock detection ──────────────────────────────────────


class TestStaleLock:
    def test_stale_lock_dead_pid(self, initialized_root):
        """Lock held by a dead PID should be automatically cleaned up."""
        lp = _lock_path(initialized_root)
        lp.write_text(json.dumps({
            "pid": 999999999,  # almost certainly not running
            "timestamp": time.time(),
            "command": "ghost",
        }))
        # Should succeed because the PID is dead.
        with YaitLock(initialized_root, "test", timeout=2.0):
            assert _lock_path(initialized_root).exists()

    def test_stale_lock_expired_timestamp(self, initialized_root):
        """Lock with a very old timestamp should be treated as stale."""
        lp = _lock_path(initialized_root)
        lp.write_text(json.dumps({
            "pid": os.getpid(),  # our own PID — alive
            "timestamp": time.time() - 120,  # 2 min ago
            "command": "old",
        }))
        # stale_timeout=1.0 means anything older than 1s is stale.
        with YaitLock(initialized_root, "test", timeout=2.0, stale_timeout=1.0):
            pass

    def test_corrupted_lock_treated_as_stale(self, initialized_root):
        """A lock file with garbage content should be cleaned up."""
        _lock_path(initialized_root).write_text("not json!!!")
        with YaitLock(initialized_root, "test", timeout=2.0):
            pass


# ── timeout ───────────────────────────────────────────────────


class TestTimeout:
    def test_lock_timeout(self, initialized_root):
        """If lock is held by a live process, acquisition should time out."""
        lp = _lock_path(initialized_root)
        lp.write_text(json.dumps({
            "pid": os.getpid(),
            "timestamp": time.time(),
            "command": "holder",
        }))
        with pytest.raises(LockTimeout):
            with YaitLock(initialized_root, "waiter", timeout=0.3, stale_timeout=60.0):
                pass


# ── re-entrant attempt ────────────────────────────────────────


class TestReentrant:
    def test_same_process_second_acquire_times_out(self, initialized_root):
        """Acquiring the lock twice from the same process should time out."""
        with YaitLock(initialized_root, "first"):
            with pytest.raises(LockTimeout):
                with YaitLock(initialized_root, "second", timeout=0.3, stale_timeout=60.0):
                    pass


# ── multiprocessing concurrency ───────────────────────────────


class TestConcurrency:
    def test_two_processes_mutual_exclusion(self, initialized_root):
        """Two processes competing for the lock should not overlap."""
        q = multiprocessing.Queue()
        root_str = str(initialized_root)

        p1 = multiprocessing.Process(
            target=_worker_acquire_lock, args=(root_str, 0.5, q)
        )
        p2 = multiprocessing.Process(
            target=_worker_acquire_lock, args=(root_str, 0.3, q)
        )
        p1.start()
        time.sleep(0.05)  # give p1 a head start
        p2.start()
        p1.join(timeout=15)
        p2.join(timeout=15)

        events = []
        while not q.empty():
            events.append(q.get_nowait())

        acquired = [e for e in events if e[0] == "acquired"]
        released = [e for e in events if e[0] == "released"]
        errors = [e for e in events if e[0] == "error"]
        assert not errors, f"Worker errors: {errors}"
        assert len(acquired) == 2, f"Expected 2 acquires, got {acquired}"
        assert len(released) == 2, f"Expected 2 releases, got {released}"

        # The first process should acquire before the second.
        # And the first release should come before the second acquire.
        first_acquired_pid = acquired[0][1]
        first_released_pid = released[0][1]
        assert first_acquired_pid == first_released_pid, (
            "First process to acquire should be first to release"
        )


# ── context manager protocol ─────────────────────────────────


class TestContextManagerProtocol:
    def test_exit_returns_none(self, initialized_root):
        lock = YaitLock(initialized_root, "test")
        lock.__enter__()
        result = lock.__exit__(None, None, None)
        assert result is None

    def test_release_idempotent(self, initialized_root):
        """Calling _release when no lock file exists should not error."""
        lock = YaitLock(initialized_root, "test")
        lock._release()  # no lock file — should be a no-op
