from __future__ import annotations

import threading
import time


class PlayQueue:
    def __init__(self, limit: int = 2, timeout: float = 120) -> None:
        self.limit = limit
        self.timeout = timeout
        self.tickets = {}
        self.lock = threading.Lock()

    def _expire(self) -> None:
        cutoff = time.monotonic() - self.timeout
        self.tickets = {ticket: seen for ticket, seen in self.tickets.items() if seen > cutoff}

    def touch(self, ticket: str) -> dict:
        with self.lock:
            self._expire()
            self.tickets[ticket] = time.monotonic()
            index = list(self.tickets).index(ticket)
            return {"admitted": index < self.limit, "position": max(0, index - self.limit + 1)}

    def admitted(self, ticket: str) -> bool:
        with self.lock:
            self._expire()
            return ticket in list(self.tickets)[:self.limit]

    def leave(self, ticket: str) -> dict:
        with self.lock:
            self.tickets.pop(ticket, None)
        return {"left": True}
