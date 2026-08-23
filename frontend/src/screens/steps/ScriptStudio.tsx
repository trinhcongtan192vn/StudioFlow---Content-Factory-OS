import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { RenderState } from "../../api/types";
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
  const pollRef = useRef<number | undefined>(undefined);
  const [startingNarration, setStartingNarration] = useState(false);
  const [downloadingAudio, setDownloadingAudio] = useState(false);
  const [narrationError, setNarrationError] = useState<string | null>(null);
  const [editingAudioIndex, setEditingAudioIndex] = useState<number | null>(null);
  const [savingAudioIndex, setSavingAudioIndex] = useState<number | null>(null);
  const [regeneratingBlockIndex, setRegeneratingBlockIndex] = useState<number | null>(null);

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

  const hasInFlight = !!renderState && renderState.shots.some((s) => s.visual_status === "generating" || s.narration_status === "generating");

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

  function playShotAudio(shotId: string, queue: string[], all: boolean) {
    if (!audioRef.current) return;
    setActiveShotId(shotId);
    setPlayQueue(queue);
    setIsPlayingAll(all);
    // Cache-bust bằng timestamp — cùng lớp bug đã fix ở Visual Studio (2026-08-21): URL
    // asset narration CỐ ĐỊNH theo shot_id, browser HTTP cache có thể trả bản CŨ nếu
    // shot này từng phát qua trước đó trong CÙNG phiên rồi mới sinh lại giọng đọc khác.
    // Gán `.src` mới mỗi lần bấm play (không cần state riêng — hàm này vốn đã chạy lại
    // mỗi lần click) nên dùng thẳng `Date.now()` thay vì đếm cacheBust như nơi khác.
    audioRef.current.src = `${api.renderShotAssetUrl(project.id, shotId, "narration")}?v=${Date.now()}`;
    audioRef.current.play();
  }

  function stopPlayback() {
    audioRef.current?.pause();
    setActiveShotId(null);
    setPlayQueue([]);
    setIsPlayingAll(false);
  }

  function togglePlaySingle(shotId: string) {
    if (activeShotId === shotId && isAudioPlaying) {
      audioRef.current?.pause();
      return;
    }
    if (activeShotId === shotId && !isAudioPlaying && audioRef.current) {
      setIsPlayingAll(false);
      audioRef.current.play();
      return;
    }
    playShotAudio(shotId, [], false);
  }

  function playAllNarration() {
    if (isPlayingAll) {
      stopPlayback();
      return;
    }
    const ordered = (script?.body || [])
      .map((b, i) => shotForBlock(b, i))
      .filter((s) => !!s && narrationStatusFor(s.shot_id)?.narration_status === "ready")
      .map((s) => s!.shot_id);
    if (!ordered.length) return;
    playShotAudio(ordered[0], ordered.slice(1), true);
  }

  function handleAudioEnded() {
    if (playQueue.length === 0) {
      setActiveShotId(null);
      setIsPlayingAll(false);
      return;
    }
    const [next, ...rest] = playQueue;
    playShotAudio(next, rest, true);
  }

  const readyNarrationCount = (script?.body || []).filter(
    (b, i) => narrationStatusFor(shotForBlock(b, i)?.shot_id)?.narration_status === "ready"
  ).length;
  const totalBlockCount = (script?.body || []).length;
  const allNarrationReady = totalBlockCount > 0 && readyNarrationCount === totalBlockCount;

  async function startNarrationBatch() {
    setStartingNarration(true);
    setNarrationError(null);
    try {
      // Idempotent (BE mục 30 IMPLEMENTATION_REPORT.md) — tạo shot list nếu chưa có,
      // KHÔNG đổi step (khác "Đi tới Visual Studio"). Cần shot_id để render/start lưu
      // được trạng thái narration theo từng block, dù chưa thật sự qua Visual Studio.
      await api.ensureShotsForNarration(project.id);
      await refresh();
      setRenderState(await api.startRender(project.id, "narration"));
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

  async function downloadNarrationFull() {
    setDownloadingAudio(true);
    setNarrationError(null);
    try {
      await api.downloadNarrationFull(project.id);
    } catch (e) {
      setNarrationError(e instanceof ApiError ? e.message : "Có lỗi khi ghép/tải giọng đọc toàn bộ script.");
    } finally {
      setDownloadingAudio(false);
    }
  }

  async function saveBlockAudio(index: number, audio: string) {
    setSavingAudioIndex(index);
    setNarrationError(null);
    try {
      await api.editScriptBlockAudio(project.id, index, audio);
      await refresh();
      setEditingAudioIndex(null);
    } catch (e) {
      setNarrationError(e instanceof ApiError ? e.message : "Có lỗi khi lưu nội dung Audio.");
    } finally {
      setSavingAudioIndex(null);
    }
  }

  async function regenerateBlockNarration(index: number, block: { block_id?: string | null }) {
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
      setRenderState(await api.regenerateShotNarration(project.id, shot.shot_id));
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

      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: "var(--space-4)" }}>
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12, padding: "5px 12px" }}
          onClick={startNarrationBatch}
          disabled={startingNarration || hasInFlight}
          title="Sinh giọng đọc thật cho toàn bộ block ngay ở bước này, không cần đợi tới Visual Studio."
        >
          {startingNarration || hasInFlight ? "Đang sinh giọng đọc..." : `Sinh giọng đọc cho toàn bộ block${totalBlockCount ? ` (${readyNarrationCount}/${totalBlockCount})` : ""}`}
        </button>
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12, padding: "5px 12px" }}
          onClick={playAllNarration}
          disabled={!isPlayingAll && readyNarrationCount === 0}
          title={readyNarrationCount === 0 ? "Chưa có giọng đọc nào sẵn sàng" : undefined}
        >
          {isPlayingAll ? "⏸ Dừng phát" : `▶ Nghe toàn bộ giọng đọc (${readyNarrationCount})`}
        </button>
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12, padding: "5px 12px" }}
          onClick={downloadNarrationFull}
          disabled={downloadingAudio || !allNarrationReady}
          title={allNarrationReady ? "Ghép giọng đọc mọi block thành 1 file .mp3 rồi tải về" : "Cần sinh xong giọng đọc cho MỌI block trước khi ghép/tải"}
        >
          {downloadingAudio ? "Đang ghép..." : "⭳ Tải giọng đọc toàn bộ script (.mp3)"}
        </button>
        <button className="btn btn-secondary" style={{ fontSize: 12, padding: "5px 12px" }} onClick={() => api.downloadTranscriptSrt(project.id)} title="Tải transcript kèm timeline dạng .srt (mỗi block = 1 cue phụ đề)">
          ⭳ Tải transcript (.srt)
        </button>
      </div>
      {narrationError && <AiErrorBanner message={narrationError} onDismiss={() => setNarrationError(null)} />}

      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: "var(--space-2)", maxWidth: 900 }}>
        {(script?.body || []).map((b, i) => {
          const shot = shotForBlock(b, i);
          const narration = narrationStatusFor(shot?.shot_id);
          const isActive = !!shot && activeShotId === shot.shot_id;
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
              {narration?.narration_status === "ready" && shot && (
                <button
                  type="button"
                  className="tag tag-accent"
                  style={{ cursor: "pointer", border: "none" }}
                  onClick={() => togglePlaySingle(shot.shot_id)}
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
                  (idempotent, mục 30/31), tạo shot cho đúng block này nếu còn thiếu. */}
              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: 10, padding: "3px 8px" }}
                onClick={() => regenerateBlockNarration(i, b)}
                disabled={regeneratingBlockIndex === i || narration?.narration_status === "generating" || hasInFlight}
                title={narration?.narration_status === "ready" ? "Sinh lại giọng đọc cho riêng block này" : "Sinh giọng đọc cho riêng block này"}
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
                  <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".06em", color: "color-mix(in srgb, var(--color-text) 50%, transparent)" }}>Audio</div>
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
                    defaultValue={b.audio}
                    autoFocus
                    disabled={savingAudioIndex === i}
                    onBlur={(e) => saveBlockAudio(i, e.target.value)}
                  />
                ) : (
                  <div style={{ textDecoration: b.warning ? "underline wavy var(--color-warning)" : "none" }}>{b.audio}</div>
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
