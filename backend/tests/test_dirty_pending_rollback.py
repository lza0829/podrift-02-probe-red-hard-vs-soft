"""夹具四：半截脏启动中回滚。

若舱体卡在「启动中」（上一次启动未走完就中断留下的脏态），
下一次启动被探针门硬拒 / 被镜像门拒绝时，必须退回点启动前快照
（已停止），不得把半截「启动中」永久留在库里。
"""
from __future__ import annotations

from conftest import last_order, pod_state, quota, set_pod_dirty


def test_dirty_pending_rolled_back_on_red_reject(client, raw):
    set_pod_dirty(raw, 2, "启动中")       # worker-b 探针红
    q0 = quota(raw)

    r = client.post("/api/启停单", json={"pod_id": 2, "action": "启动"}).json()

    assert r["status"] == "失败"
    assert r["gate"] == "开单前红灯硬拒"
    assert pod_state(raw, 2)["run_state"] == "已停止", "半截启动中必须退回快照"

    o = last_order(raw, 2)
    assert o["prev_run_state"] == "已停止"
    assert quota(raw) == q0, "回滚不得动配额"


def test_dirty_pending_rolled_back_on_image_reject(client, raw):
    set_pod_dirty(raw, 2, "启动中")
    client.post("/api/探针/2", json={"color": "绿", "fail_streak": 0})
    # worker-b 镜像仍是"拉取中"
    r = client.post("/api/启停单", json={"pod_id": 2, "action": "启动"}).json()
    assert r["status"] == "失败"
    assert r["gate"] == "镜像门"
    assert pod_state(raw, 2)["run_state"] == "已停止"


def test_dirty_pending_rolled_back_on_quota_reject(client, raw):
    # 把显存/CPU 拉到极限，让 web-a 启动必撞配额门
    client.post("/api/舱规", json={"key": "probe_fail_threshold", "value": "3"})
    # 直接改配额上限到已用，制造不足
    conn = raw()
    try:
        conn.execute("UPDATE quotas SET cpu_limit=cpu_used, mem_limit_mb=mem_used_mb WHERE id=1")
        conn.commit()
    finally:
        conn.close()
    set_pod_dirty(raw, 1, "启动中")

    r = client.post("/api/启停单", json={"pod_id": 1, "action": "启动"}).json()
    assert r["status"] == "失败"
    assert r["gate"] == "配额门"
    assert pod_state(raw, 1)["run_state"] == "已停止"


def test_dirty_pending_then_green_start_completes(client, raw):
    """脏启动中若探针绿、镜像就绪、配额足，则应正常起成，落运行中。"""
    set_pod_dirty(raw, 1, "启动中")
    r = client.post("/api/启停单", json={"pod_id": 1, "action": "启动"}).json()
    assert r["status"] == "已完成"
    assert pod_state(raw, 1)["run_state"] == "运行中"


def test_stop_clears_dirty_pending(client, raw):
    set_pod_dirty(raw, 2, "启动中")
    r = client.post("/api/启停单", json={"pod_id": 2, "action": "停止"}).json()
    assert r["status"] == "已完成"
    assert pod_state(raw, 2)["run_state"] == "已停止"
