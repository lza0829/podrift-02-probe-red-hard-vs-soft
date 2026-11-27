"""夹具二：红灯挂缺口。

题面另一臂（允许红灯启动并挂探针缺口账）**不实现**。本夹具锁定：
- 只有一套开单前红灯口径（硬拒），不存在缺口账条目；
- 重启策/对读屏/舱规下发的口径字段都是"硬拒"，无选型；
- 红灯启动不会产生任何"可起"记录，也不会出现「缺口」字样被当成成功。
"""
from __future__ import annotations

from conftest import last_order, pod_state


def _no_gap_wording(obj) -> bool:
    """递归确认返回体里没有把红灯记为可核缺口的成功路径。"""
    text = repr(obj)
    # 允许出现"不提供/禁止"这类否定说明，但不能有进行时的"挂缺口"账号字段
    banned = ["缺口账", "挂缺口", "gap_ledger", "缺口票"]
    return not any(b in text for b in banned)


def test_only_one_arm_exposed(client):
    body = client.get("/api/口径").json()
    assert body["开单前红灯口径"]["落臂"] == "开单前探针红必须硬拒启动"
    assert "缺口" not in repr(body["开单前红灯口径"])

    policy = client.get("/api/重启策").json()
    gate = policy["开单前探针门"]
    assert gate["落臂"] == "开单前红灯硬拒启动"
    assert gate["可切换口径"] is False

    align = client.get("/api/对读").json()
    assert align["开单前红灯口径"]["落臂"] == "开单前红灯硬拒启动"


def test_red_start_never_writes_gap_success(client, raw):
    r = client.post("/api/启停单", json={"pod_id": 2, "action": "启动"}).json()
    assert r["status"] == "失败"
    assert r["gate"] == "开单前红灯硬拒"
    assert _no_gap_wording(r)

    o = last_order(raw, 2)
    assert o["status"] != "已完成"
    assert pod_state(raw, 2)["run_state"] != "运行中"
    # 探针快照存在且为红，但没有"缺口"账列
    assert o["probe_color"] == "红"
    assert not any("缺口" in (k or "") for k in o.keys())


def test_no_start_with_ledger_endpoint(client):
    """不存在第二条口径的入口。"""
    paths = client.get("/openapi.json").json()["paths"]
    joined = " ".join(paths.keys())
    assert "缺口" not in joined
    assert all("缺口" not in p for p in paths)


def test_align_never_marks_red_as_success(client):
    client.post("/api/启停单", json={"pod_id": 2, "action": "启动"})
    align = client.get("/api/对读").json()
    row = next(x for x in align["舱体投影"] if x["id"] == 2)
    assert row["last_order_status"] == "失败"
    assert row["当前可起"] is False
    assert row["最近单回放"]["回放"] == "红灯硬拒"
