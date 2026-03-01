import os
import socket
import time
import uuid

from cqltrack.exceptions import LockError


class MigrationLock:
    """Distributed lock backed by Cassandra lightweight transactions.

    Uses INSERT ... IF NOT EXISTS to guarantee only one process runs
    migrations at a time.  A TTL acts as a safety net so that a lock
    left behind by a crashed process will eventually expire on its own.
    """

    LOCK_KEY = "cqltrack_global"

    def __init__(self, session, ttl=600):
        self.session = session
        self.ttl = ttl
        self.owner = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._held = False

    # -- public api ----------------------------------------------------------

    def acquire(self, retries=30, wait_seconds=2.0):
        for attempt in range(retries):
            rs = self.session.execute(
                "INSERT INTO cqltrack_lock (lock_id, owner, acquired_at) "
                "VALUES (%s, %s, toTimestamp(now())) IF NOT EXISTS USING TTL %s",
                (self.LOCK_KEY, self.owner, self.ttl),
            )
            row = rs.one()
            if row.applied:
                self._held = True
                return

            holder = getattr(row, "owner", "unknown")
            if attempt < retries - 1:
                time.sleep(wait_seconds)
            else:
                raise LockError(
                    f"Could not acquire migration lock after {retries} attempts. "
                    f"Current holder: {holder}. "
                    f"It will auto-expire within {self.ttl}s if stale."
                )

    def release(self):
        if not self._held:
            return
        self.session.execute(
            "DELETE FROM cqltrack_lock WHERE lock_id = %s IF owner = %s",
            (self.LOCK_KEY, self.owner),
        )
        self._held = False

    # -- context manager -----------------------------------------------------

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
