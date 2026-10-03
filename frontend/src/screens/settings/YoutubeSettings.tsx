import { useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { YoutubeSettingsStatus } from "../../api/types";

/** Chỉ số YouTube — cấu hình OAuth Client — **mới (2026-09-12)**, theo yêu cầu người
 * dùng: "đề xuất phương án triển khai tính năng thống kê các chỉ số cho kênh, kéo dữ
 * liệu từ youtube về". App KHÔNG nhúng sẵn 1 OAuth Client dùng chung (rủi ro bảo mật khi
 * phân phối + tranh chấp quota giữa nhiều người dùng) — người dùng TỰ đăng ký 1 Google
 * Cloud project + OAuth Client (loại "Desktop app") ở Google Cloud Console, dán
 * `client_id`/`client_secret` vào đây (mã hoá tại chỗ, cùng nguyên tắc API key provider
 * AI). Cặp này DÙNG CHUNG cho mọi kênh (chỉ là định danh của app, không phải danh tính
 * người dùng).
 *
 * **Bước "Kết nối tài khoản Google" đã CHUYỂN sang Dashboard, RIÊNG cho từng kênh** —
 * mục 154 (2026-09-19), sửa lỗ hổng: 1 Google Account có thể quản nhiều kênh YouTube
 * (brand channel/kênh được share) — dùng chung 1 token toàn app khiến 2 kênh StudioFlow
 * bị gán NHẦM cùng 1 kênh YouTube thật. Giờ mỗi kênh StudioFlow tự chạy 1 lượt OAuth
 * riêng (xem `YoutubeMetricsPanel.tsx::connect`) — Google sẽ cho chọn ĐÚNG kênh ở màn
 * đồng ý khi tài khoản quản lý nhiều kênh. */
export default function YoutubeSettings() {
  const [status, setStatus] = useState<YoutubeSettingsStatus | null>(null);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [savingClient, setSavingClient] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setStatus(await api.getYoutubeSettingsStatus());
    } catch {
      // im lặng — trạng thái ban đầu chưa cấu hình gì cũng hợp lệ, không phải lỗi cần báo
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function saveClient() {
    setSavingClient(true);
    setError(null);
    try {
      await api.saveYoutubeOAuthClient(clientId.trim(), clientSecret.trim());
      setClientId("");
      setClientSecret("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi lưu OAuth Client.");
    } finally {
      setSavingClient(false);
    }
  }

  return (
    <div>
      <h3 style={{ marginBottom: 2 }}>Chỉ số YouTube</h3>
      <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13, marginBottom: "var(--space-4)" }}>
        Kết nối tài khoản Google để kéo chỉ số thật (APV, retention, CTR, bình luận, lưu lượng theo quốc gia...) thay cho nhập tay. RPM (doanh thu) vẫn cần nhập tay — quyền doanh thu YouTube khó xin cho app cá nhân.
      </p>

      {error && (
        <div style={{ fontSize: 13, color: "var(--color-danger)", background: "var(--color-danger-bg)", borderRadius: "var(--radius-sm)", padding: "8px 10px", marginBottom: "var(--space-3)", maxWidth: 520 }}>
          {error}
        </div>
      )}

      <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 520, marginBottom: "var(--space-4)" }}>
        <div className="card-kicker">Bước 1 — OAuth Client</div>
        <div className="card-body">
          Tạo 1 Google Cloud project (console.cloud.google.com) → bật "YouTube Data API v3" + "YouTube Analytics API" → tạo OAuth Client loại "Desktop app" → dán 2 giá trị dưới đây.
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>Client ID</label>
          <input className="input" type="text" value={clientId} onChange={(e) => setClientId(e.target.value)} placeholder="xxxxxxxx.apps.googleusercontent.com" />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>Client Secret</label>
          <input className="input" type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} placeholder={status?.has_oauth_client ? "Đã lưu — nhập lại để đổi" : ""} />
        </div>
        <button className="btn btn-primary" style={{ alignSelf: "flex-start" }} onClick={saveClient} disabled={savingClient || !clientId.trim() || !clientSecret.trim()}>
          {savingClient ? "Đang lưu..." : "Lưu OAuth Client"}
        </button>
        {status?.has_oauth_client && <div style={{ fontSize: 12, color: "var(--color-accent)" }}>✓ Đã cấu hình OAuth Client</div>}
      </div>

      <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 520 }}>
        <div className="card-kicker">Bước 2 — Kết nối từng kênh</div>
        <div className="card-body">
          Vào Dashboard → chọn 1 kênh → tab "Chỉ số YouTube" → bấm "Kết nối kênh này với YouTube". Mỗi kênh StudioFlow kết nối RIÊNG (1 tài khoản Google có thể quản nhiều kênh YouTube — brand channel/kênh được share — Google sẽ cho bạn chọn đúng kênh ở màn đồng ý).
        </div>
      </div>
    </div>
  );
}
