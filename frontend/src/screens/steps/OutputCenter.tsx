import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { ProductionPack, ProjectSummary, RetentionOut, YoutubeVideoAvailable } from "../../api/types";
import AddToLibraryButton from "../../components/AddToLibraryButton";
import Lightbox, { ExpandButton } from "../../components/Lightbox";
import LibraryPicker from "../../components/LibraryPicker";
import StepHeader from "../../components/StepHeader";
import type { StepProps } from "../ProjectView";
import RenderStudio from "./RenderStudio";
import ShortVideoExportCard from "./ShortVideoExportCard";

// **Đổi (2026-08-26), theo yêu cầu người dùng**: bỏ hẳn "Output A" (export spec/prompts
// dạng markdown/JSON máy đọc — ít dùng thực tế, đã có JSON pack.json sẵn trên đĩa cho ai
// cần đọc trực tiếp). "Output B" (Render in-app) không còn núp sau nút "Mở Render
// Studio" nữa — hiển thị THẲNG (xem RenderStudio.tsx). Thêm mới "Xuất Pack": đóng gói
// TOÀN BỘ nội dung video (transcript SRT, asset ảnh/video từng shot, giọng đọc ghép full,
// video đã ghép nếu có) ra 1 folder trên máy local người dùng tự chọn — xem
// app/render/pack_export.py cho phần backend.
export default function OutputCenter({ project, pack, refresh }: StepProps) {
  return (
    <div>
      {/* Đổi (2026-08-23, theo đề xuất rà soát UX) — trước đây tự viết <h3>/<p> riêng,
          KHÔNG dùng chung StepHeader như 3 màn kia (Brief/Script Studio/Visual Studio),
          khiến "phong cách trang" đổi khác không lý do ở đúng màn cuối cùng của luồng. */}
      <StepHeader title="Output Center" description="Ghép video &amp; xuất toàn bộ nội dung ra máy local." />

      {/* Thẻ Thumbnail — chuyển từ Visual Studio sang ĐẦU Output Center (2026-09-02, theo
          yêu cầu người dùng: thumbnail chỉ dùng lúc xuất video lên YouTube, thuộc bước
          Output hơn là Visual Studio — không đụng gì tới sinh ảnh/video từng shot). */}
      <div style={{ marginBottom: "var(--space-6)" }}>
        <ThumbnailCard project={project} pack={pack} refresh={refresh} />
      </div>

      <div style={{ marginBottom: "var(--space-6)" }}>
        <PackExportCard projectId={project.id} hasShots={(pack.shots || []).length > 0} />
      </div>

      <div style={{ marginBottom: "var(--space-6)" }}>
        <RenderStudio project={project} pack={pack} />
      </div>

      <div style={{ marginBottom: "var(--space-6)" }}>
        <ShortVideoExportCard project={project} />
      </div>

      <RetentionCard project={project} />
    </div>
  );
}

/** Thẻ Thumbnail — chuyển từ Pack Review sang Visual Studio (2026-08-16), rồi sang ĐẦU
 * Output Center (2026-09-02, theo yêu cầu người dùng: thumbnail phục vụ lúc XUẤT video
 * lên YouTube, đúng ngữ cảnh bước Output hơn Visual Studio). Cho phép cả 2 đường: sinh
 * bằng AI (cần mô tả + provider image) hoặc upload ảnh có sẵn từ máy (không cần provider,
 * không cần mô tả) — không ảnh hưởng tới việc sinh ảnh/video từng shot. TRƯỚC ĐÂY (mục 18
 * IMPLEMENTATION_REPORT.md) ảnh này bắt buộc phải duyệt vì đóng vai trò "anchor" img2img
 * cho mọi shot (Tier 2) — TẮT lại 2026-08-16: verify qua GPU cho thấy khi Thumbnail là
 * ảnh nhiều chi tiết đồ hoạ (bản đồ minh hoạ, không phải ảnh chụp/nhân vật đơn giản), cơ
 * chế này đè mất nội dung riêng từng shot ở mọi mức denoise thử qua — xem mục 20. */
const DEFAULT_YOUTUBE_META = {
  thumbnail_description: "",
  thumbnail_status: "pending" as const, thumbnail_asset_path: null, thumbnail_provider: null, thumbnail_error: null, thumbnail_approved: false,
};

function ThumbnailCard({ project, pack, refresh }: { project: ProjectSummary; pack: ProductionPack; refresh: () => Promise<void> }) {
  const ym = pack.youtube_meta;
  const [desc, setDesc] = useState(ym?.thumbnail_description || "");
  const [generating, setGenerating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // `api.thumbnailUrl(project.id)` là 1 URL CỐ ĐỊNH (không đổi theo lần sinh/upload) —
  // React chỉ refetch <img> khi giá trị `src` THẬT SỰ đổi, nên ảnh cũ vẫn hiện nguyên dù
  // ảnh mới đã ghi đè xong ở backend (bug người dùng báo: "upload/tạo AI xong ảnh không
  // đổi"). Bump số này sau MỖI lần sinh/upload thành công, gắn vào query string để ép
  // trình duyệt coi là URL mới.
  const [cacheBust, setCacheBust] = useState(0);
  const [lightbox, setLightbox] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    setDesc(ym?.thumbnail_description || "");
  }, [ym?.thumbnail_description]);

  function saveDesc(value: string) {
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      api.patchPack(project.id, { youtube_meta: { ...(ym || DEFAULT_YOUTUBE_META), thumbnail_description: value } });
    }, 500);
  }

  async function generate() {
    setGenerating(true);
    setError(null);
    try {
      await api.patchPack(project.id, { youtube_meta: { ...(ym || DEFAULT_YOUTUBE_META), thumbnail_description: desc } });
      await api.generateThumbnail(project.id);
      await refresh();
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi sinh ảnh thumbnail.");
    } finally {
      setGenerating(false);
    }
  }

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      await api.uploadThumbnail(project.id, file);
      await refresh();
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload ảnh thumbnail.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function toggleApprove() {
    setApproving(true);
    setError(null);
    try {
      await api.approveThumbnail(project.id, !ym?.thumbnail_approved);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi duyệt thumbnail.");
    } finally {
      setApproving(false);
    }
  }

  const ready = ym?.thumbnail_status === "ready";
  const approved = !!ym?.thumbnail_approved;
  const thumbUrl = `${api.thumbnailUrl(project.id)}?v=${cacheBust}`;

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Thumbnail {approved && <span className="tag tag-accent" style={{ marginLeft: 6 }}>Đã duyệt</span>}
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.6 }}>Dùng khi xuất video lên YouTube — không ảnh hưởng tới ảnh/video từng shot</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "var(--space-3)", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ position: "relative", height: 124, borderRadius: "var(--radius-sm)", background: "var(--color-bg)", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
            {ready ? (
              <>
                <ExpandButton onClick={() => setLightbox(true)} />
                <img alt="Thumbnail" src={thumbUrl} style={{ width: "100%", height: "100%", objectFit: "cover", cursor: "zoom-in" }} onClick={() => setLightbox(true)} />
              </>
            ) : (
              <span style={{ fontSize: 11, opacity: 0.55, textAlign: "center", padding: 6 }}>{ym?.thumbnail_status === "generating" ? "Đang sinh ảnh…" : "Chưa có ảnh thumbnail"}</span>
            )}
          </div>
          {lightbox && <Lightbox src={thumbUrl} kind="image" onClose={() => setLightbox(false)} />}
          {ready && <AddToLibraryButton kind="image" sourceUrl={thumbUrl} name="thumbnail" />}
          <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px" }} onClick={generate} disabled={generating || uploading || !desc.trim()}>
            {generating ? "Đang tạo..." : "Tạo bằng AI"}
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload(f);
            }}
          />
          <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 8px" }} onClick={() => fileRef.current?.click()} disabled={generating || uploading}>
            {uploading ? "Đang tải lên..." : "Upload ảnh từ máy"}
          </button>
          <LibraryPicker kinds={["image"]} disabled={generating || uploading} onPick={upload} />
          <button className="btn btn-primary" style={{ fontSize: 12, padding: "5px 8px" }} onClick={toggleApprove} disabled={approving || (!ready && !approved)}>
            {approving ? "Đang lưu..." : approved ? "Bỏ duyệt" : "Duyệt"}
          </button>
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>Mô tả thumbnail (prompt tạo ảnh bằng AI — không cần điền nếu chỉ upload tay)</label>
          <textarea
            className="input"
            rows={3}
            style={{ fontSize: 13 }}
            value={desc}
            onChange={(e) => {
              setDesc(e.target.value);
              saveDesc(e.target.value);
            }}
          />
          {error && <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 4 }}>{error}</div>}
          {ym?.thumbnail_status === "error" && !error && <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 4 }}>{ym.thumbnail_error}</div>}
        </div>
      </div>
    </div>
  );
}

type ExportResult = { dest_dir: string; included: string[]; skipped: { item: string; reason: string }[] };

function PackExportCard({ projectId, hasShots }: { projectId: string; hasShots: boolean }) {
  const [destDir, setDestDir] = useState("");
  const [exporting, setExporting] = useState(false);
  const [result, setResult] = useState<ExportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // `window.studioflowNative` CHỈ có khi chạy trong Electron (xem electron/src/preload.ts)
  // — chạy dev server thuần trình duyệt fallback về ô nhập đường dẫn tay.
  const hasNativePicker = typeof window !== "undefined" && !!window.studioflowNative;

  async function chooseFolder() {
    if (!window.studioflowNative) return;
    const picked = await window.studioflowNative.chooseFolder();
    if (picked) setDestDir(picked);
  }

  async function doExport() {
    setExporting(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.exportPackBundle(projectId, destDir));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi xuất Pack.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-2)", maxWidth: 640 }}>
      <div className="card-kicker">Xuất Pack</div>
      <div className="card-title">Xuất toàn bộ nội dung ra máy local</div>
      <div className="card-body">
        Đóng gói transcript (SRT), bộ ảnh/video từng shot, giọng đọc ghép full (mp3) và video đã ghép (nếu có) ra 1 thư mục bạn chọn.
      </div>

      {!hasShots ? (
        <div style={{ fontSize: 12.5, opacity: 0.7 }}>Chưa có shot — hoàn tất Visual Studio trước.</div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 6 }}>
            {hasNativePicker ? (
              <>
                <input className="input" style={{ flex: 1 }} readOnly placeholder="Chưa chọn thư mục đích" value={destDir} />
                <button className="btn btn-secondary" onClick={chooseFolder}>
                  Chọn thư mục...
                </button>
              </>
            ) : (
              <input
                className="input"
                style={{ flex: 1 }}
                placeholder="Nhập đường dẫn thư mục đích (VD: D:\Xuất video)"
                value={destDir}
                onChange={(e) => setDestDir(e.target.value)}
              />
            )}
          </div>
          <button className="btn btn-primary btn-block" onClick={doExport} disabled={!destDir.trim() || exporting}>
            {exporting ? "Đang xuất..." : "Xuất Pack"}
          </button>
        </>
      )}

      {error && (
        <div style={{ fontSize: 12.5, color: "var(--color-danger)", background: "var(--color-danger-bg)", borderRadius: "var(--radius-sm)", padding: "6px 8px" }}>
          {error}
        </div>
      )}

      {result && (
        <div style={{ fontSize: 12.5, marginTop: 4 }}>
          <div style={{ opacity: 0.8, marginBottom: 4 }}>
            Đã xuất vào <strong>{result.dest_dir}</strong>:
          </div>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {result.included.map((item) => (
              <li key={item} style={{ color: "var(--color-accent)" }}>
                ✓ {item}
              </li>
            ))}
            {result.skipped.map((s) => (
              <li key={s.item} style={{ opacity: 0.65 }}>
                ⊘ {s.item} — {s.reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function RetentionCard({ project }: { project: ProjectSummary }) {
  const [data, setData] = useState<RetentionOut | null>(null);
  const [form, setForm] = useState({ published_at: "", ret_0: "", ret_25: "", ret_50: "", ret_100: "", avg_view_duration: "", thumbnail_ctr: "", rpm: "" });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getRetention(project.id).then(setData);
  }, [project.id]);

  async function save() {
    setSaving(true);
    try {
      const body: Record<string, number | string | null> = { published_at: form.published_at || null };
      for (const k of ["ret_0", "ret_25", "ret_50", "ret_100", "avg_view_duration", "thumbnail_ctr", "rpm"] as const) {
        body[k] = form[k] === "" ? null : parseFloat(form[k]);
      }
      const r = await api.putRetention(project.id, body);
      setData(r);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card elev-sm" style={{ maxWidth: 560, gap: "var(--space-3)" }}>
      <div className="card-kicker">Retention nạp thủ công</div>
      <div style={{ fontSize: 13, opacity: 0.75, marginTop: -4 }}>
        Các chỉ số khác (APV, retention giây 30, CTR, bình luận...) có thể kéo tự động từ YouTube ở Dashboard → kênh → tab "Chỉ số YouTube" (cần liên kết video bên dưới trước). RPM (doanh thu) luôn cần nhập tay.
      </div>

      <YoutubeVideoLinkPicker project={project} />

      <div className="hr" style={{ margin: "var(--space-1) 0" }} />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "var(--space-2)" }}>
        <NumField label="Ret. 0% (Hook)" value={form.ret_0} onChange={(v) => setForm((f) => ({ ...f, ret_0: v }))} />
        <NumField label="Ret. 25%" value={form.ret_25} onChange={(v) => setForm((f) => ({ ...f, ret_25: v }))} />
        <NumField label="Ret. 50%" value={form.ret_50} onChange={(v) => setForm((f) => ({ ...f, ret_50: v }))} />
        <NumField label="Ret. 100%" value={form.ret_100} onChange={(v) => setForm((f) => ({ ...f, ret_100: v }))} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--space-2)" }}>
        <NumField label="AVD (giây)" value={form.avg_view_duration} onChange={(v) => setForm((f) => ({ ...f, avg_view_duration: v }))} />
        <NumField label="Thumbnail CTR (%)" value={form.thumbnail_ctr} onChange={(v) => setForm((f) => ({ ...f, thumbnail_ctr: v }))} />
        <div className="field" style={{ margin: 0 }}>
          <label>Ngày đăng</label>
          <input className="input" type="date" value={form.published_at} onChange={(e) => setForm((f) => ({ ...f, published_at: e.target.value }))} />
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "var(--space-2)" }}>
        <NumField label="RPM (€ / 1.000 view — luôn nhập tay)" value={form.rpm} onChange={(v) => setForm((f) => ({ ...f, rpm: v }))} />
      </div>
      <button className="btn btn-secondary" style={{ alignSelf: "flex-start" }} onClick={save} disabled={saving}>
        {saving ? "Đang lưu..." : "Lưu số liệu"}
      </button>

      {data?.entry && (
        <div style={{ marginTop: "var(--space-2)" }}>
          <div className="hr" style={{ margin: "var(--space-2) 0" }} />
          <div style={{ fontSize: 12, opacity: 0.8 }}>
            Retention tại Hook thực tế: <strong>{data.entry.ret_0 ?? "—"}%</strong> · Benchmark kênh: <strong>{data.target_hook_strength != null ? Math.round(data.target_hook_strength * 100) : "—"}%</strong>
          </div>
          {data.diff_vs_benchmark != null && (
            <div style={{ height: 6, borderRadius: 4, background: "var(--color-neutral-800)", marginTop: 6, overflow: "hidden", position: "relative" }}>
              <div
                style={{
                  height: "100%",
                  width: `${Math.min(100, Math.max(0, 50 + data.diff_vs_benchmark * 100))}%`,
                  background: data.diff_vs_benchmark >= 0 ? "var(--color-accent)" : "var(--color-danger)",
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Chọn/đổi video YouTube tương ứng project này — **mới (2026-09-12)**. Luôn là lựa
 * chọn CHỦ ĐỘNG của người dùng (KHÔNG tự đoán theo tên trùng khớp), theo CLAUDE.md
 * nguyên tắc 3. Cần kênh đã kết nối OAuth ở Settings trước (nếu chưa, danh sách rỗng). */
function YoutubeVideoLinkPicker({ project }: { project: ProjectSummary }) {
  const [videos, setVideos] = useState<YoutubeVideoAvailable[] | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(project.youtube_video_id);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .getYoutubeVideosAvailable(project.id)
      .then((r) => {
        setVideos(r.videos);
        setCurrentId(r.current_video_id);
      })
      .catch(() => setVideos([]));
  }, [project.id]);

  async function onChange(videoId: string) {
    setSaving(true);
    try {
      const r = await api.patchYoutubeLink(project.id, videoId || null);
      setCurrentId(r.youtube_video_id);
    } finally {
      setSaving(false);
    }
  }

  if (videos === null) return null;

  return (
    <div className="field" style={{ margin: 0 }}>
      <label>Video YouTube tương ứng</label>
      <select className="input" value={currentId || ""} onChange={(e) => onChange(e.target.value)} disabled={saving}>
        <option value="">— Chưa liên kết —</option>
        {videos.map((v) => (
          <option key={v.video_id} value={v.video_id}>
            {v.title}
          </option>
        ))}
      </select>
      {videos.length === 0 && <div style={{ fontSize: 11.5, opacity: 0.6, marginTop: 4 }}>Kênh chưa kết nối YouTube, hoặc chưa có video nào — kết nối ở Dashboard → kênh → tab "Chỉ số YouTube".</div>}
    </div>
  );
}

function NumField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="field" style={{ margin: 0 }}>
      <label>{label}</label>
      <input className="input" type="number" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
