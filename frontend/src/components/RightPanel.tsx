import type { ProjectSummary } from "../api/types";
import { useApp } from "../store/AppContext";

// **Bỏ mục BrandProfile (2026-08-22)**, theo yêu cầu người dùng: panel này TRƯỚC ĐÂY
// hiện tóm tắt BrandProfile (tông giọng, content pillars, cấm kỵ, retention benchmark)
// bên cạnh luồng tạo video project — người dùng thấy không cần thiết (đã có màn "Sửa
// BrandProfile" riêng ở ChannelDialog.tsx đầy đủ hơn). Giữ lại phần "Phiên bản Pack"
// (không thuộc BrandProfile) + khung panel thu/phóng — chỉ bỏ đúng phần được yêu cầu.
export default function RightPanel({ project }: { project: ProjectSummary | null }) {
  const app = useApp();

  if (!app.rightPanelOpen) {
    return (
      <div style={{ width: 32, flex: "none", borderLeft: "1px solid var(--color-divider)" }}>
        <div style={{ padding: "var(--space-3) 0", display: "flex", justifyContent: "center" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" onClick={app.toggleRightPanel} style={{ cursor: "pointer", opacity: 0.6 }}>
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </div>
      </div>
    );
  }

  return (
    <div style={{ width: 280, flex: "none", borderLeft: "1px solid var(--color-divider)", overflow: "hidden" }}>
      <div style={{ padding: "var(--space-4)", overflowY: "auto", height: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", marginBottom: "var(--space-3)" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" onClick={app.toggleRightPanel} style={{ cursor: "pointer", opacity: 0.6 }}>
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </div>
        <div style={{ fontSize: 11, color: "color-mix(in srgb, var(--color-text) 55%, transparent)", marginBottom: 6 }}>Phiên bản Pack</div>
        <div style={{ fontSize: 12, opacity: 0.75 }}>{project ? `v${project.pack_version} · hiện hành` : "—"}</div>
      </div>
    </div>
  );
}
