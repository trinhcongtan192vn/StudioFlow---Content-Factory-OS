import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ProjectSummary } from "../api/types";
import ChannelDialog from "../components/ChannelDialog";
import { STATUS_LABEL, STATUS_DOT_COLOR, STEP_LABELS } from "../components/statusMeta";
import { useApp } from "../store/AppContext";

export default function Dashboard() {
  const app = useApp();
  const [selected, setSelected] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [editingChannelId, setEditingChannelId] = useState<string | null>(null);

  useEffect(() => {
    if (selected) api.listProjects(selected).then(setProjects);
  }, [selected]);

  async function handleDelete(e: React.MouseEvent, id: string, name: string) {
    e.stopPropagation();
    if (!confirm(`Xóa kênh "${name}"? Toàn bộ project sẽ bị archive.`)) return;
    await api.patchChannel(id, { archived: true });
    await app.refreshChannels();
    if (selected === id) setSelected(null);
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-8)" }}>
      <h2 style={{ marginBottom: 2 }}>Dashboard kênh</h2>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-6)" }}>Một cái nhìn biết ngay kênh nào đang tắc.</p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "var(--space-4)", marginBottom: "var(--space-8)" }}>
        {app.channels.map((ch) => (
          <div
            key={ch.id}
            className="card elev-sm"
            onClick={() => setSelected(selected === ch.id ? null : ch.id)}
            style={{ cursor: "pointer", border: selected === ch.id ? "1px solid var(--color-accent)" : "1px solid transparent" }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 10, justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                <div style={{ width: 36, height: 36, borderRadius: 8, background: "var(--color-accent-900)", color: "var(--color-accent-300)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 600, fontSize: 15, flex: "none" }}>{ch.letter}</div>
                <div style={{ minWidth: 0 }}>
                  <div className="card-title" style={{ fontSize: 15 }}>
                    {ch.name}
                  </div>
                  <div className="tag tag-outline" style={{ marginTop: 2, whiteSpace: "nowrap" }}>
                    {ch.niche || "—"}
                  </div>
                </div>
              </div>
              <div style={{ display: "flex", gap: 2, flex: "none" }}>
                <div
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditingChannelId(ch.id);
                  }}
                  title="Sửa BrandProfile"
                  style={{ width: 22, height: 22, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", opacity: 0.55, flex: "none" }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 113 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </div>
                <div onClick={(e) => handleDelete(e, ch.id, ch.name)} title="Xóa kênh" style={{ width: 22, height: 22, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", opacity: 0.55, flex: "none" }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                    <path d="M10 11v6" />
                    <path d="M14 11v6" />
                    <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
                  </svg>
                </div>
              </div>
            </div>
            <div className="card-meta" style={{ marginTop: 6 }}>
              <span>{ch.running_count} đang chạy</span>
              <span>·</span>
              <span>{ch.review_count} chờ duyệt</span>
            </div>
          </div>
        ))}
      </div>

      {selected && (
        <div>
          <h4 style={{ marginBottom: "var(--space-3)" }}>Dự án — {app.channels.find((c) => c.id === selected)?.name}</h4>
          <table className="table">
            <thead>
              <tr>
                <th>Dự án</th>
                <th>Trạng thái</th>
                <th>Bước hiện tại</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id} onClick={() => app.openProject(selected, p.id)} style={{ cursor: "pointer" }}>
                  <td>{p.title}</td>
                  <td>
                    <span className="tag" style={{ background: "color-mix(in srgb, " + (STATUS_DOT_COLOR[p.status] || "var(--color-neutral-600)") + " 20%, transparent)", color: STATUS_DOT_COLOR[p.status] || "inherit" }}>
                      {STATUS_LABEL[p.status] || p.status}
                    </span>
                  </td>
                  <td style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)" }}>{STEP_LABELS[p.step] || "—"}</td>
                  <td style={{ textAlign: "right", color: "var(--color-accent)" }}>Mở →</td>
                </tr>
              ))}
              {projects.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ opacity: 0.6, padding: "var(--space-3) 0" }}>
                    Chưa có project nào — mở kênh ở sidebar trái và bấm "Project mới".
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {editingChannelId && (
        <ChannelDialog
          mode="edit"
          channelId={editingChannelId}
          onClose={() => setEditingChannelId(null)}
          onSaved={async () => {
            await app.refreshChannels();
            setEditingChannelId(null);
          }}
        />
      )}
    </div>
  );
}
