import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ProductionPack, ProjectSummary, RenderState } from "../../api/types";

/** Render Studio — CHỈ còn bước ghép MP4 (ffmpeg). Sinh asset (ảnh/video/giọng đọc)
 * đã chuyển sang Visual Studio (bước ④, trước Gate #2) — nơi người dùng sinh + duyệt
 * từng shot trực tiếp. Màn này đọc lại đúng trạng thái đã duyệt đó (`render.json`,
 * qua GET /render/status) và chỉ cho ghép khi mọi shot đã `visual_status=="ready"` +
 * `approved`. Nhúng trong Output Center (thẻ "Render in-app"), không phải step
 * Stepper riêng — khớp specs/06_uiux.md §7. */
export default function RenderStudio({ project, onClose }: { project: ProjectSummary; pack: ProductionPack; onClose: () => void }) {
  const [state, setState] = useState<RenderState | null>(null);
  const [assembling, setAssembling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | undefined>(undefined);

  async function load() {
    try {
      setState(await api.getRenderStatus(project.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi tải trạng thái render.");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  const isAssembling = state?.assembly_status === "assembling";

  useEffect(() => {
    window.clearInterval(pollRef.current);
    if (isAssembling) {
      pollRef.current = window.setInterval(load, 3000);
    }
    return () => window.clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAssembling]);

  async function assemble() {
    setAssembling(true);
    setError(null);
    try {
      setState(await api.assembleVideo(project.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi ghép video.");
    } finally {
      setAssembling(false);
    }
  }

  const shots = state?.shots || [];
  const readyCount = shots.filter((s) => s.visual_status === "ready").length;
  const approvedCount = shots.filter((s) => s.visual_status === "ready" && s.approved).length;
  const allApproved = shots.length > 0 && approvedCount === shots.length;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "var(--space-4)" }}>
        <div>
          <h3 style={{ marginBottom: 2 }}>Render Studio — Ghép MP4</h3>
          <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13 }}>
            Ghép asset đã sinh &amp; duyệt ở Visual Studio thành 1 video hoàn chỉnh.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={onClose}>
          ← Quay lại
        </button>
      </div>

      {error && (
        <div style={{ fontSize: 13, color: "var(--color-danger)", background: "var(--color-danger-bg)", borderRadius: "var(--radius-sm)", padding: "8px 10px", marginBottom: "var(--space-3)" }}>
          {error}
        </div>
      )}

      {shots.length === 0 ? (
        <div style={{ fontSize: 13, opacity: 0.7, maxWidth: 640 }}>
          Chưa có asset nào — quay lại <strong>Visual Studio</strong> và bấm "Sinh asset (ảnh/video/giọng đọc) cho toàn bộ block" trước.
        </div>
      ) : (
        <div className="card elev-sm" style={{ gap: "var(--space-2)", maxWidth: 640, marginBottom: "var(--space-4)" }}>
          <div className="card-kicker">Tình trạng shot</div>
          <div style={{ fontSize: 13 }}>
            {readyCount}/{shots.length} shot đã sinh xong visual · <strong>{approvedCount}/{shots.length} đã duyệt</strong>
          </div>
          {!allApproved && (
            <div style={{ fontSize: 11.5, opacity: 0.65 }}>Cần sinh xong + bấm "Duyệt" cho MỌI shot ở Visual Studio trước khi ghép được.</div>
          )}
        </div>
      )}

      {state?.assembly_status === "done" && state.final_video_path ? (
        <div className="card elev-sm" style={{ gap: "var(--space-2)", maxWidth: 640 }}>
          <div className="card-title">Video hoàn chỉnh</div>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video controls style={{ width: "100%", borderRadius: "var(--radius-sm)" }} src={api.renderDownloadUrl(project.id)} />
          <a className="btn btn-primary btn-block" href={api.renderDownloadUrl(project.id)} target="_blank" rel="noreferrer">
            Tải MP4
          </a>
        </div>
      ) : (
        <button className="btn btn-primary" onClick={assemble} disabled={!allApproved || assembling || isAssembling}>
          {isAssembling ? "Đang ghép video..." : "Ghép MP4"}
        </button>
      )}
      {state?.assembly_status === "error" && state.assembly_error && (
        <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 6, maxWidth: 640 }}>{state.assembly_error}</div>
      )}
    </div>
  );
}
