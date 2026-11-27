from __future__ import annotations
from fastapi import APIRouter
from app.db import db
from app.services.common import rows
from app.services import probe_gate

router = APIRouter(tags=["对读屏"])


@router.get("/对读")
def align_view():
    with db() as conn:
        threshold = probe_gate.load_threshold(conn)
        pods = rows(
            conn.execute(
                """
                SELECT p.id, p.name, p.run_state, pr.color AS probe_color, pr.fail_streak,
                       i.pull_state, o.id AS last_order_id, o.action AS last_order_action,
                       o.status AS last_order_status, o.note AS last_order_note,
                       o.gate AS last_order_gate, o.probe_color AS order_probe_color,
                       o.probe_fail_streak AS order_probe_fail_streak,
                       o.probe_threshold AS order_probe_threshold, o.prev_run_state
                FROM pods p
                LEFT JOIN probes pr ON pr.pod_id = p.id
                LEFT JOIN images i ON i.id = p.image_id
                LEFT JOIN start_orders o ON o.id = (
                  SELECT MAX(id) FROM start_orders WHERE pod_id = p.id
                )
                ORDER BY p.id
                """
            )
        )
        for r in pods:
            # 当前探针能否开单（读侧实时口径）
            v = probe_gate.evaluate(
                {"color": r["probe_color"], "fail_streak": r["fail_streak"]}
                if r["probe_color"] is not None
                else None,
                threshold,
            )
            r["当前可起"] = not v.blocked
            r["当前门"] = v.label
            r["当前探针自洽"] = v.consistent

            # 最近一单是否与「红灯不算起成」口径自洽（可重放）
            if r["last_order_id"] is not None:
                replay = probe_gate.replay(
                    {
                        "action": r["last_order_action"],
                        "status": r["last_order_status"],
                        "gate": r["last_order_gate"],
                        "probe_color": r["order_probe_color"],
                        "probe_fail_streak": r["order_probe_fail_streak"],
                        "probe_threshold": r["order_probe_threshold"],
                    }
                )
                r["最近单回放"] = replay
                r["最近单自洽"] = replay["自洽"]
            else:
                r["最近单回放"] = None
                r["最近单自洽"] = True

        quota = dict(conn.execute("SELECT * FROM quotas WHERE id=1").fetchone())
        policy = dict(conn.execute("SELECT * FROM restart_policy WHERE id=1").fetchone())
        return {
            "舱体投影": pods,
            "配额": quota,
            "重启策": policy,
            "开单前红灯口径": {
                "落臂": "开单前红灯硬拒启动",
                "阈值": threshold,
                "说明": "开单前探针红 → 启停整笔失败，舱体不得进运行中；红灯不得算起成，可重放。",
                "禁止": "不提供『允许红灯启动并挂缺口账』口径，界面无选型。",
            },
        }


@router.get("/对读/回放/{order_id}")
def replay_order(order_id: int):
    """按启停单行里的探针快照重算：这单当时能不能起。"""
    with db() as conn:
        row = conn.execute("SELECT * FROM start_orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return {"错误": "启停单不存在"}
        return {"启停单": dict(row), "回放": probe_gate.replay(dict(row))}
