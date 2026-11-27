from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from app.config import DB_PATH


def connect() -> sqlite3.Connection:
    # isolation_level=None => autocommit; we manage explicit BEGIN/COMMIT below
    # so a whole 启停 can be one atomic unit and readers never see a half-start.
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def _tx(immediate: bool):
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def db():
    """Deferred transaction, for reads and simple single-statement writes."""
    return _tx(immediate=False)


def write_tx():
    """Serialized write transaction.

    Takes the SQLite write lock up front (BEGIN IMMEDIATE) so that mutating the
    probe light and submitting a 启停单 cannot interleave into two conflicting
    outcomes. Whichever commits first wins; the other re-reads committed state.
    """
    return _tx(immediate=True)


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS images (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          tag TEXT NOT NULL,
          pull_state TEXT NOT NULL,
          layers_done INTEGER NOT NULL DEFAULT 0,
          layers_total INTEGER NOT NULL DEFAULT 4,
          ready_at TEXT
        );
        CREATE TABLE IF NOT EXISTS pods (
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          image_id INTEGER,
          run_state TEXT NOT NULL,
          sidecar TEXT,
          cpu_quota REAL NOT NULL DEFAULT 1.0,
          mem_quota_mb INTEGER NOT NULL DEFAULT 512,
          FOREIGN KEY(image_id) REFERENCES images(id)
        );
        CREATE TABLE IF NOT EXISTS start_orders (
          id INTEGER PRIMARY KEY,
          pod_id INTEGER NOT NULL,
          action TEXT NOT NULL,
          target_image_id INTEGER,
          status TEXT NOT NULL,
          note TEXT,
          created_at TEXT NOT NULL,
          probe_color TEXT,
          probe_fail_streak INTEGER,
          probe_threshold INTEGER,
          gate TEXT,
          prev_run_state TEXT,
          FOREIGN KEY(pod_id) REFERENCES pods(id)
        );
        CREATE TABLE IF NOT EXISTS probes (
          id INTEGER PRIMARY KEY,
          pod_id INTEGER NOT NULL UNIQUE,
          color TEXT NOT NULL,
          fail_streak INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT,
          FOREIGN KEY(pod_id) REFERENCES pods(id)
        );
        CREATE TABLE IF NOT EXISTS quotas (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          cpu_used REAL NOT NULL,
          cpu_limit REAL NOT NULL,
          mem_used_mb INTEGER NOT NULL,
          mem_limit_mb INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS restart_policy (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          mode TEXT NOT NULL,
          backoff_sec INTEGER NOT NULL DEFAULT 5
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY,
          kind TEXT NOT NULL,
          ref TEXT,
          detail TEXT NOT NULL,
          at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )
    _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Add probe-gate audit columns to databases created before the arm landed."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(start_orders)").fetchall()}
    additions = {
        "probe_color": "TEXT",
        "probe_fail_streak": "INTEGER",
        "probe_threshold": "INTEGER",
        "gate": "TEXT",
        "prev_run_state": "TEXT",
    }
    for name, ddl in additions.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE start_orders ADD COLUMN {name} {ddl}")
