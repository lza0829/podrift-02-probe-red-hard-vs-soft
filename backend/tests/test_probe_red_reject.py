"""夹具一：开单前红灯拒启动。

红灯哨舱在开单前探针红 → 启动整笔失败，舱体不进运行中，配额不动，
对读屏该格不得计成功，且落库单行带探针快照可重放。
"""
from __future__ import annotations

from conftest import pod_state, quota, last_order


def test_red_probe_hard_rejects_start(client, raw):
    before = pod_state(raw, 2)          # worker-b: 种子为红 / 连击 3 / 阈值 3
    q_before = quota(raw)
    assert before["run_state"] == "已停止"

    r = client.post("/api/启停单", json={"pod_id": 2, "action": "启动"}).json()

    assert r["status"] == "失败"
    assert r["gate"] == "开单前红灯硬拒"
    assert "红" in r["note"]

    after = pod_state(raw, 2)
    assert after["run_state"] == "已停止", "红灯不得把舱体推进运行中"

    q_after = quota(raw)
    assert q_after["cpu_used"] == q_before["cpu_used"]
    assert q_after["mem_used_mb"] == q_before["mem_used_mb"], "硬拒不得扣配额"

    # 同笔快照：这单当时看到的探针色/连击/阈值/门
    o = last_order(raw, 2)
    assert o["status"] == "失败"
    assert o["probe_color"] == "红"
    assert o["probe_fail_streak"] == 3
    assert o["probe_threshold"] == 3
    assert o["gate"] == "开单前红灯硬拒"

    # 对读屏：不得计成功，且回放自洽
    align = client.get("/api/对读").json()
    row = next(x for x in align["舱体投影"] if x["id"] == 2)
    assert row["last_order_status"] == "失败"
    assert row["当前可起"] is False
    assert row["最近单回放"]["回放"] == "红灯硬拒"
    assert row["最近单自洽"] is True


def test_red_by_streak_even_if_color_green(client, raw):
    """口径不一也按红：绿灯但连击达阈值，仍硬拒。"""
    client.post("/api/探针/1", json={"color": "绿", "fail_streak": 3})
    r = client.post("/api/启停单", json={"pod_id": 1, "action": "启动"}).json()
    assert r["status"] == "失败"
    assert r["gate"] == "开单前红灯硬拒"
    assert pod_state(raw, 1)["run_state"] == "已停止"


def test_green_probe_allows_start_then_red_rejects_next(client, raw):
    """先绿起成，再置红后下一次启动被拒 —— 只判开单前那一刻。"""
    r1 = client.post("/api/启停单", json={"pod_id": 1, "action": "启动"}).json()
    assert r1["status"] == "已完成"
    assert pod_state(raw, 1)["run_state"] == "运行中"

    client.post("/api/探针/1", json={"color": "红", "fail_streak": 4})
    r2 = client.post("/api/启停单", json={"pod_id": 1, "action": "启动"}).json()
    assert r2["status"] == "失败"
    assert r2["gate"] == "开单前红灯硬拒"
    # 已在运行中的舱体，再点启动被探针门拒绝时不得被动停机
    assert pod_state(raw, 1)["run_state"] == "运行中"


def test_threshold_setting_is_single_source(client, raw):
    """阈值来自舱规，调高后原先的连击不再算红。"""
    client.post("/api/舱规", json={"key": "probe_fail_threshold", "value": "5"})
    client.post("/api/探针/2", json={"color": "绿", "fail_streak": 4})
    r = client.post("/api/启停单", json={"pod_id": 2, "action": "启动"}).json()
    # worker-b 镜像是"拉取中"，探针门已放行 → 应被镜像门拦，而不是探针门
    assert r["gate"] == "镜像门"
    assert r["status"] == "失败"
