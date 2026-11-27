"""开单前探针门 —— 全站唯一口径。

落臂：**开单前探针红灯必须硬拒启动**。

- 探针红（色为红，或失败连击达到/超过阈值）→ 启停单整笔失败，
  舱体不得进入「运行中」，配额不得扣减，对读屏该格不得计成功。
- 探针绿 → 放行，允许继续走后续镜像门 / 配额门。
- 红灯判定与启停结果落在**同一笔**启停单行里（探针快照 + 阈值 + 门标签），
  读侧可据此重算「这单当时能不能起」。

本模块不实现「允许开单前红灯启动并挂缺口账」的第二套口径，
界面也不提供选型。只此一套。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

DEFAULT_THRESHOLD = 3
SETTING_KEY = "probe_fail_threshold"

# 门标签，写进 start_orders.gate，读侧与回放都认这一套。
GATE_PROBE_RED = "开单前红灯硬拒"
GATE_PROBE_GREEN = "探针绿放行"
GATE_PROBE_MISSING = "探针缺失"
GATE_IMAGE = "镜像门"
GATE_QUOTA = "配额门"
GATE_STOP = "停止单"


@dataclass(frozen=True)
class Verdict:
    """一次开单前探针判定。所有字段都可序列化、可落库、可重放。"""

    blocked: bool
    color: str | None
    fail_streak: int | None
    threshold: int
    reason: str
    consistent: bool

    @property
    def label(self) -> str:
        if self.blocked:
            return GATE_PROBE_RED if self.color is not None else GATE_PROBE_MISSING
        return GATE_PROBE_GREEN

    def to_dict(self) -> dict:
        d = asdict(self)
        d["label"] = self.label
        d["可起"] = not self.blocked
        return d


def load_threshold(conn) -> int:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (SETTING_KEY,)).fetchone()
    if not row:
        return DEFAULT_THRESHOLD
    try:
        return max(1, int(str(row["value"]).strip()))
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD


def evaluate(probe, threshold: int) -> Verdict:
    """按开单前红灯口径判定。probe 为 probes 行或 None。

    红 = 颜色非绿，或失败连击 >= 阈值。两者都算红；若颜色与连击互相矛盾
    （绿却连击超阈 / 红却零连击），仍按红处理并在 consistent=False 标出，
    避免「口径不一」被当成绿放行。
    """
    if probe is None:
        return Verdict(
            blocked=True,
            color=None,
            fail_streak=None,
            threshold=threshold,
            reason="该舱无探针读数，不得起",
            consistent=False,
        )

    color = probe["color"]
    streak = int(probe["fail_streak"] or 0)
    red_by_color = color != "绿"
    red_by_streak = streak >= threshold
    blocked = red_by_color or red_by_streak

    if blocked:
        if red_by_color and red_by_streak:
            reason = f"探针红灯，失败连击 {streak} ≥ 阈值 {threshold}"
        elif red_by_color:
            reason = f"探针红灯（失败连击 {streak} < 阈值 {threshold}）"
        else:
            reason = f"失败连击 {streak} ≥ 阈值 {threshold}，按红灯计"
    else:
        reason = f"探针绿灯，失败连击 {streak} < 阈值 {threshold}"

    # 颜色与连击一致：绿<=>连击不足阈值。
    consistent = (color == "绿") == (streak < threshold)

    return Verdict(
        blocked=blocked,
        color=color,
        fail_streak=streak,
        threshold=threshold,
        reason=reason,
        consistent=consistent,
    )


def evaluate_for_pod(conn, pod_id: int) -> Verdict:
    probe = conn.execute("SELECT * FROM probes WHERE pod_id=?", (pod_id,)).fetchone()
    return evaluate(probe, load_threshold(conn))


def replay(order: dict) -> dict:
    """从启停单行里记下的探针快照重放「开单前灯能不能起」。

    返回回放判定 + 与落库结果是否自洽。读侧对读屏用它证明
    「红灯不算起成」不是口头承诺，而是可重算的。
    """
    if order.get("action") != "启动":
        return {"回放": "非启动单，不适用开单前探针门", "自洽": True}

    color = order.get("probe_color")
    streak = order.get("probe_fail_streak")
    threshold = order.get("probe_threshold")
    gate = order.get("gate")
    status = order.get("status")

    if color is None or threshold is None:
        return {"回放": "无探针快照，无法重放", "自洽": False}

    probe = {"color": color, "fail_streak": streak or 0}
    verdict = evaluate(probe, int(threshold))
    startable = not verdict.blocked

    # 口径要求：红灯不得算起成。
    if status == "已完成":
        # 记成「起成」的单，回放必须是可起。
        coherent = startable and gate == GATE_PROBE_GREEN
    elif gate == GATE_PROBE_RED:
        # 记成硬拒的单，回放必须不可起。
        coherent = not startable
    else:
        # 其它失败（镜像门 / 配额门）不归探针门判，只要求探针绿放行在先。
        coherent = startable

    return {
        "回放": "可起" if startable else "红灯硬拒",
        "回放探针": verdict.to_dict(),
        "落库门": gate,
        "落库状态": status,
        "自洽": coherent,
        "口径": "开单前红灯不得算起成",
    }
