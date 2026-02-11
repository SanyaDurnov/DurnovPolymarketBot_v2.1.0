"""
In-memory log handler for market-specific log viewing.

Stores recent log entries in a bounded deque for retrieval via API.
Logs are filtered by market_id substring match on the frontend.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class LogEntry:
    """Single log record stored in memory."""
    id: int
    timestamp: float
    timestamp_str: str
    level: str
    logger_name: str
    message: str


class MarketLogHandler(logging.Handler):
    """
    Custom logging.Handler that stores log entries in a thread-safe deque.

    deque(maxlen=5000) at ~200-300 bytes per entry = ~1.5MB max memory.
    Thread safety: deque.append() is atomic in CPython, lock protects counter only.
    """

    def __init__(self, max_entries: int = 5000):
        super().__init__()
        self._buffer: deque = deque(maxlen=max_entries)
        self._counter: int = 0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            with self._lock:
                self._counter += 1
                entry_id = self._counter

            entry = LogEntry(
                id=entry_id,
                timestamp=record.created,
                timestamp_str=time.strftime(
                    '%Y-%m-%d %H:%M:%S', time.localtime(record.created)
                ),
                level=record.levelname,
                logger_name=record.name,
                message=record.getMessage(),
            )
            self._buffer.append(entry)
        except Exception:
            self.handleError(record)

    def get_logs_for_market(
        self,
        market_id: str,
        after_id: int = 0,
        limit: int = 200,
    ) -> List[dict]:
        """
        Return log entries where market_id appears in the message.

        Args:
            market_id: UUID substring to filter on.
            after_id: Only return entries with id > after_id (incremental loading).
            limit: Max entries to return.

        Returns:
            List of log entry dicts, ordered oldest-first.
        """
        results = []
        for entry in self._buffer:
            if entry.id <= after_id:
                continue
            if market_id in entry.message:
                results.append(asdict(entry))
                if len(results) >= limit:
                    break
        return results


# Singleton instance
market_log_handler = MarketLogHandler(max_entries=5000)
