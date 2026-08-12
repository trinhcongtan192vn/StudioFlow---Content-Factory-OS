import { useApp } from "../store/AppContext";

/** Banner lỗi khi 1 thao tác cần AI thất bại (thường do chưa cấu hình / cấu hình sai
 * Provider AI — xem NoProviderConfiguredError ở backend). Luôn có lối tắt vào Cài đặt. */
export default function AiErrorBanner({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  const app = useApp();
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "flex-start",
        padding: "var(--space-3)",
        borderRadius: "var(--radius-md)",
        background: "var(--color-danger-bg)",
        color: "var(--color-danger)",
        marginBottom: "var(--space-4)",
        fontSize: 13,
        maxWidth: 820,
      }}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flex: "none", marginTop: 1 }}>
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
      <div style={{ flex: 1 }}>{message}</div>
      <button className="btn btn-secondary" style={{ fontSize: 12, flex: "none" }} onClick={app.goSettings}>
        Cấu hình ngay →
      </button>
      {onDismiss && (
        <button className="btn btn-icon btn-secondary" style={{ flex: "none", width: 22, height: 22 }} title="Đóng" onClick={onDismiss}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      )}
    </div>
  );
}
