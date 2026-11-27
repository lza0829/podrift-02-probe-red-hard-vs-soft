import React, { useEffect, useState } from "react";
import { api } from "../api";

export default function Policy() {
  const [p, setP] = useState(null);
  const load = () => api.policy().then(setP);
  useEffect(() => {
    load();
  }, []);
  if (!p) return null;
  const gate = p["开单前探针门"];
  return (
    <>
      <div className="hero">
        <h1>重启策</h1>
        <p>失败重启 / 永不 / 总是。开单前探针门为全站唯一口径，不提供选型。</p>
      </div>
      <div className="panel">
        <p>当前模式：<strong>{p.mode}</strong> · 退避 {p.backoff_sec}s</p>
        <div className="row-actions">
          {["失败重启", "永不", "总是"].map((m) => (
            <button key={m} className="btn" onClick={() => api.setPolicy({ mode: m }).then(load)}>{m}</button>
          ))}
        </div>
      </div>
      <div className="panel arm-note">
        <div>
          <span className="tag bad">唯一口径</span> {gate["落臂"]}
        </div>
        <div className="muted">
          阈值 {gate["阈值"]}（舱规可调） · 可切换口径：{gate["可切换口径"] ? "是" : "否"}
        </div>
      </div>
    </>
  );
}
