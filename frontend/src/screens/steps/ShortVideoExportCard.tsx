import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { NarrationLanguage, ProjectSummary, RenderState, ShortVideoExport } from "../../api/types";
import { NARRATION_LANGUAGES, NARRATION_LANGUAGE_LABELS } from "../../api/types";

const MAX_SHORT_EXPORTS = 3;

const STATUS_LABEL: Record<ShortVideoExport["status"], string> = {
  pending: "Đang chờ bắt đầu...",
  generating_images: "Đang sinh ảnh theo tỷ lệ 9:16...",
  assembling: "Đang ghép video...",
  done: "Đã xong",
  error: "Lỗi",
};

/** Xuất short-video 9:16 từ 1 khoảng block — mới (2026-09-12), theo yêu cầu người dùng:
 * repurpose 1 đoạn của project long-form thành YouTube Shorts/TikTok mà KHÔNG cần tạo 1
 * project short-form riêng (khác hẳn `Project.format==="short"`/`parent_project_id`, đó
 * là 1 project TRỐNG hoàn toàn). Artifact này sống NGAY trong `RenderState.short_exports`
 * của CHÍNH project long-form đang xem — tối đa 3 cái/project, hiển thị ĐẦY ĐỦ cả 3 để
 * xem lại bất kỳ lúc nào. Poll `render/status` RIÊNG (độc lập với `RenderStudio.tsx`, dù
 * cùng đọc chung `RenderState`) — chỉ bật vòng poll khi có export đang chạy dở, cùng
 * pattern `RenderStudio.tsx` đã dùng cho `assembly_progress`. */
export default function ShortVideoExportCard({ project }: { project: ProjectSummary }) {
  const [state, setState] = useState<RenderState | null>(null);
  const [startBlockId, setStartBlockId] = useState("");
  const [endBlockId, setEndBlockId] = useState("");
  const [regenerateImages, setRegenerateImages] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | undefined>(undefined);
  // Ngôn ngữ giọng đọc xuất short-video — mới (2026-09-12, theo yêu cầu người dùng "cho
  // phép chọn ngôn ngữ khi xuất short-video, tương tự như khi render long-video"). Mặc
  // định ngôn ngữ CHÍNH của kênh — cùng pattern `RenderStudio.tsx` (`lang` khởi tạo
  // `null` rồi tự set = primaryLanguage NGAY SAU KHI fetch xong, không đè lựa chọn người
  // dùng tự đổi sau đó). Backend tự chặn 400 (kèm thông điệp shot nào thiếu) nếu giọng
  // đọc ngôn ngữ chọn chưa sinh xong cho shot trong khoảng — không precompute lại ở đây
  // (cần thêm `pack.shots` + logic cắt khoảng block trùng backend, không đáng cho 1 cảnh
  // báo sớm khi lỗi 400 đã đủ rõ).
  const [lang, setLang] = useState<NarrationLanguage | null>(null);
  const [primaryLanguage, setPrimaryLanguage] = useState<NarrationLanguage>("vi");

  async function load() {
    try {
      setState(await api.getRenderStatus(project.id));
    } catch {
      // im lặng — RenderStudio (cùng màn Output Center) đã báo lỗi tải trạng thái chung
      // nếu có, không cần lặp lại thông báo ở đây.
    }
  }

  useEffect(() => {
    load();
    api.getBrandProfile(project.channel_id).then((bp) => {
      const primary = bp.primary_language || "vi";
      setPrimaryLanguage(primary);
      setLang((l) => (l == null ? primary : l));
    }, () => {} /* BrandProfile luôn tồn tại — lỗi mạng hiếm gặp, giữ mặc định "vi" */);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  const exports = state?.short_exports || [];
  const hasActive = exports.some((e) => e.status === "pending" || e.status === "generating_images" || e.status === "assembling");

  useEffect(() => {
    window.clearInterval(pollRef.current);
    if (hasActive) {
      pollRef.current = window.setInterval(load, 2000);
    }
    return () => window.clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasActive]);

  async function create() {
    setCreating(true);
    setError(null);
    try {
      await api.createShortExport(project.id, { start_block_id: startBlockId.trim(), end_block_id: endBlockId.trim(), regenerate_images: regenerateImages, lang });
      setStartBlockId("");
      setEndBlockId("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi xuất short-video.");
    } finally {
      setCreating(false);
      // Đọc lại NGAY thay vì tin response — response tạo lúc entry còn "pending" (BackgroundTasks
      // chạy SAU khi response đã dựng xong ở backend thật, xem docstring test tương ứng).
      load();
    }
  }

  async function remove(exportId: string) {
    if (!window.confirm("Xoá short-video này? Không thể hoàn tác.")) return;
    try {
      setState(await api.deleteShortExport(project.id, exportId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi xoá short-video.");
    }
  }

  const atCap = exports.length >= MAX_SHORT_EXPORTS;

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 640 }}>
      <div className="card-kicker">Xuất short-video (9:16)</div>
      <div className="card-title">Xuất short-video ({exports.length}/{MAX_SHORT_EXPORTS})</div>
      <div className="card-body">
        Chọn 1 khoảng block để xuất riêng thành video DỌC (YouTube Shorts/TikTok) — dùng ảnh 16:9 gốc (crop 2 bên cho khớp khung dọc, không co nhỏ nội dung) hoặc sinh lại ảnh đúng tỷ lệ 9:16. Shot dạng video luôn giữ nguyên bản gốc + crop cùng kiểu.
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-2)" }}>
        <div className="field" style={{ margin: 0 }}>
          <label>Mã block đầu</label>
          <input className="input" placeholder="VD: B01" value={startBlockId} onChange={(e) => setStartBlockId(e.target.value)} disabled={atCap || creating} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>Mã block cuối</label>
          <input className="input" placeholder="VD: B05" value={endBlockId} onChange={(e) => setEndBlockId(e.target.value)} disabled={atCap || creating} />
        </div>
      </div>
      <div className="field" style={{ margin: 0 }}>
        <label>Ngôn ngữ giọng đọc</label>
        <select className="input" value={lang || primaryLanguage} onChange={(e) => setLang(e.target.value as NarrationLanguage)} disabled={atCap || creating}>
          {NARRATION_LANGUAGES.map((l) => (
            <option key={l} value={l}>
              {NARRATION_LANGUAGE_LABELS[l]}
              {l === primaryLanguage ? " (ngôn ngữ chính của kênh)" : ""}
            </option>
          ))}
        </select>
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
        <input type="checkbox" checked={regenerateImages} onChange={(e) => setRegenerateImages(e.target.checked)} disabled={atCap || creating} />
        Sinh lại ảnh theo tỷ lệ 9:16 (thay vì giữ ảnh 16:9 gốc + crop)
      </label>
      <button
        className="btn btn-primary btn-block"
        onClick={create}
        disabled={creating || atCap || !startBlockId.trim() || !endBlockId.trim()}
        title={atCap ? "Đã đủ 3 short-video — xoá bớt 1 cái trước khi xuất thêm" : undefined}
      >
        {creating ? "Đang tạo..." : atCap ? "Đã đủ 3 short-video — xoá bớt để xuất thêm" : `Xuất short video (${exports.length}/${MAX_SHORT_EXPORTS})`}
      </button>

      {error && (
        <div style={{ fontSize: 12.5, color: "var(--color-danger)", background: "var(--color-danger-bg)", borderRadius: "var(--radius-sm)", padding: "6px 8px" }}>
          {error}
        </div>
      )}

      {exports.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", marginTop: 4 }}>
          {exports.map((exp) => (
            <ShortVideoExportRow key={exp.id} project={project} exportItem={exp} onDelete={() => remove(exp.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function ShortVideoExportRow({ project, exportItem, onDelete }: { project: ProjectSummary; exportItem: ShortVideoExport; onDelete: () => void }) {
  const pct = exportItem.progress_total ? Math.round(((exportItem.progress_current || 0) / exportItem.progress_total) * 100) : null;
  return (
    <div style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)", padding: "var(--space-2)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <strong style={{ fontSize: 13 }}>
          {exportItem.start_block_id} → {exportItem.end_block_id}
          {exportItem.lang && <span style={{ opacity: 0.6, fontWeight: 400 }}> · {NARRATION_LANGUAGE_LABELS[exportItem.lang]}</span>}
        </strong>
        <button className="btn btn-secondary" style={{ fontSize: 11, padding: "3px 8px" }} onClick={onDelete}>
          Xoá
        </button>
      </div>

      {exportItem.status === "done" && exportItem.video_path ? (
        <>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video
            controls
            style={{ maxHeight: "70vh", maxWidth: "100%", width: "auto", display: "block", margin: "0 auto", borderRadius: "var(--radius-sm)" }}
            src={api.shortExportDownloadUrl(project.id, exportItem.id)}
          />
          <button
            className="btn btn-primary btn-block"
            style={{ marginTop: 6 }}
            onClick={() => api.downloadShortExport(project.id, exportItem.id, exportItem.start_block_id, exportItem.end_block_id, exportItem.lang || "vi")}
          >
            Tải video
          </button>
        </>
      ) : exportItem.status === "error" ? (
        <div style={{ fontSize: 12.5, color: "var(--color-danger)" }}>{exportItem.error || "Có lỗi khi xuất short-video."}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ fontSize: 12.5 }}>
            {exportItem.progress_label || STATUS_LABEL[exportItem.status]}
            {pct != null ? ` (${exportItem.progress_current}/${exportItem.progress_total})` : ""}
          </div>
          <div style={{ height: 6, borderRadius: 999, background: "var(--color-neutral-800)", overflow: "hidden" }}>
            <div style={{ height: "100%", borderRadius: 999, background: "var(--color-accent)", transition: "width 0.4s ease", width: pct != null ? `${pct}%` : "30%" }} />
          </div>
        </div>
      )}
    </div>
  );
}
