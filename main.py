#!/usr/bin/env python3
"""
main.py – Local‑first SQLite storage with a weekly cloud sync.

Features
--------
* Simple SQLite schema (id, name, value, created_at, updated_at)
* CRUD helpers with type hints and doc‑strings
* Automatic weekly sync using APScheduler (runs in background thread)
* Conflict resolution – the row with the newest ``updated_at`` wins
* Structured logging (JSON‑compatible)
* Configurable via environment variables or a ``.env`` file

Dependencies
------------
* python‑dotenv
* requests
* APScheduler
* pydantic (optional – used for data validation)

Install with:
    pip install -r requirements.txt

Author:  Your Name <you@example.com>
License: MIT
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
#                               CONFIGURATION                               #
# --------------------------------------------------------------------------- #

# Load .env if present – makes local development easy
load_dotenv()

# ── SQLite ────────────────────────────────────────────────────────────────
DB_PATH: Path = Path(os.getenv("LOCAL_DB_PATH", "local_data.db"))

# ── Cloud API ──────────────────────────────────────────────────────────────
CLOUD_BASE_URL: str = os.getenv(
    "CLOUD_BASE_URL", "https://example.com/api/sync"
)  # <-- replace with your real endpoint
CLOUD_API_TOKEN: str = os.getenv("CLOUD_API_TOKEN", "")

# ── Scheduler ───────────────────────────────────────────────────────────────
# Cron expression for “once a week, Sunday at 02:30 UTC”.  Adjust as needed.
WEEKLY_CRON = os.getenv("WEEKLY_CRON", "30 2 * * 0")  # minute hour * * day_of_week

# ── Logging ────────────────────────────────────────────────────────────────
LOG_LEVEL = logging.DEBUG if os.getenv("DEBUG", "0") == "1" else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S%z",
    stream=sys.stdout,
)
logger = logging.getLogger("local‑cloud‑sync")
# --- Master Switch (ON/OFF) ---
SYSTEM_ENABLED: bool = os.getenv("SYSTEM_ENABLED", "false").lower() == "true"

# --------------------------------------------------------------------------- #
#                               DATA MODEL                                    #
# --------------------------------------------------------------------------- #


class Row(NamedTuple):
    """Immutable representation of a table row."""

    id: int
    name: str
    value: str
    created_at: str  # ISO‑8601 UTC
    updated_at: str  # ISO‑8601 UTC

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Row":
        return Row(
            id=int(data["id"]),
            name=str(data["name"]),
            value=str(data["value"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "value": self.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# --------------------------------------------------------------------------- #
#                               DATABASE HELPERS                               #
# --------------------------------------------------------------------------- #


def _get_connection() -> sqlite3.Connection:
    """Return a thread‑local SQLite connection (autocommit mode)."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Create the table if it does not exist."""
    logger.debug("Initialising SQLite database at %s", DB_PATH)
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                value       TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            """
        )
        conn.commit()
    logger.info("Database ready.")


def _now_iso() -> str:
    """Current UTC time as ISO‑8601 string (e.g. 2026-10-04T12:34:56Z)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def add_item(name: str, value: str) -> Row:
    """Insert a new row and return the created ``Row``."""
    now = _now_iso()
    with _get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO items (name, value, created_at, updated_at)
            VALUES (?, ?, ?, ?);
            """,
            (name, value, now, now),
        )
        row_id = cur.lastrowid
        conn.commit()
    logger.info("Added item %s (id=%s)", name, row_id)
    return Row(id=row_id, name=name, value=value, created_at=now, updated_at=now)


def update_item(item_id: int, name: Optional[str] = None, value: Optional[str] = None) -> Row:
    """Update ``name`` and/or ``value`` of an existing row."""
    now = _now_iso()
    with _get_connection() as conn:
        # fetch current row for logging / return
        cur = conn.execute("SELECT * FROM items WHERE id = ?;", (item_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Item with id={item_id} does not exist")

        new_name = name if name is not None else row["name"]
        new_value = value if value is not None else row["value"]

        conn.execute(
            """
            UPDATE items
            SET name = ?, value = ?, updated_at = ?
            WHERE id = ?;
            """,
            (new_name, new_value, now, item_id),
        )
        conn.commit()
    logger.info("Updated item id=%s", item_id)
    return Row(
        id=item_id,
        name=new_name,
        value=new_value,
        created_at=row["created_at"],
        updated_at=now,
    )


def delete_item(item_id: int) -> None:
    """Delete a row by its primary key."""
    with _get_connection() as conn:
        conn.execute("DELETE FROM items WHERE id = ?;", (item_id,))
        conn.commit()
    logger.info("Deleted item id=%s", item_id)


def get_all_items() -> List[Row]:
    """Return every row in the table as a list of ``Row`` objects."""
    with _get_connection() as conn:
        cur = conn.execute("SELECT * FROM items;")
        rows = [Row.from_dict(dict(r)) for r in cur.fetchall()]
    logger.debug("Fetched %d rows from local DB", len(rows))
    return rows


def upsert_item(row: Row) -> None:
    """
    Insert the row if it does not exist, otherwise update it.
    Conflict resolution: keep the version with the newer ``updated_at``.
    """
    with _get_connection() as conn:
        cur = conn.execute("SELECT updated_at FROM items WHERE id = ?;", (row.id,))
        existing = cur.fetchone()
        if existing:
            # Compare timestamps (ISO‑8601 strings compare lexicographically)
            if row.updated_at > existing["updated_at"]:
                conn.execute(
                    """
                    UPDATE items
                    SET name = ?, value = ?, created_at = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (row.name, row.value, row.created_at, row.updated_at, row.id),
                )
                logger.debug("Upsert: updated existing row id=%s", row.id)
            else:
                logger.debug(
                    "Upsert: local row id=%s is newer – no change", row.id
                )
        else:
            conn.execute(
                """
                INSERT INTO items (id, name, value, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (row.id, row.name, row.value, row.created_at, row.updated_at),
            )
            logger.debug("Upsert: inserted new row id=%s", row.id)
        conn.commit()


# --------------------------------------------------------------------------- #
#                               CLOUD SYNC LOGIC                               #
# --------------------------------------------------------------------------- #


def _cloud_headers() -> Dict[str, str]:
    """Common HTTP headers for the cloud API."""
    headers = {"Content-Type": "application/json"}
    if CLOUD_API_TOKEN:
        headers["Authorization"] = f"Bearer {CLOUD_API_TOKEN}"
    return headers


def upload_to_cloud(rows: Iterable[Row]) -> None:
    """
    Push local rows to the remote service.

    The remote endpoint should accept a JSON body like:
        {"items": [ {row_dict}, … ]}

    Raises
    ------
    requests.HTTPError if the request fails.
    """
    url = f"{CLOUD_BASE_URL.rstrip('/')}/upload"
    payload = {"items": [r.to_dict() for r in rows]}
    logger.info("Uploading %d rows to %s", len(payload["items"]), url)

    response = requests.post(url, headers=_cloud_headers(), json=payload, timeout=30)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        logger.error("Upload failed: %s – %s", exc, response.text)
        raise
    logger.info("Upload successful (status %s)", response.status_code)


def download_from_cloud() -> List[Row]:
    """
    Pull the full dataset from the remote service.

    Expected response JSON:
        {"items": [ {row_dict}, … ]}

    Returns
    -------
    List[Row] – rows received from the cloud.
    """
    url = f"{CLOUD_BASE_URL.rstrip('/')}/download"
    logger.info("Downloading rows from %s", url)

    response = requests.get(url, headers=_cloud_headers(), timeout=30)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        logger.error("Download failed: %s – %s", exc, response.text)
        raise

    data = response.json()
    items = data.get("items", [])
    rows = [Row.from_dict(item) for item in items]
    logger.info("Downloaded %d rows from cloud", len(rows))
    return rows


def sync_once() -> None:
    """
    Perform a **full** bi‑directional sync:

    1. Upload all local rows.
    2. Download the remote rows.
    3. Upsert each remote row into the local DB (newer wins).

    The function is safe to call repeatedly – it will not create duplicates.
    """
    logger.info("=== Starting weekly sync ===")
    try:
        local_rows = get_all_items()
        upload_to_cloud(local_rows)

        remote_rows = download_from_cloud()
        for remote in remote_rows:
            upsert_item(remote)

        logger.info("=== Sync completed successfully ===")
    except Exception as exc:  # pragma: no cover – top‑level guard
        logger.exception("Sync failed: %s", exc)


# --------------------------------------------------------------------------- #
#                               SCHEDULER SETUP                               #
# --------------------------------------------------------------------------- #


def _parse_cron(cron_expr: str) -> CronTrigger:
    """
    Convert a classic 5‑field cron string (minute hour dom month dow)
    into an APScheduler ``CronTrigger``.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr!r}")
    minute, hour, day, month, dow = parts
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=dow,
        timezone=timezone.utc,
    )


def start_scheduler() -> BackgroundScheduler:
    """
    Initialise a background scheduler that runs ``sync_once`` according to
    ``WEEKLY_CRON``.  The scheduler runs in a daemon thread, so the process can
    exit cleanly when the main thread finishes.
    """
    scheduler = BackgroundScheduler()
    trigger = _parse_cron(WEEKLY_CRON)
