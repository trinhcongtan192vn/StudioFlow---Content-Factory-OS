import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { BackgroundVideoOverride, BgMusicOverride, CaptionLayer, CharacterReferenceStatus, GpuStatus, ImageLayer, ImageLayerPosition, IntroAssetStatus, LayerBlendMode, LayerPosition, NarrationLanguage, OverlayEffectOverride, ProductionPack, ProjectSummary, RenderState, Shot, ShotRenderStatus, ShotUploadBatchResult, VaultAutoFillSuggestionsResult, VideoLayer, WatermarkScanSummary } from "../../api/types";
import { NARRATION_LANGUAGES, NARRATION_LANGUAGE_LABELS } from "../../api/types";
import AddToLibraryButton from "../../components/AddToLibraryButton";
import AiErrorBanner from "../../components/AiErrorBanner";
import Lightbox, { ExpandButton } from "../../components/Lightbox";
import LibraryPicker from "../../components/LibraryPicker";
import ProgressBar from "../../components/ProgressBar";
import VaultClipPicker from "../../components/VaultClipPicker";
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

  // Tiếng Việt tham chiếu dưới narration ngôn ngữ chính — mới (2026-09-09), theo yêu cầu
  // người dùng: tương tự cách Script Studio đã làm (xem ScriptStudio.tsx). Chỉ cần biết
  // `primary_language` để quyết định CÓ hiện panel tham chiếu hay không (KHÔNG cần
  // `viewLang` như Script Studio — Visual Studio không có khái niệm "đang xem ngôn ngữ
  // nào", luôn hiện đúng 1 bản ngôn ngữ chính).
  const [primaryLanguage, setPrimaryLanguage] = useState<NarrationLanguage>("vi");
  useEffect(() => {
    api
      .getBrandProfile(project.channel_id)
      .then((bp) => setPrimaryLanguage(bp.primary_language || "vi"))
      .catch(() => {
        /* BrandProfile luôn tồn tại (tạo kèm kênh) — lỗi hiếm, giữ mặc định "vi" */
      });
  }, [project.channel_id]);

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

  // Khớp shot ↔ block theo `block_id` TRƯỚC (ổn định, duy nhất) — cùng bugfix đã áp dụng
  // ở Script Studio (`shotForBlock`, mục 31 IMPLEMENTATION_REPORT.md: `timestamp_sec` có
  // thể lệch giữa lúc tạo shot và lúc script sửa/import lại). Fallback về khớp
  // `timestamp_sec` (hành vi cũ) khi shot chưa có `block_id` (dữ liệu cũ).
  function bodyItemFor(shot: Shot) {
    if (shot.block_id) {
      const byBlock = body.find((b) => b.block_id === shot.block_id);
      if (byBlock) return byBlock;
    }
    return body.find((b) => b.timestamp_sec === shot.linked_timestamp_sec);
  }

  function narrationTextsFor(shot: Shot): { primary: string; vi: string } {
    const b = bodyItemFor(shot);
    return { primary: b?.audio || "", vi: b?.audio_by_lang?.vi || "" };
  }

  async function patchShot(shotId: string, patch: Partial<{ visual_fx: string; audio_sfx: string; visual_type: string; transition_to_next: string; camera_motion: string }>) {
    await api.patchShot(project.id, shotId, patch);
    await refresh();
  }

  // Bulk edit "Chuyển cảnh sang shot kế tiếp"/"Chuyển động camera" cho nhiều/tất cả shot
  // — mới (2026-09-10), theo yêu cầu người dùng. `selectedShots` sống ở component CHA
  // (không phải trong từng ShotCard) vì thanh công cụ bulk cần biết tổng số đã chọn +
  // gọi API 1 lần cho cả danh sách.
  const [selectedShots, setSelectedShots] = useState<Set<string>>(new Set());
  const [bulkTransition, setBulkTransition] = useState("cut");
  const [bulkCameraMotion, setBulkCameraMotion] = useState("none");
  const [applyingBulkTransition, setApplyingBulkTransition] = useState(false);
  const [applyingBulkCameraMotion, setApplyingBulkCameraMotion] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);

  function toggleShotSelect(shotId: string) {
    setSelectedShots((s) => {
      const next = new Set(s);
      if (next.has(shotId)) next.delete(shotId);
      else next.add(shotId);
      return next;
    });
  }

  const allShotsSelected = pack.shots.length > 0 && pack.shots.every((v) => selectedShots.has(v.shot_id));
  function toggleSelectAllShots() {
    setSelectedShots(allShotsSelected ? new Set() : new Set(pack.shots.map((v) => v.shot_id)));
  }

  // "Chuyển cảnh sang shot kế tiếp" không có ý nghĩa cho shot CUỐI (không có shot kế
  // tiếp để chuyển sang — xem field tương ứng ẩn ở ShotCard khi `isLast`) — loại khỏi
  // danh sách áp dụng để tránh gửi 1 field không đổi gì (không hại nếu gửi, nhưng đếm số
  // shot áp dụng THẬT khớp UI hơn).
  const selectableForTransition = pack.shots.filter((v, i) => selectedShots.has(v.shot_id) && i < pack.shots.length - 1);
  // "Chuyển động camera (ảnh tĩnh)" chỉ có ý nghĩa cho shot ẢNH — lọc tương tự.
  const selectableForCameraMotion = pack.shots.filter((v) => selectedShots.has(v.shot_id) && v.visual_type === "image");

  async function applyBulkTransition() {
    if (selectableForTransition.length === 0) return;
    setApplyingBulkTransition(true);
    setBulkError(null);
    try {
      await api.patchShotsBulk(
        project.id,
        selectableForTransition.map((v) => v.shot_id),
        { transition_to_next: bulkTransition }
      );
      await refresh();
    } catch (e) {
      setBulkError(describeAiError(e, "Có lỗi khi áp dụng hàng loạt."));
    } finally {
      setApplyingBulkTransition(false);
    }
  }

  async function applyBulkCameraMotion() {
    if (selectableForCameraMotion.length === 0) return;
    setApplyingBulkCameraMotion(true);
    setBulkError(null);
    try {
      await api.patchShotsBulk(
        project.id,
        selectableForCameraMotion.map((v) => v.shot_id),
        { camera_motion: bulkCameraMotion }
      );
      await refresh();
    } catch (e) {
      setBulkError(describeAiError(e, "Có lỗi khi áp dụng hàng loạt."));
    } finally {
      setApplyingBulkCameraMotion(false);
    }
  }

  // Lưu ảnh/video đã sinh của shot đã chọn vào Kho Tài Nguyên — mới (2026-09-11), theo
  // yêu cầu người dùng: "cho phép chọn Lưu tài nguyên cho ảnh/video ở một hoặc nhiều
  // block 1 lúc". Tái dùng ĐÚNG checkbox bulk-select đã có ở trên (mục 130) — chọn 1
  // shot vẫn dùng được cơ chế này bình thường, không cần nút riêng cho từng shot.
  const [applyingSaveToVault, setApplyingSaveToVault] = useState(false);
  const [saveToVaultResult, setSaveToVaultResult] = useState<{ saved: number; updated: number; skipped: { shot_id: string; reason: string }[] } | null>(null);

  async function saveSelectedToVault() {
    if (selectedShots.size === 0) return;
    setApplyingSaveToVault(true);
    setBulkError(null);
    setSaveToVaultResult(null);
    try {
      const result = await api.saveShotsToVault(project.id, Array.from(selectedShots));
      setSaveToVaultResult({ saved: result.saved.length, updated: result.updated.length, skipped: result.skipped });
      await refresh();
    } catch (e) {
      setBulkError(describeAiError(e, "Có lỗi khi lưu vào Kho tài nguyên."));
    } finally {
      setApplyingSaveToVault(false);
    }
  }

  // Tự động điền block còn thiếu từ Kho Tài Nguyên — mới (2026-09-11), theo yêu cầu
  // người dùng: quét shot chưa có visual, gợi ý ảnh/video khớp từ Kho, mở màn review
  // cho người dùng bỏ bớt gợi ý không phù hợp trước khi thật sự gán.
  const [autoFillResult, setAutoFillResult] = useState<VaultAutoFillSuggestionsResult | null>(null);
  const [scanningAutoFill, setScanningAutoFill] = useState(false);
  const [autoFillError, setAutoFillError] = useState<string | null>(null);
  // Tiến trình quét — **mới (2026-09-13)**, theo yêu cầu người dùng cần biết đang quét
  // gì/tới đâu/bao lâu (job nền poll được, xem client.ts::startVaultAutoFillScan).
  const [autoFillProgress, setAutoFillProgress] = useState<{ current: number; total: number; label: string | null; elapsedSec: number } | null>(null);
  const autoFillPollRef = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearInterval(autoFillPollRef.current), []);

  async function openAutoFillScan() {
    setScanningAutoFill(true);
    setAutoFillError(null);
    setAutoFillProgress(null);
    try {
      await api.startVaultAutoFillScan(project.id);
    } catch (e) {
      setAutoFillError(describeAiError(e, "Có lỗi khi bắt đầu quét Kho tài nguyên."));
      setScanningAutoFill(false);
      return;
    }
    window.clearInterval(autoFillPollRef.current);
    autoFillPollRef.current = window.setInterval(async () => {
      let s;
      try {
        s = await api.getVaultAutoFillScanStatus(project.id);
      } catch {
        return; // lỗi mạng thoáng qua — thử lại ở lượt poll tiếp theo
      }
      if (s.status === "running") {
        setAutoFillProgress({ current: s.current || 0, total: s.total || 0, label: s.current_label ?? null, elapsedSec: s.elapsed_sec || 0 });
        return;
      }
      window.clearInterval(autoFillPollRef.current);
      setScanningAutoFill(false);
      setAutoFillProgress(null);
      if (s.status === "error") {
        setAutoFillError(s.error || "Có lỗi khi quét gợi ý từ Kho tài nguyên.");
      } else if (s.status === "done" && s.result) {
        if (s.result.matched_count === 0) {
          setAutoFillError("Không tìm thấy gợi ý nào đủ tin cậy trong Kho Tài Nguyên cho các shot còn thiếu visual.");
        } else {
          setAutoFillResult(s.result);
        }
      }
    }, 800);
  }

  // Upload cả folder ảnh/video khớp theo mã block — mới (2026-09-16), theo yêu cầu
  // người dùng: chọn 1 folder có sẵn (tên file trùng shot_id, VD "B01.png"), backend tự
  // khớp + upload, popup báo số file khớp/chưa khớp + liệt kê tên file chưa khớp.
  const [uploadingBatch, setUploadingBatch] = useState(false);
  const [batchUploadError, setBatchUploadError] = useState<string | null>(null);
  const [batchUploadResult, setBatchUploadResult] = useState<ShotUploadBatchResult | null>(null);
  const batchFolderInputRef = useRef<HTMLInputElement>(null);

  async function handleBatchFolderPicked(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploadingBatch(true);
    setBatchUploadError(null);
    try {
      const result = await api.uploadShotVisualBatch(project.id, Array.from(files));
      setRenderState(result.state);
      for (const m of result.matched) bumpShotCacheBust(m.shot_id);
      setBatchUploadResult(result);
    } catch (e) {
      setBatchUploadError(describeAiError(e, "Có lỗi khi upload folder."));
    } finally {
      setUploadingBatch(false);
    }
  }

  async function toggleType(shotId: string, current: string) {
    const next = current === "image" ? "video" : "image";
    await api.patchShot(project.id, shotId, { visual_type: next });
    await refresh();
  }

  // Chỉ còn sinh VISUAL — batch giọng đọc chuyển hẳn sang Script Studio (2026-09-02,
  // mục 109, theo yêu cầu người dùng: "bỏ chức năng sinh giọng đọc cho toàn bộ block ở
  // màn Visual", nút tương ứng — kể cả bản "sinh lại kể cả đã có" — chuyển sang
  // ScriptStudio.tsx). Per-shot narration ("Tạo giọng đọc" ở từng ShotCard) KHÔNG đổi.
  async function startAssetGeneration(force = false) {
    setStartingRender(true);
    setAiError(null);
    try {
      setRenderState(await api.startRender(project.id, "visual", force));
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

  async function assignVaultClip(shotId: string, clipId: string) {
    // Video Slot nguồn "Video từ Kho" (CHANGE_Semantic_BRoll_Asset_Vault.md §7.3) — cùng
    // hành vi cache-bust như uploadVisualAsset (asset thay TẠI CHỖ, cần ép trình duyệt
    // coi là URL mới). Lỗi tự hiện trong VaultClipPicker (giống LibraryPicker), không
    // throw ra banner đầu trang.
    setRenderState(await api.assignVaultClip(project.id, shotId, clipId));
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

  async function removeShotWatermark(shotId: string, mode: "auto" | "gemini" = "auto") {
    setAiError(null);
    try {
      setRenderState(await api.removeShotWatermark(project.id, shotId, mode));
      // Bug thật (2026-09-19, người dùng báo "xoá xong nhưng video vẫn còn watermark") —
      // file THẬT đã được xoá đúng trên đĩa (`visual_asset_path` đổi tên sang `_nowm`),
      // nhưng preview <video>/<img> KHÔNG BAO GIỜ refetch vì thiếu `bumpShotCacheBust` ở
      // đây (mọi hành động đổi asset khác — upload/regenerate/assign vault clip — đều có
      // gọi, riêng hàm này bị bỏ sót từ lúc build tính năng xoá watermark). Bump SAU KHI
      // poll xong (không phải ngay sau POST) — endpoint này chạy qua BackgroundTasks, file
      // mới chỉ tồn tại SAU khi nền hoàn tất; bump quá sớm sẽ khiến trình duyệt fetch lại
      // nhưng vẫn nhận đúng file CŨ rồi cache luôn kết quả sai đó.
      window.setTimeout(async () => {
        await loadRenderStatus();
        bumpShotCacheBust(shotId);
      }, 1200);
      window.setTimeout(async () => {
        await loadRenderStatus();
        bumpShotCacheBust(shotId);
      }, 3000);
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi xoá watermark cho shot này."));
    }
  }

  const [removingAllWatermarks, setRemovingAllWatermarks] = useState(false);
  const [dismissedWatermarkSummaryAt, setDismissedWatermarkSummaryAt] = useState<string | null>(null);
  async function removeAllWatermarks(mode: "auto" | "gemini" = "auto") {
    setRemovingAllWatermarks(true);
    setAiError(null);
    const previousFinishedAt = renderState?.watermark_scan_summary?.finished_at ?? null;
    try {
      await api.removeAllShotsWatermark(project.id, mode);
      setDismissedWatermarkSummaryAt(null); // lượt quét mới — banner tóm tắt cũ (nếu đang ẩn) không còn liên quan
      // Bug thật (2026-09-04): 2 lần poll cố định (1.2s/3s) cũ giả định sẽ "bắt được" ít
      // nhất 1 shot đang `visual_status=="generating"` để tự bật vòng poll liên tục qua
      // `hasInFlight` — với batch nhiều shot xử lý NHANH (VD ảnh dùng vị trí cố định, không
      // qua Florence-2 nữa), cả 2 lần poll có thể "lọt" đúng khoảng giữa 2 shot (shot trước
      // đã "ready", shot sau chưa kịp chuyển "generating") nên không bắt được gì, UI dừng
      // cập nhật hẳn dù backend vẫn đang xử lý tiếp — nhìn như "chỉ chạy shot đầu rồi dừng".
      // Fix: poll LIÊN TỤC tới khi `watermark_scan_summary.finished_at` (mốc BackgroundTask
      // ghi lúc thật sự xong, không suy đoán qua trạng thái từng shot) đổi khác giá trị
      // trước khi bấm — tín hiệu "đã xong" chắc chắn, không phụ thuộc kịp bắt shot nào.
      for (let i = 0; i < 60; i++) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const fresh = await api.getRenderStatus(project.id);
        setRenderState(fresh);
        if (fresh.watermark_scan_summary && fresh.watermark_scan_summary.finished_at !== previousFinishedAt) {
          // Cùng bug thật vừa sửa ở removeShotWatermark — preview <video>/<img> không tự
          // refetch nếu thiếu bumpShotCacheBust dù file trên đĩa đã đổi. Bump cho MỌI shot
          // (rẻ, chỉ vài lượt fetch thừa cho shot không đổi) thay vì tính lại đúng shot nào
          // vừa "cleaned" — đơn giản hơn hẳn mà không có tác dụng phụ đáng kể.
          for (const s of fresh.shots) bumpShotCacheBust(s.shot_id);
          break;
        }
      }
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi xoá watermark cho toàn bộ block."));
    } finally {
      setRemovingAllWatermarks(false);
    }
  }

  async function removeVisualAsset(shotId: string) {
    setAiError(null);
    try {
      setRenderState(await api.removeShotVisual(project.id, shotId));
    } catch (e) {
      setAiError(describeAiError(e, "Có lỗi khi xoá ảnh/video của shot."));
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
            Viết mô tả, sinh ảnh/video và giọng đọc THẬT cho từng shot — theo đúng đoạn script tương ứng. Ghép MP4 ở Output Center khi mọi shot đã sinh xong.
            <StatsBar {...computeEstimatedStats(pack)} />
          </>
        }
        actions={
          <>
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "5px 12px" }}
              onClick={() => startAssetGeneration()}
              disabled={startingRender || hasInFlight}
              title="Sinh ảnh/video cho toàn bộ block — giọng đọc sinh ở bước Script Studio"
            >
              {startingRender || hasInFlight ? "Đang sinh..." : "Sinh Visual (ảnh/video) cho toàn bộ block"}
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
            {/* Sinh lại TOÀN BỘ (force) — gộp vào menu phụ (2026-08-23, theo đề xuất rà
                soát UX): hành động này SINH LẠI TỐN PHÍ + BỎ DUYỆT mọi shot đã ready,
                khác hẳn nút an toàn ở trên (chỉ lấp chỗ pending/error) — TRƯỚC ĐÂY đứng
                ngang hàng thị giác với hành động dùng hằng ngày (cùng cỡ nút, chỉ khác
                màu chữ), dễ bấm nhầm. Đưa vào "⋯ Tuỳ chọn khác" để tách bạch rõ mức độ
                rủi ro mà vẫn 1 cú click là tới, không mất chức năng. */}
            <OverflowMenu
              label="⋯ Tuỳ chọn khác"
              items={[
                {
                  label: "Sinh lại TOÀN BỘ Visual (kể cả đã có)",
                  title: "Sinh lại TOÀN BỘ ảnh/video cho block, KỂ CẢ shot đã có sẵn — dùng khi vừa đổi BrandProfile sang checkpoint/style mới. Tốn phí/thời gian lại từ đầu, và bỏ duyệt các shot bị sinh lại.",
                  danger: true,
                  disabled: startingRender || hasInFlight,
                  onClick: () => startAssetGeneration(true),
                },
                {
                  label: removingAllWatermarks ? "Đang quét/xoá watermark..." : "Xoá watermark toàn bộ slot",
                  title: "Xoá watermark cho MỌI shot đã có ảnh/video sẵn sàng (bỏ qua shot chưa sinh xong, VÀ bỏ qua ảnh không rõ nguồn Gemini — dùng nút riêng nếu chắc chắn có watermark Gemini) — video tự định vị bằng so sánh nhiều frame, dự phòng Florence-2 + LaMa. Có thể mất vài phút tuỳ số lượng shot.",
                  disabled: removingAllWatermarks || startingRender || hasInFlight,
                  onClick: () => removeAllWatermarks("auto"),
                },
                {
                  label: removingAllWatermarks ? "Đang quét/xoá watermark..." : "Xoá watermark Gemini toàn bộ slot",
                  title: "Ép xoá watermark Gemini tại vị trí cố định góc dưới-phải cho MỌI shot đã có ảnh/video sẵn sàng (ảnh lẫn video), không cần biết provider — dùng khi bạn chắc chắn CẢ block đều có watermark Gemini.",
                  disabled: removingAllWatermarks || startingRender || hasInFlight,
                  onClick: () => removeAllWatermarks("gemini"),
                },
                {
                  label: scanningAutoFill ? "Đang quét Kho tài nguyên..." : "Tự động điền từ Kho tài nguyên",
                  title: "Quét các shot CHƯA có visual, gợi ý ảnh/video khớp từ Kho Tài Nguyên (chỉ gợi ý match thật chắc) — mở màn xem trước để bạn bỏ bớt gợi ý không phù hợp rồi mới gán.",
                  disabled: scanningAutoFill,
                  onClick: openAutoFillScan,
                },
                {
                  label: uploadingBatch ? "Đang upload folder..." : "Upload ảnh/video từ folder (theo mã block)",
                  title: 'Chọn 1 folder có sẵn ảnh/video, tên file trùng mã block (VD "B01.png") — tự động khớp + upload, ghi đè block đã có sẵn nếu trùng tên. Hiện popup báo số file khớp/chưa khớp.',
                  disabled: uploadingBatch,
                  onClick: () => batchFolderInputRef.current?.click(),
                },
              ]}
            />
            <input
              ref={batchFolderInputRef}
              type="file"
              multiple
              // @ts-expect-error webkitdirectory chưa có trong type HTMLInputElement chuẩn — thuộc tính Chromium (Electron renderer chạy Chromium nên dùng được thẳng, không cần IPC riêng)
              webkitdirectory=""
              style={{ display: "none" }}
              onChange={(e) => {
                handleBatchFolderPicked(e.target.files);
                e.target.value = "";
              }}
            />
            <button className="btn btn-primary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={goOutput} disabled={busy}>
              {busy ? "Đang chuyển..." : "Đi tới Output →"}
            </button>
          </>
        }
      />

      {aiError && <AiErrorBanner message={aiError} onDismiss={() => setAiError(null)} />}
      {autoFillProgress && (
        <div style={{ marginBottom: "var(--space-3)" }}>
          <ProgressBar
            current={autoFillProgress.current}
            total={autoFillProgress.total}
            label={`Đang quét ${autoFillProgress.current}/${autoFillProgress.total}${autoFillProgress.label ? ` — ${autoFillProgress.label}` : ""} (${Math.round(autoFillProgress.elapsedSec)}s)`}
          />
        </div>
      )}
      {autoFillError && <AiErrorBanner message={autoFillError} onDismiss={() => setAutoFillError(null)} />}
      {autoFillResult && (
        <VaultAutoFillModal
          projectId={project.id}
          result={autoFillResult}
          onClose={() => setAutoFillResult(null)}
          onApplied={async () => {
            setAutoFillResult(null);
            await refresh();
            await loadRenderStatus();
          }}
        />
      )}
      {batchUploadError && <AiErrorBanner message={batchUploadError} onDismiss={() => setBatchUploadError(null)} />}
      {batchUploadResult && <ShotUploadBatchModal result={batchUploadResult} onClose={() => setBatchUploadResult(null)} />}

      {renderState?.watermark_scan_summary && renderState.watermark_scan_summary.finished_at !== dismissedWatermarkSummaryAt && (
        <WatermarkSummaryBanner
          summary={renderState.watermark_scan_summary}
          onDismiss={() => setDismissedWatermarkSummaryAt(renderState.watermark_scan_summary!.finished_at)}
        />
      )}

      <IntroShotCard projectId={project.id} channelId={project.channel_id} intro={renderState?.intro ?? null} refresh={loadRenderStatus} isVertical={project.format === "short"} />

      <CharacterReferenceCard projectId={project.id} characterReference={renderState?.character_reference ?? null} refresh={loadRenderStatus} />

      <BgMusicCard projectId={project.id} channelId={project.channel_id} bgMusic={renderState?.bg_music ?? null} refresh={loadRenderStatus} />

      <OverlayEffectCard projectId={project.id} channelId={project.channel_id} overlay={renderState?.overlay ?? null} refresh={loadRenderStatus} />

      <BackgroundVideoCard projectId={project.id} backgroundVideo={renderState?.background_video ?? null} refresh={loadRenderStatus} />

      <LayersCard projectId={project.id} layers={renderState?.layers ?? []} refresh={loadRenderStatus} />

      <ImageLayersCard projectId={project.id} layers={renderState?.image_layers ?? []} refresh={loadRenderStatus} />

      <CaptionLayerCard projectId={project.id} channelId={project.channel_id} captionLayer={renderState?.caption_layer ?? null} refresh={loadRenderStatus} />

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

      {pack.shots.length > 0 && (
        <div className="card elev-sm" style={{ gap: "var(--space-2)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input type="checkbox" checked={allShotsSelected} onChange={toggleSelectAllShots} />
            <span style={{ fontSize: 12.5, opacity: 0.8 }}>
              {selectedShots.size === 0 ? "Chọn shot để sửa hàng loạt" : `Đã chọn ${selectedShots.size}/${pack.shots.length} shot`}
            </span>
          </div>
          {selectedShots.size > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-4)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <label style={{ fontSize: 12.5, opacity: 0.8 }}>Chuyển cảnh sang shot kế tiếp:</label>
                <select className="input" style={{ fontSize: 12.5, width: "auto" }} value={bulkTransition} onChange={(e) => setBulkTransition(e.target.value)}>
                  {TRANSITION_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 12, padding: "5px 10px" }}
                  onClick={applyBulkTransition}
                  disabled={applyingBulkTransition || selectableForTransition.length === 0}
                  title={selectableForTransition.length === 0 ? "Không có shot nào trong lựa chọn có shot kế tiếp (loại shot cuối)" : `Áp dụng cho ${selectableForTransition.length} shot`}
                >
                  {applyingBulkTransition ? "Đang áp dụng..." : `Áp dụng (${selectableForTransition.length} shot)`}
                </button>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <label style={{ fontSize: 12.5, opacity: 0.8 }}>Chuyển động camera (ảnh tĩnh):</label>
                <select className="input" style={{ fontSize: 12.5, width: "auto" }} value={bulkCameraMotion} onChange={(e) => setBulkCameraMotion(e.target.value)}>
                  {CAMERA_MOTION_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 12, padding: "5px 10px" }}
                  onClick={applyBulkCameraMotion}
                  disabled={applyingBulkCameraMotion || selectableForCameraMotion.length === 0}
                  title={selectableForCameraMotion.length === 0 ? "Không có shot ảnh nào trong lựa chọn (loại shot video)" : `Áp dụng cho ${selectableForCameraMotion.length} ảnh`}
                >
                  {applyingBulkCameraMotion ? "Đang áp dụng..." : `Áp dụng (${selectableForCameraMotion.length} ảnh)`}
                </button>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 12, padding: "5px 10px" }}
                  onClick={saveSelectedToVault}
                  disabled={applyingSaveToVault}
                  title="Lưu ảnh/video đã sinh của các shot đã chọn vào Kho Tài Nguyên để tái sử dụng cho project khác cùng kênh"
                >
                  {applyingSaveToVault ? "Đang lưu..." : `Lưu vào Kho tài nguyên (${selectedShots.size})`}
                </button>
              </div>
            </div>
          )}
          {saveToVaultResult && (
            <div style={{ fontSize: 12, opacity: 0.85 }}>
              Đã lưu {saveToVaultResult.saved} shot mới, cập nhật {saveToVaultResult.updated} shot đã lưu trước đó.
              {saveToVaultResult.skipped.length > 0 && (
                <>
                  {" "}
                  Bỏ qua {saveToVaultResult.skipped.length} shot:{" "}
                  {saveToVaultResult.skipped.map((s) => `${s.shot_id} (${s.reason})`).join(", ")}
                </>
              )}
            </div>
          )}
          {bulkError && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{bulkError}</div>}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", maxWidth: 900 }}>
        {pack.shots.map((v, i) => {
          const { primary, vi } = narrationTextsFor(v);
          return (
            <ShotCard
              key={v.shot_id}
              projectId={project.id}
              shot={v}
              isLast={i === pack.shots.length - 1}
              status={statusFor(v.shot_id)}
              snippet={primary}
              viSnippet={vi}
              showViSnippet={primaryLanguage !== "vi"}
              selected={selectedShots.has(v.shot_id)}
              onToggleSelect={() => toggleShotSelect(v.shot_id)}
              onToggleType={() => toggleType(v.shot_id, v.visual_type)}
              onPatchShot={(patch) => patchShot(v.shot_id, patch)}
              onGenerateVisualAsset={() => regenVisualAsset(v.shot_id)}
              onGenerateNarrationAsset={() => regenNarrationAsset(v.shot_id)}
              onUploadVisualAsset={(file) => uploadVisualAsset(v.shot_id, file)}
              onAssignVaultClip={(clipId) => assignVaultClip(v.shot_id, clipId)}
              onRemoveVisual={() => removeVisualAsset(v.shot_id)}
              onRemoveWatermark={() => removeShotWatermark(v.shot_id)}
              onRemoveWatermarkGemini={() => removeShotWatermark(v.shot_id, "gemini")}
              disableGenerate={hasInFlight}
              nowTick={nowTick}
              cacheBust={shotCacheBust[v.shot_id] || 0}
              isVertical={project.format === "short"}
            />
          );
        })}
      </div>
    </div>
  );
}

/** Menu thả xuống cho các hành động PHỤ/ít dùng, tách khỏi hàng nút chính ở header —
 * mới (2026-08-23, theo đề xuất rà soát UX: "header Visual Studio 7 nút cùng cỡ, không
 * phân cấp"). Đóng bằng cách bấm ra ngoài — cùng cơ chế backdrop-click-to-close đã dùng
 * ở `LibraryPicker.tsx`/`ScriptImportControls.tsx` (`.dialog-backdrop`), chỉ khác backdrop
 * ở đây TRONG SUỐT (không làm tối màn hình — đây là menu phụ, không phải dialog chặn thao
 * tác chính) và panel neo cạnh nút bấm thay vì giữa màn hình. */
function OverflowMenu({ label, items }: { label: string; items: { label: string; title: string; danger?: boolean; disabled?: boolean; onClick: () => void }[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => setOpen((o) => !o)}>
        {label}
      </button>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 10 }} onClick={() => setOpen(false)} />
          <div
            className="card elev-md"
            style={{ position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 11, minWidth: 260, padding: 6, gap: 2 }}
          >
            {items.map((item) => (
              <button
                key={item.label}
                className="btn btn-secondary"
                style={{ fontSize: 12, padding: "7px 10px", justifyContent: "flex-start", border: "none", color: item.danger ? "var(--color-danger)" : undefined }}
                title={item.title}
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false);
                  item.onClick();
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ShotCard({
  projectId,
  shot,
  isLast,
  status,
  snippet,
  viSnippet,
  showViSnippet,
  selected,
  onToggleSelect,
  onToggleType,
  onPatchShot,
  onGenerateVisualAsset,
  onGenerateNarrationAsset,
  onUploadVisualAsset,
  onAssignVaultClip,
  onRemoveVisual,
  onRemoveWatermark,
  onRemoveWatermarkGemini,
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
  // Tiếng Việt tham chiếu (mới 2026-09-09) — hiện dưới `snippet` khi kênh có ngôn ngữ
  // chính KHÁC tiếng Việt (`showViSnippet`, tính sẵn ở component cha từ `primary_language`
  // — cùng kiểu dữ liệu/điều kiện Script Studio đã dùng, xem ScriptStudio.tsx).
  viSnippet: string;
  showViSnippet: boolean;
  // Chọn nhiều shot để bulk edit "Chuyển cảnh"/"Chuyển động camera" — mới (2026-09-10),
  // tính ở component cha (`VisualStudio`, `selectedShots: Set<string>`) — thanh công cụ
  // bulk cần biết TỔNG số đã chọn, không hợp lý sống riêng trong từng ShotCard.
  selected: boolean;
  onToggleSelect: () => void;
  onToggleType: () => void;
  onPatchShot: (patch: Partial<{ visual_fx: string; audio_sfx: string; visual_type: string; transition_to_next: string; camera_motion: string }>) => void;
  onGenerateVisualAsset: () => void;
  onGenerateNarrationAsset: () => void;
  onUploadVisualAsset: (file: File) => Promise<void>;
  onAssignVaultClip: (clipId: string) => Promise<void>;
  onRemoveVisual: () => void;
  onRemoveWatermark: () => void;
  // Nút riêng "Xoá watermark Gemini" — **mới (2026-09-18)** — ép chạy Gemini corner-
  // removal bất kể `status.visual_provider`, chỉ hiện cho shot ẢNH (xem docstring nút
  // "Xoá watermark" bên dưới về lý do tách riêng).
  onRemoveWatermarkGemini: () => void;
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
        <input type="checkbox" checked={selected} onChange={onToggleSelect} title="Chọn để sửa hàng loạt" />
        <span className="tag tag-neutral" style={{ fontFamily: "ui-monospace,monospace" }}>
          {shot.shot_id} · {shot.linked_timestamp_sec}s
        </span>
        <span className={`tag ${shot.visual_type === "video" ? "tag-accent-2" : "tag-accent"}`} onClick={onToggleType} style={{ cursor: "pointer" }}>
          {shot.visual_type === "video" ? "Video" : "Image"}
        </span>
        <StatusTag label="Visual" status={visualStatus} />
        <StatusTag label="Giọng đọc" status={narrationStatus} />
        {status?.saved_to_vault_clip_id && (
          <span className="tag tag-neutral" style={{ opacity: 0.75 }} title="Ảnh/video của shot này đã được lưu vào Kho Tài Nguyên">
            ✓ Đã lưu vào Kho
          </span>
        )}
      </div>
      <div style={{ fontSize: 13, opacity: 0.8, padding: 8, background: "var(--color-bg)", borderRadius: "var(--radius-sm)" }}>
        {snippet}
        {/* Tiếng Việt tham chiếu (2026-09-04, cùng recipe Script Studio) — chỉ hiện khi
            ngôn ngữ chính của kênh KHÔNG phải tiếng Việt. Đọc-only, giúp đối chiếu
            nội dung shot khi làm việc với kênh nước ngoài. */}
        {showViSnippet && (
          <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px dashed var(--color-divider)" }}>
            <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: ".06em", opacity: 0.5, marginBottom: 2 }}>Tiếng Việt (tham chiếu)</div>
            <div style={{ opacity: 0.75 }}>{viSnippet || <span style={{ opacity: 0.45 }}>— chưa có —</span>}</div>
          </div>
        )}
      </div>

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
            {/* Video/Ảnh từ Kho — CHANGE_Semantic_BRoll_Asset_Vault.md §7.3. Kho Tài
                Nguyên giờ chứa CẢ ảnh (lưu từ Visual Studio) lẫn video (cắt B-roll,
                2026-09-11) — không còn gate riêng shot video, `mediaKind` khớp
                `shot.visual_type` để backend lọc đúng loại. */}
            <VaultClipPicker
              projectId={projectId}
              shotId={shot.shot_id}
              mediaKind={shot.visual_type === "video" ? "video" : "image"}
              disabled={uploading || disableGenerate}
              onPick={async (clipId) => {
                setUploading(true);
                setUploadError(null);
                try {
                  await onAssignVaultClip(clipId);
                } catch (err) {
                  setUploadError(err instanceof Error ? err.message : "Có lỗi khi gán clip từ Kho.");
                } finally {
                  setUploading(false);
                }
              }}
            />
            {/* `btn-secondary` (đổi 2026-08-23, theo đề xuất rà soát UX) — TRƯỚC ĐÂY
                cũng `btn-primary` NGANG HÀNG với "Tạo ảnh/video" ở trên, 2 nút primary
                cạnh nhau khiến không còn nút nào thực sự "nổi bật nhất". Giữ ĐÚNG 1
                primary/hàng — khớp quy tắc áp dụng cho mọi card khác trong màn này
                (BgMusicCard/OverlayEffectCard/IntroShotCard vốn không có nút primary). */}
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "5px 10px" }}
              onClick={onGenerateNarrationAsset}
              disabled={narrationStatus === "generating" || disableGenerate}
              title={disableGenerate && narrationStatus !== "generating" ? "Đang có tiến trình sinh asset khác chạy cho project này — đợi xong hoặc bấm Dừng" : undefined}
            >
              {narrationStatus === "generating" ? `Đang sinh… ${formatElapsed(narrationElapsedSec || 0)}` : "Tạo giọng đọc"}
            </button>
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "5px 10px" }}
              onClick={onRemoveWatermark}
              disabled={visualStatus !== "ready" || disableGenerate}
              title={
                shot.visual_type === "video"
                  ? "Xoá watermark trên video hiện có của shot này — tự định vị bằng cách so sánh nhiều frame (vùng không đổi qua thời gian), dự phòng Florence-2 + LaMa nếu không tìm được (không phát hiện được sẽ báo rõ, không phải lỗi)"
                  : 'Chỉ tự chạy khi ảnh chắc chắn sinh từ Gemini (vá vị trí watermark Gemini/Nano Banana cố định, góc dưới phải) — ảnh nguồn khác dùng nút "Xoá watermark Gemini" nếu chắc chắn có watermark Gemini, hoặc bỏ qua nếu không có watermark'
              }
            >
              {visualStatus === "generating" ? "Đang xử lý..." : "Xoá watermark"}
            </button>
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12, padding: "5px 10px" }}
              onClick={onRemoveWatermarkGemini}
              disabled={visualStatus !== "ready" || disableGenerate}
              title="Ép xoá watermark Gemini tại vị trí cố định (góc dưới-phải) — áp dụng cho CẢ ảnh lẫn video, bất kể hệ thống có nhận ra nguồn/provider hay không. Dùng khi bạn chắc chắn asset này có watermark Gemini (kể cả upload tay)."
            >
              Xoá watermark Gemini
            </button>
            {status?.visual_asset_path && (
              <button
                className="btn btn-secondary"
                style={{ fontSize: 12, padding: "5px 10px", color: "var(--color-danger)" }}
                onClick={onRemoveVisual}
                disabled={disableGenerate}
                title="Xoá ảnh/video hiện có của shot này — trả về trạng thái chưa sinh, không tự sinh/upload lại cái khác"
              >
                Xoá {shot.visual_type === "video" ? "video" : "ảnh"}
              </button>
            )}
          </div>
          {uploadError && <div style={{ fontSize: 11.5, color: "var(--color-danger)" }}>{uploadError}</div>}
          {status?.visual_watermark_progress_total != null && status.visual_watermark_progress_current != null && (
            <ProgressBar current={status.visual_watermark_progress_current} total={status.visual_watermark_progress_total} label={status.visual_watermark_progress_label} />
          )}
          {status?.visual_watermark_note && (
            <div style={{ fontSize: 11.5, color: "color-mix(in srgb, var(--color-text) 65%, transparent)" }}>{status.visual_watermark_note}</div>
          )}
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

/** Màn review "Tự động điền từ Kho tài nguyên" — mới (2026-09-11), theo yêu cầu người
 * dùng: "mở ra màn danh sách các shot đang có kèm ảnh/video gợi ý. User có thể bỏ các
 * ảnh match ko phù hợp và accept các ảnh phù hợp còn lại để gắn với shot." Nhận `result`
 * đã quét SẴN từ component cha (KHÔNG tự fetch lại — tránh lệch dữ liệu giữa lúc mở modal
 * và lúc áp dụng). Mỗi dòng mặc định TICK (đã qua ngưỡng tin cậy cao ở backend) — người
 * dùng BỎ tick dòng không phù hợp thay vì phải tick từng dòng đúng. */
function VaultAutoFillModal({
  projectId,
  result,
  onClose,
  onApplied,
}: {
  projectId: string;
  result: VaultAutoFillSuggestionsResult;
  onClose: () => void;
  onApplied: () => Promise<void>;
}) {
  const [accepted, setAccepted] = useState<Set<string>>(new Set(result.suggestions.map((s) => s.shot_id)));
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(shotId: string) {
    setAccepted((s) => {
      const next = new Set(s);
      if (next.has(shotId)) next.delete(shotId);
      else next.add(shotId);
      return next;
    });
  }

  async function apply() {
    const items = result.suggestions.filter((s) => accepted.has(s.shot_id)).map((s) => ({ shot_id: s.shot_id, clip_id: s.clip_id }));
    if (items.length === 0) {
      onClose();
      return;
    }
    setApplying(true);
    setError(null);
    try {
      await api.applyVaultAutoFill(projectId, items);
      await onApplied();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi áp dụng gợi ý.");
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" style={{ width: "min(640px,100%)", maxHeight: "80vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-title">Tự động điền từ Kho tài nguyên</div>
        <div style={{ fontSize: 12.5, opacity: 0.75, marginBottom: 8 }}>
          Đã quét {result.scanned_count} shot còn thiếu visual, tìm được {result.suggestions.length} gợi ý đủ tin cậy. Bỏ tick dòng nào không phù hợp trước khi áp dụng.
        </div>
        {error && <div style={{ fontSize: 12, color: "var(--color-danger)", marginBottom: 8 }}>{error}</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {result.suggestions.map((s) => (
            <label
              key={s.shot_id}
              style={{
                display: "flex", alignItems: "center", gap: 10, padding: "8px 10px",
                borderRadius: "var(--radius-sm)", background: "var(--color-bg)", cursor: "pointer",
              }}
            >
              <input type="checkbox" checked={accepted.has(s.shot_id)} onChange={() => toggle(s.shot_id)} />
              <div style={{ width: 64, height: 48, flex: "none", borderRadius: 4, overflow: "hidden", background: "var(--color-neutral-800)" }}>
                {s.media_kind === "image" ? (
                  // eslint-disable-next-line jsx-a11y/alt-text
                  <img src={api.clipFileUrl(s.clip_id)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                ) : (
                  // eslint-disable-next-line jsx-a11y/media-has-caption
                  <video src={api.clipFileUrl(s.clip_id)} preload="metadata" muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                )}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontFamily: "ui-monospace,monospace", opacity: 0.7 }}>{s.shot_id}</div>
                <div style={{ fontSize: 12.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={s.caption}>
                  {s.caption || s.clip_id}
                </div>
              </div>
              {s.match_score != null && (
                <span className="tag tag-accent" style={{ fontSize: 10.5, flex: "none" }}>
                  {Math.round(s.match_score * 100)}% match
                </span>
              )}
            </label>
          ))}
        </div>
        <div className="dialog-actions">
          <button className="btn btn-secondary" onClick={onClose} disabled={applying}>
            Huỷ
          </button>
          <button className="btn btn-primary" onClick={apply} disabled={applying}>
            {applying ? "Đang áp dụng..." : `Áp dụng (${accepted.size} đã chọn)`}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Popup báo cáo "Upload ảnh/video từ folder (theo mã block)" — mới (2026-09-16), theo
 * yêu cầu người dùng: chỉ BÁO CÁO kết quả (upload đã xong khi popup này mở, khác
 * `VaultAutoFillModal` — không có bước "chọn rồi áp dụng"), liệt kê rõ file nào chưa
 * khớp kèm lý do để người dùng tự đổi tên/sửa rồi thử lại. */
function ShotUploadBatchModal({ result, onClose }: { result: ShotUploadBatchResult; onClose: () => void }) {
  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" style={{ width: "min(560px,100%)", maxHeight: "80vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-title">Upload ảnh/video từ folder</div>
        <div style={{ fontSize: 12.5, opacity: 0.85, marginBottom: 8 }}>
          Đã khớp + upload <strong>{result.matched.length}</strong> file
          {result.unmatched.length > 0 ? `, ${result.unmatched.length} file chưa khớp.` : "."}
        </div>
        {result.unmatched.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {result.unmatched.map((u) => (
              <div key={u.filename} style={{ padding: "6px 10px", borderRadius: "var(--radius-sm)", background: "var(--color-danger-bg)" }}>
                <div style={{ fontSize: 12.5, fontFamily: "ui-monospace,monospace" }}>{u.filename}</div>
                <div style={{ fontSize: 11.5, color: "var(--color-danger)" }}>{u.reason}</div>
              </div>
            ))}
          </div>
        )}
        <div className="dialog-actions">
          <button className="btn btn-primary" onClick={onClose}>
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}

/** Banner tóm tắt 1 lượt "Xoá watermark toàn bộ slot" (2026-08-28) — người dùng yêu cầu
 * rõ "nếu ảnh nào không phát hiện watermark thì có thông báo rõ ràng"; với cả BLOCK, gộp
 * 1 banner duy nhất sau khi quét xong dễ thấy hơn hẳn phải tự rà từng shot. Màu trung
 * tính (accent, không phải danger) trừ khi có shot lỗi thật — "không tìm thấy watermark"
 * không phải điều gì đáng báo động, chỉ là thông tin. */
function WatermarkSummaryBanner({ summary, onDismiss }: { summary: WatermarkScanSummary; onDismiss: () => void }) {
  const parts: string[] = [];
  if (summary.cleaned > 0) parts.push(`${summary.cleaned} shot đã xoá watermark`);
  if (summary.no_watermark > 0) parts.push(`${summary.no_watermark} shot không phát hiện watermark`);
  if (summary.failed > 0) parts.push(`${summary.failed} shot lỗi`);
  return (
    <div
      style={{
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, fontSize: 12.5, padding: "8px 12px",
        marginBottom: "var(--space-3)", maxWidth: 900, borderRadius: "var(--radius-sm)",
        background: summary.failed > 0 ? "var(--color-danger-bg)" : "color-mix(in srgb, var(--color-accent) 12%, transparent)",
        color: summary.failed > 0 ? "var(--color-danger)" : "var(--color-text)",
      }}
    >
      <span>
        Đã quét {summary.scanned} shot — {parts.join(", ") || "không có shot nào đủ điều kiện quét"}.
      </span>
      <button className="btn btn-icon btn-secondary" onClick={onDismiss} title="Đóng" style={{ flex: "none" }}>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>
    </div>
  );
}

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

/** Ảnh nhân vật tham khảo RIÊNG của project — **mới (2026-09-09, mục 127)**, theo yêu cầu
 * người dùng: upload 1 ảnh nhân vật (VD ảnh shot trước đã ưng ý), backend TỰ ĐỘNG sinh
 * `description` qua VisionProvider (đồng bộ, xong ngay trong response upload — xem
 * `app/routers/render.py::upload_character_reference`) — mô tả này tự nối vào MỌI prompt
 * sinh ảnh của project (xem `_build_visual_prompt`), đây là bản TỰ ĐỘNG HOÁ của cách làm
 * thủ công đã verify hiệu quả thật ở mục 126 (mô tả ngoại hình nhân vật bằng chữ giữ
 * đồng nhất tốt hơn hẳn Flux Redux/PuLID-Flux). KHÔNG có cấp kênh để kế thừa (khác
 * `IntroShotCard`/`BgMusicCard` — nhân vật tham khảo đặc thù từng project, không có
 * BrandProfile field tương ứng) — đơn giản hơn nhiều: 1 ảnh, 1 mô tả, sửa tay được. */
function CharacterReferenceCard({ projectId, characterReference, refresh }: { projectId: string; characterReference: CharacterReferenceStatus | null; refresh: () => Promise<void> }) {
  const [uploading, setUploading] = useState(false);
  const [recaptioning, setRecaptioning] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cacheBust, setCacheBust] = useState(0);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [editingDesc, setEditingDesc] = useState(false);
  const [savingDesc, setSavingDesc] = useState(false);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      await api.uploadCharacterReference(projectId, file);
      await refresh();
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload ảnh nhân vật tham khảo.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function recaption() {
    setRecaptioning(true);
    setError(null);
    try {
      await api.recaptionCharacterReference(projectId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi sinh lại mô tả.");
    } finally {
      setRecaptioning(false);
    }
  }

  async function saveDescription(value: string) {
    setSavingDesc(true);
    setError(null);
    try {
      await api.patchCharacterReferenceDescription(projectId, value);
      await refresh();
      setEditingDesc(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi lưu mô tả.");
    } finally {
      setSavingDesc(false);
    }
  }

  async function remove() {
    if (!confirm("Bỏ ảnh nhân vật tham khảo? Mô tả sẽ không còn được nối vào prompt sinh ảnh nữa.")) return;
    setRemoving(true);
    setError(null);
    try {
      await api.deleteCharacterReference(projectId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi bỏ ảnh tham khảo.");
    } finally {
      setRemoving(false);
    }
  }

  const hasImage = !!characterReference?.image_path;

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Nhân vật tham khảo (tuỳ chọn){" "}
          {hasImage && <span className="tag tag-accent" style={{ marginLeft: 6 }}>Đang dùng — nối mô tả vào mọi prompt sinh ảnh</span>}
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.6 }}>Upload 1 ảnh nhân vật (VD ảnh shot đã ưng ý) — tự sinh mô tả ngoại hình, giúp giữ đồng nhất nhân vật giữa các shot</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "var(--space-3)", alignItems: "flex-start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ height: 140, borderRadius: "var(--radius-sm)", background: "var(--color-bg)", display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
            {hasImage ? (
              <img alt="Nhân vật tham khảo" src={`${api.characterReferenceAssetUrl(projectId)}?v=${cacheBust}`} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            ) : (
              <span style={{ fontSize: 11.5, opacity: 0.5, textAlign: "center", padding: 8 }}>Chưa có</span>
            )}
          </div>
          {hasImage && <AddToLibraryButton kind="image" sourceUrl={`${api.characterReferenceAssetUrl(projectId)}?v=${cacheBust}`} name="nhan-vat-tham-khao" />}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          <div className="field" style={{ margin: 0 }}>
            <label>Mô tả ngoại hình (tự sinh, nối vào mọi prompt sinh ảnh)</label>
            {editingDesc ? (
              <textarea
                className="input"
                rows={2}
                style={{ fontSize: 13 }}
                defaultValue={characterReference?.description || ""}
                autoFocus
                disabled={savingDesc}
                onBlur={(e) => saveDescription(e.target.value)}
              />
            ) : (
              <div
                style={{ fontSize: 13, opacity: hasImage ? 1 : 0.5, padding: 8, background: "var(--color-bg)", borderRadius: "var(--radius-sm)", cursor: hasImage ? "text" : "default" }}
                onClick={() => hasImage && setEditingDesc(true)}
              >
                {characterReference?.description || (hasImage ? "— chưa có, đang sinh hoặc bấm để tự gõ —" : "— upload ảnh để tự sinh mô tả —")}
              </div>
            )}
            {characterReference?.caption_error && (
              <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 4 }}>Lỗi sinh mô tả tự động: {characterReference.caption_error}</div>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
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
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => fileRef.current?.click()} disabled={uploading}>
              {uploading ? "Đang tải lên..." : hasImage ? "Thay ảnh" : "Upload ảnh"}
            </button>
            {hasImage && (
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={recaption} disabled={recaptioning}>
                {recaptioning ? "Đang sinh lại..." : "Sinh lại mô tả"}
              </button>
            )}
            {hasImage && (
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px", color: "var(--color-danger)" }} onClick={remove} disabled={removing}>
                {removing ? "Đang bỏ..." : "Bỏ ảnh tham khảo"}
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
 * `pack.shots`, sống trong render.json (render module tách biệt script core).
 *
 * **Đổi (2026-08-23, theo yêu cầu người dùng "cũng cần inherit từ brand profile ...
 * tương tự intro video")**: TRƯỚC ĐÂY khi project chưa upload gì, card hiện trống dù lúc
 * ghép MP4 THẬT SỰ đã tự fallback dùng nhạc nền mặc định cấp kênh (`resolve_bg_music_
 * source`, fallback NGẦM, không hiện gì ở UI) — giờ card HIỂN THỊ đúng nhạc nền thương
 * hiệu sẽ dùng (preview thật, có thể nghe), gắn nhãn "Kế thừa từ hồ sơ thương hiệu",
 * cùng nguyên tắc `IntroShotCard`. KHÔNG có nút "tắt hẳn kế thừa" như intro (bg-music
 * không có khái niệm `disabled` — chỉ override hoặc không) vì chưa có yêu cầu đó.
 *
 * **Đổi thêm (2026-08-23, theo yêu cầu người dùng "cũng cần bổ sung cấu hình âm lượng ở
 * Visual Studio tương tự như ở brand profile")**: thanh trượt âm lượng giờ LUÔN hiện khi
 * CÓ nguồn nhạc (asset riêng HOẶC đang kế thừa brand) — cho phép "dùng nhạc brand, chỉnh
 * âm lượng riêng cho project này" mà KHÔNG cần upload lại file. PATCH volume-only (chưa
 * có asset riêng) tạo `BgMusicOverride(asset_path=None, volume=X)` — `resolve_bg_music_
 * source` (đã đổi cùng đợt) áp dụng ĐÚNG volume này lên file nhạc của BRAND, không còn
 * bị bỏ qua như trước. Giá trị khởi điểm của thanh trượt khi CHƯA có override riêng =
 * volume hiện tại của brand (không phải mặc định cứng 0.3) để không gây "nhảy giá trị"
 * khi người dùng vừa mở card. Đọc BrandProfile qua `api.getBrandProfile` chỉ để HIỂN
 * THỊ, không PUT lại — cùng nguyên tắc `IntroShotCard`. */
function BgMusicCard({ projectId, channelId, bgMusic, refresh }: { projectId: string; channelId: string; bgMusic: BgMusicOverride | null; refresh: () => Promise<void> }) {
  const [uploading, setUploading] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cacheBust, setCacheBust] = useState(0);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // Nhạc nền mặc định cấp kênh — CHỈ đọc để hiển thị preview "kế thừa" + volume khởi
  // điểm cho thanh trượt, không bao giờ ghi ngược lại (xem docstring). `""` = chưa cấu
  // hình field đó ở BrandProfile.
  const [brandBgMusicPath, setBrandBgMusicPath] = useState("");
  const [brandBgMusicVolume, setBrandBgMusicVolume] = useState(0.3);
  useEffect(() => {
    let cancelled = false;
    api
      .getBrandProfile(channelId)
      .then((bp) => {
        if (cancelled) return;
        setBrandBgMusicPath(bp.bg_music_path || "");
        setBrandBgMusicVolume(bp.bg_music_volume ?? 0.3);
      })
      .catch(() => {
        if (!cancelled) {
          setBrandBgMusicPath("");
          setBrandBgMusicVolume(0.3);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [channelId, cacheBust]);

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
  const isInheriting = !hasAsset && !!brandBgMusicPath;
  const hasSource = hasAsset || isInheriting;
  const volume = bgMusic?.volume ?? brandBgMusicVolume;

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Nhạc nền riêng {hasAsset && <span className="tag tag-accent" style={{ marginLeft: 6 }}>Đang dùng — ghi đè nhạc nền mặc định của kênh</span>}
          {isInheriting && <span className="tag" style={{ marginLeft: 6 }}>Kế thừa từ hồ sơ thương hiệu</span>}
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
          <>
            {isInheriting && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <audio controls style={{ flex: 1, height: 32, minWidth: 160 }} src={`${api.brandBgMusicUrl(channelId)}?v=${cacheBust}`} />
                <AddToLibraryButton kind="music" sourceUrl={`${api.brandBgMusicUrl(channelId)}?v=${cacheBust}`} name="nhac-nen-thuong-hieu" />
              </div>
            )}
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
          </>
        )}
        {hasSource && (
          <div style={{ maxWidth: 320 }}>
            <label style={{ fontSize: 11 }}>
              Âm lượng nhạc nền so với giọng đọc chính ({Math.round(volume * 100)}%)
              {isInheriting && <span style={{ opacity: 0.6 }}> — chỉnh riêng cho project này, vẫn dùng nhạc của kênh</span>}
            </label>
            <input key={hasAsset ? "own" : "inherit"} type="range" min={0} max={1} step={0.05} defaultValue={volume} onMouseUp={(e) => setVolume(parseFloat((e.target as HTMLInputElement).value))} onTouchEnd={(e) => setVolume(parseFloat((e.target as HTMLInputElement).value))} style={{ width: "100%" }} />
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
 * chỉ đổi audio→video, xem `app/render/overlay.py::resolve_overlay_source`.
 *
 * **Đổi (2026-08-23, theo yêu cầu người dùng "cũng cần inherit từ brand profile ...
 * tương tự intro video")** — cùng lý do/nguyên tắc đổi ở `BgMusicCard`: hiển thị THẬT
 * overlay mặc định cấp kênh (preview video, gắn nhãn "Kế thừa từ hồ sơ thương hiệu") khi
 * project chưa có overlay riêng, thay vì hiện trống dù thực tế lúc ghép vẫn tự dùng overlay
 * thương hiệu. */
function OverlayEffectCard({ projectId, channelId, overlay, refresh }: { projectId: string; channelId: string; overlay: OverlayEffectOverride | null; refresh: () => Promise<void> }) {
  const [uploading, setUploading] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [enabling, setEnabling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cacheBust, setCacheBust] = useState(0);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // Overlay mặc định cấp kênh — CHỈ đọc để hiển thị preview "kế thừa", không bao giờ
  // ghi ngược lại (xem docstring). `""` = chưa cấu hình field đó ở BrandProfile.
  const [brandOverlayPath, setBrandOverlayPath] = useState("");
  useEffect(() => {
    let cancelled = false;
    api
      .getBrandProfile(channelId)
      .then((bp) => {
        if (!cancelled) setBrandOverlayPath(bp.overlay_effect_path || "");
      })
      .catch(() => {
        if (!cancelled) setBrandOverlayPath("");
      });
    return () => {
      cancelled = true;
    };
  }, [channelId, cacheBust]);

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
      setError(e instanceof ApiError ? e.message : "Có lỗi khi bỏ hiệu ứng lớp phủ.");
    } finally {
      setRemoving(false);
    }
  }

  async function enableInherit() {
    setEnabling(true);
    setError(null);
    try {
      await api.enableOverlayInherit(projectId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi dùng lại mặc định thương hiệu.");
    } finally {
      setEnabling(false);
    }
  }

  const hasAsset = !!overlay?.asset_path;
  const isDisabled = !!overlay?.disabled;
  const isInheriting = !hasAsset && !isDisabled && !!brandOverlayPath;
  const opacity = overlay?.opacity ?? 0.5;

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Hiệu ứng lớp phủ riêng {hasAsset && <span className="tag tag-accent" style={{ marginLeft: 6 }}>Đang dùng — ghi đè hiệu ứng mặc định của kênh</span>}
          {isInheriting && <span className="tag" style={{ marginLeft: 6 }}>Kế thừa từ hồ sơ thương hiệu</span>}
          {isDisabled && <span className="tag tag-outline" style={{ marginLeft: 6, color: "var(--color-danger)" }}>Đã tắt — không dùng overlay</span>}
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.6 }}>Tuỳ chọn — override hiệu ứng lớp phủ mặc định của kênh (sửa ở BrandProfile) chỉ cho project này. VD mưa/tuyết rơi.</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        {hasAsset ? (
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <video controls muted style={{ flex: 1, maxHeight: 120, minWidth: 160 }} src={`${api.projectOverlayUrl(projectId)}?v=${cacheBust}`} />
            <AddToLibraryButton kind="video" sourceUrl={`${api.projectOverlayUrl(projectId)}?v=${cacheBust}`} name="overlay-project" />
            <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px", color: "var(--color-danger)" }} onClick={remove} disabled={removing}>
              {removing ? "Đang bỏ..." : "Bỏ hiệu ứng lớp phủ"}
            </button>
          </div>
        ) : (
          <>
            {isInheriting && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <video controls muted style={{ flex: 1, maxHeight: 120, minWidth: 160 }} src={`${api.brandOverlayUrl(channelId)}?v=${cacheBust}`} />
                <AddToLibraryButton kind="video" sourceUrl={`${api.brandOverlayUrl(channelId)}?v=${cacheBust}`} name="overlay-thuong-hieu" />
              </div>
            )}
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
              {/* Bỏ hẳn overlay (kể cả đang KẾ THỪA từ kênh) — mới (2026-09-02), theo yêu
                  cầu người dùng: trước đây không có cách tắt overlay khi đang kế thừa,
                  chỉ xoá được override RIÊNG (đã có sẵn asset). */}
              {isInheriting && (
                <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px", color: "var(--color-danger)" }} onClick={remove} disabled={removing}>
                  {removing ? "Đang bỏ..." : "Bỏ hiệu ứng lớp phủ"}
                </button>
              )}
              {isDisabled && brandOverlayPath && (
                <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={enableInherit} disabled={enabling}>
                  {enabling ? "Đang bật lại..." : "Dùng lại mặc định thương hiệu"}
                </button>
              )}
            </div>
          </>
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

/** Video nền CHUNG cho toàn bộ block — **mới (2026-09-02)**, theo yêu cầu người dùng:
 * loop theo đúng tổng thời lượng timeline (không phân biệt ranh giới từng shot). Shot
 * NÀO CHƯA cấu hình visual riêng (chưa sinh/upload ảnh/video ở ShotCard) tự lấy đúng
 * đoạn nền tương ứng làm nội dung; shot ĐÃ có visual riêng thay thế TOÀN MÀN HÌNH cho
 * đúng khoảng thời gian của nó (cắt cảnh về nền ngay sau khi hết shot) — xem
 * `app/render/assembly.py::assemble_video`. KHÁC hẳn "Hiệu ứng lớp phủ" ở trên (overlay
 * đè MỜ liên tục suốt video, KHÔNG thay thế nội dung) — đây thay THẾ HẲN cho những slot
 * chưa cấu hình gì, KHÔNG có cấp kênh mặc định để kế thừa (thuần override của project).
 *
 * **Nhiều video (mới 2026-09-02, mục 110)** — theo yêu cầu người dùng: cho phép upload
 * NHIỀU video (nối thành 1 "playlist" lúc ghép), bật/tắt xáo trộn thứ tự mỗi lượt ghép
 * ("random loop"), và chọn hiệu ứng chuyển cảnh giữa các video (cùng danh sách dùng cho
 * shot-to-shot, `TRANSITION_OPTIONS`). 2 tuỳ chọn này chỉ có Ý NGHĨA khi có ≥2 video —
 * ẩn hẳn khi chỉ có 0-1 video để đỡ rối. */
function BackgroundVideoCard({ projectId, backgroundVideo, refresh }: { projectId: string; backgroundVideo: BackgroundVideoOverride | null; refresh: () => Promise<void> }) {
  const [uploading, setUploading] = useState(false);
  const [removingIndex, setRemovingIndex] = useState<number | null>(null);
  const [removingAll, setRemovingAll] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cacheBust, setCacheBust] = useState(0);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function uploadFiles(files: FileList | File[]) {
    setUploading(true);
    setError(null);
    try {
      // Tuần tự (không Promise.all) — mỗi lần upload APPEND vào asset_paths qua
      // render.json đọc-sửa-ghi (xem router), song song thật sự có thể ghi đè nhau.
      for (const f of Array.from(files)) {
        await api.uploadProjectBackgroundVideo(projectId, f);
      }
      await refresh();
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload video nền.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function removeItem(index: number) {
    setRemovingIndex(index);
    setError(null);
    try {
      await api.deleteProjectBackgroundVideoItem(projectId, index);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi bỏ video nền.");
    } finally {
      setRemovingIndex(null);
    }
  }

  async function removeAll() {
    setRemovingAll(true);
    setError(null);
    try {
      await api.deleteProjectBackgroundVideo(projectId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi bỏ video nền.");
    } finally {
      setRemovingAll(false);
    }
  }

  async function patchSettings(patch: Partial<{ random_order: boolean; transition: string }>) {
    setSavingSettings(true);
    setError(null);
    try {
      await api.patchProjectBackgroundVideoSettings(projectId, patch);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi lưu cấu hình video nền.");
    } finally {
      setSavingSettings(false);
    }
  }

  const paths = backgroundVideo?.asset_paths || [];
  const hasAssets = paths.length > 0;

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Video nền chung {hasAssets && <span className="tag tag-accent" style={{ marginLeft: 6 }}>Đang dùng ({paths.length} video)</span>}
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.6 }}>Tuỳ chọn — loop suốt toàn bộ giọng đọc, lấp cho slot nào CHƯA cấu hình ảnh/video riêng. Slot đã có visual riêng vẫn thay thế toàn màn hình như bình thường.</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        {hasAssets && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {paths.map((_, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span className="tag tag-neutral" style={{ fontFamily: "ui-monospace,monospace" }}>
                  #{i + 1}
                </span>
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <video controls muted style={{ flex: 1, maxHeight: 100, minWidth: 160 }} src={`${api.projectBackgroundVideoUrl(projectId, i)}?v=${cacheBust}`} />
                <AddToLibraryButton kind="video" sourceUrl={`${api.projectBackgroundVideoUrl(projectId, i)}?v=${cacheBust}`} name={`video-nen-project-${i + 1}`} />
                <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px", color: "var(--color-danger)" }} onClick={() => removeItem(i)} disabled={removingIndex === i}>
                  {removingIndex === i ? "Đang bỏ..." : "Bỏ video này"}
                </button>
              </div>
            ))}
            {paths.length > 1 && (
              <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", fontSize: 12.5 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                  <input type="checkbox" checked={backgroundVideo?.random_order ?? false} disabled={savingSettings} onChange={(e) => patchSettings({ random_order: e.target.checked })} />
                  Random loop (xáo trộn thứ tự các video mỗi lượt ghép)
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  Chuyển cảnh giữa các video:
                  <select className="input" style={{ fontSize: 12, width: "auto" }} value={backgroundVideo?.transition ?? "cut"} disabled={savingSettings} onChange={(e) => patchSettings({ transition: e.target.value })}>
                    {TRANSITION_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
            <div>
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px", color: "var(--color-danger)" }} onClick={removeAll} disabled={removingAll}>
                {removingAll ? "Đang bỏ..." : "Bỏ toàn bộ video nền"}
              </button>
            </div>
          </div>
        )}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            ref={fileRef}
            type="file"
            accept="video/mp4,video/webm,video/quicktime"
            multiple
            style={{ display: "none" }}
            onChange={(e) => {
              const files = e.target.files;
              if (files && files.length > 0) uploadFiles(files);
            }}
          />
          <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? "Đang tải lên..." : "Thêm video nền"}
          </button>
          <LibraryPicker kinds={["video"]} disabled={uploading} onPick={(file) => uploadFiles([file])} />
        </div>
        {error && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{error}</div>}
      </div>
    </div>
  );
}

// Lưới chọn vị trí 3x3 — dùng chung cho layer MỚI (sắp upload) và từng layer ĐÃ có
// (đổi vị trí tại chỗ). Ô đang chọn tô sáng — mới (2026-09-02, mục 112).
const POSITION_GRID: LayerPosition[] = [
  "top-left", "top-center", "top-right",
  "middle-left", "center", "middle-right",
  "bottom-left", "bottom-center", "bottom-right",
];

// `allowFull` — mới (2026-09-02, mục 115), theo yêu cầu người dùng: layer ẢNH "ngoài hỗ
// trợ 9 vị trí layer thì còn hỗ trợ thêm full khung hình" — thêm 1 nút riêng BÊN DƯỚI
// lưới 3x3 (không phải ô thứ 10 trong lưới — "full" về ý nghĩa khác hẳn 1 VỊ TRÍ trong
// lưới, xứng đáng tách biệt về thị giác). Generic theo `P` để dùng CHUNG được cho cả
// `LayerPosition` (layer video, không có "full") lẫn `ImageLayerPosition` (layer ảnh, có
// "full") mà vẫn giữ đúng kiểu tại từng nơi gọi — ép kiểu `as P` bên trong an toàn vì
// literal string luôn là thành viên hợp lệ của `P` theo đúng cách hàm được gọi.
function PositionGridPicker<P extends string>({ value, onChange, disabled, allowFull }: { value: P; onChange: (p: P) => void; disabled?: boolean; allowFull?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 26px)", gridTemplateRows: "repeat(3, 26px)", gap: 3 }}>
        {POSITION_GRID.map((pos) => (
          <button
            key={pos}
            type="button"
            title={pos}
            disabled={disabled}
            onClick={() => onChange(pos as P)}
            style={{
              border: "1px solid color-mix(in srgb, var(--color-text) 25%, transparent)",
              borderRadius: 3,
              background: pos === (value as string) ? "var(--color-accent)" : "transparent",
              cursor: disabled ? "default" : "pointer",
              padding: 0,
            }}
          />
        ))}
      </div>
      {allowFull && (
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange("full" as P)}
          className={value === ("full" as P) ? "btn btn-primary" : "btn btn-secondary"}
          style={{ fontSize: 10.5, padding: "3px 6px" }}
        >
          Toàn khung hình
        </button>
      )}
    </div>
  );
}

/** Layer video ĐỊNH VỊ theo lưới 3x3 (VD voice wave, logo) — **mới (2026-09-02, mục
 * 112)**, theo yêu cầu người dùng: "thêm layer voice wave (dạng video loop) vào bên
 * trên video nền", đặt tại 1 trong 9 ô lưới thay vì phủ hết khung hình như "Hiệu ứng
 * lớp phủ" (screen-blend, dành cho clip nền đen VD mưa/tuyết). Nguồn CẦN CÓ SẴN kênh
 * alpha (WebM VP9/MOV ProRes4444 trong suốt) — xem docstring backend `VideoLayer`.
 * Nhiều layer cùng lúc (danh sách) — VD voice wave góc dưới + logo góc trên. */
function LayersCard({ projectId, layers, refresh }: { projectId: string; layers: VideoLayer[]; refresh: () => Promise<void> }) {
  const [uploading, setUploading] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cacheBust, setCacheBust] = useState(0);
  const fileRef = useRef<HTMLInputElement | null>(null);
  // Bug thật (2026-09-03): preview mỗi layer dùng <video loop> (khác preview overlay/
  // video nền — KHÔNG loop) — nếu người dùng bấm play để xem trước rồi bấm "Bỏ layer"
  // trong lúc nó ĐANG PHÁT, `loop` khiến trình duyệt liên tục tự request lại file, giữ
  // handle đọc trên Windows LÂU HƠN cửa sổ thử lại 1.5s của `unlink_retrying` (backend) —
  // khác 1 khoá thoáng qua bình thường, đây là khoá ĐANG DIỄN RA liên tục. Giữ ref tới
  // từng <video> để chủ động dừng + tháo hẳn `src` NGAY TRƯỚC khi gọi xoá, ép trình duyệt
  // nhả file kịp trong cửa sổ thử lại của backend thay vì trông chờ hoàn toàn vào đó.
  const videoRefs = useRef<Map<string, HTMLVideoElement>>(new Map());

  // Cấu hình cho layer SẮP upload — chọn TRƯỚC khi bấm chọn file, gửi kèm ngay lúc
  // upload (khác layer ĐÃ có — chỉnh tại chỗ qua PATCH sau khi đã tồn tại).
  const [pendingPosition, setPendingPosition] = useState<LayerPosition>("bottom-center");
  const [pendingWidthPct, setPendingWidthPct] = useState(0.3);
  const [pendingOpacity, setPendingOpacity] = useState(1);
  // "screen" — mới (2026-09-02, mục 113), theo yêu cầu người dùng: nguồn NỀN ĐEN ĐẶC
  // (không có sẵn kênh alpha) — dùng kỹ thuật screen-blend thay vì overlay alpha thẳng.
  const [pendingBlendMode, setPendingBlendMode] = useState<LayerBlendMode>("alpha");

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      await api.uploadProjectLayer(projectId, file, pendingPosition, pendingWidthPct, pendingOpacity, pendingBlendMode);
      await refresh();
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload layer.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function patchLayer(layerId: string, patch: Partial<{ position: LayerPosition; width_pct: number; opacity: number; blend_mode: LayerBlendMode }>) {
    setSavingId(layerId);
    setError(null);
    try {
      await api.patchProjectLayer(projectId, layerId, patch);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi lưu cấu hình layer.");
    } finally {
      setSavingId(null);
    }
  }

  async function removeLayer(layerId: string) {
    setRemovingId(layerId);
    setError(null);
    try {
      // Dừng + tháo hẳn preview TRƯỚC khi gọi xoá — xem ghi chú ở khai báo `videoRefs`.
      const videoEl = videoRefs.current.get(layerId);
      if (videoEl) {
        videoEl.pause();
        videoEl.removeAttribute("src");
        videoEl.load();
      }
      await api.deleteProjectLayer(projectId, layerId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi bỏ layer.");
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Layer video định vị {layers.length > 0 && <span className="tag tag-accent" style={{ marginLeft: 6 }}>{layers.length} layer</span>}
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.6 }}>
          Tuỳ chọn — đặt 1 video loop (VD voice wave, logo) tại 1 vị trí cố định trên khung hình, đè suốt toàn bộ video. Nguồn có sẵn nền TRONG SUỐT (alpha) chọn "Trong suốt (alpha)"; nguồn nền ĐEN ĐẶC (clip hiệu ứng thường) chọn "Nền đen (screen)".
        </span>
      </div>

      {layers.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {layers.map((layer) => (
            <div key={layer.id} style={{ display: "flex", alignItems: "flex-start", gap: 16, flexWrap: "wrap", padding: 8, background: "var(--color-bg)", borderRadius: "var(--radius-sm)" }}>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video
                ref={(el) => {
                  if (el) videoRefs.current.set(layer.id, el);
                  else videoRefs.current.delete(layer.id);
                }}
                controls
                muted
                loop
                style={{ width: 160, maxHeight: 100 }}
                src={`${api.projectLayerAssetUrl(projectId, layer.id)}?v=${cacheBust}`}
              />
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 11 }}>Vị trí</label>
                <PositionGridPicker value={layer.position} disabled={savingId === layer.id} onChange={(pos) => patchLayer(layer.id, { position: pos })} />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={{ fontSize: 11 }}>Kiểu nguồn</label>
                <select
                  className="input"
                  style={{ fontSize: 12 }}
                  value={layer.blend_mode}
                  disabled={savingId === layer.id}
                  onChange={(e) => patchLayer(layer.id, { blend_mode: e.target.value as LayerBlendMode })}
                >
                  <option value="alpha">Trong suốt (alpha)</option>
                  <option value="screen">Nền đen (screen)</option>
                </select>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 160 }}>
                <label style={{ fontSize: 11 }}>Kích thước ({Math.round(layer.width_pct * 100)}% chiều rộng)</label>
                <input
                  key={`w-${layer.width_pct}`}
                  type="range"
                  min={0.05}
                  max={1}
                  step={0.05}
                  defaultValue={layer.width_pct}
                  onMouseUp={(e) => patchLayer(layer.id, { width_pct: parseFloat((e.target as HTMLInputElement).value) })}
                  onTouchEnd={(e) => patchLayer(layer.id, { width_pct: parseFloat((e.target as HTMLInputElement).value) })}
                />
                <label style={{ fontSize: 11 }}>Độ mờ ({Math.round(layer.opacity * 100)}%)</label>
                <input
                  key={`o-${layer.opacity}`}
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  defaultValue={layer.opacity}
                  onMouseUp={(e) => patchLayer(layer.id, { opacity: parseFloat((e.target as HTMLInputElement).value) })}
                  onTouchEnd={(e) => patchLayer(layer.id, { opacity: parseFloat((e.target as HTMLInputElement).value) })}
                />
              </div>
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px", color: "var(--color-danger)" }} onClick={() => removeLayer(layer.id)} disabled={removingId === layer.id}>
                {removingId === layer.id ? "Đang bỏ..." : "Bỏ layer"}
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        style={{
          display: "flex", alignItems: "flex-end", gap: 20, flexWrap: "wrap",
          paddingTop: layers.length > 0 ? "var(--space-2)" : 0,
          borderTop: layers.length > 0 ? "1px solid color-mix(in srgb, var(--color-text) 12%, transparent)" : undefined,
        }}
      >
        <div>
          <label style={{ fontSize: 11 }}>Vị trí layer mới</label>
          <PositionGridPicker value={pendingPosition} disabled={uploading} onChange={setPendingPosition} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <label style={{ fontSize: 11 }}>Kiểu nguồn</label>
          <select className="input" style={{ fontSize: 12 }} value={pendingBlendMode} disabled={uploading} onChange={(e) => setPendingBlendMode(e.target.value as LayerBlendMode)}>
            <option value="alpha">Trong suốt (alpha)</option>
            <option value="screen">Nền đen (screen)</option>
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 160 }}>
          <label style={{ fontSize: 11 }}>Kích thước ({Math.round(pendingWidthPct * 100)}%)</label>
          <input type="range" min={0.05} max={1} step={0.05} value={pendingWidthPct} disabled={uploading} onChange={(e) => setPendingWidthPct(parseFloat(e.target.value))} />
          <label style={{ fontSize: 11 }}>Độ mờ ({Math.round(pendingOpacity * 100)}%)</label>
          <input type="range" min={0} max={1} step={0.05} value={pendingOpacity} disabled={uploading} onChange={(e) => setPendingOpacity(parseFloat(e.target.value))} />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            ref={fileRef}
            type="file"
            accept="video/webm,video/quicktime,video/mp4"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload(f);
            }}
          />
          <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? "Đang tải lên..." : "Thêm layer"}
          </button>
          <LibraryPicker kinds={["video"]} disabled={uploading} onPick={upload} />
        </div>
      </div>
      {error && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{error}</div>}
    </div>
  );
}

/** Layer ẢNH ĐỊNH VỊ — **mới (2026-09-02, mục 115)**, theo yêu cầu người dùng: "bổ sung
 * thêm block... setup Layer ảnh định vị với chức năng tương tự [layer video] nhưng cho
 * ảnh nền đen hoặc không có nền. Ngoài hỗ trợ 9 vị trí layer thì còn hỗ trợ thêm full
 * khung hình". Song song `LayersCard` ở trên (danh sách riêng, không dùng chung) — khác
 * 2 điểm: nhận ẢNH (PNG/JPEG/WEBP) thay vì video loop, và lưới vị trí có thêm nút "Toàn
 * khung hình" (`PositionGridPicker allowFull`) — ẩn thanh trượt kích thước khi chọn "full"
 * (không có ý nghĩa, ảnh phủ đúng khung hình xuất). */
function ImageLayersCard({ projectId, layers, refresh }: { projectId: string; layers: ImageLayer[]; refresh: () => Promise<void> }) {
  const [uploading, setUploading] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cacheBust, setCacheBust] = useState(0);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const [pendingPosition, setPendingPosition] = useState<ImageLayerPosition>("bottom-center");
  const [pendingWidthPct, setPendingWidthPct] = useState(0.3);
  const [pendingOpacity, setPendingOpacity] = useState(1);
  const [pendingBlendMode, setPendingBlendMode] = useState<LayerBlendMode>("alpha");

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      await api.uploadProjectImageLayer(projectId, file, pendingPosition, pendingWidthPct, pendingOpacity, pendingBlendMode);
      await refresh();
      setCacheBust((n) => n + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi upload layer ảnh.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function patchLayer(layerId: string, patch: Partial<{ position: ImageLayerPosition; width_pct: number; opacity: number; blend_mode: LayerBlendMode }>) {
    setSavingId(layerId);
    setError(null);
    try {
      await api.patchProjectImageLayer(projectId, layerId, patch);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi lưu cấu hình layer ảnh.");
    } finally {
      setSavingId(null);
    }
  }

  async function removeLayer(layerId: string) {
    setRemovingId(layerId);
    setError(null);
    try {
      await api.deleteProjectImageLayer(projectId, layerId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi bỏ layer ảnh.");
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Layer ảnh định vị {layers.length > 0 && <span className="tag tag-accent" style={{ marginLeft: 6 }}>{layers.length} layer</span>}
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.6 }}>
          Tuỳ chọn — đặt 1 ảnh (VD khung viền, watermark, vignette) tại 1 vị trí cố định HOẶC phủ toàn khung hình, đè suốt toàn bộ video. Nguồn có sẵn nền TRONG SUỐT chọn "Trong suốt (alpha)"; nguồn nền ĐEN ĐẶC hoặc không nền chọn "Nền đen (screen)".
        </span>
      </div>

      {layers.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {layers.map((layer) => (
            <div key={layer.id} style={{ display: "flex", alignItems: "flex-start", gap: 16, flexWrap: "wrap", padding: 8, background: "var(--color-bg)", borderRadius: "var(--radius-sm)" }}>
              {/* eslint-disable-next-line jsx-a11y/img-redundant-alt */}
              <img alt="layer ảnh" style={{ width: 160, maxHeight: 100, objectFit: "contain", background: "repeating-conic-gradient(#8883 0% 25%, transparent 0% 50%) 50% / 12px 12px" }} src={`${api.projectImageLayerAssetUrl(projectId, layer.id)}?v=${cacheBust}`} />
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 11 }}>Vị trí</label>
                <PositionGridPicker value={layer.position} disabled={savingId === layer.id} allowFull onChange={(pos) => patchLayer(layer.id, { position: pos })} />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label style={{ fontSize: 11 }}>Kiểu nguồn</label>
                <select
                  className="input"
                  style={{ fontSize: 12 }}
                  value={layer.blend_mode}
                  disabled={savingId === layer.id}
                  onChange={(e) => patchLayer(layer.id, { blend_mode: e.target.value as LayerBlendMode })}
                >
                  <option value="alpha">Trong suốt (alpha)</option>
                  <option value="screen">Nền đen (screen)</option>
                </select>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 160 }}>
                {layer.position !== "full" && (
                  <>
                    <label style={{ fontSize: 11 }}>Kích thước ({Math.round(layer.width_pct * 100)}% chiều rộng)</label>
                    <input
                      key={`w-${layer.width_pct}`}
                      type="range"
                      min={0.05}
                      max={1}
                      step={0.05}
                      defaultValue={layer.width_pct}
                      onMouseUp={(e) => patchLayer(layer.id, { width_pct: parseFloat((e.target as HTMLInputElement).value) })}
                      onTouchEnd={(e) => patchLayer(layer.id, { width_pct: parseFloat((e.target as HTMLInputElement).value) })}
                    />
                  </>
                )}
                <label style={{ fontSize: 11 }}>Độ mờ ({Math.round(layer.opacity * 100)}%)</label>
                <input
                  key={`o-${layer.opacity}`}
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  defaultValue={layer.opacity}
                  onMouseUp={(e) => patchLayer(layer.id, { opacity: parseFloat((e.target as HTMLInputElement).value) })}
                  onTouchEnd={(e) => patchLayer(layer.id, { opacity: parseFloat((e.target as HTMLInputElement).value) })}
                />
              </div>
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px", color: "var(--color-danger)" }} onClick={() => removeLayer(layer.id)} disabled={removingId === layer.id}>
                {removingId === layer.id ? "Đang bỏ..." : "Bỏ layer"}
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        style={{
          display: "flex", alignItems: "flex-end", gap: 20, flexWrap: "wrap",
          paddingTop: layers.length > 0 ? "var(--space-2)" : 0,
          borderTop: layers.length > 0 ? "1px solid color-mix(in srgb, var(--color-text) 12%, transparent)" : undefined,
        }}
      >
        <div>
          <label style={{ fontSize: 11 }}>Vị trí layer mới</label>
          <PositionGridPicker value={pendingPosition} disabled={uploading} allowFull onChange={setPendingPosition} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <label style={{ fontSize: 11 }}>Kiểu nguồn</label>
          <select className="input" style={{ fontSize: 12 }} value={pendingBlendMode} disabled={uploading} onChange={(e) => setPendingBlendMode(e.target.value as LayerBlendMode)}>
            <option value="alpha">Trong suốt (alpha)</option>
            <option value="screen">Nền đen (screen)</option>
          </select>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 160 }}>
          {pendingPosition !== "full" && (
            <>
              <label style={{ fontSize: 11 }}>Kích thước ({Math.round(pendingWidthPct * 100)}%)</label>
              <input type="range" min={0.05} max={1} step={0.05} value={pendingWidthPct} disabled={uploading} onChange={(e) => setPendingWidthPct(parseFloat(e.target.value))} />
            </>
          )}
          <label style={{ fontSize: 11 }}>Độ mờ ({Math.round(pendingOpacity * 100)}%)</label>
          <input type="range" min={0} max={1} step={0.05} value={pendingOpacity} disabled={uploading} onChange={(e) => setPendingOpacity(parseFloat(e.target.value))} />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
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
          <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 10px" }} onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? "Đang tải lên..." : "Thêm layer"}
          </button>
          <LibraryPicker kinds={["image"]} disabled={uploading} onPick={upload} />
        </div>
      </div>
      {error && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{error}</div>}
    </div>
  );
}

/** Layer CAPTION (phụ đề cứng burn-in) — **mới (2026-09-12)**, theo yêu cầu người dùng:
 * "Bổ sung tính năng cho phép user thêm caption vào video ở bước visual studio... chọn
 * 9 vị trí, kích thước, độ mờ tương tự phần Layer video định vị". KHÁC LayersCard/
 * ImageLayersCard (list, nhiều instance, upload file) — đây là 1 CẤU HÌNH DUY NHẤT/
 * project, KHÔNG có upload gì (nội dung lấy thẳng từ script, đã sinh giọng đọc hay chưa
 * không quan trọng — chỉ cần có chữ). Ngôn ngữ caption — theo yêu cầu người dùng xác
 * nhận thêm ("chọn cả loại ngôn ngữ nữa") — mặc định "Theo ngôn ngữ đang ghép video"
 * (`lang: null`), đổi được sang ngôn ngữ KHÁC độc lập với ngôn ngữ giọng đọc. */
function CaptionLayerCard({ projectId, channelId, captionLayer, refresh }: { projectId: string; channelId: string; captionLayer: CaptionLayer | null; refresh: () => Promise<void> }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [primaryLanguage, setPrimaryLanguage] = useState<NarrationLanguage>("vi");

  useEffect(() => {
    api.getBrandProfile(channelId).then((bp) => setPrimaryLanguage(bp.primary_language || "vi"), () => {});
  }, [channelId]);

  const layer: CaptionLayer = captionLayer ?? { enabled: false, position: "bottom-center", size_pct: 0.045, opacity: 1, lang: null };

  async function patchCaption(patch: Partial<{ enabled: boolean; position: LayerPosition; size_pct: number; opacity: number; lang: NarrationLanguage | null }>) {
    setSaving(true);
    setError(null);
    try {
      await api.patchCaptionLayer(projectId, patch);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi lưu cấu hình caption.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 900, marginBottom: "var(--space-3)" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div className="card-title">
          Caption (phụ đề cứng) {layer.enabled && <span className="tag tag-accent" style={{ marginLeft: 6 }}>Đang bật</span>}
        </div>
        <span style={{ fontSize: 11.5, opacity: 0.6 }}>
          Tuỳ chọn — chèn phụ đề cứng (burn-in) lấy từ nội dung kịch bản vào video khi ghép, tự cắt nhỏ theo cảnh, đè suốt toàn bộ video (kể cả short-video export).
        </span>
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
        <input type="checkbox" checked={layer.enabled} disabled={saving} onChange={(e) => patchCaption({ enabled: e.target.checked })} />
        Bật caption
      </label>

      {layer.enabled && (
        <div style={{ display: "flex", alignItems: "flex-end", gap: 20, flexWrap: "wrap" }}>
          <div>
            <label style={{ fontSize: 11 }}>Vị trí</label>
            <PositionGridPicker value={layer.position} disabled={saving} onChange={(pos) => patchCaption({ position: pos })} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 160 }}>
            <label style={{ fontSize: 11 }}>Kích thước chữ ({Math.round(layer.size_pct * 100)}% chiều cao)</label>
            <input
              key={`s-${layer.size_pct}`}
              type="range"
              min={0.01}
              max={0.3}
              step={0.005}
              defaultValue={layer.size_pct}
              disabled={saving}
              onMouseUp={(e) => patchCaption({ size_pct: parseFloat((e.target as HTMLInputElement).value) })}
              onTouchEnd={(e) => patchCaption({ size_pct: parseFloat((e.target as HTMLInputElement).value) })}
            />
            <label style={{ fontSize: 11 }}>Độ mờ ({Math.round(layer.opacity * 100)}%)</label>
            <input
              key={`o-${layer.opacity}`}
              type="range"
              min={0}
              max={1}
              step={0.05}
              defaultValue={layer.opacity}
              disabled={saving}
              onMouseUp={(e) => patchCaption({ opacity: parseFloat((e.target as HTMLInputElement).value) })}
              onTouchEnd={(e) => patchCaption({ opacity: parseFloat((e.target as HTMLInputElement).value) })}
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label style={{ fontSize: 11 }}>Ngôn ngữ caption</label>
            <select className="input" style={{ fontSize: 12 }} value={layer.lang ?? ""} disabled={saving} onChange={(e) => patchCaption({ lang: (e.target.value || null) as NarrationLanguage | null })}>
              <option value="">Theo ngôn ngữ đang ghép video</option>
              {NARRATION_LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {NARRATION_LANGUAGE_LABELS[l]}
                  {l === primaryLanguage ? " (ngôn ngữ chính của kênh)" : ""}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
      {error && <div style={{ fontSize: 12, color: "var(--color-danger)" }}>{error}</div>}
    </div>
  );
}

