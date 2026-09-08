import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { AssembleConfig, ExportCodec, ExportQuality, ExportResolution, GpuEncodeStatus, ProductionPack, ProjectSummary, RenderState } from "../../api/types";

const RESOLUTION_LABEL: Record<ExportResolution, string> = { "720p": "720p (1280×720)", "1080p": "1080p (1920×1080)", "4k": "4K (3840×2160)" };
// Short-form (9:16) — mới (2026-08-21): cùng 3 mức chất lượng nhưng chiều DỌC (khớp
// `app/render/assembly.py::RESOLUTION_MAP_VERTICAL`) — chỉ đổi NHÃN hiển thị, giá trị
// `resolution` gửi lên API vẫn y hệt ("720p"/"1080p"/"4k"), backend tự chọn map đúng
// theo `Project.format`.
const RESOLUTION_LABEL_VERTICAL: Record<ExportResolution, string> = { "720p": "720p (720×1280 dọc)", "1080p": "1080p (1080×1920 dọc)", "4k": "4K (2160×3840 dọc)" };
const CODEC_LABEL: Record<ExportCodec, string> = {
  h264: "MP4 · H.264 — tương thích rộng nhất (khuyến nghị cho YouTube)",
  h265: "MP4 · H.265/HEVC — file nhẹ hơn ~30-50%, cần trình phát/thiết bị mới hơn",
  vp9: "WebM · VP9 — mã nguồn mở, YouTube cũng nhận",
};
const QUALITY_LABEL: Record<ExportQuality, string> = { low: "Thấp (file nhẹ)", medium: "Trung bình (khuyến nghị)", high: "Cao (file nặng hơn)" };

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return m > 0 ? `${m} phút ${s}s` : `${s}s`;
}

/** Render Studio — CHỈ còn bước ghép video (ffmpeg). Sinh asset (ảnh/video/giọng đọc)
 * đã chuyển sang Visual Studio (bước ④, trước Gate #2) — nơi người dùng sinh + duyệt
 * từng shot trực tiếp. Màn này đọc lại đúng trạng thái đó (`render.json`, qua GET
 * /render/status) và chỉ cho ghép khi mọi shot đã `visual_status=="ready"` (không còn
 * gate theo `approved` — bỏ 2026-09-02, theo yêu cầu người dùng: bỏ luồng duyệt block,
 * không cần duyệt mới ghép được). Nhúng THẲNG trong Output Center — **đổi (2026-08-26), theo yêu cầu người
 * dùng**: trước đây núp sau nút "Mở Render Studio" (che bằng `renderOpen` state, xem
 * lịch sử component), giờ hiển thị NGAY khi vào Output Center, không cần thêm 1 bước
 * bấm để thấy — đây vốn đã là đường xuất video CHÍNH (duy nhất còn lại sau khi bỏ
 * "Output A"), không có lý do gì phải ẩn sau 1 entry point riêng nữa.
 *
 * Cấu hình export (độ phân giải/codec/chất lượng, giống hộp thoại export phần mềm edit
 * video) + thanh tiến trình (theo segment, kèm ước lượng thời gian còn lại) — thêm
 * theo yêu cầu người dùng, xem app/render/assembly.py cho phần backend tương ứng. */
export default function RenderStudio({ project }: { project: ProjectSummary; pack: ProductionPack }) {
  const [state, setState] = useState<RenderState | null>(null);
  const [assembling, setAssembling] = useState(false);
  const [resettingStuck, setResettingStuck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<AssembleConfig>({ resolution: "1080p", codec: "h264", quality: "medium", use_gpu: false });
  // Trạng thái NVENC thật của máy — không chỉ tra `ffmpeg -encoders`, vì encoder có thể
  // ĐĂNG KÝ nhưng driver NVIDIA chưa đủ mới để chạy được (gặp thật lúc phát triển tính
  // năng này). Kiểm 1 lần khi mở màn, disable checkbox NGAY nếu không dùng được thay vì
  // để người dùng bấm "Ghép video" rồi mới biết fail.
  const [gpuEncode, setGpuEncode] = useState<GpuEncodeStatus | null>(null);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const pollRef = useRef<number | undefined>(undefined);
  const tickRef = useRef<number | undefined>(undefined);
  // `api.renderDownloadUrl(id)` là URL CỐ ĐỊNH (không đổi giữa các lần ghép) — trình
  // duyệt không tự refetch <video> khi backend đã ghi ĐÈ final.mp4 bằng bản MỚI (bug
  // thật người dùng báo, 2026-08-20 — cùng lớp bug đã biết ở ThumbnailCard, xem ghi chú
  // "cacheBust" ở đó). Bump sau MỖI lần ghép xong, gắn vào query string để ép trình
  // duyệt coi là URL mới — không thì người dùng ghép lại (VD sau khi thêm intro) vẫn
  // thấy đúng video CŨ, tưởng nhầm thay đổi không có tác dụng.
  const [cacheBust, setCacheBust] = useState(0);

  async function load() {
    try {
      setState(await api.getRenderStatus(project.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi tải trạng thái render.");
    }
  }

  useEffect(() => {
    load();
    api.getGpuEncodeStatus().then(setGpuEncode, () => setGpuEncode({ available: false, message: "Không kiểm tra được GPU encode." }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  // Mặc định TICK sẵn "Mã hoá bằng GPU (NVENC)" khi máy dùng được — **mới (2026-08-26)**,
  // theo yêu cầu người dùng: trước đây `use_gpu` khởi tạo `false` cố định, người dùng
  // phải tự tick mỗi lần dù máy luôn hỗ trợ GPU. Chỉ tự bật MỘT LẦN khi `gpuEncode` xác
  // nhận `available` — không đè lên lựa chọn người dùng tự tắt sau đó (không phụ thuộc
  // lại `gpuEncode` trong deps, chỉ chạy lại khi chính `gpuEncode` đổi giá trị lần đầu).
  useEffect(() => {
    if (gpuEncode?.available) {
      setConfig((c) => (c.codec === "vp9" ? c : { ...c, use_gpu: true }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gpuEncode]);

  const isAssembling = state?.assembly_status === "assembling";

  useEffect(() => {
    window.clearInterval(pollRef.current);
    if (isAssembling) {
      pollRef.current = window.setInterval(load, 2000);
    }
    return () => window.clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAssembling]);

  // Bump cacheBust đúng lúc CHUYỂN sang "done" (không phải mỗi lần render trong khi đã
  // done) — bắt được cả 2 đường tới trạng thái này: `assemble()` tự load() sau 1s, VÀ
  // vòng poll ở trên trong lúc đang ghép.
  const prevAssemblyStatusRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (state?.assembly_status === "done" && prevAssemblyStatusRef.current !== "done") {
      setCacheBust((n) => n + 1);
    }
    prevAssemblyStatusRef.current = state?.assembly_status;
  }, [state?.assembly_status]);

  useEffect(() => {
    window.clearInterval(tickRef.current);
    if (isAssembling) {
      tickRef.current = window.setInterval(() => setNowTick(Date.now()), 1000);
    }
    return () => window.clearInterval(tickRef.current);
  }, [isAssembling]);

  async function assemble() {
    setAssembling(true);
    setError(null);
    try {
      setState(await api.assembleVideo(project.id, config));
      // BackgroundTasks chạy sau khi response trả về — poll thêm 1 nhịp ngắn để bắt
      // kịp trạng thái thật, cùng lý do đã ghi ở VisualStudio.tsx::startAssetGeneration.
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi ghép video.");
    } finally {
      setAssembling(false);
    }
  }

  // "Đặt lại tiến trình bị treo" — **mới (2026-09-02, mục 111)**, theo yêu cầu người
  // dùng ("giải pháp để xử lý ở tầng UI cho user biết và làm"): bug thật gặp — 1 project
  // dài bị kẹt "assembling" mãi mãi vì thread ghép chết lặng giữa chừng, phải nhờ sửa
  // tay render.json mới bấm ghép lại được. Nút này gọi endpoint mới `render/assemble/
  // reset` — backend tự chối (409) nếu tiến trình vẫn đang chạy THẬT (không phải kẹt),
  // nên bấm nhầm lúc đang chạy bình thường không phá gì cả, chỉ báo lỗi rõ ràng.
  async function resetStuck() {
    setResettingStuck(true);
    setError(null);
    try {
      setState(await api.resetStuckAssembly(project.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Có lỗi khi đặt lại tiến trình.");
    } finally {
      setResettingStuck(false);
    }
  }

  const shots = state?.shots || [];
  const readyCount = shots.filter((s) => s.visual_status === "ready").length;
  // Không còn gate theo `approved` (2026-09-02, theo yêu cầu người dùng — bỏ luồng duyệt
  // block, chỉ cần visual "ready" là ghép được). Shot KHÔNG có visual riêng vẫn tính là
  // "sẵn sàng" nếu project có video nền chung (BackgroundVideoCard, Visual Studio) — khớp
  // đúng điều kiện `assembly.py` Pass 1 đang cho phép.
  const hasBackgroundVideo = !!state?.background_video?.asset_paths?.length;
  const notReadyCount = shots.filter((s) => s.visual_status !== "ready" && !(hasBackgroundVideo && !s.visual_asset_path)).length;
  const canAssemble = shots.length > 0 && notReadyCount === 0;

  // Bug thật người dùng báo (2026-08-23): ảnh hiện ở Visual Studio khác ảnh trong video
  // đã ghép — nguyên nhân là sinh lại ảnh/giọng đọc SAU lần ghép cuối, video cũ không tự
  // cập nhật (đúng theo thiết kế — ghép là hành động rõ ràng người dùng tự bấm, không tự
  // chạy ngầm), nhưng KHÔNG có gì báo cho người dùng biết video đang xem đã lệch so với
  // asset mới nhất. So `assembly_completed_at` (set lúc ghép xong, §04) với
  // `visual_updated_at`/`narration_updated_at` từng shot (set lúc sinh/upload xong — 2
  // field mới cùng đợt) để phát hiện + cảnh báo rõ.
  const staleShotIds = state?.assembly_completed_at
    ? shots
        .filter((s) => {
          const completedAt = new Date(state.assembly_completed_at as string).getTime();
          const visualNewer = !!s.visual_updated_at && new Date(s.visual_updated_at).getTime() > completedAt;
          const narrationNewer = !!s.narration_updated_at && new Date(s.narration_updated_at).getTime() > completedAt;
          return visualNewer || narrationNewer;
        })
        .map((s) => s.shot_id)
    : [];

  const progress = state?.assembly_progress;
  const progressPct = progress && progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0;
  const elapsedSec = state?.assembly_started_at ? Math.max(0, (nowTick - new Date(state.assembly_started_at).getTime()) / 1000) : 0;
  // Ước lượng "còn lại" PHẢI tính theo thời gian trôi từ khi STAGE HIỆN TẠI bắt đầu
  // (`stage_started_at`, mới 2026-09-02, mục 108), KHÔNG PHẢI từ lúc cả assembly bắt đầu
  // (`elapsedSec` ở trên) — project có dùng video nền chung sẽ chạy bước dựng video nền
  // (stage "background_video", có thể mất vài phút với video dài) TRƯỚC stage "segments";
  // gộp chung elapsed sẽ làm thời gian trung bình/segment bị thổi phồng sai lệch ngay ở
  // segment đầu tiên tính xong.
  const stageElapsedSec = progress?.stage_started_at ? Math.max(0, (nowTick - new Date(progress.stage_started_at).getTime()) / 1000) : elapsedSec;
  const remainingSec = progress && progress.current > 0 && progress.stage === "segments" ? (stageElapsedSec / progress.current) * (progress.total - progress.current) : null;

  return (
    <div>
      <div style={{ marginBottom: "var(--space-4)" }}>
        <h3 style={{ marginBottom: 2 }}>Render Studio — Ghép video</h3>
        <p style={{ color: "color-mix(in srgb, var(--color-text) 60%, transparent)", fontSize: 13 }}>
          Ghép asset đã sinh ở Visual Studio thành 1 video hoàn chỉnh.
        </p>
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
            <strong>{readyCount}/{shots.length} shot đã sinh xong visual</strong>
          </div>
          {!canAssemble && (
            <div style={{ fontSize: 11.5, opacity: 0.65 }}>Cần sinh xong visual cho MỌI shot ở Visual Studio trước khi ghép được{hasBackgroundVideo ? " (trừ shot dùng video nền chung)" : ""}.</div>
          )}
        </div>
      )}

      {state?.assembly_status === "done" && staleShotIds.length > 0 && (
        <div
          style={{
            fontSize: 12.5, color: "var(--color-warning)", background: "color-mix(in srgb, var(--color-warning) 12%, transparent)",
            borderRadius: "var(--radius-sm)", padding: "8px 10px", marginBottom: "var(--space-3)", maxWidth: 640,
          }}
        >
          ⚠ Video bên dưới KHÔNG còn khớp — shot {staleShotIds.join(", ")} đã sinh lại ảnh/video/giọng đọc SAU lần ghép gần nhất. Bấm "Ghép lại" để cập nhật video theo đúng asset mới nhất.
        </div>
      )}

      {state?.assembly_status === "done" && state.final_video_path ? (
        <div className="card elev-sm" style={{ gap: "var(--space-2)", maxWidth: 640 }}>
          <div className="card-title">Video hoàn chỉnh</div>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          {/* Short-form (9:16) — mới (2026-08-22): `width: 100%` (khớp card 640px) làm
              video DỌC cao gấp ~1.78 lần bề rộng (VD 640px rộng → ~1138px cao) — tràn
              khỏi viewport, phải cuộn mới xem hết. Vertical: giới hạn theo CHIỀU CAO
              (`maxHeight`, khớp cách Lightbox.tsx đã làm cho preview full-size), để
              chiều rộng tự co lại theo đúng tỷ lệ 9:16 thay vì ép đầy 640px. */}
          <video
            controls
            style={
              project.format === "short"
                ? { maxHeight: "70vh", maxWidth: "100%", width: "auto", display: "block", margin: "0 auto", borderRadius: "var(--radius-sm)" }
                : { width: "100%", borderRadius: "var(--radius-sm)" }
            }
            src={`${api.renderDownloadUrl(project.id)}?v=${cacheBust}`}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" style={{ flex: 1 }} onClick={() => api.downloadRenderFile(project.id)}>
              Tải video
            </button>
            <button className="btn btn-secondary" onClick={() => setState((s) => (s ? { ...s, assembly_status: "not_started", final_video_path: null } : s))}>
              Ghép lại (đổi cấu hình)
            </button>
          </div>
        </div>
      ) : isAssembling ? (
        <div className="card elev-sm" style={{ gap: "var(--space-2)", maxWidth: 640 }}>
          <div className="card-title">
            {progress?.stage === "background_video"
              ? `Đang dựng video nền chung (${progress.current}/${progress.total})... — video dài có thể mất vài phút`
              : progress?.stage === "concat"
              ? "Đang ghép nối các cảnh lại..."
              : `Đang ghép cảnh ${progress?.current ?? 0}/${progress?.total ?? "?"}...`}
          </div>
          <div style={{ height: 8, borderRadius: 999, background: "var(--color-neutral-800)", overflow: "hidden" }}>
            <div
              style={{
                height: "100%", borderRadius: 999, background: "var(--color-accent)", transition: "width 0.4s ease",
                width: `${progress?.stage === "concat" ? 100 : progressPct}%`,
              }}
            />
          </div>
          <div style={{ fontSize: 12, opacity: 0.75, display: "flex", justifyContent: "space-between" }}>
            <span>Đã chạy: {formatDuration(elapsedSec)}</span>
            <span>{remainingSec !== null ? `Còn khoảng: ${formatDuration(remainingSec)}` : "Đang ước lượng..."}</span>
          </div>
          {/* "Đặt lại tiến trình bị treo" — mới (2026-09-02, mục 111). LUÔN hiện (không
              đợi 1 ngưỡng thời gian cố định) — bước "background_video" với video dài có
              thể mất rất lâu MÀ VẪN đang chạy bình thường (số 0/N không nhúc nhích SUỐT
              bước đó là chuyện thật, không phải dấu hiệu treo — xem mục 108), nên không
              có ngưỡng "bao lâu là treo" đáng tin cậy để tự động cảnh báo mà không báo
              nhầm. Thay vào đó: LUÔN cho người dùng quyền tự quyết ngay khi họ nghi ngờ,
              gợi ý rõ SAU 5 phút, backend tự chối (409) nếu tiến trình vẫn đang chạy thật. */}
          <div style={{ fontSize: 11.5, opacity: 0.65, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
            <span>
              {elapsedSec > 300
                ? "Đã chạy khá lâu — nếu nghi ngờ bị treo (không nhúc nhích dù đợi thêm), bạn có thể đặt lại."
                : "Nghi ngờ bị treo?"}
            </span>
            <button className="btn btn-secondary" style={{ fontSize: 11, padding: "3px 8px" }} onClick={resetStuck} disabled={resettingStuck}>
              {resettingStuck ? "Đang đặt lại..." : "Đặt lại tiến trình bị treo"}
            </button>
          </div>
        </div>
      ) : (
        <div className="card elev-sm" style={{ gap: "var(--space-3)", maxWidth: 640 }}>
          <div className="card-kicker">Cấu hình xuất video</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
            <div className="field" style={{ margin: 0 }}>
              <label>Độ phân giải</label>
              <select className="input" value={config.resolution} onChange={(e) => setConfig((c) => ({ ...c, resolution: e.target.value as ExportResolution }))}>
                {(Object.keys(RESOLUTION_LABEL) as ExportResolution[]).map((r) => (
                  <option key={r} value={r}>
                    {(project.format === "short" ? RESOLUTION_LABEL_VERTICAL : RESOLUTION_LABEL)[r]}
                  </option>
                ))}
              </select>
            </div>
            <div className="field" style={{ margin: 0 }}>
              <label>Chất lượng</label>
              <select className="input" value={config.quality} onChange={(e) => setConfig((c) => ({ ...c, quality: e.target.value as ExportQuality }))}>
                {(Object.keys(QUALITY_LABEL) as ExportQuality[]).map((q) => (
                  <option key={q} value={q}>
                    {QUALITY_LABEL[q]}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label>Định dạng</label>
            <select
              className="input"
              value={config.codec}
              onChange={(e) => {
                const codec = e.target.value as ExportCodec;
                // VP9 không có encoder GPU (không có `vp9_nvenc`) — tự tắt use_gpu để
                // tránh gửi tổ hợp không hợp lệ (backend cũng chặn, nhưng tắt sẵn ở UI
                // đỡ người dùng bị 400 bất ngờ).
                setConfig((c) => ({ ...c, codec, use_gpu: codec === "vp9" ? false : c.use_gpu }));
              }}
            >
              {(Object.keys(CODEC_LABEL) as ExportCodec[]).map((c) => (
                <option key={c} value={c}>
                  {CODEC_LABEL[c]}
                </option>
              ))}
            </select>
          </div>
          {config.codec !== "vp9" && (
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, opacity: gpuEncode?.available ? 1 : 0.6 }}>
              <input
                type="checkbox"
                checked={config.use_gpu}
                disabled={!gpuEncode?.available}
                onChange={(e) => setConfig((c) => ({ ...c, use_gpu: e.target.checked }))}
              />
              Mã hoá bằng GPU (NVENC) — nhanh hơn, giảm tải CPU
              {gpuEncode === null && <span style={{ opacity: 0.7 }}>&nbsp;(đang kiểm tra...)</span>}
              {gpuEncode && !gpuEncode.available && (
                <span style={{ color: "var(--color-danger)" }} title={gpuEncode.message}>
                  &nbsp;— không dùng được trên máy này{gpuEncode.message ? `: ${gpuEncode.message.slice(0, 140)}${gpuEncode.message.length > 140 ? "…" : ""}` : ""}
                </span>
              )}
            </label>
          )}
          <button className="btn btn-primary" onClick={assemble} disabled={!canAssemble || assembling}>
            {assembling ? "Đang bắt đầu..." : "Ghép video"}
          </button>
        </div>
      )}
      {state?.assembly_status === "error" && state.assembly_error && (
        <div style={{ fontSize: 12, color: "var(--color-danger)", marginTop: 6, maxWidth: 640 }}>{state.assembly_error}</div>
      )}
    </div>
  );
}
