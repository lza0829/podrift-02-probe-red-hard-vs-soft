import React, { useEffect, useState } from "react";
import { api } from "../api";

export default function Align() {
  const [data, setData] = useState(null);
  const [replay, setReplay] = useState(null);

  const load = () => api.align().then(setData);
  useEffect(() => {
    load();
  }, []);

  const doReplay = (orderId) =>
    api.replayOrder(orderId).then(setReplay);

  if (!data) return null;
  const arm = data["开单前红灯口径"];

  return (
    <>
      <div className="hero">
        <h1>对读屏</h1>
        <p>
          启停结果、探针色、镜像拉取态同屏投影。<strong>{arm["落臂"]}</strong>
          ：开单前红灯不得算起成，口径可重放。
        </p>
      </div>

      <div className="panel arm-note">
        <div>
          <span className="tag bad">唯一口径</span> {arm["说明"]}
        </div>
        <div className="muted">{arm["禁止"]} · 阈值 {arm["阈值"]}</div>
      </div>

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>舱</th>
              <th>运行</th>
              <th>探针</th>
              <th>当前可起</th>
              <th>镜像</th>
              <th>最近启停</th>
              <th>回放</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data["舱体投影"].map((r) => (
              <tr key={r.id}>
                <td>{r.name}</td>
                <td>
                  <span className={`tag ${r.run_state === "运行中" ? "ok" : "warn"}`}>
                    {r.run_state}
                  </span>
                </td>
                <td>
                  <span className={`tag ${r.probe_color === "绿" ? "ok" : "bad"}`}>
                    {r.probe_color} · {r.fail_streak}
                  </span>
                </td>
                <td>
                  <span className={`tag ${r["当前可起"] ? "ok" : "bad"}`}>
                    {r["当前可起"] ? "可起" : "红灯硬拒"}
                  </span>
                </td>
                <td>{r.pull_state || "—"}</td>
                <td>
                  <span className={`tag ${r.last_order_status === "已完成" ? "ok" : r.last_order_status === "失败" ? "bad" : "warn"}`}>
                    {r.last_order_status || "—"}
                  </span>{" "}
                  {r.last_order_gate || ""} {r.last_order_note || ""}
                </td>
                <td>
                  {r["最近单回放"] ? (
                    <span className={`tag ${r["最近单自洽"] ? "ok" : "bad"}`}>
                      {r["最近单回放"]["回放"]} · {r["最近单自洽"] ? "自洽" : "不自洽"}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  {r.last_order_id && (
                    <button className="btn" onClick={() => doReplay(r.last_order_id)}>
                      重放
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {replay && (
        <div className="panel replay-box">
          <h3>启停单 #{replay["启停单"].id} 回放</h3>
          <pre>{JSON.stringify(replay["回放"], null, 2)}</pre>
        </div>
      )}
    </>
  );
}
