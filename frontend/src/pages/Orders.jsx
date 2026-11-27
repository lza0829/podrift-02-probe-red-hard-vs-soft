import React, { useEffect, useState } from "react";
import { api } from "../api";

const statusClass = (s) =>
  s === "已完成" ? "ok" : s === "失败" ? "bad" : "warn";

export default function Orders() {
  const [pods, setPods] = useState([]);
  const [orders, setOrders] = useState([]);
  const [flash, setFlash] = useState(null);

  const load = () =>
    Promise.all([api.pods(), api.orders()]).then(([p, o]) => {
      setPods(p);
      setOrders(o);
    });

  useEffect(() => {
    load();
  }, []);

  const act = (podId, action) =>
    api.createOrder({ pod_id: podId, action }).then((r) => {
      if (action === "启动" && r.status === "失败") {
        setFlash({
          kind: r.gate === "开单前红灯硬拒" ? "bad" : "warn",
          text:
            r.gate === "开单前红灯硬拒"
              ? `开单前红灯硬拒：${r.note}（舱体保持 ${r.prev_run_state}，配额未动）`
              : `启动失败：${r.note}`,
          gate: r.gate,
        });
      } else {
        setFlash({ kind: "ok", text: `${action} → ${r.status}`, gate: r.gate });
      }
      return load();
    });

  return (
    <>
      <div className="hero">
        <h1>启停单</h1>
        <p>
          开单前探针红即硬拒启动：整笔失败，舱体不得进运行中，配额不动，
          对读屏该格不得计成功。红灯与启停成败同笔落库。
        </p>
      </div>

      {flash && (
        <div className={`panel gate-banner ${flash.kind}`}>
          <strong>{flash.gate ? `门：${flash.gate}` : ""}</strong> {flash.text}
        </div>
      )}

      <div className="panel">
        <div className="row-actions">
          {pods.map((p) => {
            const blocked = p["开单前可起"] === false;
            return (
              <span key={p.id} className="pod-action">
                <strong>{p.name}</strong>{" "}
                <span className={`tag ${p.probe_color === "绿" ? "ok" : "bad"}`}>
                  探针 {p.probe_color} · {p.fail_streak}
                </span>{" "}
                <button
                  className="btn"
                  onClick={() => act(p.id, "启动")}
                  title={blocked ? "开单前红灯：启动必被硬拒" : "启动"}
                >
                  启动
                </button>
                <button className="btn" onClick={() => act(p.id, "停止")}>
                  停止
                </button>
                {blocked && <span className="tag bad">红灯 · 启动将硬拒</span>}
              </span>
            );
          })}
        </div>
      </div>

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>舱</th>
              <th>动作</th>
              <th>状态</th>
              <th>说明</th>
              <th>门</th>
              <th>开单前探针</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id}>
                <td>{o.id}</td>
                <td>{o.pod_id}</td>
                <td>{o.action}</td>
                <td>
                  <span className={`tag ${statusClass(o.status)}`}>{o.status}</span>
                </td>
                <td>{o.note}</td>
                <td>
                  {o.gate ? (
                    <span className={`tag ${o.gate === "开单前红灯硬拒" ? "bad" : "warn"}`}>
                      {o.gate}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  {o.action === "启动" && o.probe_color
                    ? `${o.probe_color} · ${o.probe_fail_streak}/${o.probe_threshold}`
                    : "—"}
                </td>
                <td>{o.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
