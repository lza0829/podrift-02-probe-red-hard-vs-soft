"""夹具三：改探针并发点启动 —— 不得落成双结局。

两个 HTTP 请求真并发：一个置红、一个点启动。串行化写锁保证两种
可接受结局之一，绝不会同时出现「已完成 + 探针红」：

  A) 置红先提交 → 启动读到红 → 硬拒(失败)，舱体不进运行中；
  B) 启动先提交 → 绿放行起成，探针随后置红，但该启动单落库时快照为绿。

关键不变量：启停单若非「已完成」，舱体必不在运行中；若「已完成」，
该单探针快照必为可起(绿)。
"""
from __future__ import annotations

import threading

import httpx

from conftest import pod_state, quota


def _race(client, start_body, probe_body, pod_id):
    barrier = threading.Barrier(2)
    results = {}

    def do_start():
        barrier.wait()
        results["start"] = client.post("/api/启停单", json=start_body).json()

    def do_probe():
        barrier.wait()
        results["probe"] = client.post(f"/api/探针/{pod_id}", json=probe_body).json()

    threads = [threading.Thread(target=do_start), threading.Thread(target=do_probe)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    return results["start"], results["probe"]


def test_concurrent_probe_change_and_start_never_double_outcome(live_server, raw):
    seen_completed = 0
    seen_rejected = 0
    rounds = 0
    max_rounds = 30

    with httpx.Client(base_url=live_server, timeout=10) as client:
        while rounds < max_rounds and not (seen_completed and seen_rejected):
            rounds += 1
            # 复位到"开单前绿 / 已停止"
            client.post("/api/探针/1", json={"color": "绿", "fail_streak": 0})
            client.post("/api/启停单", json={"pod_id": 1, "action": "停止"})

            start, _probe = _race(
                client,
                {"pod_id": 1, "action": "启动"},
                {"color": "红", "fail_streak": 5},
                pod_id=1,
            )

            final_pod = pod_state(raw, 1)

            # 不变量 1：失败单绝不能留下运行中
            if start["status"] != "已完成":
                assert final_pod["run_state"] != "运行中", (
                    f"round {rounds}: 启动失败却留下运行中 {final_pod}"
                )
            else:
                # 不变量 2：已完成单，其落库探针快照必须是可起（绿）
                assert start["gate"] == "探针绿放行"
                assert start["probe"]["blocked"] is False
                assert final_pod["run_state"] == "运行中"

            if start["status"] == "已完成":
                seen_completed += 1
            else:
                seen_rejected += 1

    assert seen_completed > 0 and seen_rejected > 0, (
        f"并发未覆盖两种结局: completed={seen_completed} rejected={seen_rejected}"
    )


def test_concurrent_start_never_double_charges_quota(live_server, raw):
    """同时点两次启动：最多一次成，配额只扣一次。"""
    with httpx.Client(base_url=live_server, timeout=10) as client:
        client.post("/api/探针/1", json={"color": "绿", "fail_streak": 0})
        q0 = quota(raw)

        barrier = threading.Barrier(2)
        outs = []

        def do_start():
            barrier.wait()
            outs.append(client.post("/api/启停单", json={"pod_id": 1, "action": "启动"}).json())

        ts = [threading.Thread(target=do_start) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=15)

    completed = [o for o in outs if o["status"] == "已完成"]
    assert len(completed) == 1, f"应恰有一次起成，实际 {outs}"
    q1 = quota(raw)
    assert abs((q1["cpu_used"] - q0["cpu_used"]) - 0.5) < 1e-9
    assert (q1["mem_used_mb"] - q0["mem_used_mb"]) == 256
    assert pod_state(raw, 1)["run_state"] == "运行中"
