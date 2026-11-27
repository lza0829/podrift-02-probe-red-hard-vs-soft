from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from app.db import db, write_tx
from app.services.common import now_iso, rows
from app.services import probe_gate

router = APIRouter(tags=["探针灯"])


class ProbePatch(BaseModel):
    color: str
    fail_streak: int | None = None


@router.get("/探针")
def list_probes():
    with db() as conn:
        threshold = probe_gate.load_threshold(conn)
        data = rows(
            conn.execute(
                """
                SELECT pr.*, p.name AS pod_name, p.run_state
                FROM probes pr JOIN pods p ON p.id = pr.pod_id
                ORDER BY pr.pod_id
                """
            )
        )
        for r in data:
            v = probe_gate.evaluate(r, threshold)
            r["阈值"] = threshold
            r["红灯"] = v.blocked
            r["门口径"] = v.label
            r["自洽"] = v.consistent
        return data


@router.post("/探针/{pod_id}")
def set_probe(pod_id: int, body: ProbePatch):
    """改探针与开单走同一把写锁，避免「改探针同时点启动」落成双结局。"""
    with write_tx() as conn:
        pod = conn.execute("SELECT * FROM pods WHERE id=?", (pod_id,)).fetchone()
        if not pod:
            return {"错误": "舱体不存在"}
        streak = body.fail_streak
        if streak is None:
            streak = 0 if body.color == "绿" else 1
        conn.execute(
            "UPDATE probes SET color=?, fail_streak=?, updated_at=? WHERE pod_id=?",
            (body.color, streak, now_iso(), pod_id),
        )
        conn.execute(
            "INSERT INTO events(kind, ref, detail, at) VALUES (?,?,?,?)",
            ("探针", str(pod_id), f"置{body.color}，连击 {streak}", now_iso()),
        )
        v = probe_gate.evaluate(
            conn.execute("SELECT * FROM probes WHERE pod_id=?", (pod_id,)).fetchone(),
            probe_gate.load_threshold(conn),
        )
        return {"ok": True, "探针判定": v.to_dict()}
