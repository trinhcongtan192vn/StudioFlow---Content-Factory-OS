import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { BgMusicOverride, GpuStatus, IntroAssetStatus, OverlayEffectOverride, ProductionPack, ProjectSummary, RenderState, Shot, ShotRenderStatus } from "../../api/types";
import AddToLibraryButton from "../../components/AddToLibraryButton";
import AiErrorBanner from "../../components/AiErrorBanner";
import Lightbox, { ExpandButton } from "../../components/Lightbox";
import LibraryPicker from "../../components/LibraryPicker";
import { computeEstimatedStats } from "../../components/packStats";
import StatsBar from "../../components/StatsBar";
import StepHeader from "../../components/StepHeader";
import type { StepProps } from "../ProjectView";

// Thời lượng thật đo được trên GPU local (RTX 5060 Ti, xem IMPLEMENTATION_REPORT.md
// mục 16.6c) — chỉ để hiện gợi ý ước lượng cho người dùng đỡ sốt ruột, KHÔNG phải cam
// kết chính xác (máy khác/tải khác sẽ khác nhiều).
const ESTIMATED_SEC = { image: 30, video: 12 * 60 };

// Khớp `backend/app/render/transitions.py::TRANSITIONS` (nguồn sự thật duy nhất —
// đổi 1 bên thì đổi cả 2, backend validate lại giá trị nên gửi sai sẽ bị 400 rõ ràng,
// không âm thầm sai) — chọn transition giữa shot này và shot KẾ TIẾP (2026-08-17, theo
// yêu cầu người dùng ở Visual Studio, tránh ghép video toàn cắt cứng nhàm chán).
const TRANSITION_OPTIONS: { value: string; label: string }[] = [
  { value: "cut", label: "Cắt cứng (mặc định)" },
  { value: "fade", label: "Hoà tan (crossfade mượt)" },
  { value: "fadeblack", label: "Mờ qua đen" },
  { value: "dissolve", label: "Tan dần" },
  { value: "wipeleft", label: "Gạt trái" },
  { value: "wiperight", label: "Gạt phải" },
  { value: "smoothleft", label: "Trượt mượt trái" },
  { value: "smoothright", label: "Trượt mượt phải" },
];

// Khớp `backend/app/render/camera_motion.py::CAMERA_MOTIONS` (nguồn sự thật duy nhất)
// — hiệu ứng Ken Burns cho ẢNH tĩnh (2026-08-19, theo yêu cầu người dùng). CHỈ hiện khi
// shot là "image" (video đã có chuyển động thật sẵn, xem điều kiện render dưới).
const CAMERA_MOTION_OPTIONS: { value: string; label: string }[] = [
  { value: "none", label: "Không hiệu ứng (mặc định)" },
  { value: "zoom_in", label: "Phóng to (Zoom in)" },
  { value: "zoom_out", label: "Thu nhỏ (Zoom out)" },
  { value: "pan_left", label: "Trượt trái (Pan left)" },
  { value: "pan_right", label: "Trượt phải (Pan right)" },
  { value: "tilt_up", label: "Trượt lên (Tilt up)" },
  { value: "tilt_down", label: "Trượt xuống (Tilt down)" },
  { value: "roll", label: "Xoay nhẹ (Roll)" },
  { value: "orbit", label: "Lượn quanh chủ thể (Orbit)" },
];

function formatElapsed(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return m > 0 ? `${m} phút ${s}s` : `${s}s`;
}

// Short-form (9:16) — mới (2026-08-21): cột preview 220px/box 124px vốn tính cho khung
// NGANG 16:9 — project short-form đổi sang cột hẹp hơn + box cao hơn để khớp tỷ lệ dọc,
// tránh box vuông/ngang trông sai lệch rõ khi ảnh/video thật sự là 9:16. Dùng chung cho
// ShotCard/IntroShotCard (ThumbnailCard giữ nguyên 16:9 — thumbnail YouTube LUÔN ngang
// bất kể project long/short).
function previewColWidth(isVertical: boolean): number {
  return isVertical ? 140 : 220;
}
function previewBoxHeight(isVertical: boolean): number {
  return isVertical ? 249 : 124; // 140 * 16/9 ≈ 249 — giữ đúng tỷ lệ 9:16 cho box placeholder
}

export default function VisualStudio({ project, pack, refresh, busy, setBusy }: StepProps) {
  const [aiError, setAiError] = useState<string | null>(null);
  const [renderState, setRenderState] = useState<RenderState | null>(null);
  const [gpuStatus, setGpuStatus] = useState<GpuStatus | null>(null);
  const [startingRender, setStartingRender] = useState(false);
  const [cancellingRender, setCancellingRender] = useState(false);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const pollRef = useRef<number | undefined>(undefined);
  const tickRef = useRef<number | undefined>(undefined);
  const body = pack.script?.body || [];

  function describeAiError(e: unknown, fallback: string): string {
    return e instanceof ApiError ? e.message : fallback;
  }

  async function loadRenderStatus() {
    try {
      setRenderState(await api.getRenderStatus(project.id));
    } catch {
      /* chưa từng sinh asset — bỏ qua, hiện trạng thái "chưa sinh" mặc định */
    }
    try {
      setGpuStatus(await api.getGpuStatus(project.id));
    } catch {
      /* thông tin phụ trợ — lỗi thì bỏ qua, không hiện gì thay vì chặn màn hình chính */
    }
  }

  useEffect(() => {
    loadRenderStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  const hasInFlight = !!renderState && renderState.shots.some((s) => s.visual_status === "generating" || s.narration_status === "generating");
  const pendingApprovalCount = renderState ? renderState.shots.filter((s) => s.visual_status === "ready" && !s.approved).length : 0;

  useEffect(() => {
    window.clearInterval(pollRef.current);
    if (hasInFlight) {
      pollRef.current = window.setInterval(loadRenderStatus, 3000);
    }
    return () => window.clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasInFlight]);

  // Đồng hồ đếm giây riêng (tick 1s) — độc lập với vòng poll 3s ở trên, để hiển thị
  // thời gian đã trôi mượt hơn thay vì nhảy cách quãng 3 giây 1 lần.
  useEffect(() => {
    window.clearInterval(tickRef.current);
    if (hasInFlight) {
      tickRef.current = window.setInterval(() => setNowTick(Date.now()), 1000);
    }
    return () => window.clearInterval(tickRef.current);
  }, [hasInFlight]);

  function statusFor(shotId: string): ShotRenderStatus | undefined {
    return renderState?.shots.find((s) => s.shot_id === shotId);
  }

  function snippetFor(ts: number | null) {
    return body.find((b) => b.timestamp_sec === ts)?.audio || "";
  }

  async function patchShot(shotId: string, patch: Partial<{ visual_fx: string; audio_sfx: string; visual_type: string; transition_to_next: string; camera_motion: string }>) {
    await api.patchShot(project.id, shotId, patch);
    await refresh();
  }

  async function toggleType(shotId: string, current: string) {
    const next = current === "image" ? "video" : "image";
    await api.patchShot(project.id, shotId, { visual_type: next });
    await refresh();
  }

  async function startAssetGeneration(kind: "both" | "visual" | "narration" = "both", force = false) {
    setStartingRender(true);
    setAiError(null);
    try {
      setRenderState(await api.startRender(project.id, kind, force));
      // BackgroundTasks (FastAPI) chỉ thực sự chạy SAU KHI response HTTP này đã trả
      // về — state vừa nhận được vẫn là "trước khi sinh" (pending/error cũ), nên
      // hasInFlight tính từ nó là false → useEffect bên dưới KHÔNG tự bật vòng poll,
      // UI đứng im dù nền đã bắt đầu chạy thật (chỉ đổi khi có việc khác kích lại, VD
      // điều hướng đi/về). Giữ nút ở trạng thái "Đang sinh asset..." (startingRender)
      // qua 1 nhịp chờ ngắn rồi poll lại — bắt kịp trạng thái "generating" đầu tiên,
      // từ đó vòng poll 3s (dựa trên hasInFlight) tự tiếp quản, không cần giữ tay nữa.
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
      await loadRenderStatus();
      window.setTimeout(loadRenderStatus, 3000); // phòng khi nền vẫn chưa kịp cập nhật ở nhịp trên
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi bắt đầu sinh asset."));
    } finally {
      setStartingRender(false);
    }
  }

  async function cancelAssetGeneration() {
    setCancellingRender(true);
    setAiError(null);
    try {
      setRenderState(await api.cancelRender(project.id));
      // Job GPU local (nếu có) bị /interrupt ngay ở backend, nhưng shot ĐANG "generating"
      // cần 1 nhịp để vòng lặp nền nhận ra cờ huỷ + ghi lại trạng thái cuối (error/ready)
      // — poll lại sau đó để phản ánh đúng, không hiện "generating" treo mãi.
      window.setTimeout(loadRenderStatus, 1200);
      window.setTimeout(loadRenderStatus, 3000);
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi dừng sinh asset."));
    } finally {
      setCancellingRender(false);
    }
  }

  // URL asset/shot (`api.renderShotAssetUrl`) là CỐ ĐỊNH theo shot_id+kind — browser
  // chỉ refetch <img>/<video> khi `src` THẬT SỰ đổi chuỗi. Sinh lại bằng AI (đè cùng
  // đuôi .png/.mp4) hoặc upload (đè cùng shot_id) đều có thể giữ NGUYÊN URL, ảnh/video
  // cũ vẫn hiện dù file trên đĩa đã đổi — cùng bug đã fix cho Thumbnail (`ThumbnailCard`
  // bên dưới), giờ áp dụng thêm cho từng shot. Đếm riêng theo shot_id, bump sau MỖI lần
  // sinh lại/upload thành công, gắn vào query string ép browser coi là URL mới.
  const [shotCacheBust, setShotCacheBust] = useState<Record<string, number>>({});
  function bumpShotCacheBust(shotId: string) {
    setShotCacheBust((prev) => ({ ...prev, [shotId]: (prev[shotId] || 0) + 1 }));
  }

  async function regenVisualAsset(shotId: string) {
    setAiError(null);
    try {
      setRenderState(await api.regenerateShotVisualAsset(project.id, shotId));
      bumpShotCacheBust(shotId);
      // Cùng lý do ở startAssetGeneration — endpoint này cũng chạy qua BackgroundTasks.
      window.setTimeout(loadRenderStatus, 1200);
      window.setTimeout(loadRenderStatus, 3000);
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi sinh ảnh/video cho shot này."));
    }
  }

  async function uploadVisualAsset(shotId: string, file: File) {
    // KHÔNG dùng aiError (banner đầu trang) cho lỗi upload — banner đó không nêu rõ
    // shot nào, dễ nhầm khi có nhiều thẻ trên màn cùng lúc. ShotCard tự hiện lỗi ngay
    // dưới nút upload của chính nó (xem handleFilePicked) — throw lại để nó bắt được.
    setRenderState(await api.uploadShotVisual(project.id, shotId, file));
    bumpShotCacheBust(shotId);
  }

  async function regenNarrationAsset(shotId: string) {
    setAiError(null);
    try {
      setRenderState(await api.regenerateShotNarration(project.id, shotId));
      // Bug thật người dùng báo (2026-08-21): sinh lại giọng đọc xong (kể cả đổi hẳn
      // sang giọng voice clone ở BrandProfile), preview <audio> vẫn phát bản CŨ — cùng
      // lớp bug cache-bust đã biết (ThumbnailCard/IntroShotCard/ChannelDialog...), trước
      // đây CHỈ bump cho ảnh/video (`uploadVisualAsset`/`regenVisualAsset`), bỏ sót
      // audio narration. URL asset narration CỐ ĐỊNH theo shot_id — bump NGAY (trước cả
      // khi sinh xong) để lần đầu `<audio>` mount lại sau khi `narration_status` chuyển
      // "ready" đã mang query string mới, ép trình duyệt fetch bản thật mới nhất.
      bumpShotCacheBust(shotId);
      window.setTimeout(loadRenderStatus, 1200);
      window.setTimeout(loadRenderStatus, 3000);
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi sinh giọng đọc cho shot này."));
    }
  }

  async function approveAsset(shotId: string) {
    setAiError(null);
    try {
      setRenderState(await api.approveShotAsset(project.id, shotId, true));
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi duyệt shot."));
    }
  }

  const [approvingAll, setApprovingAll] = useState(false);
  async function approveAllAssets() {
    setApprovingAll(true);
    setAiError(null);
    try {
      setRenderState(await api.approveAllShots(project.id));
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi duyệt toàn bộ block."));
    } finally {
      setApprovingAll(false);
    }
  }

  async function goOutput() {
    setBusy(true);
    setAiError(null);
    try {
      // KHÔNG còn Pack Review/Gate #2 (2026-08-17, mục 44) — đi thẳng vào Output,
      // render/assemble và export tự kiểm shot đã sẵn sàng + đã duyệt lúc cần.
      await api.enterOutput(project.id);
      await refresh();
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi chuyển sang Output."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <StepHeader
        title="Visual Studio"
        description={
          <>
            Viết mô tả, sinh ảnh/video và giọng đọc THẬT cho từng shot — theo đúng đoạn script tương ứng. Duyệt shot sau khi sinh xong, ghép MP4 ở Output Center.
            <StatsBar {...computeEstimatedStats(pack)} />
          </>
        }
        actions={
          <>
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "5px 12px" }}
              onClick={() => startAssetGeneration("visual")}
              disabled={startingRender || hasInFlight}
              title="Chỉ sinh ảnh/video cho toàn bộ block — không đụng giọng đọc"
            >
              {startingRender || hasInFlight ? "Đang sinh..." : "Sinh Visual (ảnh/video) cho toàn bộ block"}
            </button>
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "5px 12px" }}
              onClick={() => startAssetGeneration("narration")}
              disabled={startingRender || hasInFlight}
              title="Chỉ sinh giọng đọc cho toàn bộ block — không đụng ảnh/video"
            >
              {startingRender || hasInFlight ? "Đang sinh..." : "Sinh giọng đọc cho toàn bộ block"}
            </button>
            {/* Sinh lại TOÀN BỘ (force) — mới (2026-08-22), theo yêu cầu người dùng: 2 nút
                trên chỉ lấp chỗ pending/error (bỏ qua shot đã ready — tránh tốn phí lại
                khi resume sau lỗi 1 vài shot), không có cách nào sinh lại HÀNG LOẠT shot
                ĐÃ CÓ SẴN asset — cần khi đổi BrandProfile sang giọng/style ảnh mới. Tách
                riêng, màu cảnh báo — hành động này SINH LẠI (tốn phí lại) + BỎ DUYỆT mọi
                shot visual đã ready, khác hẳn 2 nút trên (an toàn, không đụng gì đã có). */}
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "5px 12px", color: "var(--color-danger)" }}
              onClick={() => startAssetGeneration("visual", true)}
              disabled={startingRender || hasInFlight}
              title="Sinh lại TOÀN BỘ ảnh/video cho block, KỂ CẢ shot đã có sẵn — dùng khi vừa đổi BrandProfile sang checkpoint/style mới. Tốn phí/thời gian lại từ đầu, và bỏ duyệt các shot bị sinh lại."
            >
              {startingRender || hasInFlight ? "Đang sinh..." : "Sinh lại TOÀN BỘ Visual (kể cả đã có)"}
            </button>
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "5px 12px", color: "var(--color-danger)" }}
              onClick={() => startAssetGeneration("narration", true)}
              disabled={startingRender || hasInFlight}
              title="Sinh lại TOÀN BỘ giọng đọc cho block, KỂ CẢ shot đã có sẵn — dùng khi vừa đổi BrandProfile sang giọng đọc mới. Tốn phí/thời gian lại từ đầu."
            >
              {startingRender || hasInFlight ? "Đang sinh..." : "Sinh lại TOÀN BỘ giọng đọc (kể cả đã có)"}
            </button>
            {(hasInFlight || startingRender) && (
              <button
                className="btn btn-secondary"
                style={{ fontSize: 12, padding: "5px 12px", color: "var(--color-danger)" }}
                onClick={cancelAssetGeneration}
                disabled={cancellingRender}
                title="Dừng các shot chưa sinh xong — shot đã sinh xong (ready) không bị ảnh hưởng. Shot đang sinh video local sẽ bị dừng ngay tại GPU."
              >
                {cancellingRender ? "Đang dừng..." : "⏹ Dừng"}
              </button>
            )}
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "5px 12px" }}
              onClick={approveAllAssets}
              disabled={approvingAll || pendingApprovalCount === 0}
              title="Duyệt mọi shot đã sinh xong ảnh/video (visual ready) mà chưa duyệt — bỏ qua shot đang sinh hoặc bị lỗi"
            >
              {approvingAll ? "Đang duyệt..." : `Duyệt toàn bộ block${pendingApprovalCount > 0 ? ` (${pendingApprovalCount})` : ""}`}
            </button>
            <button className="btn btn-primary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={goOutput} disabled={busy}>
              {busy ? "Đang chuyển..." : "Đi tới Output →"}
            </button>
          </>
        }
      />

      {aiError && <AiErrorBanner message={aiError} onDismiss={() => setAiError(null)} />}

      <ThumbnailCard project={project} pack={pack} refresh={refresh} />

      <IntroShotCard projectId={project.id} channelId={project.channel_id} intro={renderState?.intro ?? null} refresh={loadRenderStatus} isVertical={project.format === "short"} />

      <BgMusicCard projectId={project.id} bgMusic={renderState?.bg_music ?? null} refresh={loadRenderStatus} />

      <OverlayEffectCard projectId={project.id} overlay={renderState?.overlay ?? null} refresh={loadRenderStatus} />

      {hasInFlight && gpuStatus && (
        <div
          style={{
            display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, padding: "6px 10px", marginBottom: "var(--space-3)", maxWidth: 900,
            borderRadius: "var(--radius-sm)", background: "var(--color-neutral-800)", color: "color-mix(in srgb, var(--color-text) 80%, transparent)",
          }}
        >
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: gpuStatus.reachable ? "var(--color-accent)" : "var(--color-neutral-600)", flex: "none" }} />
          {gpuStatus.reachable
            ? `GPU local (${gpuStatus.gpu_name || "ComfyUI"}) — ${gpuStatus.queue_running} job đang chạy${gpuStatus.queue_pending > 0 ? `, ${gpuStatus.queue_pending} job chờ` : ""}. Video local thường mất 7-18 phút/clip, ảnh ~30 giây — cứ để chạy nền, không cần giữ màn hình.`
            : "Không kết nối được tới GPU local (ComfyUI) để xem tiến trình — asset vẫn có thể đang sinh qua provider khác (cloud)."}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", maxWidth: 900 }}>
        {pack.shots.map((v, i) => (
          <ShotCard
            key={v.shot_id}
            projectId={project.id}
            shot={v}
            isLast={i === pack.shots.length - 1}
            status={statusFor(v.shot_id)}
            snippet={snippetFor(v.linked_timestamp_sec)}
            onToggleType={() => toggleType(v.shot_id, v.visual_type)}
            onPatchShot={(patch) => patchShot(v.shot_id, patch)}
            onGenerateVisualAsset={() => regenVisualAsset(v.shot_id)}
            onGenerateNarrationAsset={() => regenNarrationAsset(v.shot_id)}
            onUploadVisualAsset={(file) => uploadVisualAsset(v.shot_id, file)}
            onApprove={() => approveAsset(v.shot_id)}
            disableGenerate={hasInFlight}
            nowTick={nowTick}
            cacheBust={shotCacheBust[v.shot_id] || 0}
            isVertical={project.format === "short"}
          />
        ))}
      </div>
    </div>
  );
}

function ShotCard({
  projectId,
  shot,
  isLast,
  status,
  snippet,
  onToggleType,
  onPatchShot,
  onGenerateVisualAsset,
  onGenerateNarrationAsset,
  onUploadVisualAsset,
  onApprove,
  disableGenerate,
  nowTick,
  cacheBust,
  isVertical,
}: {
  projectId: string;
  shot: Shot;
  isLast: boolean;
  status: ShotRenderStatus | undefined;
  snippet: string;
  onToggleType: () => void;
  onPatchShot: (patch: Partial<{ visual_fx: string; audio_sfx: string; visual_type: string; transition_to_next: string; camera_motion: string }>) => void;
  onGenerateVisualAsset: () => void;
  onGenerateNarrationAsset: () => void;
  onUploadVisualAsset: (file: File) => Promise<void>;
  onApprove: () => void;
  // true khi BẤT KỲ shot nào trong project đang generate (không chỉ shot này) — chặn
  // bấm "sinh lại" chồng lên batch/shot khác đang chạy nền, tránh 2 BackgroundTasks
  // cùng ghi đè render.json (xem giải thích đầy đủ ở engine.py::_in_progress).
  disableGenerate: boolean;
  nowTick: number; // đồng hồ đếm (ms epoch) tick mỗi 1s khi có shot đang generate — dùng tính thời gian đã trôi, xem VisualStudio component cha.
  cacheBust: number;
  // Short-form (9:16) — mới (2026-08-21): đổi kích thước khung preview cho vừa khung dọc,
  // xem PREVIEW_COL_WIDTH/PREVIEW_BOX_HEIGHT bên dưới.
  isVertical: boolean;
}) {
  const visualStatus = status?.visual_status || "pending";
  const narrationStatus = status?.narration_status || "pending";
  const visualElapsedSec = status?.visual_started_at ? Math.max(0, (nowTick - new Date(status.visual_started_at).getTime()) / 1000) : null;
  const narrationElapsedSec = status?.narration_started_at ? Math.max(0, (nowTick - new Date(status.narration_started_at).getTime()) / 1000) : null;
  const estimatedVisualSec = shot.visual_type === "video" ? ESTIMATED_SEC.video : ESTIMATED_SEC.image;

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function handleFilePicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // cho phép chọn lại đúng file cũ lần sau (input không tự bắn onChange nếu value không đổi)
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      await onUploadVisualAsset(file);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Có lỗi khi upload.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span className="tag tag-neutral" style={{ fontFamily: "ui-monospace,monospace" }}>
          {shot.shot_id} · {shot.linked_timestamp_sec}s
        </span>
        <span className={`tag ${shot.visual_type === "video" ? "tag-accent-2" : "tag-accent"}`} onClick={onToggleType} style={{ cursor: "pointer" }}>
          {shot.visual_type === "video" ? "Video" : "Image"}
        </span>
        <StatusTag label="Visual" status={visualStatus} />
        <StatusTag label="Giọng đọc" status={narrationStatus} />
        {status?.approved && <span className="tag tag-accent">Đã duyệt</span>}
      </div>
      <div style={{ fontSize: 13, opacity: 0.8, padding: 8, background: "var(--color-bg)", borderRadius: "var(--radius-sm)" }}>{snippet}</div>

      <div style={{ display: "grid", gridTemplateColumns: `${previewColWidth(isVertical)}px 1fr`, gap: "var(--space-3)", alignItems: "flex-start" }}>
        <ShotPreview projectId={projectId} shot={shot} status={status} cacheBust={cacheBust} isVertical={isVertical} />
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          <div className="field" style={{ margin: 0 }}>
            <label>Hình ảnh &amp; Hiệu ứng (Visual/FX)</label>
            <textarea className="input" rows={2} style={{ fontSize: 13 }} defaultValue={shot.visual_fx} onBlur={(e) => onPatchShot({ visual_fx: e.target.value })} />
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label>Âm thanh &amp; Nhạc nền (Audio/SFX)</label>
            <textarea className="input" rows={2} style={{ fontSize: 13 }} defaultValue={shot.audio_sfx} onBlur={(e) => onPatchShot({ audio_sfx: e.target.value })} />
          </div>
          {!isLast && (
            <div className="field" style={{ margin: 0 }}>
              <label>Chuyển cảnh sang shot kế tiếp</label>
              <select
                className="input"
                style={{ fontSize: 13 }}
                value={shot.transition_to_next || "cut"}
                onChange={(e) => onPatchShot({ transition_to_next: e.target.value })}
              >
                {TRANSITION_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          {shot.visual_type === "image" && (
            <div className="field" style={{ margin: 0 }}>
              <label>Chuyển động camera (ảnh tĩnh)</label>
              <select
                className="input"
                style={{ fontSize: 13 }}
                value={shot.camera_motion || "none"}
                onChange={(e) => onPatchShot({ camera_motion: e.target.value })}
              >
                {CAMERA_MOTION_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              className="btn btn-primary"
              style={{ fontSize: 12, padding: "5px 10px" }}
              onClick={onGenerateVisualAsset}
              disabled={visualStatus === "generating" || disableGenerate}
              title={disableGenerate && visualStatus !== "generating" ? "Đang có tiến trình sinh asset khác chạy cho project này — đợi xong hoặc bấm Dừng" : undefined}
            >
              {visualStatus === "generating"
                ? `Đang sinh… ${formatElapsed(visualElapsedSec || 0)} / ~${formatElapsed(estimatedVisualSec)}`
                : `Tạo ${shot.visual_type === "video" ? "video" : "ảnh"}`}
            </button>
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "5px 10px" }}
              onClick={() => fileRef.current?.click()}
              disabled={uploading || disableGenerate}
              title={`Upload ${shot.visual_type === "video" ? "video" : "ảnh"} có sẵn từ máy — thay thế asset của shot này, không cần AI`}
            >
              {uploading ? "Đang tải lên..." : `↑ Upload ${shot.visual_type === "video" ? "video" : "ảnh"}`}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept={shot.visual_type === "video" ? "video/mp4,video/webm,video/quicktime" : "image/png,image/jpeg,image/webp"}
              style={{ display: "none" }}
              onChange={handleFilePicked}
            />
            <LibraryPicker
              kinds={[shot.visual_type === "video" ? "video" : "image"]}
              disabled={uploading || disableGenerate}
              onPick={async (file) => {
                setUploading(true);
                setUploadError(null);
                try {
                  await onUploadVisualAsset(file);
                } catch (err) {
                  setUploadError(err instanceof Error ? err.message : "Có lỗi khi upload.");
                } finally {
                  setUploading(false);
                }
              }}
            />
            <button
              className="btn btn-primary"
              style={{ fontSize: 12, padding: "5px 10px" }}
              onClick={onGenerateNarrationAsset}
              disabled={narrationStatus === "generating" || disableGenerate}
              title={disableGenerate && narrationStatus !== "generating" ? "Đang có tiến trình sinh asset khác chạy cho project này — đợi xong hoặc bấm Dừng" : undefined}
            >
              {narrationStatus === "generating" ? `Đang sinh… ${formatElapsed(narrationElapsedSec || 0)}` : "Tạo giọng đọc"}
            </button>
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={onApprove} disabled={visualStatus !== "ready" || status?.approved}>
              {status?.approved ? "Đã duyệt" : "Duyệt"}
            </button>
          </div>
          {uploadError && <div style={{ fontSize: 11.5, color: "var(--color-danger)" }}>{uploadError}</div>}
        </div>
      </div>
    </div>
  );
}

function ShotPreview({ projectId, shot, status, cacheBust, isVertical }: { projectId: string; shot: Shot; status: ShotRenderStatus | undefined; cacheBust: number; isVertical: boolean }) {
  const [lightbox, setLightbox] = useState(false);
  const assetUrl = `${api.renderShotAssetUrl(projectId, shot.shot_id, "visual")}?v=${cacheBust}`;
  return (
    <div>
      {status?.visual_status === "ready" ? (
        <div style={{ position: "relative" }}>
          <ExpandButton onClick={() => setLightbox(true)} />
          {shot.visual_type === "video" ? (
            // eslint-disable-next-line jsx-a11y/media-has-caption
            <video controls style={{ width: "100%", borderRadius: "var(--radius-sm)" }} src={assetUrl} />
          ) : (
            <img alt={shot.shot_id} style={{ width: "100%", borderRadius: "var(--radius-sm)", display: "block", cursor: "zoom-in" }} src={assetUrl} onClick={() => setLightbox(true)} />
          )}
        </div>
      ) : (
        <div
          style={{
            height: previewBoxHeight(isVertical),
            borderRadius: "var(--radius-sm)",
            background: "var(--color-bg)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
            padding: 6,
            fontSize: 11,
            opacity: 0.6,
            color: status?.visual_status === "error" ? "var(--color-danger)" : undefined,
          }}
        >
          {status?.visual_status === "error" ? status.visual_error : status?.visual_status === "generating" ? "Đang sinh…" : `${shot.visual_type === "video" ? "Video" : "Image"} — chưa sinh`}
        </div>
      )}
      {status?.narration_status === "ready" && (
        // eslint-disable-next-line jsx-a11y/media-has-caption
        <audio controls style={{ width: "100%", marginTop: 6 }} src={`${api.renderShotAssetUrl(projectId, shot.shot_id, "narration")}?v=${cacheBust}`} />
      )}
      {status?.narration_status === "error" && <div style={{ fontSize: 11, color: "var(--color-danger)", marginTop: 4 }}>{status.narration_error}</div>}
      {lightbox && <Lightbox src={assetUrl} kind={shot.visual_type === "video" ? "video" : "image"} onClose={() => setLightbox(false)} />}
    </div>
  );
}

function StatusTag({ label, status }: { label: string; status: string }) {
  const color =
    status === "ready" ? "var(--color-accent)" : status === "error" ? "var(--color-danger)" : status === "generating" ? "var(--color-warning)" : "var(--color-neutral-600)";
  return (
    <span className="tag tag-outline" style={{ fontSize: 10, color }}>
      {label}: {status}
    </span>
  );
}

/** Thẻ Thumbnail — chuyển từ Pack Review sang ĐẦU Visual Studio (theo yêu cầu người
 * dùng). Cho phép cả 2 đường: sinh bằng AI (cần mô tả + provider image) hoặc upload
 * ảnh có sẵn từ máy (không cần provider, không cần mô tả) — dùng cho lúc xuất video
 * lên YouTube (Pack Review/Output Center), không còn ảnh hưởng tới việc sinh ảnh/video
 * từng shot. TRƯỚC ĐÂY (mục 18 IMPLEMENTATION_REPORT.md) ảnh này bắt buộc phải duyệt vì
 * đóng vai trò "anchor" img2img cho mọi shot (Tier 2) — TẮT lại 2026-08-16: verify qua
 * GPU cho thấy khi Thumbnail là ảnh nhiều chi tiết đồ hoạ (bản đồ minh hoạ, không phải
 * ảnh chụp/nhân vật đơn giản), cơ chế này đè mất nội dung riêng từng shot ở mọi mức
 * denoise thử qua — xem mục 20. */
const DEFAULT_YOUTUBE_META = {
  thumbnail_description: "",
  thumbnail_status: "pending" as const, thumbnail_asset_path: null, thumbnail_provider: null, thumbnail_error: null, thumbnail_approved: false,
};

/** Shot mở đầu (intro) riêng của project — **mới (2026-08-20)**, theo yêu cầu người
 * dùng: upload ảnh+audio đi kèm (bắt buộc) HOẶC video, khi "đủ" sẽ OVERRIDE video/audio
 * thương hiệu cấp kênh (BrandProfile, sửa ở ChannelDialog.tsx) khi ghép MP4 — xem
 * app/render/intro.py::resolve_intro_source. Không gắn với `pack.shots` (không phải
 * AI sinh, không có timestamp trong kịch bản) — sống trong `render.json` riêng
 * (`RenderState.intro`), cùng nguyên tắc "render module tách biệt script core".
 *
 * **Đổi (2026-08-20, theo phản hồi người dùng)**: tách nút "Upload ảnh hoặc video" gộp
 * ban đầu thành 2 nút riêng "Upload video"/"Upload ảnh" (rõ ràng hơn, khớp đúng ý người
 * dùng "chia thành 3 nút"), VÀ audio giờ upload ĐỘC LẬP được (không còn bắt buộc phải
 * có ảnh trước) — chỉ có audio (không ảnh/video) vẫn dùng được, tự minh hoạ bằng ảnh
 * shot đầu tiên lúc ghép, giống hệt cách audio thương hiệu cấp kênh hoạt động.
 *
 * **Đổi (2026-08-22, theo yêu cầu người dùng "để inherit từ brand profile")**: TRƯỚC ĐÂY
 * khi project chưa upload gì, card hiện trống ("Chưa có") dù lúc ghép MP4 THẬT SỰ đã tự
 * fallback dùng video/audio thương hiệu cấp kênh (fallback NGẦM, không hiện gì ở UI) —
 * giờ card HIỂN THỊ đúng asset thương hiệu sẽ dùng (preview thật, không chỉ text gợi ý),
 * gắn nhãn "Kế thừa từ hồ sơ thương hiệu". Người dùng bấm "Bỏ shot mở đầu" để TẮT HẲN
 * (không dùng brand nữa, `IntroAssetStatus.disabled=True`) hoặc upload video/ảnh/audio
 * riêng để THAY THẾ (override, hành vi cũ không đổi). Toàn bộ chỉnh sửa ở đây CHỈ ghi
 * vào `render.json` của project (qua `app/routers/render.py::delete_intro`/
 * `enable_intro_inherit`/`upload_intro_*`) — KHÔNG BAO GIỜ đụng tới BrandProfile cấp
 * kênh (đọc BrandProfile qua `api.getBrandProfile` chỉ để HIỂN THỊ, không PUT lại). */
function IntroShotCard({ projectId, channelId, intro, refresh, isVertical }: { projectId: string; channelId: string; intro: IntroAssetStatus | null; refresh: () => Promise<void>; isVertical: boolean }) {
  const [uploadingVideo, setUploadingVideo] = useState(false);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [uploadingAudio, setUploadingAudio] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [enabling, setEnabling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Cùng lý do cacheBust của ThumbnailCard — URL cố định nên trình duyệt không tự refetch
  // sau khi thay ảnh/video/audio, phải tự ép bằng query string đổi theo mỗi lần upload.
  const [cacheBust, setCacheBust] = useState(0);
  const videoFileRef = useRef<HTMLInputElement | null>(null);
  const imageFileRef = useRef<HTMLInputElement | null>(null);
  const audioFileRef = useRef<HTMLInputElement | null>(null);

  // Video/audio thương hiệu cấp kênh — CHỈ đọc để hiển thị preview "kế thừa", không bao
  // giờ ghi ngược lại (xem docstring). `""` = chưa cấu hình field đó ở BrandProfile.
  const [brandIntroVideoPath, setBrandIntroVideoPath] = useState("");
  const [brandIntroAudioPath, setBrandIntroAudioPath] = useState("");
  useEffect(() => {
    let cancelled = false;
    api
      .getBrandProfile(channelId)
      .then((bp) => {
        if (cancelled) return;
        setBrandIntroVideoPath(bp.intro_video_path || "");
        setBrandIntroAudioPath(bp.intro_audio_path || "");
      })
      .catch(() => {
        if (!cancelled) {
          setBrandIntroVideoPath("");
          setBrandIntroAudioPath("");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [channelId, cacheBust]);

  async function uploadVisual(file: File, setBusy: (b: boolean) => void, ref: React.RefObject<HTMLInputElement | null>) {
    setBusy(true);
    setError(null);
    try {
      await api.uploadIntroVisual(projectId, file);
      await refresh();
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload shot mở đầu.");
    } finally {
      setBusy(false);
      if (ref.current) ref.current.value = "";
    }
  }

  async function uploadAudio(file: File) {
    setUploadingAudio(true);
    setError(null);
    try {
      await api.uploadIntroAudio(projectId, file);
      await refresh();
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload audio.");
    } finally {
      setUploadingAudio(false);
      if (audioFileRef.current) audioFileRef.current.value = "";
    }
  }

  async function setTransition(value: string) {
    setError(null);
    try {
      await api.patchIntroTransition(projectId, value);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi đổi hiệu ứng chuyển cảnh.");
    }
  }

  async function removeIntro() {
    setRemoving(true);
    setError(null);
    try {
      await api.deleteIntro(projectId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi bỏ shot mở đầu.");
    } finally {
      setRemoving(false);
    }
  }

  async function enableInherit() {
    setEnabling(true);
    setError(null);
    try {
      await api.enableIntroInherit(projectId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi dùng lại mặc định thương hiệu.");
    } finally {
      setEnabling(false);
    }
  }

  const hasVisual = !!intro?.visual_asset_path;
  const hasAudio = !!intro?.audio_asset_path;
  const isVideo = hasVisual && intro?.kind === "video";
  const isImageComplete = hasVisual && intro?.kind === "image" && hasAudio;
  const isAudioOnly = !hasVisual && hasAudio;
  const hasOwnOverride = isVideo || isImageComplete || isAudioOnly;
  const isDisabled = !!intro?.disabled;
  const brandHasVideo = !hasOwnOverride && !isDisabled && !!brandIntroVideoPath;
  const brandHasAudio = !hasOwnOverride && !isDisabled && !brandIntroVideoPath && !!brandIntroAudioPath;
  const isInheriting = brandHasVideo || brandHasAudio;
  // "Video" theo nghĩa "không cần khối Audio riêng bên dưới" — đúng cho CẢ video riêng
  // của project LẪN video thương hiệu đang kế thừa (cùng lý do: video tự có audio).
  const effectiveIsVideo = isVideo || brandHasVideo;

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Shot mở đầu (intro){" "}
          {hasOwnOverride && <span className="tag tag-accent" style={{ marginLeft: 6 }}>Đang dùng — ghi đè video/audio thương hiệu</span>}
          {isInheriting && <span className="tag" style={{ marginLeft: 6 }}>Kế thừa từ hồ sơ thương hiệu</span>}
          {isDisabled && <span className="tag tag-outline" style={{ marginLeft: 6, color: "var(--color-danger)" }}>Đã tắt — không có shot mở đầu</span>}
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.6 }}>Mặc định kế thừa video/audio thương hiệu cấp kênh — có thể thay bằng ảnh/video/audio riêng, hoặc bỏ hẳn cho project này</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: `${previewColWidth(isVertical)}px 1fr`, gap: "var(--space-3)", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ height: previewBoxHeight(isVertical), borderRadius: "var(--radius-sm)", background: "var(--color-bg)", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
            {hasVisual ? (
              isVideo ? (
                // eslint-disable-next-line jsx-a11y/media-has-caption
                <video controls style={{ width: "100%", height: "100%", objectFit: "cover" }} src={`${api.introAssetUrl(projectId, "visual")}?v=${cacheBust}`} />
              ) : (
                <img alt="Shot mở đầu" src={`${api.introAssetUrl(projectId, "visual")}?v=${cacheBust}`} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              )
            ) : brandHasVideo ? (
              // eslint-disable-next-line jsx-a11y/media-has-caption
              <video controls style={{ width: "100%", height: "100%", objectFit: "cover" }} src={`${api.brandIntroUrl(channelId)}?v=${cacheBust}`} />
            ) : (
              <span style={{ fontSize: 11.5, opacity: 0.5, textAlign: "center", padding: 8 }}>
                {isAudioOnly || brandHasAudio ? "Sẽ dùng ảnh shot đầu tiên" : isDisabled ? "Đã tắt shot mở đầu" : "Chưa có"}
              </span>
            )}
          </div>
          {hasVisual && <AddToLibraryButton kind={isVideo ? "video" : "image"} sourceUrl={`${api.introAssetUrl(projectId, "visual")}?v=${cacheBust}`} name="shot-mo-dau" />}
          {!hasVisual && brandHasVideo && <AddToLibraryButton kind="video" sourceUrl={`${api.brandIntroUrl(channelId)}?v=${cacheBust}`} name="shot-mo-dau-thuong-hieu" />}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          <div className="field" style={{ margin: 0 }}>
            <label>Chuyển cảnh sang shot đầu tiên</label>
            <select className="input" style={{ fontSize: 13 }} value={intro?.transition_to_next || "cut"} onChange={(e) => setTransition(e.target.value)} disabled={isDisabled}>
              {TRANSITION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          {!effectiveIsVideo && (
            <div>
              <label style={{ fontSize: 11.5, opacity: 0.75 }}>Audio {!hasVisual && !brandHasAudio && "(chưa có ảnh — sẽ tự dùng ảnh shot đầu tiên)"}</label>
              {hasAudio ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                  <audio controls style={{ flex: 1, height: 32 }} src={`${api.introAssetUrl(projectId, "audio")}?v=${cacheBust}`} />
                  <AddToLibraryButton kind="music" sourceUrl={`${api.introAssetUrl(projectId, "audio")}?v=${cacheBust}`} name="shot-mo-dau-audio" />
                </div>
              ) : brandHasAudio ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                  <audio controls style={{ flex: 1, height: 32 }} src={`${api.brandIntroUrl(channelId)}?v=${cacheBust}`} />
                  <AddToLibraryButton kind="music" sourceUrl={`${api.brandIntroUrl(channelId)}?v=${cacheBust}`} name="shot-mo-dau-audio-thuong-hieu" />
                </div>
              ) : hasVisual ? (
                <div style={{ fontSize: 12, color: "var(--color-danger)" }}>Chưa có audio — ảnh mở đầu CHƯA dùng được tới khi upload audio (bắt buộc đi kèm).</div>
              ) : null}
            </div>
          )}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              ref={videoFileRef}
              type="file"
              accept="video/mp4,video/webm,video/quicktime"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) uploadVisual(f, setUploadingVideo, videoFileRef);
              }}
            />
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => videoFileRef.current?.click()} disabled={uploadingVideo}>
              {uploadingVideo ? "Đang tải lên..." : hasVisual && isVideo ? "Thay video" : "Upload video riêng"}
            </button>
            <input
              ref={imageFileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) uploadVisual(f, setUploadingImage, imageFileRef);
              }}
            />
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => imageFileRef.current?.click()} disabled={uploadingImage}>
              {uploadingImage ? "Đang tải lên..." : hasVisual && !isVideo ? "Thay ảnh" : "Upload ảnh riêng"}
            </button>
            <input
              ref={audioFileRef}
              type="file"
              accept="audio/wav,audio/mpeg,audio/mp3"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) uploadAudio(f);
              }}
            />
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => audioFileRef.current?.click()} disabled={uploadingAudio || isVideo}>
              {uploadingAudio ? "Đang tải lên..." : hasAudio ? "Thay audio" : "Upload audio riêng"}
            </button>
            <LibraryPicker
              kinds={["video", "image", "music"]}
              disabled={uploadingVideo || uploadingImage || uploadingAudio}
              onPick={(file) => {
                if (file.type.startsWith("video/")) uploadVisual(file, setUploadingVideo, videoFileRef);
                else if (file.type.startsWith("image/")) uploadVisual(file, setUploadingImage, imageFileRef);
                else uploadAudio(file);
              }}
            />
            {(hasOwnOverride || isInheriting) && (
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px", color: "var(--color-danger)" }} onClick={removeIntro} disabled={removing}>
                {removing ? "Đang bỏ..." : "Bỏ shot mở đầu"}
              </button>
            )}
            {isDisabled && (brandIntroVideoPath || brandIntroAudioPath) && (
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={enableInherit} disabled={enabling}>
                {enabling ? "Đang bật lại..." : "Dùng lại mặc định thương hiệu"}
              </button>
            )}
          </div>
          {error && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{error}</div>}
        </div>
      </div>
    </div>
  );
}

/** Nhạc nền RIÊNG của project — **mới (2026-08-20)**, theo yêu cầu người dùng: override
 * hẳn nhạc nền mặc định cấp kênh (sửa ở ChannelDialog.tsx) khi có, cùng cấu trúc
 * `RenderState.bg_music` như `IntroShotCard` dùng `RenderState.intro` — tách riêng khỏi
 * `pack.shots`, sống trong render.json (render module tách biệt script core). */
function BgMusicCard({ projectId, bgMusic, refresh }: { projectId: string; bgMusic: BgMusicOverride | null; refresh: () => Promise<void> }) {
  const [uploading, setUploading] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cacheBust, setCacheBust] = useState(0);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      await api.uploadProjectBgMusic(projectId, file);
      await refresh();
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload nhạc nền.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function setVolume(volume: number) {
    try {
      await api.patchProjectBgMusicVolume(projectId, volume);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi chỉnh âm lượng.");
    }
  }

  async function remove() {
    setRemoving(true);
    setError(null);
    try {
      await api.deleteProjectBgMusic(projectId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi bỏ nhạc nền riêng.");
    } finally {
      setRemoving(false);
    }
  }

  const hasAsset = !!bgMusic?.asset_path;
  const volume = bgMusic?.volume ?? 0.3;

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Nhạc nền riêng {hasAsset && <span className="tag tag-accent" style={{ marginLeft: 6 }}>Đang dùng — ghi đè nhạc nền mặc định của kênh</span>}
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.6 }}>Tuỳ chọn — override nhạc nền mặc định của kênh (sửa ở BrandProfile) chỉ cho project này</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        {hasAsset ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <audio controls style={{ flex: 1, height: 32, minWidth: 160 }} src={`${api.projectBgMusicUrl(projectId)}?v=${cacheBust}`} />
            <AddToLibraryButton kind="music" sourceUrl={`${api.projectBgMusicUrl(projectId)}?v=${cacheBust}`} name="nhac-nen-project" />
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={remove} disabled={removing}>
              {removing ? "Đang bỏ..." : "Bỏ nhạc nền riêng"}
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              ref={fileRef}
              type="file"
              accept="audio/wav,audio/mpeg,audio/mp3"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload(f);
              }}
            />
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => fileRef.current?.click()} disabled={uploading}>
              {uploading ? "Đang tải lên..." : "Upload nhạc nền"}
            </button>
            <LibraryPicker kinds={["music"]} disabled={uploading} onPick={upload} />
          </div>
        )}
        {hasAsset && (
          <div style={{ maxWidth: 320 }}>
            <label style={{ fontSize: 11 }}>Âm lượng nhạc nền so với giọng đọc chính ({Math.round(volume * 100)}%)</label>
            <input type="range" min={0} max={1} step={0.05} defaultValue={volume} onMouseUp={(e) => setVolume(parseFloat((e.target as HTMLInputElement).value))} onTouchEnd={(e) => setVolume(parseFloat((e.target as HTMLInputElement).value))} style={{ width: "100%" }} />
          </div>
        )}
        {error && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{error}</div>}
      </div>
    </div>
  );
}

/** Hiệu ứng lớp phủ (overlay, VD mưa/tuyết rơi) RIÊNG của project — **mới (2026-08-22)**,
 * theo yêu cầu người dùng: override hẳn overlay mặc định cấp kênh (sửa ở ChannelDialog.tsx)
 * khi có, cùng cấu trúc `RenderState.overlay` như `BgMusicCard` dùng `RenderState.bg_music`
 * — tách riêng khỏi `pack.shots`, sống trong render.json (render module tách biệt script
 * core). Blend ĐÈ LIÊN TỤC lên TOÀN BỘ video (kể cả intro) — mô phỏng 1-1 `BgMusicCard`,
 * chỉ đổi audio→video, xem `app/render/overlay.py::resolve_overlay_source`. */
function OverlayEffectCard({ projectId, overlay, refresh }: { projectId: string; overlay: OverlayEffectOverride | null; refresh: () => Promise<void> }) {
  const [uploading, setUploading] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cacheBust, setCacheBust] = useState(0);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      await api.uploadProjectOverlay(projectId, file);
      await refresh();
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload hiệu ứng lớp phủ.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function setOpacity(opacity: number) {
    try {
      await api.patchProjectOverlayOpacity(projectId, opacity);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi chỉnh cường độ.");
    }
  }

  async function remove() {
    setRemoving(true);
    setError(null);
    try {
      await api.deleteProjectOverlay(projectId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi bỏ hiệu ứng lớp phủ riêng.");
    } finally {
      setRemoving(false);
    }
  }

  const hasAsset = !!overlay?.asset_path;
  const opacity = overlay?.opacity ?? 0.5;

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Hiệu ứng lớp phủ riêng {hasAsset && <span className="tag tag-accent" style={{ marginLeft: 6 }}>Đang dùng — ghi đè hiệu ứng mặc định của kênh</span>}
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.6 }}>Tuỳ chọn — override hiệu ứng lớp phủ mặc định của kênh (sửa ở BrandProfile) chỉ cho project này. VD mưa/tuyết rơi.</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        {hasAsset ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <video controls muted style={{ flex: 1, maxHeight: 120, minWidth: 160 }} src={`${api.projectOverlayUrl(projectId)}?v=${cacheBust}`} />
            <AddToLibraryButton kind="video" sourceUrl={`${api.projectOverlayUrl(projectId)}?v=${cacheBust}`} name="overlay-project" />
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={remove} disabled={removing}>
              {removing ? "Đang bỏ..." : "Bỏ hiệu ứng lớp phủ riêng"}
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <input
              ref={fileRef}
              type="file"
              accept="video/mp4,video/webm,video/quicktime"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload(f);
              }}
            />
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => fileRef.current?.click()} disabled={uploading}>
              {uploading ? "Đang tải lên..." : "Upload hiệu ứng lớp phủ"}
            </button>
            <LibraryPicker kinds={["video"]} disabled={uploading} onPick={upload} />
          </div>
        )}
        {hasAsset && (
          <div style={{ maxWidth: 320 }}>
            <label style={{ fontSize: 11 }}>Cường độ hiệu ứng ({Math.round(opacity * 100)}%)</label>
            <input type="range" min={0} max={1} step={0.05} defaultValue={opacity} onMouseUp={(e) => setOpacity(parseFloat((e.target as HTMLInputElement).value))} onTouchEnd={(e) => setOpacity(parseFloat((e.target as HTMLInputElement).value))} style={{ width: "100%" }} />
          </div>
        )}
        {error && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{error}</div>}
      </div>
    </div>
  );
}

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
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
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
