// "Local Services & GPU Monitor" — cuối trang Dashboard (2026-08-27, theo yêu cầu người
// dùng: xem/bật/tắt Ollama/OmniVoice/ComfyUI + tình trạng GPU mà không cần rời app).
// Xem app/local_services.py cho chi tiết backend + giới hạn thật đã verify (Windows WDDM
// không báo VRAM per-process — panel chỉ hiện tổng VRAM dùng/tổng, không breakdown
// từng service).
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { LocalServicesResponse } from "../api/types";

const POLL_INTERVAL_MS = 5000;

export default function LocalServicesPanel() {
  const [data, setData] = useState<LocalServicesResponse | null>(null);
  const [busyService, setBusyService] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const mountedRef = useRef(true);

  async function refresh() {
    try {
      const res = await api.getLocalServices();
      if (mountedRef.current) setData(res);
    } catch {
      /* backend chưa sẵn sàng lúc mới mở app — bỏ qua, thử lại ở lượt poll sau */
    }
  }

  useEffect(() => {
    mountedRef.current = true;
    refresh();
    const id = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      mountedRef.current = false;
      window.clearInterval(id);
    };
  }, []);

  async function handleToggle(name: string, running: boolean) {
    if (running && !confirm("Tắt service này có thể làm gián đoạn tiến trình đang chạy (sinh ảnh/video/giọng đọc dở). Vẫn tắt?")) return;
    setBusyService(name);
    setActionMessage(null);
    try {
      const result = running ? await api.stopLocalService(name) : await api.startLocalService(name);
      setActionMessage(result.message);
    } catch (e) {
      setActionMessage(e instanceof Error ? e.message : "Có lỗi khi bật/tắt service.");
    } finally {
      setBusyService(null);
      await refresh();
    }
  }

  if (!data) return null;

  const { services, gpu } = data;

  return (
    <div className="card elev-sm" style={{ marginTop: "var(--space-8)", padding: "var(--space-4)" }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: "var(--space-3)" }}>Local Services & GPU</div>

      {gpu.available ? (
        <div style={{ marginBottom: "var(--space-4)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 4 }}>
            <span>{gpu.name} — {gpu.utilization_pct}% util, {gpu.temperature_c}°C</span>
            <span style={{ opacity: 0.7 }}>
              {((gpu.memory_used_mb || 0) / 1024).toFixed(1)} / {((gpu.memory_total_mb || 0) / 1024).toFixed(1)} GB VRAM
            </span>
          </div>
          <div style={{ height: 6, borderRadius: 4, background: "var(--color-bg)", overflow: "hidden" }}>
            <div
              style={{
                height: "100%",
                width: `${Math.min(100, ((gpu.memory_used_mb || 0) / Math.max(1, gpu.memory_total_mb || 1)) * 100)}%`,
                background: "var(--color-accent)",
                transition: "width 0.4s",
              }}
            />
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 12.5, opacity: 0.6, marginBottom: "var(--space-4)" }}>Không đọc được thông tin GPU (nvidia-smi không có trên máy, hoặc không có GPU NVIDIA).</div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {services.map((s) => (
          <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
            <span
              style={{
                width: 8, height: 8, borderRadius: "50%", flex: "none",
                background: s.running ? "var(--color-accent)" : "var(--color-neutral-600)",
              }}
              title={s.running ? "Đang chạy" : "Đã tắt"}
            />
            <span style={{ flex: 1 }}>
              {s.display_name}
              {gpu.available && gpu.services_using_gpu?.includes(s.name) && <span style={{ opacity: 0.55, marginLeft: 6 }}>· đang giữ GPU</span>}
            </span>
            <button
              className="btn btn-secondary"
              style={{ fontSize: 11.5, padding: "3px 10px" }}
              disabled={busyService === s.name}
              onClick={() => handleToggle(s.name, s.running)}
            >
              {busyService === s.name ? "Đang xử lý..." : s.running ? "Tắt" : "Bật"}
            </button>
          </div>
        ))}
      </div>

      {actionMessage && <div style={{ fontSize: 11.5, opacity: 0.65, marginTop: "var(--space-2)" }}>{actionMessage}</div>}
    </div>
  );
}
