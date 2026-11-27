from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from app.db import db, write_tx
from app.services.common import now_iso, rows
from app.services import probe_gate

router = APIRouter(tags=["启停单"])

RUNNING = "运行中"
STOPPED = "已停止"
PENDING = "启动中"  # 半截脏态：一次启动未走完就中断会留下它


class OrderIn(BaseModel):
    pod_id: int
    action: str  # 启动 | 停止
    target_image_id: int | None = None


def _norm_action(action: str) -> str:
    a = (action or "").strip()
    if a in ("启动", "start", "Start"):
        return "启动"
    if a in ("停止", "stop", "Stop"):
        return "停止"
    return a


@router.get("/启停单")
def list_orders():
    with db() as conn:
        return rows(conn.execute("SELECT * FROM start_orders ORDER BY id DESC"))


@router.post("/启停单")
def create_order(body: OrderIn):
    """一次启停 = 一笔串行化写事务。

    探针判定、舱体状态、配额扣减、启停单落库全部在同一 BEGIN IMMEDIATE
    里完成：要么整笔成，要么整笔退回点启动前快照。读侧永远不会看到
    「已完成 / 舱体运行中 / 探针全红」这种自相矛盾的中间态。
    """
    with write_tx() as conn:
        pod = conn.execute("SELECT * FROM pods WHERE id=?", (body.pod_id,)).fetchone()
        if not pod:
            return {"错误": "舱体不存在"}

        action = _norm_action(body.action)
        img_id = body.target_image_id or pod["image_id"]
        prev_run_state = pod["run_state"]
        threshold = probe_gate.load_threshold(conn)

        result = {
            "id": None,
            "status": "失败",
            "note": "",
            "gate": None,
            "prev_run_state": prev_run_state,
            "probe": None,
        }

        if action == "启动":
            verdict = probe_gate.evaluate(
                conn.execute("SELECT * FROM probes WHERE pod_id=?", (body.pod_id,)).fetchone(),
                threshold,
            )
            result["probe"] = verdict.to_dict()

            if verdict.blocked:
                # 开单前红灯 → 硬拒。整笔失败；若舱体正卡在半截「启动中」，
                # 同笔退回点启动前快照，绝不留下半截启动中。
                if prev_run_state == PENDING:
                    conn.execute("UPDATE pods SET run_state=? WHERE id=?", (STOPPED, body.pod_id))
                    result["prev_run_state"] = STOPPED
                result["status"] = "失败"
                result["note"] = f"开单前探针红灯，拒绝启动：{verdict.reason}"
                result["gate"] = verdict.label
            else:
                img = conn.execute("SELECT * FROM images WHERE id=?", (img_id,)).fetchone()
                q = conn.execute("SELECT * FROM quotas WHERE id=1").fetchone()
                need_cpu = float(pod["cpu_quota"])
                need_mem = int(pod["mem_quota_mb"])

                if not img or img["pull_state"] != "已就绪":
                    result["status"] = "失败"
                    result["note"] = "镜像未就绪"
                    result["gate"] = probe_gate.GATE_IMAGE
                elif float(q["cpu_used"]) + need_cpu > float(q["cpu_limit"]) or int(
                    q["mem_used_mb"]
                ) + need_mem > int(q["mem_limit_mb"]):
                    result["status"] = "失败"
                    result["note"] = "配额不足"
                    result["gate"] = probe_gate.GATE_QUOTA
                elif prev_run_state == RUNNING:
                    # 已在运行再点启动：不重复扣配额，也不假装起成。
                    result["status"] = "失败"
                    result["note"] = "舱体已在运行中"
                    result["gate"] = probe_gate.GATE_PROBE_GREEN
                else:
                    conn.execute(
                        "UPDATE pods SET run_state=?, image_id=? WHERE id=?",
                        (RUNNING, img_id, body.pod_id),
                    )
                    conn.execute(
                        "UPDATE quotas SET cpu_used=cpu_used+?, mem_used_mb=mem_used_mb+? WHERE id=1",
                        (need_cpu, need_mem),
                    )
                    result["status"] = "已完成"
                    result["note"] = "启动成功"
                    result["gate"] = probe_gate.GATE_PROBE_GREEN

                # 任何启动失败都把半截「启动中」退回点启动前快照。
                if result["status"] == "失败" and prev_run_state == PENDING:
                    conn.execute("UPDATE pods SET run_state=? WHERE id=?", (STOPPED, body.pod_id))
                    result["prev_run_state"] = STOPPED

            # 探针快照与判定同笔落库
            snap_color = verdict.color
            snap_streak = verdict.fail_streak
            snap_threshold = verdict.threshold
            gate = result["gate"]

        elif action == "停止":
            if prev_run_state in (RUNNING, PENDING):
                conn.execute("UPDATE pods SET run_state=? WHERE id=?", (STOPPED, body.pod_id))
                if prev_run_state == RUNNING:
                    conn.execute(
                        "UPDATE quotas SET cpu_used=MAX(0, cpu_used-?), mem_used_mb=MAX(0, mem_used_mb-?) WHERE id=1",
                        (float(pod["cpu_quota"]), int(pod["mem_quota_mb"])),
                    )
            result["status"] = "已完成"
            result["note"] = "停止成功"
            result["gate"] = probe_gate.GATE_STOP
            # 停止单不适用开单前探针门，快照留空
            snap_color = None
            snap_streak = None
            snap_threshold = threshold
            gate = result["gate"]

        else:
            result["status"] = "失败"
            result["note"] = f"未知动作:{action}"
            result["gate"] = None
            snap_color = None
            snap_streak = None
            snap_threshold = threshold
            gate = None

        cur = conn.execute(
            """INSERT INTO start_orders
               (pod_id, action, target_image_id, status, note, created_at,
                probe_color, probe_fail_streak, probe_threshold, gate, prev_run_state)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                body.pod_id,
                action,
                img_id,
                result["status"],
                result["note"],
                now_iso(),
                snap_color,
                snap_streak,
                snap_threshold,
                gate,
                result["prev_run_state"],
            ),
        )
        result["id"] = cur.lastrowid
        conn.execute(
            "INSERT INTO events(kind, ref, detail, at) VALUES (?,?,?,?)",
            (
                "启停单",
                str(cur.lastrowid),
                f"{action} → {result['status']} {result['note']}",
                now_iso(),
            ),
        )
        return result
