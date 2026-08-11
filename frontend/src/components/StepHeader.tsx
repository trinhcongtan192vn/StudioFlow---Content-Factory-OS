import type { ReactNode } from "react";

/**
 * Header sticky dùng chung cho các bước trong ProjectView — đưa nút hành động lên
 * đầu màn thay vì cuối trang (đã build vòng 4, khớp cập nhật design). `top`/`margin`
 * âm bù đắp padding của canvas cha (`var(--space-6)`) để header dính sát mép trên khi
 * cuộn — xem ProjectView.tsx (canvas có padding var(--space-6)).
 *
 * Khác với CSS gốc trong design: có thêm `background: var(--color-bg)` — file design
 * không đặt màu nền cho header sticky nên card bên dưới sẽ lộ qua khi cuộn lên; đây là
 * lỗi nhỏ trong chính file design, bản build vá lại cho đúng ý đồ "dính header".
 */
export default function StepHeader({ title, description, actions, extra }: { title: string; description?: ReactNode; actions?: ReactNode; extra?: ReactNode }) {
  return (
    <>
      <div
        style={{
          position: "sticky",
          top: "calc(-1 * var(--space-6))",
          margin: "0 calc(-1 * var(--space-6)) var(--space-6) calc(-1 * var(--space-6))",
          padding: "var(--space-4) var(--space-6)",
          borderBottom: "1px solid var(--color-neutral-800)",
          background: "var(--color-bg)",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "var(--space-4)",
          flexWrap: "wrap",
          zIndex: 1,
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <h3 style={{ margin: "0 0 2px" }}>{title}</h3>
          {description && <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, margin: 0 }}>{description}</p>}
        </div>
        {actions && <div style={{ display: "flex", alignItems: "center", gap: 10, flex: "1 1 auto", minWidth: 0, flexWrap: "wrap", justifyContent: "flex-end" }}>{actions}</div>}
      </div>
      {extra}
    </>
  );
}
