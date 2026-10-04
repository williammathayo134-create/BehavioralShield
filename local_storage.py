#!/usr/bin/env python3
"""
monitoring.py

A tiny, production‑ready SQLite helper that stores two kinds of data:

* sensor_logs      – generic time‑series sensor readings
* security_events  – discrete security‑related events

The module can be imported and used from other code, or executed directly
to see a quick demo.

Author : Your Name
License: MIT
"""

from __future__ import annotations

import sqlite3
import pathlib
import datetime as dt
from typing import Any, Iterable, List, Tuple, Optional, Dict

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
DB_PATH = pathlib.Path(__file__).with_name("monitoring.db")  # same folder as script


# --------------------------------------------------------------------------- #
# Helper functions
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    """Return current UTC time as ISO‑8601 string (e.g. '2026-10-04T12:34:56Z')."""
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# --------------------------------------------------------------------------- #
# Main class
# --------------------------------------------------------------------------- #
class MonitoringDB:
    """
    Simple wrapper around an SQLite database that stores sensor logs and security events.

    Typical usage
    -------------
    >>> db = MonitoringDB()
    >>> db.insert_sensor_log(sensor_id=1, value=23.5)
    >>> db.insert_security_event(event_type='door_open', description='Main entrance')
    >>> rows = db.get_sensor_logs(sensor_id=1, limit=10)
    >>> db.close()
    """

    def __init__(self, db_file: pathlib.Path | str = DB_PATH):
        self.db_file = pathlib.Path(db_file)
        self.conn = sqlite3.connect(self.db_file, detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.row_factory = sqlite3.Row   # rows behave like dicts
        self._create_tables()

    # ------------------------------------------------------------------- #
    # Table creation
    # ------------------------------------------------------------------- #
    def _create_tables(self) -> None:
        """Create the two tables if they do not already exist."""
        cur = self.conn.cursor()

        # sensor_logs – generic time‑series data
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sensor_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id   INTEGER NOT NULL,
                timestamp   TEXT    NOT NULL,   -- ISO‑8601 UTC
                value       REAL    NOT NULL,
                unit        TEXT,               -- optional unit (e.g. '°C')
                metadata    TEXT                 -- JSON string or any extra info
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_sensor_logs_sensor_ts ON sensor_logs(sensor_id, timestamp);"
        )

        # security_events – discrete events
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS security_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT    NOT NULL,   -- e.g. 'alarm', 'door_open'
                timestamp   TEXT    NOT NULL,   -- ISO‑8601 UTC
                severity    INTEGER NOT NULL DEFAULT 1,   -- 1 (low) … 5 (critical)
                description TEXT,
                metadata    TEXT                 -- JSON string or any extra info
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_security_events_type_ts ON security_events(event_type, timestamp);"
        )

        self.conn.commit()

    # ------------------------------------------------------------------- #
    # INSERT helpers
    # ------------------------------------------------------------------- #
    def insert_sensor_log(
        self,
        sensor_id: int,
        value: float,
        *,
        timestamp: Optional[str] = None,
        unit: Optional[str] = None,
        metadata: Optional[str] = None,
    ) -> int:
        """
        Insert a single sensor reading.

        Returns
        -------
        int
            The newly generated row id.
        """
        ts = timestamp or _now_iso()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO sensor_logs (sensor_id, timestamp, value, unit, metadata)
            VALUES (?, ?, ?, ?, ?);
            """,
            (sensor_id, ts, value, unit, metadata),
        )
        self.conn.commit()
        return cur.lastrowid

    def insert_security_event(
        self,
        event_type: str,
        *,
        timestamp: Optional[str] = None,
        severity: int = 1,
        description: Optional[str] = None,
        metadata: Optional[str] = None,
    ) -> int:
        """
        Insert a single security event.

        Returns
        -------
        int
            The newly generated row id.
        """
        ts = timestamp or _now_iso()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO security_events (event_type, timestamp, severity, description, metadata)
            VALUES (?, ?, ?, ?, ?);
            """,
            (event_type, ts, severity, description, metadata),
        )
        self.conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------- #
    # Bulk insert helpers (more efficient for many rows)
    # ------------------------------------------------------------------- #
    def bulk_insert_sensor_logs(self, rows: Iterable[Tuple[int, float, str, Optional[str], Optional[str]]]) -> None:
        """
        Insert many sensor logs at once.

        Parameters
        ----------
        rows : iterable of tuples
            Each tuple must be (sensor_id, value, timestamp, unit, metadata).
            ``timestamp`` may be ``None`` – in that case the current UTC time is used.
        """
        cur = self.conn.cursor()
        data = [
            (sid, val, ts or _now_iso(), unit, meta)
            for sid, val, ts, unit, meta in rows
        ]
        cur.executemany(
            """
            INSERT INTO sensor_logs (sensor_id, timestamp, value, unit, metadata)
            VALUES (?, ?, ?, ?, ?);
            """,
            data,
        )
        self.conn.commit()

    def bulk_insert_security_events(self, rows: Iterable[Tuple[str, str, int, Optional[str], Optional[str]]]) -> None:
        """
        Insert many security events at once.

        Parameters
        ----------
        rows : iterable of tuples
            Each tuple must be (event_type, timestamp, severity, description, metadata).
            ``timestamp`` may be ``None`` – the current UTC time will be used.
        """
        cur = self.conn.cursor()
        data = [
            (etype, ts or _now_iso(), sev, desc, meta)
            for etype, ts, sev, desc, meta in rows
        ]
        cur.executemany(
            """
            INSERT INTO security_events (event_type, timestamp, severity, description, metadata)
            VALUES (?, ?, ?, ?, ?);
            """,
            data,
        )
        self.conn.commit()

    # ------------------------------------------------------------------- #
    # Query helpers
    # ------------------------------------------------------------------- #
    def get_sensor_logs(
        self,
        *,
        sensor_id: Optional[int] = None,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
        limit: int = 100,
        order: str = "DESC",
    ) -> List[sqlite3.Row]:
        """
        Retrieve sensor logs with optional filtering.

        Returns a list of ``sqlite3.Row`` objects (behave like dicts).
        """
        sql = "SELECT * FROM sensor_logs WHERE 1=1"
        params: List[Any] = []

        if sensor_id is not None:
            sql += " AND sensor_id = ?"
            params.append(sensor_id)
        if start_ts is not None:
            sql += " AND timestamp >= ?"
            params.append(start_ts)
        if end_ts is not None:
            sql += " AND timestamp <= ?"
            params.append(end_ts)

        sql += f" ORDER BY timestamp {order} LIMIT ?"
        params.append(limit)

        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()

    def get_security_events(
        self,
        *,
        event_type: Optional[str] = None,
        min_severity: int = 1,
        start_ts: Optional[str] = None,
        end_ts: Optional[str] = None,
        limit: int = 100,
        order: str = "DESC",
    ) -> List[sqlite3.Row]:
        """
        Retrieve security events with optional filtering.
        """
        sql = "SELECT * FROM security_events WHERE severity >= ?"
        params: List[Any] = [min_severity]

        if event_type is not None:
            sql += " AND event_type = ?"
            params.append(event_type)
        if start_ts is not None:
            sql += " AND timestamp >= ?"
            params.append(start_ts)
        if end_ts is not None:
            sql += " AND timestamp <= ?"
            params.append(end_ts)

        sql += f" ORDER BY timestamp {order} LIMIT ?"
        params.append(limit)

        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()

    # ------------------------------------------------------------------- #
    # Maintenance helpers
    # ------------------------------------------------------------------- #
    def purge_old_sensor_logs(self, keep_days: int = 30) -> int:
        """
        Delete sensor logs older than *keep_days*.

        Returns
        -------
        int
            Number of rows removed.
        """
        cutoff = (dt.datetime.utcnow() - dt.timedelta(days=keep_days)).replace(microsecond=0).isoformat() + "Z"
        cur = self.conn.cursor()
        cur.execute("DELETE FROM sensor_logs WHERE timestamp < ?", (cutoff,))
        removed = cur.rowcount
        self.conn.commit()
        return removed

    def purge_old_security_events(self, keep_days: int = 90) -> int:
        """
        Delete security events older than *keep_days*.

        Returns
        -------
        int
            Number of rows removed.
        """
        cutoff = (dt.datetime.utcnow() - dt.timedelta(days=keep_days)).replace(microsecond=0).isoformat() + "Z"
        cur = self.conn.cursor()
        cur.execute("DELETE FROM security_events WHERE timestamp < ?", (cutoff,))
        removed = cur.rowcount
        self.conn.commit()
        return removed

    # ------------------------------------------------------------------- #
    # Clean‑up
    # ------------------------------------------------------------------- #
    def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self.conn:
            self.conn.close()
            self.conn = None  # type: ignore

    # Context‑manager support (so you can use `with MonitoringDB() as db:`)
    def __enter__(self) -> "MonitoringDB":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# --------------------------------------------------------------------------- #
# Demo / simple CLI
# --------------------------------------------------------------------------- #
def _demo() -> None:
    """Run a tiny interactive demo when the script is executed directly."""
    print("=== MonitoringDB demo ===")
    with MonitoringDB() as db:
        # Insert a few rows
        print("Inserting sample data …")
        db.insert_sensor_log(sensor_id=1, value=22.7, unit="°C")
        db.insert_sensor_log(sensor_id=2, value=55.1, unit="%")
        db.insert_security_event(event_type="door_open", severity=2, description="Front door opened")
        db.insert_security_event(event_type="alarm", severity=5, description="Fire alarm triggered")

        # Query recent sensor logs
        print("\nLatest sensor logs (limit 5):")
        for row in db.get_sensor_logs(limit=5):
            print(dict(row))

        # Query recent security events
        print("\nRecent security events (limit 5):")
        for row in db.get_security_events(limit=5):
            print(dict(row))

        # Show purge result (won't delete anything in this demo)
        removed_logs = db.purge_old_sensor_logs(keep_days=0)  # 0 days → delete everything older than now
        removed_events = db.purge_old_security_events(keep_days=0)
        print(f"\nPurged {removed_logs} old sensor logs and {removed_events} old security events.")


if __name__ == "__main__":
    _demo()