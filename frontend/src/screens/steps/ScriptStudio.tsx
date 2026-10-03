import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { NarrationLanguage, RenderState, ScriptBodyItem } from "../../api/types";
import { NARRATION_LANGUAGES, NARRATION_LANGUAGE_LABELS } from "../../api/types";
import AiErrorBanner from "../../components/AiErrorBanner";
import { computeEstimatedStats } from "../../components/packStats";
import StatsBar from "../../components/StatsBar";
import StepHeader from "../../components/StepHeader";
import type { StepProps } from "../ProjectView";

export default function ScriptStudio({ project, pack, refresh, busy, setBusy }: StepProps) {
  const script = pack.script;
  const [aiError, setAiError] = useState<string | null>(null);

  const [renderState, setRenderState] = useState<RenderState | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [activeShotId, setActiveShotId] = useState<string | null>(null);
  const [isAudioPlaying, setIsAudioPlaying] = useState(false);
  const [playQueue, setPlayQueue] = useState<string[]>([]);
  const [isPlayingAll, setIsPlayingAll] = useState(false);
  // Ngôn ngữ đang phát (giọng đọc đa ngôn ngữ, 2026-09-04) — theo cùng hàng đợi phát,
  // KHÔNG đổi giữa chừng 1 lượt "Nghe toàn bộ" (mỗi lượt phát chỉ 1 ngôn ngữ).
  const [playingLang, setPlayingLang] = useState<NarrationLanguage>("vi");
  const pollRef = useRef<number | undefined>(undefined);
  const [startingNarration, setStartingNarration] = useState(false);
  const [cancellingNarration, setCancellingNarration] = useState(false);
  const [downloadingAudio, setDownloadingAudio] = useState(false);
  const [narrationError, setNarrationError] = useState<string | null>(null);
  const [editingAudioIndex, setEditingAudioIndex] = useState<number | null>(null);
  const [savingAudioIndex, setSavingAudioIndex] = useState<number | null>(null);
  const [regeneratingBlockIndex, setRegeneratingBlockIndex] = useState<number | null>(null);

  // Giọng đọc đa ngôn ngữ cho thị trường nước ngoài (2026-09-04) — `primaryLanguage`
  // (BrandProfile cấp kênh) quyết định panel Audio MẶC ĐỊNH hiện ngôn ngữ nào (field
  // `audio`/`narration_*` gốc — KHÔNG đổi hành vi render/timestamp). `viewLang` — ngôn
  // ngữ NGƯỜI DÙNG đang chọn xem/thao tác (mặc định = primaryLanguage, đổi qua thanh tag
  // ở đầu trang) — mọi nút hàng loạt (sinh/nghe/tải) + panel Audio từng block đều theo
  // `viewLang` này, KHÔNG phải "primaryLanguage" cố định.
  const [primaryLanguage, setPrimaryLanguage] = useState<NarrationLanguage>("vi");
  const [viewLang, setViewLang] = useState<NarrationLanguage>("vi");
  useEffect(() => {
    api
      .getBrandProfile(project.channel_id)
      .then((bp) => {
        const lang = bp.primary_language || "vi";
        setPrimaryLanguage(lang);
        setViewLang(lang);
      })
      .catch(() => {
        /* BrandProfile luôn tồn tại (tạo kèm kênh) — lỗi hiếm, giữ mặc định "vi" */
      });
  }, [project.channel_id]);

  function loadRenderStatus() {
    api
      .getRenderStatus(project.id)
      .then(setRenderState)
      .catch(() => {
        /* chưa từng sinh asset — bỏ qua, coi như chưa có giọng đọc nào */
      });
  }

  useEffect(() => {
    loadRenderStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

  // Giọng đọc đa ngôn ngữ (2026-09-04) — PHẢI kiểm tra CẢ `narration_translations` (mọi
  // ngôn ngữ khác), không chỉ field `narration_status` gốc — nếu không, batch sinh giọng
  // đọc ngôn ngữ KHÁC ngôn ngữ chính sẽ không tự bật được vòng poll liên tục 3s bên dưới
  // (chỉ còn 2 lần poll cố định lúc bấm nút, có thể "lọt" nếu batch chạy lâu hơn — cùng
  // lớp bug đã sửa ở VisualStudio.tsx::removeAllWatermarks, mục báo cáo trước).
  const hasInFlight =
    !!renderState &&
    renderState.shots.some(
      (s) => s.visual_status === "generating" || s.narration_status === "generating" || Object.values(s.narration_translations).some((t) => t?.narration_status === "generating")
    );

  useEffect(() => {
    window.clearInterval(pollRef.current);
    if (hasInFlight) {
      pollRef.current = window.setInterval(loadRenderStatus, 3000);
    }
    return () => window.clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasInFlight]);

  const hasBody = (script?.body?.length || 0) > 0;

  // Khớp block ↔ shot theo `block_id` (script import — field ổn định, duy nhất) thay vì
  // `timestamp_sec` (bug thật, mục 31 IMPLEMENTATION_REPORT.md: giá trị này có thể lệch
  // giữa lúc tạo shot và lúc script được sửa/import lại, khiến so khớp `===` thất bại
  // âm thầm — Script Studio hiện thiếu giọng đọc dù Visual Studio đã sinh đủ).
  function shotForBlock(block: { block_id?: string | null }, index: number) {
    if (block.block_id) {
      return pack.shots.find((s) => s.block_id === block.block_id);
    }
    return pack.shots[index];
  }

  function narrationStatusFor(shotId: string | undefined) {
    if (!shotId) return undefined;
    return renderState?.shots.find((s) => s.shot_id === shotId);
  }

  // Giọng đọc đa ngôn ngữ (2026-09-04) — chuẩn hoá về CÙNG 1 shape dù đọc từ field gốc
  // (ngôn ngữ chính) hay `narration_translations[lang]` (ngôn ngữ khác), để mọi UI dùng
  // chung 1 logic thay vì rẽ nhánh khắp nơi.
  function narrationEntryForLang(shotId: string | undefined, lang: NarrationLanguage) {
    const shot = narrationStatusFor(shotId);
    if (!shot) return undefined;
    if (lang === primaryLanguage) return { narration_status: shot.narration_status, narration_error: shot.narration_error };
    return shot.narration_translations[lang];
  }

  function textForLang(b: ScriptBodyItem, lang: NarrationLanguage): string {
    return lang === primaryLanguage ? b.audio : b.audio_by_lang?.[lang] || "";
  }

  function assetUrlForLang(shotId: string, lang: NarrationLanguage): string {
    return lang === primaryLanguage ? api.renderShotAssetUrl(project.id, shotId, "narration") : api.renderShotNarrationTranslationAssetUrl(project.id, shotId, lang);
  }

  function playShotAudio(shotId: string, queue: string[], all: boolean, lang: NarrationLanguage) {
    if (!audioRef.current) return;
    setActiveShotId(shotId);
    setPlayQueue(queue);
    setIsPlayingAll(all);
    setPlayingLang(lang);
    // Cache-bust bằng timestamp — cùng lớp bug đã fix ở Visual Studio (2026-08-21): URL
    // asset narration CỐ ĐỊNH theo shot_id, browser HTTP cache có thể trả bản CŨ nếu
    // shot này từng phát qua trước đó trong CÙNG phiên rồi mới sinh lại giọng đọc khác.
    // Gán `.src` mới mỗi lần bấm play (không cần state riêng — hàm này vốn đã chạy lại
    // mỗi lần click) nên dùng thẳng `Date.now()` thay vì đếm cacheBust như nơi khác.
    audioRef.current.src = `${assetUrlForLang(shotId, lang)}?v=${Date.now()}`;
    audioRef.current.play();
  }

  function stopPlayback() {
    audioRef.current?.pause();
    setActiveShotId(null);
    setPlayQueue([]);
    setIsPlayingAll(false);
  }

  function togglePlaySingle(shotId: string, lang: NarrationLanguage) {
    if (activeShotId === shotId && playingLang === lang && isAudioPlaying) {
      audioRef.current?.pause();
      return;
    }
    if (activeShotId === shotId && playingLang === lang && !isAudioPlaying && audioRef.current) {
      setIsPlayingAll(false);
      audioRef.current.play();
      return;
    }
    playShotAudio(shotId, [], false, lang);
  }

  function playAllNarrationLang(lang: NarrationLanguage) {
    if (isPlayingAll && playingLang === lang) {
      stopPlayback();
      return;
    }
    const ordered = (script?.body || [])
      .map((b, i) => shotForBlock(b, i))
      .filter((s) => !!s && narrationEntryForLang(s!.shot_id, lang)?.narration_status === "ready")
      .map((s) => s!.shot_id);
    if (!ordered.length) return;
    playShotAudio(ordered[0], ordered.slice(1), true, lang);
  }

  function handleAudioEnded() {
    if (playQueue.length === 0) {
      setActiveShotId(null);
      setIsPlayingAll(false);
      return;
    }
    const [next, ...rest] = playQueue;
    playShotAudio(next, rest, true, playingLang);
  }

  function readyCountForLang(lang: NarrationLanguage): number {
    return (script?.body || []).filter((b, i) => narrationEntryForLang(shotForBlock(b, i)?.shot_id, lang)?.narration_status === "ready").length;
  }
  const totalBlockCount = (script?.body || []).length;
  const readyNarrationCount = readyCountForLang(viewLang);
  const allNarrationReady = totalBlockCount > 0 && readyNarrationCount === totalBlockCount;
  // Ngôn ngữ nào đã ĐỘNG TỚI (có ít nhất 1 block đã dịch HOẶC đã sinh giọng đọc) — dùng
  // để quyết định tag nào hiện chấm trạng thái "đã có nội dung" ở thanh chọn ngôn ngữ,
  // không phải để giới hạn ngôn ngữ nào chọn được (6 ngôn ngữ LUÔN chọn được).
  function langHasAnyContent(lang: NarrationLanguage): boolean {
    if (lang === primaryLanguage) return true;
    return (script?.body || []).some((b) => (b.audio_by_lang?.[lang] || "").trim().length > 0);
  }

  // `force` — **mới (2026-09-02, mục 109)**: nút "Sinh lại TOÀN BỘ giọng đọc (kể cả đã
  // có)" chuyển từ Visual Studio sang đây (theo yêu cầu người dùng: bỏ hẳn batch giọng
  // đọc ở Visual Studio, gộp cả 2 mức "chỉ lấp chỗ trống" và "sinh lại toàn bộ" vào 1
  // bước duy nhất — Script Studio, nơi kịch bản/giọng đọc được chốt trước khi qua Visual
  // Studio làm hình ảnh).
  async function startNarrationBatch(force = false, lang: NarrationLanguage = primaryLanguage) {
    setStartingNarration(true);
    setNarrationError(null);
    try {
      // Idempotent (BE mục 30 IMPLEMENTATION_REPORT.md) — tạo shot list nếu chưa có,
      // KHÔNG đổi step (khác "Đi tới Visual Studio"). Cần shot_id để render/start lưu
      // được trạng thái narration theo từng block, dù chưa thật sự qua Visual Studio.
      await api.ensureShotsForNarration(project.id);
      await refresh();
      // Giọng đọc đa ngôn ngữ (2026-09-04) — ngôn ngữ CHÍNH đi endpoint gốc (0 đổi hành
      // vi), ngôn ngữ khác đi endpoint riêng theo `lang` (xem app/routers/render.py::
      // start_narration_translation_batch).
      setRenderState(lang === primaryLanguage ? await api.startRender(project.id, "narration", force) : await api.startNarrationTranslationBatch(project.id, lang, force));
      // Cùng lý do timing đã ghi ở VisualStudio.tsx::startAssetGeneration — BackgroundTasks
      // chỉ chạy SAU khi response HTTP trả về, state vừa nhận vẫn là "trước khi sinh".
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
      loadRenderStatus();
      window.setTimeout(loadRenderStatus, 3000);
    } catch (e) {
      setNarrationError(e instanceof ApiError ? e.message : "Có lỗi khi sinh giọng đọc cho toàn bộ block.");
    } finally {
      setStartingNarration(false);
    }
  }

  // Nút "Dừng" — **mới (2026-09-02, mục 110)**, theo yêu cầu người dùng: batch giọng đọc
  // giờ quản lý CHÍNH ở Script Studio (mục 109) nhưng nút dừng vẫn chỉ nằm ở Visual
  // Studio, buộc người dùng rời màn này mới dừng được. Cờ "đang chạy" (`_in_progress`/
  // `_cancel_requested`, `engine.py`) là PER-PROJECT, KHÔNG tách theo kind (visual hay
  // narration) — chỉ 1 batch chạy được cùng lúc cho 1 project (`_require_not_in_progress`
  // chặn mở batch mới khi đã có 1 cái đang chạy), nên KHÔNG cần/không thể "tách riêng" ở
  // tầng backend (không có 2 tiến trình visual+narration chạy song song để tách) — gọi
  // ĐÚNG endpoint `POST render/cancel` y hệt Visual Studio, chỉ khác ở CHỖ hiện nút (màn
  // người dùng đang thao tác), để họ không phải rời Script Studio mới dừng được.
  async function cancelAssetGeneration() {
    setCancellingNarration(true);
    setNarrationError(null);
    try {
      setRenderState(await api.cancelRender(project.id));
      window.setTimeout(loadRenderStatus, 1200);
      window.setTimeout(loadRenderStatus, 3000);
    } catch (e) {
      setNarrationError(e instanceof ApiError ? e.message : "Có lỗi khi dừng sinh giọng đọc.");
    } finally {
      setCancellingNarration(false);
    }
  }

  // Tốc độ giọng đọc TOÀN BỘ block — **mới (2026-09-02, mục 109)**, theo yêu cầu người
  // dùng. Chỉ LƯU giá trị — áp dụng cho lần (re)generate TIẾP THEO (time-stretch file
  // audio sau khi sinh, xem backend `engine.py::_apply_narration_speed`), KHÔNG tự sinh
  // lại narration đã có sẵn (đúng nguyên tắc "không tự chạy ngầm").
  async function setNarrationSpeed(speed: number) {
    setNarrationError(null);
    try {
      setRenderState(await api.patchNarrationSpeed(project.id, speed));
    } catch (e) {
      setNarrationError(e instanceof ApiError ? e.message : "Có lỗi khi chỉnh tốc độ giọng đọc.");
    }
  }

  async function downloadNarrationFull(lang: NarrationLanguage = primaryLanguage) {
    setDownloadingAudio(true);
    setNarrationError(null);
    try {
      await (lang === primaryLanguage ? api.downloadNarrationFull(project.id) : api.downloadNarrationFullLang(project.id, lang));
    } catch (e) {
      setNarrationError(e instanceof ApiError ? e.message : "Có lỗi khi ghép/tải giọng đọc toàn bộ script.");
    } finally {
      setDownloadingAudio(false);
    }
  }

  async function saveBlockAudio(index: number, audio: string, lang: NarrationLanguage = primaryLanguage) {
    setSavingAudioIndex(index);
    setNarrationError(null);
    try {
      // Ngôn ngữ CHÍNH đi đúng endpoint gốc (0 đổi hành vi) — ngôn ngữ khác ghi vào
      // `audio_by_lang[lang]` (xem app/routers/pipeline.py::edit_script_block_translation).
      await (lang === primaryLanguage ? api.editScriptBlockAudio(project.id, index, audio) : api.editScriptBlockTranslation(project.id, index, lang, audio));
      await refresh();
      setEditingAudioIndex(null);
    } catch (e) {
      setNarrationError(e instanceof ApiError ? e.message : "Có lỗi khi lưu nội dung Audio.");
    } finally {
      setSavingAudioIndex(null);
    }
  }

  async function regenerateBlockNarration(index: number, block: { block_id?: string | null }, lang: NarrationLanguage = primaryLanguage) {
    setRegeneratingBlockIndex(index);
    setNarrationError(null);
    try {
      // Đảm bảo có shot cho block này trước (idempotent — mục 30/31 IMPLEMENTATION_REPORT.md).
      // Dùng THẲNG response trả về (không dựa vào `pack` prop — vẫn là bản CŨ trong closure
      // này cho tới lần render kế tiếp sau `refresh()`).
      const updatedPack = await api.ensureShotsForNarration(project.id);
      await refresh();
      const shot = block.block_id ? updatedPack.shots.find((s) => s.block_id === block.block_id) : updatedPack.shots[index];
      if (!shot) throw new Error("Không tìm thấy shot tương ứng cho block này.");
      setRenderState(lang === primaryLanguage ? await api.regenerateShotNarration(project.id, shot.shot_id) : await api.regenerateShotNarrationTranslation(project.id, shot.shot_id, lang));
      await new Promise((resolve) => window.setTimeout(resolve, 1200));
      loadRenderStatus();
      window.setTimeout(loadRenderStatus, 3000);
    } catch (e) {
      setNarrationError(e instanceof ApiError || e instanceof Error ? e.message : "Có lỗi khi sinh giọng đọc cho block này.");
    } finally {
      setRegeneratingBlockIndex(null);
    }
  }

  async function goVisualStudio() {
    setBusy(true);
    setAiError(null);
    try {
      await api.generateVisualShots(project.id);
      await refresh();
    } catch (e) {
      setAiError(e instanceof ApiError ? e.message : "Có lỗi khi sinh shot cho Visual Studio.");
    } finally {
      setBusy(false);
    }
  }

  const warningCount = (script?.body || []).filter((b) => b.warning).length;

  return (
    <div>
      <StepHeader
        title="Script Studio"
        description={
          <>
            Master Production Script — Âm thanh / Hình ảnh / Chỉ dẫn, theo timeline.
            {warningCount > 0 && <span style={{ marginLeft: 8 }}>· {warningCount} cảnh báo</span>}
            {hasBody && <StatsBar {...computeEstimatedStats(pack)} />}
          </>
        }
        actions={
          <button className="btn btn-primary" onClick={goVisualStudio} disabled={busy}>
            {busy ? "Đang xử lý..." : "Đi tới Visual Studio →"}
          </button>
        }
      />

      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} onEnded={handleAudioEnded} onPlay={() => setIsAudioPlaying(true)} onPause={() => setIsAudioPlaying(false)} style={{ display: "none" }} />

      {aiError && <AiErrorBanner message={aiError} onDismiss={() => setAiError(null)} />}

      {/* Giọng đọc đa ngôn ngữ cho thị trường nước ngoài (2026-09-04) — chọn ngôn ngữ
          đang xem/thao tác. Toàn bộ nút hàng loạt + panel Audio từng block bên dưới đều
          theo `viewLang` — mặc định = ngôn ngữ chính của kênh (0 đổi hành vi nếu không
          bấm tag nào). */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: "var(--space-2)" }}>
        <span style={{ fontSize: 11, opacity: 0.6, marginRight: 2 }}>Ngôn ngữ:</span>
        {NARRATION_LANGUAGES.map((lang) => (
          <button
            key={lang}
            type="button"
            className={viewLang === lang ? "tag tag-accent" : "tag tag-outline"}
            style={{ cursor: "pointer", border: "none" }}
            onClick={() => setViewLang(lang)}
            title={lang === primaryLanguage ? "Ngôn ngữ chính của kênh" : undefined}
          >
            {NARRATION_LANGUAGE_LABELS[lang]}
            {lang === primaryLanguage ? " ★" : ""}
            {langHasAnyContent(lang) && lang !== primaryLanguage ? ` (${readyCountForLang(lang)}/${totalBlockCount})` : ""}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: "var(--space-2)" }}>
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12, padding: "5px 12px" }}
          onClick={() => startNarrationBatch(false, viewLang)}
          disabled={startingNarration || hasInFlight}
          title="Sinh giọng đọc thật cho toàn bộ block ngay ở bước này, không cần đợi tới Visual Studio. Bỏ qua block đã sinh xong (chỉ lấp chỗ trống/lỗi)."
        >
          {startingNarration || hasInFlight
            ? "Đang sinh giọng đọc..."
            : `Sinh giọng đọc [${NARRATION_LANGUAGE_LABELS[viewLang]}]${totalBlockCount ? ` (${readyNarrationCount}/${totalBlockCount})` : ""}`}
        </button>
        {/* Sinh lại TOÀN BỘ (force) — chuyển từ Visual Studio sang đây (2026-09-02, mục
            109, theo yêu cầu người dùng). Màu cảnh báo — tốn phí/thời gian lại từ đầu,
            kể cả block ĐÃ sinh xong, khác nút an toàn ở trên (chỉ lấp chỗ trống). */}
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12, padding: "5px 12px", color: "var(--color-danger)" }}
          onClick={() => startNarrationBatch(true, viewLang)}
          disabled={startingNarration || hasInFlight}
          title="Sinh lại TOÀN BỘ giọng đọc cho block, KỂ CẢ block đã có sẵn — dùng khi vừa đổi BrandProfile sang giọng đọc mới hoặc vừa chỉnh tốc độ giọng đọc. Tốn phí/thời gian lại từ đầu."
        >
          {startingNarration || hasInFlight ? "Đang sinh giọng đọc..." : `Sinh lại TOÀN BỘ [${NARRATION_LANGUAGE_LABELS[viewLang]}] (kể cả đã có)`}
        </button>
        {(hasInFlight || startingNarration) && (
          <button
            className="btn btn-secondary"
            style={{ fontSize: 12, padding: "5px 12px", color: "var(--color-danger)" }}
            onClick={cancelAssetGeneration}
            disabled={cancellingNarration}
            title="Dừng tiến trình sinh giọng đọc (hoặc ảnh/video nếu đang chạy từ Visual Studio) đang chạy cho project này — block đã sinh xong (ready) không bị ảnh hưởng."
          >
            {cancellingNarration ? "Đang dừng..." : "⏹ Dừng"}
          </button>
        )}
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12, padding: "5px 12px" }}
          onClick={() => playAllNarrationLang(viewLang)}
          disabled={!(isPlayingAll && playingLang === viewLang) && readyNarrationCount === 0}
          title={readyNarrationCount === 0 ? "Chưa có giọng đọc nào sẵn sàng" : undefined}
        >
          {isPlayingAll && playingLang === viewLang ? "⏸ Dừng phát" : `▶ Nghe toàn bộ giọng đọc (${readyNarrationCount})`}
        </button>
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12, padding: "5px 12px" }}
          onClick={() => downloadNarrationFull(viewLang)}
          disabled={downloadingAudio || !allNarrationReady}
          title={allNarrationReady ? "Ghép giọng đọc mọi block thành 1 file .mp3 rồi tải về" : "Cần sinh xong giọng đọc cho MỌI block trước khi ghép/tải"}
        >
          {downloadingAudio ? "Đang ghép..." : "⭳ Tải giọng đọc toàn bộ script (.mp3)"}
        </button>
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12, padding: "5px 12px" }}
          onClick={() => (viewLang === primaryLanguage ? api.downloadTranscriptSrt(project.id) : api.downloadTranscriptSrtLang(project.id, viewLang))}
          title="Tải transcript kèm timeline dạng .srt (mỗi block = 1 cue phụ đề)"
        >
          ⭳ Tải transcript (.srt)
        </button>
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12, padding: "5px 12px" }}
          onClick={() => (viewLang === primaryLanguage ? api.downloadTranscriptTxt(project.id) : api.downloadTranscriptTxtLang(project.id, viewLang))}
          title="Tải kịch bản dạng .txt thuần, không timestamp — đọc/duyệt/dịch nội dung liền mạch"
        >
          ⭳ Tải kịch bản (.txt)
        </button>
        {viewLang !== primaryLanguage && (
          <button
            className="btn btn-secondary"
            style={{ fontSize: 12, padding: "5px 12px" }}
            onClick={() => api.downloadScriptImportTemplate(project.id, true)}
            title="Tải file mẫu 11 cột (1 cột VO/ngôn ngữ) — điền bản dịch sẵn rồi nhập lại qua 'Nhập kịch bản từ file' để điền hàng loạt thay vì gõ tay từng block."
          >
            ⭳ Tải mẫu nhập đa ngôn ngữ
          </button>
        )}
      </div>

      {/* Tốc độ giọng đọc TOÀN BỘ block — mới (2026-09-02, mục 109). Chỉ lưu giá trị,
          áp dụng cho lần (re)generate TIẾP THEO (xem setNarrationSpeed) — bấm 1 trong 2
          nút phía trên SAU KHI chỉnh để nghe đúng tốc độ mới. */}
      <div style={{ maxWidth: 360, marginBottom: "var(--space-4)" }}>
        <label style={{ fontSize: 11 }}>
          Tốc độ giọng đọc ({(renderState?.narration_speed ?? 1).toFixed(2)}x{(renderState?.narration_speed ?? 1) === 1 ? " — mặc định" : ""})
        </label>
        <input
          key={renderState?.narration_speed ?? 1}
          type="range"
          min={0.5}
          max={2}
          step={0.05}
          defaultValue={renderState?.narration_speed ?? 1}
          onMouseUp={(e) => setNarrationSpeed(parseFloat((e.target as HTMLInputElement).value))}
          onTouchEnd={(e) => setNarrationSpeed(parseFloat((e.target as HTMLInputElement).value))}
          style={{ width: "100%" }}
        />
        <div style={{ fontSize: 10.5, opacity: 0.6 }}>Chỉ áp dụng cho giọng đọc SINH MỚI sau khi chỉnh — bấm "Sinh giọng đọc" (hoặc "Sinh lại TOÀN BỘ") ở trên để áp dụng cho block đã có sẵn.</div>
      </div>
      {narrationError && <AiErrorBanner message={narrationError} onDismiss={() => setNarrationError(null)} />}

      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "var(--space-2)", maxWidth: 900 }}>
        {(script?.body || []).map((b, i) => {
          const shot = shotForBlock(b, i);
          const narration = narrationEntryForLang(shot?.shot_id, viewLang);
          const isActive = !!shot && activeShotId === shot.shot_id && playingLang === viewLang;
          // Ngôn ngữ nào đã có giọng đọc READY cho block này — tag trạng thái nhỏ, độc
          // lập với `viewLang` đang xem (giọng đọc đa ngôn ngữ, 2026-09-04).
          const readyLangs = shot ? NARRATION_LANGUAGES.filter((lang) => narrationEntryForLang(shot.shot_id, lang)?.narration_status === "ready" && textForLang(b, lang).trim()) : [];
          const showViText = primaryLanguage !== "vi" && viewLang !== "vi";
          return (
          <div key={i} className="card elev-sm" style={{ gap: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              {b.block_id && (
                <span className="tag tag-outline" style={{ fontFamily: "ui-monospace,monospace" }}>
                  {b.block_id}
                </span>
              )}
              {/* shot_id — đối chiếu trực tiếp với thẻ shot ở Visual Studio (cùng
                  hiện "{shot_id} · {linked_timestamp_sec}s"), dễ nhận ra ngay khi
                  block này CHƯA có shot tương ứng (mục 31 IMPLEMENTATION_REPORT.md —
                  trước đây lệch âm thầm, giờ hiện rõ để tự kiểm tra). */}
              {shot ? (
                <span className="tag tag-outline" style={{ fontFamily: "ui-monospace,monospace", opacity: 0.7 }} title="shot_id — đối chiếu với Visual Studio">
                  shot: {shot.shot_id}
                </span>
              ) : (
                <span className="tag tag-warning" style={{ fontSize: 10 }} title="Block này chưa có shot tương ứng ở Visual Studio">
                  Chưa có shot
                </span>
              )}
              <span className="tag tag-neutral" style={{ fontFamily: "ui-monospace,monospace" }}>
                {b.timestamp_sec}s{b.end_sec ? `–${b.end_sec}s` : ""}
              </span>
              {b.visual_type && <span className="tag tag-accent-2">{b.visual_type}</span>}
              {/* Giọng đọc đã sẵn sàng ở ngôn ngữ nào (2026-09-04) — độc lập với `viewLang`
                  đang xem, giúp thấy ngay tiến độ đa ngôn ngữ của TỪNG block. */}
              {readyLangs.length > 0 && (
                <span style={{ display: "flex", gap: 3 }} title="Đã sẵn sàng giọng đọc">
                  {readyLangs.map((lang) => (
                    <span key={lang} className="tag tag-outline" style={{ fontSize: 9, padding: "1px 5px", opacity: lang === viewLang ? 1 : 0.55 }}>
                      {lang.toUpperCase()}
                    </span>
                  ))}
                </span>
              )}
              {narration?.narration_status === "ready" && shot && (
                <button
                  type="button"
                  className="tag tag-accent"
                  style={{ cursor: "pointer", border: "none" }}
                  onClick={() => togglePlaySingle(shot.shot_id, viewLang)}
                >
                  {isActive && isAudioPlaying ? "⏸ Đang phát" : "▶ Nghe giọng đọc"}
                </button>
              )}
              {narration?.narration_status === "generating" && (
                <span className="tag tag-outline" style={{ fontSize: 10 }}>
                  Đang tạo giọng đọc…
                </span>
              )}
              {/* Nút "Tạo giọng đọc" RIÊNG từng block (2026-08-17, theo yêu cầu người
                  dùng) — khác nút batch "cho toàn bộ block" ở toolbar trên. Không cần
                  `shot` đã tồn tại — handler tự gọi `ensureShotsForNarration` trước
                  (idempotent, mục 30/31), tạo shot cho đúng block này nếu còn thiếu.
                  Luôn theo `viewLang` đang chọn (giọng đọc đa ngôn ngữ, 2026-09-04). */}
              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: 10, padding: "3px 8px" }}
                onClick={() => regenerateBlockNarration(i, b, viewLang)}
                disabled={regeneratingBlockIndex === i || narration?.narration_status === "generating" || hasInFlight || (viewLang !== primaryLanguage && !textForLang(b, viewLang).trim())}
                title={
                  viewLang !== primaryLanguage && !textForLang(b, viewLang).trim()
                    ? "Chưa có văn bản dịch cho ngôn ngữ này — nhập ở ô Audio bên dưới trước"
                    : narration?.narration_status === "ready"
                      ? "Sinh lại giọng đọc cho riêng block này"
                      : "Sinh giọng đọc cho riêng block này"
                }
              >
                {regeneratingBlockIndex === i ? "Đang sinh..." : narration?.narration_status === "ready" ? "↻ Sinh lại giọng đọc" : "Tạo giọng đọc"}
              </button>
              {b.warning && (
                <>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: b.warning.severity === "red" ? "var(--color-danger)" : "var(--color-warning)" }} />
                  <span style={{ fontSize: 12, color: b.warning.severity === "red" ? "var(--color-danger)" : "var(--color-warning)" }}>{b.warning.message}</span>
                </>
              )}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--space-3)", fontSize: 13 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 3 }}>
                  <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".06em", color: "color-mix(in srgb, var(--color-text) 50%, transparent)" }}>
                    Audio {viewLang !== primaryLanguage ? `[${NARRATION_LANGUAGE_LABELS[viewLang]}]` : ""}
                  </div>
                  {/* Nút edit RIÊNG cho Audio (2026-08-17, theo yêu cầu người dùng) —
                      Visual/Direction chỉ đọc (nội dung AI viết prompt lúc sinh shot,
                      không phải lời đọc trực tiếp). */}
                  <button
                    type="button"
                    className="btn btn-icon btn-secondary"
                    style={{ width: 18, height: 18, flex: "none" }}
                    title="Sửa nội dung Audio (VO) của block này"
                    onClick={() => setEditingAudioIndex(editingAudioIndex === i ? null : i)}
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
                    </svg>
                  </button>
                </div>
                {editingAudioIndex === i ? (
                  <textarea
                    className="input"
                    rows={3}
                    style={{ fontSize: 13 }}
                    defaultValue={textForLang(b, viewLang)}
                    autoFocus
                    disabled={savingAudioIndex === i}
                    onBlur={(e) => saveBlockAudio(i, e.target.value, viewLang)}
                  />
                ) : (
                  <div style={{ textDecoration: b.warning && viewLang === primaryLanguage ? "underline wavy var(--color-warning)" : "none" }}>
                    {textForLang(b, viewLang) || <span style={{ opacity: 0.45 }}>— chưa có bản dịch —</span>}
                  </div>
                )}
                {/* Tiếng Việt tham chiếu (2026-09-04) — chỉ hiện khi ngôn ngữ chính KHÔNG
                    phải tiếng Việt VÀ đang xem 1 ngôn ngữ khác tiếng Việt (tránh lặp 2
                    panel giống hệt nhau). Đọc-only, giúp đối chiếu khi dịch/kiểm tra. */}
                {showViText && (
                  <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px dashed var(--color-divider)" }}>
                    <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: ".06em", opacity: 0.5, marginBottom: 2 }}>Tiếng Việt (tham chiếu)</div>
                    <div style={{ opacity: 0.75 }}>{b.audio_by_lang?.vi || <span style={{ opacity: 0.45 }}>— chưa có —</span>}</div>
                  </div>
                )}
              </div>
              <Col label="Visual" value={b.visual} />
              <Col label={b.direction_label || "Direction"} value={b.direction} muted />
            </div>
          </div>
          );
        })}
      </div>
    </div>
  );
}

function Col({ label, value, underline, muted }: { label: string; value: string; underline?: boolean; muted?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".06em", color: "color-mix(in srgb, var(--color-text) 50%, transparent)", marginBottom: 3 }}>{label}</div>
      <div style={{ textDecoration: underline ? "underline wavy var(--color-warning)" : "none", opacity: muted ? 0.75 : 1 }}>{value}</div>
    </div>
  );
}
