"""Persistence for delivery state and seen-event bookkeeping.

One connection is opened per operation, the way a request-scoped service
would. Callers share the database file, not the connection.
"""
import os
import sqlite3
import tempfile
import uuid

from .models import DeliveryState
from .state import next_state

_SCHEMA = """
CREATE TABLE IF NOT EXISTS deliveries (
    message_id  TEXT PRIMARY KEY,
    state       TEXT NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS seen_events (
    message_id        TEXT NOT NULL,
    event_type        TEXT NOT NULL,
    provider_event_id TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path=None):
        if path is None:
            path = os.path.join(tempfile.gettempdir(),
                                f"webhook-ingest-{uuid.uuid4().hex}.db")
        self.path = path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    # -- dedup bookkeeping -------------------------------------------------

    def is_duplicate(self, event):
        """True if we have already processed this event."""
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT 1 FROM seen_events WHERE provider_event_id = ?",
                (event.provider_event_id,),
            )
            return cur.fetchone() is not None

    def record_seen(self, event):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO seen_events (message_id, event_type, provider_event_id) "
                "VALUES (?, ?, ?)",
                (event.message_id, event.event_type.value, event.provider_event_id),
            )

    # -- delivery state ----------------------------------------------------

    def get(self, message_id):
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT state, event_count FROM deliveries WHERE message_id = ?",
                (message_id,),
            )
            row = cur.fetchone()
        if row is None:
            return DeliveryState.QUEUED, 0
        return DeliveryState(row[0]), row[1]

    def apply_event(self, event):
        """Advance the delivery row for this event and return the new state."""
        current, count = self.get(event.message_id)

        resolved = next_state(current, event)

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO deliveries (message_id, state, event_count) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(message_id) DO UPDATE SET state = ?, event_count = ?",
                (event.message_id, resolved.value, count + 1,
                 resolved.value, count + 1),
            )
        return resolved
