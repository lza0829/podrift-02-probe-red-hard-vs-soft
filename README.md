# 舱隙 podrift — 开单前探针红灯口径

## 落臂（全站唯一）

**开单前探针红 → 启停整笔硬拒启动。**

- 探针红 = 颜色非绿，**或** 失败连击 ≥ 阈值（`probe_fail_threshold`，默认 3）。两者矛盾时按红处理。
- 红灯启动：整笔失败；舱体**不得**进入「运行中」；配额**不**扣减；对读屏该格**不**计成功。
- 每条启停单与判定的探针快照（色 / 连击 / 阈值 / 门）**同笔**落库，读侧可重算「这单当时能不能起」。
- 启动失败若遇半截「启动中」脏态，同笔**退回点启动前快照**（已停止）。
- 不实现「允许红灯启动并挂探针缺口账」的第二套口径，界面**不弹选型**。

边界：只管**开单前**红灯能不能起。已运行后再红、镜像未就绪另立。

## 一致性保证

- 写路径统一 `BEGIN IMMEDIATE` 串行化（`app/db.py:write_tx`）。改探针与开单互斥，
  并发只可能落成「先红后拒」或「先起后红」，绝无双结局、绝不双扣配额。
- 当前状态每次由探针行 + 阈值实时重算，不在库里存互斥标志位。

## 主要端点

| 端点 | 说明 |
| --- | --- |
| `POST /api/启停单` | 一笔事务内：探针门 → 镜像门 → 配额门 → 落单 |
| `GET /api/探针` | 探针灯，附阈值、红灯判定、自洽 |
| `GET /api/对读` | 对读屏，附「当前可起」与最近单回放自洽 |
| `GET /api/对读/回放/{id}` | 按单内探针快照重放判定 |
| `GET /api/口径` | 只读口径说明（无选型） |

## 夹具（四类必备场景）

```
cd backend && pytest tests -q
```

- `test_probe_red_reject.py` — 开单前红灯拒启动（含按连击判红、阈值可调）
- `test_red_gap_not_implemented.py` — 红灯挂缺口**不实现**，只此一套口径
- `test_concurrent_probe_start.py` — 改探针并发点启动、并发双启动不双扣
- `test_dirty_pending_rollback.py` — 半截脏启动中回滚到点启动前快照

## 本地运行

```bash
# 后端
cd backend && python -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt pytest httpx
PODRIFT_DB=/tmp/podrift.db ../.venv/bin/uvicorn app.main:app --port 12100
# 前端
cd frontend && npm install && npm run dev   # 端口 7100，代理 /api → 12100
```
