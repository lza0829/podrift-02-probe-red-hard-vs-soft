import React, { useEffect, useState } from "react";
import { api } from "../api";

export default function Rules() {
  const [settings, setSettings] = useState([]);
  const [events, setEvents] = useState([]);
  const [arm, setArm] = useState(null);

  const load = () =>
    Promise.all([api.settings(), api.events(), api.arm()]).then(([s, e, a]) => {
      setSettings(s);
      setEvents(e);
      setArm(a);
    });

  useEffect(() => {
    load();
  }, []);

  const saveThreshold = (key, value) => api.setSetting({ key, value }).then(load);

  return (
    <>
      <div className="hero">
        <h1>舱规</h1>
        <p>全局默认阈值与事件痕。开单前探针阈值可调，但红灯必须硬拒的口径不可切。</p>
      </div>

      {arm && (
        <div className="panel arm-note">
          <div>
            <span className="tag bad">唯一口径</span> {arm["开单前红灯口径"]["落臂"]}
          </div>
          <ul className="muted">
            {Object.entries(arm["开单前红灯口径"])
              .filter(([k]) => k !== "落臂")
              .map(([k, v]) => (
                <li key={k}>
                  <strong>{k}</strong>：{v}
                </li>
              ))}
          </ul>
          <div className="muted">另行立项：{arm["另行立项"].join("、")}</div>
        </div>
      )}

      <div className="panel">
        <table>
          <thead><tr><th>键</th><th>值</th><th></th></tr></thead>
          <tbody>
            {settings.map((s) => (
              <tr key={s.key}>
                <td>{s.key}</td>
                <td>{s.value}</td>
                <td>
                  {s.key === "probe_fail_threshold" && (
                    <button
                      className="btn"
                      onClick={() => {
                        const next = prompt("新阈值", s.value);
                        if (next) saveThreshold(s.key, next);
                      }}
                    >
                      调阈值
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel">
        <table>
          <thead><tr><th>事件</th><th>引用</th><th>详情</th><th>时间</th></tr></thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}><td>{e.kind}</td><td>{e.ref}</td><td>{e.detail}</td><td>{e.at}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
