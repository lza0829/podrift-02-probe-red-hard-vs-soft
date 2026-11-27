from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from app.db import db, write_tx
from app.services.common import now_iso
from app.services import probe_gate

router = APIRouter(tags=["重启策"])


class PolicyIn(BaseModel):
    mode: str
    backoff_sec: int | None = None


@router.get("/重启策")
def get_policy():
    with db() as conn:
        row = conn.execute("SELECT * FROM restart_policy WHERE id=1").fetchone()
        policy = dict(row) if row else {}
        # 全站唯一口径，读侧只读不选。
        policy["开单前探针门"] = {
            "落臂": "开单前红灯硬拒启动",
            "阈值": probe_gate.load_threshold(conn),
            "可改阈值": True,
            "可切换口径": False,
        }
        return policy


@router.post("/重启策")
def set_policy(body: PolicyIn):
    with write_tx() as conn:
        backoff = body.backoff_sec
        if backoff is None:
            cur = conn.execute("SELECT backoff_sec FROM restart_policy WHERE id=1").fetchone()
            backoff = int(cur["backoff_sec"])
        conn.execute(
            "UPDATE restart_policy SET mode=?, backoff_sec=? WHERE id=1",
            (body.mode, backoff),
        )
        conn.execute(
            "INSERT INTO events(kind, ref, detail, at) VALUES (?,?,?,?)",
            ("重启策", "1", f"模式改为 {body.mode}", now_iso()),
        )
        return {"ok": True}
