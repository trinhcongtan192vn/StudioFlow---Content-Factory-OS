import type { ReactNode } from "react";
import type { ProductionPack, ProjectSummary } from "../api/types";
import { useApp } from "../store/AppContext";

// **Đổi (2026-08-23, theo đề xuất rà soát UX)**: TRƯỚC ĐÂY (2026-08-22) panel này bị bỏ
// gần như trống sau khi bỏ tóm tắt BrandProfile (người dùng thấy không cần thiết) — chỉ
// còn lại "Phiên bản Pack", chiếm cố định 280px trên MỌI màn mà gần như không có tác
// dụng gì. Giờ hiện lại "1 việc thật" — vài chỉ số ngữ cảnh KHÔNG lặp lại thông tin đã
// hiện ở nội dung chính (StatsBar ở StepHeader đã có từ/shot/thời lượng ước tính, không
// nhắc lại ở đây): định danh kênh (tên+niche — chỉ hiện dạng breadcrumb text ở header,
// không có ở đâu khác), định dạng (Long-form/Short 9:16 — badge Short chỉ hiện khi
// short-form, ở đây hiện RÕ cả 2 trường hợp), phiên bản Pack (giữ nguyên), và số cảnh
// báo guardrail (script.body[].warning — TRƯỚC ĐÂY chỉ thấy được khi đang ở đúng màn
// Script Studio, giờ thấy được xuyên suốt cả luồng). Tất cả tính từ props đã có sẵn
// (project + pack) — KHÔNG gọi thêm API nào, giữ chi phí thấp đúng tinh thần đề xuất.
export default function RightPanel({ project, pack }: { project: ProjectSummary | null; pack: ProductionPack | null }) {
  const app = useApp();
  const channel = app.channels.find((c) => c.id === project?.channel_id);
  const warningCount = (pack?.script?.body || []).filter((b) => b.warning).length;

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
      <div style={{ padding: "var(--space-4)", overflowY: "auto", height: "100%", display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" onClick={app.toggleRightPanel} style={{ cursor: "pointer", opacity: 0.6 }}>
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </div>

        <PanelField label="Kênh">{channel ? `${channel.name} · ${channel.niche || "chưa đặt niche"}` : "—"}</PanelField>
        <PanelField label="Định dạng">{project?.format === "short" ? "Short-form (9:16)" : "Long-form (16:9)"}</PanelField>
        <PanelField label="Phiên bản Pack">{project ? `v${project.pack_version} · hiện hành` : "—"}</PanelField>
        <PanelField label="Số shot">{pack ? pack.shots.length : "—"}</PanelField>
        <PanelField label="Cảnh báo guardrail">
          {warningCount > 0 ? <span style={{ color: "var(--color-warning)" }}>{warningCount} cảnh báo</span> : "Không có cảnh báo"}
        </PanelField>
      </div>
    </div>
  );
}

function PanelField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "color-mix(in srgb, var(--color-text) 55%, transparent)", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 12.5, opacity: 0.9 }}>{children}</div>
    </div>
  );
}
