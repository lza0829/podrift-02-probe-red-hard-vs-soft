from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from app.db import db, write_tx
from app.services.common import now_iso, row_dict, rows
from app.services import probe_gate
from app.config import PROJECT_NAME

router = APIRouter(tags=["舱规"])


class SettingIn(BaseModel):
    key: str
    value: str


@router.get("/舱规")
def list_settings():
    with db() as conn:
        data = rows(conn.execute("SELECT * FROM settings ORDER BY key"))
        if not any(s["key"] == probe_gate.SETTING_KEY for s in data):
            data.append({"key": probe_gate.SETTING_KEY, "value": str(probe_gate.DEFAULT_THRESHOLD)})
        return data


@router.post("/舱规")
def set_setting(body: SettingIn):
    with write_tx() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (body.key, body.value),
        )
        conn.execute(
            "INSERT INTO events(kind, ref, detail, at) VALUES (?,?,?,?)",
            ("舱规", body.key, f"改为 {body.value}", now_iso()),
        )
        return {"ok": True}


@router.get("/事件")
def list_events():
    with db() as conn:
        return rows(conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT 80"))


@router.get("/口径")
def describe_arm():
    """全站开单前红灯口径，只读。界面不得弹选型。"""
    with db() as conn:
        threshold = probe_gate.load_threshold(conn)
    return {
        "产品": PROJECT_NAME,
        "开单前红灯口径": {
            "落臂": "开单前探针红必须硬拒启动",
            "探针红": "色为红，或失败连击达到阈值",
            "启动": "整笔失败；舱体不得进运行中；对读屏该格不得计成功",
            "回滚": "启动失败退回点启动前快照，不留在半截启动中",
            "可重放": "每单记探针色/连击/阈值/门，读侧可重算能不能起",
            "阈值": threshold,
        },
        "另行立项": ["已运行后再红", "镜像未就绪"],
    }
