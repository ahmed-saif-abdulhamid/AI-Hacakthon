"""Pipeline work off the request path: one daemon thread per run advances it to its next stop."""

from __future__ import annotations

import threading

from proveit import orchestrator


class RunWorkers:
    """Registry of the worker thread advancing each run. A run never has two live workers."""

    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def advance(self, run_id: str) -> None:
        """Advance ``run_id`` in the background, unless a worker for it is already running."""
        with self._lock:
            if self._is_alive(run_id):
                return
            thread = threading.Thread(target=orchestrator.advance, args=(run_id,), daemon=True, name=f"run-{run_id}")
            self._threads[run_id] = thread
            thread.start()

    def is_working(self, run_id: str) -> bool:
        with self._lock:
            return self._is_alive(run_id)

    def _is_alive(self, run_id: str) -> bool:
        thread = self._threads.get(run_id)
        return thread is not None and thread.is_alive()


run_workers = RunWorkers()
