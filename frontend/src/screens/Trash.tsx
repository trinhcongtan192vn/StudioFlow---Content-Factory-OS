import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { TrashOut } from "../api/types";
import { useApp } from "../store/AppContext";

export default function Trash() {
  const app = useApp();
  const [trash, setTrash] = useState<TrashOut | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    setTrash(await api.getTrash());
  }

  useEffect(() => {
    load();
  }, []);

  async function restoreChannel(id: string) {
    setBusyId(id);
    try {
      await api.restoreChannel(id);
      await Promise.all([load(), app.refreshChannels()]);
    } finally {
      setBusyId(null);
    }
  }

  async function deleteChannelForever(id: string, name: string) {
    if (!confirm(`Xoá vĩnh viễn kênh "${name}"? Toàn bộ project, BrandProfile và file trên đĩa sẽ mất — KHÔNG thể khôi phục.`)) return;
    setBusyId(id);
    try {
      await api.deleteChannelPermanent(id);
      await load();
    } finally {
      setBusyId(null);
    }
  }

  async function restoreProject(id: string, channelId: string) {
    setBusyId(id);
    try {
      await api.restoreProject(id);
      await load();
      app.bumpProjectsVersion(channelId);
    } finally {
      setBusyId(null);
    }
  }

  async function deleteProjectForever(id: string, title: string, channelId: string) {
    if (!confirm(`Xoá vĩnh viễn project "${title}"? Toàn bộ kịch bản, asset và file trên đĩa sẽ mất — KHÔNG thể khôi phục.`)) return;
    setBusyId(id);
    try {
      await api.deleteProjectPermanent(id);
      await load();
      app.bumpProjectsVersion(channelId);
    } finally {
      setBusyId(null);
    }
  }

  if (!trash) {
    return <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", opacity: 0.6 }}>Đang tải...</div>;
  }

  const empty = trash.channels.length === 0 && trash.projects.length === 0;

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-8)" }}>
      <h2 style={{ marginBottom: 2 }}>Thùng rác</h2>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-6)" }}>
        Kênh/project đã xoá — khôi phục lại hoặc xoá vĩnh viễn (mất hẳn dữ liệu trên đĩa, không thể hoàn tác).
      </p>

      {empty && <div style={{ opacity: 0.6, fontSize: 13 }}>Thùng rác đang trống.</div>}

      {trash.channels.length > 0 && (
        <div style={{ marginBottom: "var(--space-8)" }}>
          <h4 style={{ marginBottom: "var(--space-3)" }}>Kênh đã xoá ({trash.channels.length})</h4>
          <table className="table">
            <thead>
              <tr>
                <th>Kênh</th>
                <th>Lĩnh vực</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {trash.channels.map((ch) => (
                <tr key={ch.id}>
                  <td>{ch.name}</td>
                  <td style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)" }}>{ch.niche || "—"}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px", marginRight: 6 }} disabled={busyId === ch.id} onClick={() => restoreChannel(ch.id)}>
                      Khôi phục
                    </button>
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px", color: "var(--color-danger)" }} disabled={busyId === ch.id} onClick={() => deleteChannelForever(ch.id, ch.name)}>
                      Xoá vĩnh viễn
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {trash.projects.length > 0 && (
        <div>
          <h4 style={{ marginBottom: "var(--space-3)" }}>Project đã xoá ({trash.projects.length})</h4>
          <table className="table">
            <thead>
              <tr>
                <th>Dự án</th>
                <th>Kênh</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {trash.projects.map((p) => (
                <tr key={p.id}>
                  <td>{p.title}</td>
                  <td style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)" }}>{p.channel_name}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px", marginRight: 6 }} disabled={busyId === p.id} onClick={() => restoreProject(p.id, p.channel_id)}>
                      Khôi phục
                    </button>
                    <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px", color: "var(--color-danger)" }} disabled={busyId === p.id} onClick={() => deleteProjectForever(p.id, p.title, p.channel_id)}>
                      Xoá vĩnh viễn
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
