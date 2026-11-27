from __future__ import annotations
import importlib
import sys

import pytest


def _purge_app_modules() -> None:
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    p = tmp_path / "podrift.db"
    monkeypatch.setenv("PODRIFT_DB", str(p))
    _purge_app_modules()
    return p


@pytest.fixture()
def client(db_path):
    from fastapi.testclient import TestClient
    main = importlib.import_module("app.main")
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def raw(db_path):
    """Direct sqlite access for asserting committed state (point-in-time)."""
    import sqlite3

    def _connect():
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    return _connect


def pod_state(raw, pod_id):
    conn = raw()
    try:
        return dict(conn.execute("SELECT * FROM pods WHERE id=?", (pod_id,)).fetchone())
    finally:
        conn.close()


def quota(raw):
    conn = raw()
    try:
        return dict(conn.execute("SELECT * FROM quotas WHERE id=1").fetchone())
    finally:
        conn.close()


def last_order(raw, pod_id):
    conn = raw()
    try:
        row = conn.execute(
            "SELECT * FROM start_orders WHERE pod_id=? ORDER BY id DESC LIMIT 1", (pod_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_pod_dirty(raw, pod_id, state="启动中"):
    conn = raw()
    try:
        conn.execute("UPDATE pods SET run_state=? WHERE id=?", (state, pod_id))
        conn.commit()
    finally:
        conn.close()


def all_orders(raw, pod_id):
    conn = raw()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM start_orders WHERE pod_id=? ORDER BY id", (pod_id,)
            ).fetchall()
        ]
    finally:
        conn.close()


@pytest.fixture()
def live_server(db_path):
    """Real uvicorn server in a thread — needed for genuine concurrent requests."""
    import socket
    import threading
    import time

    import uvicorn

    _purge_app_modules()
    main = importlib.import_module("app.main")

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    config = uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("uvicorn failed to start")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)
