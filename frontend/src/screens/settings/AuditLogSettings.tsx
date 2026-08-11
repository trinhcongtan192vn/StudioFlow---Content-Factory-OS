import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { AuditLogEntry } from "../../api/types";

const FILTERS = [
  { key: "all", label: "Tất cả", type: undefined },
  { key: "system", label: "Hệ thống", type: "system" },
  { key: "expense", label: "Chi phí AI", type: "expense" },
] as const;

export default function AuditLogSettings() {
  const [filter, setFilter] = useState<string>("all");
  const [log, setLog] = useState<AuditLogEntry[]>([]);

  useEffect(() => {
    const f = FILTERS.find((x) => x.key === filter);
    api.getAuditLog(f?.type).then(setLog);
  }, [filter]);

  return (
    <div>
      <h3 style={{ marginBottom: 2 }}>Audit Log</h3>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-4)" }}>Nhật ký thao tác nhạy cảm &amp; chi phí sử dụng AI.</p>
      <div className="seg" style={{ marginBottom: "var(--space-4)", maxWidth: 420 }}>
        {FILTERS.map((f) => (
          <label key={f.key} className={`seg-opt ${filter === f.key ? "active" : ""}`} onClick={() => setFilter(f.key)} style={{ whiteSpace: "nowrap" }}>
            {f.label}
          </label>
        ))}
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>Thời gian</th>
            <th>Kênh/Project</th>
            <th>Hành động</th>
            <th>Chi tiết</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {log.map((a, i) => (
            <tr key={i}>
              <td style={{ fontFamily: "ui-monospace,monospace", fontSize: 12, whiteSpace: "nowrap" }}>{a.time}</td>
              <td>{a.entity || "—"}</td>
              <td>{a.action}</td>
              <td style={{ opacity: 0.75 }}>{a.detail}</td>
              <td style={{ textAlign: "right", fontFamily: "ui-monospace,monospace" }}>{a.type === "expense" && a.cost != null ? `$${a.cost.toFixed(2)}` : "—"}</td>
            </tr>
          ))}
          {log.length === 0 && (
            <tr>
              <td colSpan={5} style={{ opacity: 0.6, padding: "var(--space-3) 0" }}>
                Chưa có nhật ký.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
