import React, { useEffect, useState } from "react";
import { api } from "../api";

export default function Probes() {
  const [rows, setRows] = useState([]);
  const [note, setNote] = useState(null);
  const load = () => api.probes().then(setRows);
  useEffect(() => {
    load();
  }, []);

  const flip = (podId, body, label) =>
    api.setProbe(podId, body).then((r) => {
      const v = r["探针判定"];
      setNote(
        `${label}：现为${v.color}，连击 ${v.fail_streak}/${v.threshold} → ${
          v.blocked ? "开单前红灯，启动必被硬拒" : "开单前放行"
        }`
      );
      return load();
    });

  return (
    <>
      <div className="hero">
        <h1>探针灯</h1>
        <p>
          健康探针红绿与连续失败次数。<strong>开单前红灯必须硬拒启动</strong>
          —— 红灯不得算「起成」，不挂缺口账，界面无口径选型。红灯与启停成败同笔。
        </p>
      </div>

      {note && (
        <div className={`panel gate-banner ${note.includes("硬拒") ? "bad" : "ok"}`}>
          {note}
        </div>
      )}

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>舱</th>
              <th>运行</th>
              <th>颜色</th>
              <th>失败连击</th>
              <th>阈值</th>
              <th>开单前判定</th>
              <th>自洽</th>
              <th>更新</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.pod_id}>
                <td>{r.pod_name}</td>
                <td>
                  <span className={`tag ${r.run_state === "运行中" ? "ok" : "warn"}`}>
                    {r.run_state}
                  </span>
                </td>
                <td>
                  <span className={`tag ${r.color === "绿" ? "ok" : "bad"}`}>{r.color}</span>
                </td>
                <td>{r.fail_streak}</td>
                <td>{r["阈值"]}</td>
                <td>
                  <span className={`tag ${r["红灯"] ? "bad" : "ok"}`}>{r["门口径"]}</span>
                </td>
                <td>
                  {r["自洽"] ? (
                    <span className="tag ok">一致</span>
                  ) : (
                    <span className="tag warn">色与连击不一 · 按红</span>
                  )}
                </td>
                <td>{r.updated_at}</td>
                <td>
                  <button
                    className="btn"
                    onClick={() => flip(r.pod_id, { color: "绿", fail_streak: 0 }, r.pod_name)}
                  >
                    置绿
                  </button>
                  <button
                    className="btn"
                    onClick={() =>
                      flip(
                        r.pod_id,
                        { color: "红", fail_streak: (r.fail_streak || 0) + 1 },
                        r.pod_name
                      )
                    }
                  >
                    置红
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
