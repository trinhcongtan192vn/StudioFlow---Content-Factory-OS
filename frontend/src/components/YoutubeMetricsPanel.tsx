import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ChannelSummary, YoutubeChannelMetricsOut, YoutubeRetentionChapter } from "../api/types";

/** Chỉ số YouTube theo TOÀN KÊNH + THEO TỪNG VIDEO — **mới (2026-09-12)**, theo yêu cầu
 * người dùng: "Khi bấm vào dashboard và bấm vào kênh... còn cần hiển thị được thông tin
 * các chỉ số cốt lõi theo toàn bộ kênh và theo từng video". Hiện trong tab "Chỉ số
 * YouTube" ở Dashboard (cạnh tab "Dự án" đã có sẵn). Chưa kết nối OAuth (Settings) →
 * hiện hướng dẫn; đã kết nối nhưng kênh này chưa gắn YouTube → nút "Kết nối kênh này với
 * YouTube"; đã gắn → nút "Đồng bộ" (thủ công, KHÔNG tự động chạy nền — CLAUDE.md nguyên
 * tắc 3) + thẻ chỉ số + bảng video. */
export default function YoutubeMetricsPanel({ channel, onChannelUpdated }: { channel: ChannelSummary; onChannelUpdated: () => Promise<void> }) {
  const [metrics, setMetrics] = useState<YoutubeChannelMetricsOut | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedProjectId, setExpandedProjectId] = useState<string | null>(null);
  const [chapters, setChapters] = useState<YoutubeRetentionChapter[] | null>(null);
  const [chaptersLoading, setChaptersLoading] = useState(false);
  const pollRef = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearInterval(pollRef.current), []);

  useEffect(() => {
    if (channel.youtube_channel_id) {
      api.getYoutubeChannelMetrics(channel.id).then(setMetrics, () => {});
    } else {
      setMetrics(null);
    }
  }, [channel.id, channel.youtube_channel_id]);

  async function connect() {
    // OAuth RIÊNG cho từng kênh (mục 154, 2026-09-19) — mở trình duyệt hệ thống tới màn
    // đồng ý Google CHO ĐÚNG KÊNH NÀY (channel.id nhúng trong `state`, xem backend
    // `authorize-url`/`oauth/callback`), rồi poll tới khi callback lưu xong token +
    // gán `Channel.youtube_channel_id`. Cùng pattern polling trước đây nằm ở
    // `YoutubeSettings.tsx` (đã bỏ, giờ per-channel).
    if (!window.studioflowNative) {
      setError("Kết nối YouTube chỉ dùng được trong app desktop (không phải chạy dev server thuần trình duyệt).");
      return;
    }
    setConnecting(true);
    setError(null);
    try {
      const redirectUri = api.youtubeOAuthCallbackUrl();
      const { url } = await api.getYoutubeChannelAuthorizeUrl(channel.id, redirectUri);
      await window.studioflowNative.openExternal(url);
      window.clearInterval(pollRef.current);
      pollRef.current = window.setInterval(async () => {
        const s = await api.getYoutubeChannelOAuthStatus(channel.id);
        if (s.connected) {
          window.clearInterval(pollRef.current);
          setConnecting(false);
          await onChannelUpdated();
        }
      }, 2000);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi mở màn kết nối Google.");
      setConnecting(false);
    }
  }

  async function disconnect() {
    if (!confirm("Ngắt kết nối kênh này với YouTube? Lịch sử chỉ số đã đồng bộ vẫn được giữ lại.")) return;
    await api.disconnectChannelFromYoutube(channel.id);
    await onChannelUpdated();
  }

  async function sync() {
    setSyncing(true);
    setError(null);
    try {
      setMetrics(await api.syncYoutubeMetrics(channel.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi đồng bộ chỉ số YouTube.");
    } finally {
      setSyncing(false);
    }
  }

  async function toggleChapters(projectId: string) {
    if (expandedProjectId === projectId) {
      setExpandedProjectId(null);
      setChapters(null);
      return;
    }
    setExpandedProjectId(projectId);
    setChapters(null);
    setChaptersLoading(true);
    try {
      const r = await api.getRetentionChapters(projectId);
      setChapters(r.chapters);
    } catch {
      setChapters([]);
    } finally {
      setChaptersLoading(false);
    }
  }

  if (!channel.youtube_channel_id) {
    return (
      <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 520 }}>
        <div className="card-title">Chưa kết nối YouTube cho kênh này</div>
        <div className="card-body">
          Cần cấu hình OAuth Client ở Settings → "Chỉ số YouTube" trước (1 lần cho toàn app), sau đó bấm nút dưới đây — trình duyệt sẽ mở màn đồng ý Google RIÊNG cho kênh này (nếu tài khoản Google quản nhiều kênh, chọn đúng kênh muốn gắn ở đó).
        </div>
        {error && <div style={{ fontSize: 12.5, color: "var(--color-danger)" }}>{error}</div>}
        <button className="btn btn-primary" style={{ alignSelf: "flex-start" }} onClick={connect} disabled={connecting}>
          {connecting ? "Đang chờ đồng ý trên trình duyệt..." : "Kết nối kênh này với YouTube"}
        </button>
      </div>
    );
  }

  const snap = metrics?.channel_snapshot ?? null;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-3)", flexWrap: "wrap", gap: 8 }}>
        <div style={{ fontSize: 13 }}>
          Kênh YouTube: <strong>{channel.youtube_channel_title}</strong>
          {snap && <span style={{ opacity: 0.6, marginLeft: 8 }}>Đồng bộ lúc: {new Date(snap.synced_at).toLocaleString("vi-VN")}</span>}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-primary" onClick={sync} disabled={syncing}>
            {syncing ? "Đang đồng bộ..." : "Đồng bộ chỉ số YouTube"}
          </button>
          <button className="btn btn-secondary" onClick={disconnect}>
            Ngắt kết nối
          </button>
        </div>
      </div>

      {error && <div style={{ fontSize: 12.5, color: "var(--color-danger)", marginBottom: "var(--space-3)" }}>{error}</div>}

      {!snap ? (
        <div style={{ fontSize: 13, opacity: 0.7, marginBottom: "var(--space-4)" }}>Chưa có dữ liệu — bấm "Đồng bộ chỉ số YouTube" (cần ít nhất 1 project đã liên kết video YouTube ở Output Center).</div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: "var(--space-2)", marginBottom: "var(--space-5)" }}>
          <MetricCard label="APV toàn kênh" value={snap.avg_view_percentage} suffix="%" target="≥45%" ok={snap.avg_view_percentage != null && snap.avg_view_percentage >= 45} northStar />
          <MetricCard
            label="CTR thumbnail"
            value={snap.avg_impression_ctr}
            suffix="%"
            target="5-8%"
            ok={snap.avg_impression_ctr != null && snap.avg_impression_ctr >= 5 && snap.avg_impression_ctr <= 8}
            note="YouTube không lộ chỉ số này qua API công khai — nhập tay ở Output Center"
          />
          <MetricCard label="Retention giây 30" value={snap.avg_retention_at_30s} suffix="%" target="≥70%" ok={snap.avg_retention_at_30s != null && snap.avg_retention_at_30s >= 70} />
          <MetricCard label="Bình luận/1.000 view" value={snap.comments_per_1000_views} />
          <MetricCard label="Lưu lượng DE/AT/CH" value={snap.de_at_ch_views_pct} suffix="%" />
          <MetricCard label="Subscriber" value={snap.subscriber_count} />
        </div>
      )}

      {metrics && metrics.videos.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Video</th>
                <th>Views</th>
                <th>APV</th>
                <th>Retention 30s</th>
                <th>CTR</th>
                <th>Bình luận/1.000</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {metrics.videos.map((v) => (
                <>
                  <tr key={v.project_id}>
                    <td>{v.project_title}</td>
                    <td>{v.metrics?.views ?? "—"}</td>
                    <td>{v.metrics?.avg_view_percentage != null ? `${v.metrics.avg_view_percentage.toFixed(1)}%` : "—"}</td>
                    <td>{v.metrics?.retention_at_30s != null ? `${v.metrics.retention_at_30s.toFixed(1)}%` : "—"}</td>
                    <td>{v.metrics?.impression_ctr != null ? `${v.metrics.impression_ctr.toFixed(1)}%` : "—"}</td>
                    <td>{v.metrics?.comments_per_1000_views != null ? v.metrics.comments_per_1000_views.toFixed(1) : "—"}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn btn-secondary" style={{ fontSize: 11, padding: "3px 8px" }} onClick={() => toggleChapters(v.project_id)} disabled={!v.metrics}>
                        {expandedProjectId === v.project_id ? "Ẩn" : "Theo chương"}
                      </button>
                    </td>
                  </tr>
                  {expandedProjectId === v.project_id && (
                    <tr>
                      <td colSpan={7}>
                        {chaptersLoading ? (
                          <div style={{ fontSize: 12, opacity: 0.6, padding: "6px 0" }}>Đang tải...</div>
                        ) : chapters && chapters.length > 0 ? (
                          <RetentionChaptersChart chapters={chapters} />
                        ) : (
                          <div style={{ fontSize: 12, opacity: 0.6, padding: "6px 0" }}>Chưa có dữ liệu retention theo chương cho video này.</div>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, suffix = "", target, ok, northStar, note }: { label: string; value: number | null; suffix?: string; target?: string; ok?: boolean; northStar?: boolean; note?: string }) {
  return (
    <div
      className="card elev-sm"
      style={{
        gap: 4,
        padding: "10px 12px",
        border: northStar ? "1px solid color-mix(in srgb, var(--color-accent) 40%, transparent)" : undefined,
      }}
      title={note}
    >
      <div style={{ fontSize: 11, opacity: 0.6 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600, color: value == null ? undefined : ok === false ? "var(--color-warning)" : ok === true ? "var(--color-accent)" : undefined }}>
        {value != null ? `${typeof value === "number" && !Number.isInteger(value) ? value.toFixed(1) : value}${suffix}` : "—"}
      </div>
      {target && <div style={{ fontSize: 10.5, opacity: 0.5 }}>Mục tiêu: {target}</div>}
      {note && <div style={{ fontSize: 10, opacity: 0.5, fontStyle: "italic" }}>{note}</div>}
    </div>
  );
}

function RetentionChaptersChart({ chapters }: { chapters: YoutubeRetentionChapter[] }) {
  const worst = chapters.reduce((min, c) => (c.avg_retention < min.avg_retention ? c : min), chapters[0]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "6px 0" }}>
      {chapters.map((c) => (
        <div key={c.block_id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 60, fontSize: 11, opacity: 0.7, flex: "none" }}>{c.block_id}</div>
          <div style={{ flex: 1, height: 8, borderRadius: 999, background: "var(--color-neutral-800)", overflow: "hidden" }}>
            <div
              style={{
                height: "100%",
                width: `${Math.max(0, Math.min(100, c.avg_retention * 100))}%`,
                background: c.block_id === worst.block_id ? "var(--color-danger)" : "var(--color-accent)",
              }}
            />
          </div>
          <div style={{ width: 48, fontSize: 11, textAlign: "right", flex: "none" }}>{(c.avg_retention * 100).toFixed(0)}%</div>
        </div>
      ))}
      <div style={{ fontSize: 11, opacity: 0.6, marginTop: 2 }}>Chương tụt mạnh nhất: {worst.block_id}</div>
    </div>
  );
}
